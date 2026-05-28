"""Tests for the per-game draft prediction — Slice 3 CORE.

Two layers, both offline (httpx.MockTransport — NO respx, NO live key) and
backed by the tiny fixture draft model (so the prediction core actually runs):

  * ``build_match_prediction`` is exercised as a PURE function on the recorded
    match-detail fixture: it reconstructs the 10-name draft, runs the draft
    model (predicted PredictionResponse), and reads the ACTUAL winner_side +
    player_won from the detail.
  * ``GET /riot/match/{matchId}/prediction`` is exercised through a TestClient
    with the Riot client dependency overridden — 200 (predicted + actual) and
    the error mapping (transport 404 -> 404, missing key -> 503, non-SR draft
    -> 422).
"""

import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.draft_reconstruction import DraftReconstructionError
from app.match_prediction import DRAFT_SLOTS, build_match_prediction
from app.riot_client import RiotClient
from fixtures import load_fixture, make_riot_transport

# The target puuid is the recorded blue-side TOP (Aatrox) whose team WON.
TARGET_PUUID = "AbCdEf_recorded-fixture-puuid-0123456789abcdef0123456789abcdef0123456789abcd"
# A red-side participant whose team LOST.
RED_PUUID = "puuid-red-mid-000000000000000000000000000000000000000000000000000000000000000"
MATCH_ID = "EUW1_6000000001"


# ──────────────────────────────────────────
# Pure build_match_prediction (model fixture in place via api_main)
# ──────────────────────────────────────────

def test_build_reconstructs_full_10_name_draft(api_main):
    detail = load_fixture("riot_match_detail.json")
    result = build_match_prediction(detail, TARGET_PUUID)

    # All 10 slots present, mapped to display names from the shared index.
    assert set(result["draft"].keys()) == set(DRAFT_SLOTS)
    assert result["draft"]["blue_top"] == "Aatrox"      # championId 266
    assert result["draft"]["blue_jungle"] == "LeeSin"   # 64
    assert result["draft"]["blue_mid"] == "Ahri"        # 103
    assert result["draft"]["blue_adc"] == "Jinx"        # 222
    assert result["draft"]["blue_support"] == "Thresh"  # 412
    assert result["draft"]["red_top"] == "Garen"        # 86
    assert result["draft"]["red_mid"] == "Orianna"      # 61
    assert result["draft"]["red_support"] == "Leona"    # 89
    assert result["match_id"] == MATCH_ID


def test_build_runs_the_draft_model(api_main):
    """The predicted block is a real PredictionResponse from the draft model."""
    detail = load_fixture("riot_match_detail.json")
    predicted = build_match_prediction(detail, TARGET_PUUID)["predicted"]

    assert predicted.model_used == "draft"
    assert predicted.winner in ("Blue Team", "Red Team")
    assert 0.0 <= predicted.blue_win_probability <= 1.0
    assert 0.0 <= predicted.red_win_probability <= 1.0
    assert predicted.blue_win_probability + predicted.red_win_probability == pytest.approx(1.0)
    assert 0.0 <= predicted.confidence <= 1.0
    # The fixture model reports 0.66 accuracy (see conftest).
    assert predicted.model_accuracy == pytest.approx(0.66)


def test_build_extracts_actual_result_blue_won(api_main):
    """Blue team won in the fixture; the target (blue) player therefore won."""
    detail = load_fixture("riot_match_detail.json")
    actual = build_match_prediction(detail, TARGET_PUUID)["actual"]

    assert actual["winner_side"] == "Blue Team"
    assert actual["player_won"] is True


def test_build_actual_player_won_false_for_losing_side(api_main):
    """A red-side participant lost; winner_side is unchanged (Blue)."""
    detail = load_fixture("riot_match_detail.json")
    result = build_match_prediction(detail, RED_PUUID)

    assert result["actual"]["winner_side"] == "Blue Team"
    assert result["actual"]["player_won"] is False


def test_build_winner_side_falls_back_to_participants(api_main):
    """With info.teams absent, winner_side is derived from participants' win."""
    detail = copy.deepcopy(load_fixture("riot_match_detail.json"))
    del detail["info"]["teams"]
    result = build_match_prediction(detail, TARGET_PUUID)
    assert result["actual"]["winner_side"] == "Blue Team"


