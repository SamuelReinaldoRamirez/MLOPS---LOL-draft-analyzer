"""Tests for the LIVE-game spectator prediction — Slice 4 CORE.

Two layers, both offline (httpx.MockTransport — NO respx, NO live key) and
backed by the tiny fixture draft model (so the prediction core actually runs):

  * ``build_live_prediction`` is exercised as a PURE function on the recorded
    spectator-v5 ``CurrentGameInfo`` fixture: it reconstructs the 10-name draft
    via the participant-ORDER fallback (spectator data has NO lane info, so
    ``fallback_used`` is True), runs the draft model (predicted
    PredictionResponse), and exposes NO actual result (the game is in progress).
  * ``GET /riot/live/{puuid}/prediction`` is exercised through a TestClient with
    the Riot client dependency overridden:
      (a) in-game fixture        -> 200 {in_game: true, predicted...}
      (b) transport 404 not-in-game -> 200 {in_game: false}
      (c) missing key            -> 503
      (d) 429 rate limited       -> 429
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.draft_reconstruction import DraftReconstructionError
from app.match_prediction import DRAFT_SLOTS, build_live_prediction
from app.riot_client import RiotClient
from fixtures import load_fixture, make_riot_transport

# Reuse the puuid recorded in riot_account_v1.json for cross-fixture consistency.
TARGET_PUUID = "AbCdEf_recorded-fixture-puuid-0123456789abcdef0123456789abcdef0123456789abcd"
GAME_ID = "6000000123"


# ──────────────────────────────────────────
# Pure build_live_prediction (model fixture in place via api_main)
# ──────────────────────────────────────────

def test_build_reconstructs_full_10_name_draft(api_main):
    """Spectator participants (no positions) -> 10 names via order-fallback."""
    info = load_fixture("riot_active_game.json")
    result = build_live_prediction(info, TARGET_PUUID)

    assert set(result["draft"].keys()) == set(DRAFT_SLOTS)
    # Champion ids resolve from the shared index, assigned in participant order.
    assert result["draft"]["blue_top"] == "Aatrox"      # championId 266
    assert result["draft"]["blue_jungle"] == "LeeSin"   # 64
    assert result["draft"]["blue_mid"] == "Ahri"        # 103
    assert result["draft"]["blue_adc"] == "Jinx"        # 222
    assert result["draft"]["blue_support"] == "Thresh"  # 412
    assert result["draft"]["red_top"] == "Garen"        # 86
    assert result["draft"]["red_jungle"] == "Graves"    # 104
    assert result["draft"]["red_mid"] == "Orianna"      # 61
    assert result["draft"]["red_adc"] == "Kaisa"        # 145
    assert result["draft"]["red_support"] == "Leona"    # 89
    assert result["game_id"] == GAME_ID
    assert result["queue_id"] == 420


def test_build_fallback_used_true_for_spectator(api_main):
    """Spectator data has no lane field at all -> always the order-fallback."""
    info = load_fixture("riot_active_game.json")
    result = build_live_prediction(info, TARGET_PUUID)
    assert result["fallback_used"] is True
    assert isinstance(result["warnings"], list)


def test_build_no_actual_result_key(api_main):
    """The game is in progress: there must be NO actual-result block."""
    info = load_fixture("riot_active_game.json")
    result = build_live_prediction(info, TARGET_PUUID)
    assert "actual" not in result


def test_build_runs_the_draft_model(api_main):
    """The predicted block is a real PredictionResponse from the draft model."""
    info = load_fixture("riot_active_game.json")
    predicted = build_live_prediction(info, TARGET_PUUID)["predicted"]

    assert predicted.model_used == "draft"
    assert predicted.winner in ("Blue Team", "Red Team")
    assert 0.0 <= predicted.blue_win_probability <= 1.0
    assert 0.0 <= predicted.red_win_probability <= 1.0
    assert predicted.blue_win_probability + predicted.red_win_probability == pytest.approx(1.0)
    assert 0.0 <= predicted.confidence <= 1.0
    # The fixture model reports 0.66 accuracy (see conftest).
    assert predicted.model_accuracy == pytest.approx(0.66)


def test_build_raises_for_non_sr_queue(api_main):
    """A non-SR-5v5 queue (e.g. ARAM 450) -> DraftReconstructionError (-> 422)."""
    info = dict(load_fixture("riot_active_game.json"))
    info["gameQueueConfigId"] = 450  # ARAM
    with pytest.raises(DraftReconstructionError):
        build_live_prediction(info, TARGET_PUUID)


def test_build_raises_for_non_5v5(api_main):
    """A side without exactly 5 players is a hard DraftReconstructionError."""
    info = load_fixture("riot_active_game.json")
    info = {**info, "participants": info["participants"][:-1]}  # drop one
    with pytest.raises(DraftReconstructionError):
        build_live_prediction(info, TARGET_PUUID)


# ──────────────────────────────────────────
# GET /riot/live/{puuid}/prediction route
# ──────────────────────────────────────────

def _route_client(api_main, handler, monkeypatch, api_key="TEST-KEY"):
    monkeypatch.setenv("RIOT_API_KEY", api_key)
    riot = RiotClient(api_key=api_key, transport=make_riot_transport(handler))
    api_main.app.dependency_overrides[api_main.get_riot_client] = lambda: riot
    return TestClient(api_main.app)


def test_route_in_game_returns_predicted(api_main, monkeypatch):
    info = load_fixture("riot_active_game.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Riot-Token")
        # spectator-v5 uses PLATFORM routing on the active-games path.
        assert "/lol/spectator/v5/active-games/by-summoner/" in request.url.path
        assert request.url.host == "euw1.api.riotgames.com"
        return httpx.Response(200, json=info)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/live/{TARGET_PUUID}/prediction",
            params={"region": "euw1"},
        )
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["in_game"] is True
    assert body["puuid"] == TARGET_PUUID
    assert body["platform"] == "euw1"
    assert body["game_id"] == GAME_ID
    assert body["queue_id"] == 420

    # Draft (10 names) reconstructed from participant order.
    assert body["draft"]["blue_top"] == "Aatrox"
    assert body["draft"]["red_support"] == "Leona"

    # Predicted block from the draft model; spectator data has no lanes.
    assert body["predicted"]["model_used"] == "draft"
    assert body["predicted"]["winner"] in ("Blue Team", "Red Team")
    assert body["predicted"]["blue_win_probability"] + body["predicted"][
        "red_win_probability"
    ] == pytest.approx(1.0)
    assert body["fallback_used"] is True

    # In-progress game: no actual result is surfaced.
    assert "actual" not in body


def test_route_not_in_game_returns_in_game_false(api_main, monkeypatch):
    """Spectator-v5 404 (player not in a game) -> 200 {in_game: false}."""
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(f"/riot/live/{TARGET_PUUID}/prediction")
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["in_game"] is False
    assert body["puuid"] == TARGET_PUUID
    # No prediction when not in a game.
    assert body["predicted"] is None
    assert body["draft"] is None


def test_route_503_when_key_unset(api_main, monkeypatch):
    # No dependency override: REAL get_riot_client with no key -> clean 503.
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    client = TestClient(api_main.app)
    resp = client.get(f"/riot/live/{TARGET_PUUID}/prediction")
    assert resp.status_code == 503
    assert "detail" in resp.json()


def test_route_429_rate_limited(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(429)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(f"/riot/live/{TARGET_PUUID}/prediction")
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 429


def test_route_502_upstream(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"status": {"status_code": 500}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(f"/riot/live/{TARGET_PUUID}/prediction")
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_route_422_for_non_sr_game(api_main, monkeypatch):
    """A live ARAM game (queue 450) -> 422 (draft cannot be reconstructed)."""
    info = dict(load_fixture("riot_active_game.json"))
    info["gameQueueConfigId"] = 450

    def handler(request):
        return httpx.Response(200, json=info)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(f"/riot/live/{TARGET_PUUID}/prediction")
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert "detail" in resp.json()