def test_build_fallback_used_flag_clean_positions(api_main):
    """All positions present & valid -> reconstruction does not use fallback."""
    detail = load_fixture("riot_match_detail.json")
    result = build_match_prediction(detail, TARGET_PUUID)
    assert result["fallback_used"] is False
    assert isinstance(result["warnings"], list)


def test_build_fallback_used_when_positions_missing(api_main):
    """Stripping teamPosition forces the deterministic order-fallback."""
    detail = copy.deepcopy(load_fixture("riot_match_detail.json"))
    for p in detail["info"]["participants"]:
        p.pop("teamPosition", None)
        p.pop("individualPosition", None)
    result = build_match_prediction(detail, TARGET_PUUID)
    assert result["fallback_used"] is True
    # Still 10 valid names, assigned in participant order.
    assert set(result["draft"].keys()) == set(DRAFT_SLOTS)
    assert result["draft"]["blue_top"] == "Aatrox"


def test_build_raises_for_non_5v5(api_main):
    """A team without exactly 5 players is a hard DraftReconstructionError."""
    detail = copy.deepcopy(load_fixture("riot_match_detail.json"))
    # Drop one red participant -> red has 4 players.
    detail["info"]["participants"] = detail["info"]["participants"][:-1]
    with pytest.raises(DraftReconstructionError):
        build_match_prediction(detail, TARGET_PUUID)


# ──────────────────────────────────────────
# GET /riot/match/{matchId}/prediction route
# ──────────────────────────────────────────

def _route_client(api_main, handler, monkeypatch, api_key="TEST-KEY"):
    monkeypatch.setenv("RIOT_API_KEY", api_key)
    riot = RiotClient(api_key=api_key, transport=make_riot_transport(handler))
    api_main.app.dependency_overrides[api_main.get_riot_client] = lambda: riot
    return TestClient(api_main.app)


def test_route_returns_predicted_and_actual(api_main, monkeypatch):
    detail = load_fixture("riot_match_detail.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Riot-Token")
        # The detail endpoint ends with the match id (no trailing /ids).
        assert request.url.path.endswith(MATCH_ID)
        return httpx.Response(200, json=detail)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/prediction",
            params={"puuid": TARGET_PUUID, "region": "euw1"},
        )
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["match_id"] == MATCH_ID
    assert body["puuid"] == TARGET_PUUID
    assert body["platform"] == "euw1"

    # Draft (10 names).
    assert body["draft"]["blue_top"] == "Aatrox"
    assert body["draft"]["red_support"] == "Leona"

    # Predicted block.
    assert body["predicted"]["model_used"] == "draft"
    assert body["predicted"]["winner"] in ("Blue Team", "Red Team")
    assert body["predicted"]["blue_win_probability"] + body["predicted"][
        "red_win_probability"
    ] == pytest.approx(1.0)

    # Actual block matches the fixture (blue won; target player won).
    assert body["actual"]["winner_side"] == "Blue Team"
    assert body["actual"]["player_won"] is True
    assert body["fallback_used"] is False


def test_route_404_when_match_not_found(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/prediction", params={"puuid": TARGET_PUUID}
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_route_429_rate_limited(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(429)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/prediction", params={"puuid": TARGET_PUUID}
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 429


def test_route_503_when_key_unset(api_main, monkeypatch):
    # No dependency override: REAL get_riot_client with no key -> clean 503.
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    client = TestClient(api_main.app)
    resp = client.get(
        f"/riot/match/{MATCH_ID}/prediction", params={"puuid": TARGET_PUUID}
    )
    assert resp.status_code == 503
    assert "detail" in resp.json()


def test_route_502_upstream(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"status": {"status_code": 500}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/prediction", params={"puuid": TARGET_PUUID}
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_route_422_for_non_sr_match(api_main, monkeypatch):
    """A match whose draft cannot be reconstructed (4v6) -> 422."""
    detail = copy.deepcopy(load_fixture("riot_match_detail.json"))
    # Move a red participant to blue so teams are 6 vs 4 -> reconstruction fails.
    detail["info"]["participants"][5]["teamId"] = 100

    def handler(request):
        return httpx.Response(200, json=detail)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/prediction", params={"puuid": TARGET_PUUID}
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_route_400_when_puuid_missing(api_main):
    client = TestClient(api_main.app)
    # puuid is a required query param -> FastAPI 422 (validation).
    resp = client.get(f"/riot/match/{MATCH_ID}/prediction")
    assert resp.status_code == 422
