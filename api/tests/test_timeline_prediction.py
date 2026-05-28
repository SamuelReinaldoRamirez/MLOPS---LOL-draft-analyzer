"""Tests for the per-game TIMELINE win-probability progression.

Two layers, both offline (httpx.MockTransport — NO respx, NO live key) and
backed by the tiny fixture @10 timeline model (so the prediction core runs):

  * ``build_timeline_features`` is exercised as a PURE function on a recorded
    timeline + a matching detail: gold-diff sign, per-role diffs, the four
    ``first_*_team_100`` flags (incl. the BUILDING_KILL opposite-team rule and a
    blue-vs-red first blood), and short-game truncation.
  * ``GET /riot/match/{matchId}/timeline-prediction`` is exercised through a
    TestClient with the Riot client dependency overridden — 200 (checkpoints +
    actual) and the error mapping (transport 404->404, 429, missing key->503).

The fixture timeline has 17 frames (indices 0..16) so minutes 5/10/15 have a
frame and 20 does NOT — exercising the short-game truncation. The conftest
fixture model is the @10 schema, so the route is asserted with checkpoints at
those minutes regardless of the underlying model bundle.
"""

import copy

import httpx
import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.riot_client import RiotClient
from app.timeline_features import (
    TimelineReconstructionError,
    available_minutes,
    build_timeline_features,
    build_timeline_prediction,
)
from fixtures import load_fixture, make_riot_transport

MATCH_ID = "EUW1_7000000002"


def _timeline_features_for(minute):
    """The @minute model's feature schema (mirrors the conftest @10 columns)."""
    return [
        f"gold_diff_at_{minute}",
        "first_blood_team_100",
        "first_tower_team_100",
        "first_dragon_team_100",
        "first_herald_team_100",
        f"top_gold_diff_at_{minute}",
        f"jungle_gold_diff_at_{minute}",
        f"mid_gold_diff_at_{minute}",
        f"adc_gold_diff_at_{minute}",
        f"support_gold_diff_at_{minute}",
    ]


def _make_at_bundle(minute, seed):
    """Build a tiny fitted LogisticRegression bundle for the @minute model."""
    cols = _timeline_features_for(minute)
    rng = np.random.default_rng(seed)
    n, n_feat = 60, len(cols)
    X = rng.normal(size=(n, n_feat))
    y = (X[:, 0] + rng.normal(scale=0.1, size=n) > 0).astype(int)
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(max_iter=500).fit(scaler.transform(X), y)
    return {
        "model": model,
        "scaler": scaler,
        "feature_columns": list(cols),
        "features": list(cols),
        "metadata": {"model_type": "LogisticRegression", "accuracy": 0.66},
    }


@pytest.fixture()
def api_main_timeline(api_main):
    """`api_main` with at5/at15/at20 models also written into MODELS_DIR.

    The shared conftest only ships model_draft + model_at10, but the timeline
    progression needs every available minute (5/10/15 for the 17-frame fixture).
    We add the missing minute models into the SAME temp MODELS_DIR and clear the
    cache so the route/core load them. Scoped to this module only (conftest is
    untouched), so no other test is affected.
    """
    models_dir = api_main.MODELS_DIR
    for minute, seed in ((5, 5), (15, 15), (20, 20)):
        joblib.dump(_make_at_bundle(minute, seed), models_dir / f"model_at{minute}.pkl")
    api_main._model_cache.clear()
    return api_main
# Target = blue-side participantId 1 (team 100, won). A red puuid (lost) below.
BLUE_PUUID = "tl-blue-top-0000000000000000000000000000000000000000000000000000000000000000"
RED_PUUID = "tl-red-top-00000000000000000000000000000000000000000000000000000000000000000"


def _detail():
    """A match-v5 detail matching the timeline fixture (participantId 1..10).

    Blue (team 100) = participantIds 1..5 (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY),
    red (team 200) = 6..10 (same role order). Blue won. This is what the
    reconstruction reads for the role->participantId mapping + the actual
    result; the per-minute gold comes from the timeline fixture.
    """
    roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    participants = []
    for idx, role in enumerate(roles):
        participants.append(
            {
                "puuid": BLUE_PUUID if idx == 0 else f"tl-blue-{idx}",
                "participantId": idx + 1,
                "championId": 266,
                "teamId": 100,
                "teamPosition": role,
                "win": True,
            }
        )
    for idx, role in enumerate(roles):
        participants.append(
            {
                "puuid": RED_PUUID if idx == 0 else f"tl-red-{idx}",
                "participantId": idx + 6,
                "championId": 86,
                "teamId": 200,
                "teamPosition": role,
                "win": False,
            }
        )
    return {
        "metadata": {"matchId": MATCH_ID, "participants": [p["puuid"] for p in participants]},
        "info": {
            "gameId": 7000000002,
            "gameDuration": 1010,
            "queueId": 420,
            "participants": participants,
            "teams": [
                {"teamId": 100, "win": True},
                {"teamId": 200, "win": False},
            ],
        },
    }


# Expected per-participant totalGold at frame `minute` in the fixture:
#   blue pid p (1..5): 500 + minute*350 + p*10
#   red  pid p (6..10): 500 + minute*300 + (p-5)*10
def _blue_gold(pid, minute):
    return 500 + minute * 350 + pid * 10


def _red_gold(pid, minute):
    return 500 + minute * 300 + (pid - 5) * 10


# ──────────────────────────────────────────
# Pure build_timeline_features
# ──────────────────────────────────────────

def test_available_minutes_truncates_short_game():
    """17 frames (0..16) -> 5/10/15 available, 20 dropped (no frames[20])."""
    timeline = load_fixture("riot_match_timeline.json")
    assert available_minutes(timeline) == [5, 10, 15]


def test_available_minutes_skips_below_five():
    """A game with only 3 frames has no checkpoint at all."""
    timeline = copy.deepcopy(load_fixture("riot_match_timeline.json"))
    timeline["info"]["frames"] = timeline["info"]["frames"][:3]
    assert available_minutes(timeline) == []


def test_gold_diff_sign_and_magnitude_at_10():
    """Total gold_diff = blue(1..5) − red(6..10) at frame 10 (blue ahead)."""
    timeline = load_fixture("riot_match_timeline.json")
    feats = build_timeline_features(_detail(), timeline, 10)

    expected_blue = sum(_blue_gold(p, 10) for p in range(1, 6))
    expected_red = sum(_red_gold(p, 10) for p in range(6, 11))
    assert feats["gold_diff_at_10"] == pytest.approx(expected_blue - expected_red)
    assert feats["gold_diff_at_10"] > 0  # blue is richer in the fixture


def test_per_role_gold_diff_at_10():
    """Each role diff = blue role participant − red role participant gold."""
    timeline = load_fixture("riot_match_timeline.json")
    feats = build_timeline_features(_detail(), timeline, 10)

    # role -> (blue pid, red pid): top=1/6, jungle=2/7, mid=3/8, adc=4/9, support=5/10
    for role, (b, r) in {
        "top": (1, 6),
        "jungle": (2, 7),
        "mid": (3, 8),
        "adc": (4, 9),
        "support": (5, 10),
    }.items():
        assert feats[f"{role}_gold_diff_at_10"] == pytest.approx(
            _blue_gold(b, 10) - _red_gold(r, 10)
        ), role


def test_per_role_falls_back_to_zero_when_role_unmapped():
    """A role missing on one side (empty teamPosition) -> that role diff is 0."""
    detail = _detail()
    # Blank the blue MID position -> mid cannot be mapped on blue.
    detail["info"]["participants"][2]["teamPosition"] = ""
    timeline = load_fixture("riot_match_timeline.json")
    feats = build_timeline_features(detail, timeline, 10)
    assert feats["mid_gold_diff_at_10"] == 0
    # Other roles still resolve.
    assert feats["top_gold_diff_at_10"] != 0


def test_first_blood_blue_at_10():
    """First CHAMPION_KILL (150000ms) by killerId 3 (blue) -> flag 1 by minute 10."""
    timeline = load_fixture("riot_match_timeline.json")
    feats = build_timeline_features(_detail(), timeline, 10)
    assert feats["first_blood_team_100"] == 1


def test_first_blood_red_when_red_kills_first():
    """If the first kill is by a red participant (6..10), the flag is 0."""
    timeline = copy.deepcopy(load_fixture("riot_match_timeline.json"))
    # Replace the blue first-blood event with an earlier red kill.
    timeline["info"]["frames"][2]["events"] = [
        {"type": "CHAMPION_KILL", "timestamp": 90000, "killerId": 8, "victimId": 1}
    ]
    feats = build_timeline_features(_detail(), timeline, 10)
    assert feats["first_blood_team_100"] == 0


def test_first_tower_uses_opposite_team_rule_at_15():
    """BUILDING_KILL TOWER teamId=200 (red LOST) -> blue (100) got first tower."""
    timeline = load_fixture("riot_match_timeline.json")
    # Tower event is at 12:30, so it counts at minute 15 but NOT at minute 10.
    feats10 = build_timeline_features(_detail(), timeline, 10)
    feats15 = build_timeline_features(_detail(), timeline, 15)
    assert feats10["first_tower_team_100"] == 0  # before the cutoff
    assert feats15["first_tower_team_100"] == 1  # blue got it (opposite of teamId)


def test_first_tower_blue_loses_tower_gives_red_flag_zero():
    """If teamId=100 lost the tower, blue did NOT get first tower (flag 0)."""
    timeline = copy.deepcopy(load_fixture("riot_match_timeline.json"))
    for ev in timeline["info"]["frames"][12]["events"]:
        if ev.get("type") == "BUILDING_KILL":
            ev["teamId"] = 100  # blue lost it -> red got first tower
    feats15 = build_timeline_features(_detail(), timeline, 15)
    assert feats15["first_tower_team_100"] == 0


def test_first_dragon_red_first_herald_blue_at_10():
    """Dragon (red, killerTeamId) -> 0; Herald (blue, via killerId) -> 1, by min 10."""
    timeline = load_fixture("riot_match_timeline.json")
    feats = build_timeline_features(_detail(), timeline, 10)
    assert feats["first_dragon_team_100"] == 0  # red took dragon
    assert feats["first_herald_team_100"] == 1  # blue took herald


def test_objectives_zero_before_they_happen_at_5():
    """At minute 5, dragon/herald/tower haven't happened yet -> all 0 except blood."""
    timeline = load_fixture("riot_match_timeline.json")
    feats = build_timeline_features(_detail(), timeline, 5)
    assert feats["first_blood_team_100"] == 1  # blood at 02:30 < 5:00
    assert feats["first_dragon_team_100"] == 0  # dragon at 08:30 > 5:00
    assert feats["first_herald_team_100"] == 0  # herald at 09:30 > 5:00
    assert feats["first_tower_team_100"] == 0  # tower at 12:30 > 5:00


def test_build_features_raises_for_missing_frame():
    """A minute with no frame is a hard TimelineReconstructionError."""
    timeline = copy.deepcopy(load_fixture("riot_match_timeline.json"))
    timeline["info"]["frames"] = timeline["info"]["frames"][:11]  # frames 0..10
    with pytest.raises(TimelineReconstructionError):
        build_timeline_features(_detail(), timeline, 15)


# ──────────────────────────────────────────
# Pure build_timeline_prediction (model fixture in place via api_main)
# ──────────────────────────────────────────

def test_build_prediction_checkpoints_and_actual(api_main_timeline):
    """Produces a checkpoint per available minute + the actual result."""
    timeline = load_fixture("riot_match_timeline.json")
    result = build_timeline_prediction(_detail(), timeline, BLUE_PUUID)

    assert result["match_id"] == MATCH_ID
    assert result["game_duration"] == 1010
    assert [cp["minute"] for cp in result["checkpoints"]] == [5, 10, 15]

    for cp in result["checkpoints"]:
        pred = cp["predicted"]
        assert pred.model_used == f"at{cp['minute']}" or pred.model_used.startswith("at")
        assert 0.0 <= pred.blue_win_probability <= 1.0
        assert pred.blue_win_probability + pred.red_win_probability == pytest.approx(1.0)
        assert "gold_diff" in cp

    assert result["actual"]["winner_side"] == "Blue Team"
    assert result["actual"]["player_won"] is True


def test_build_prediction_player_won_false_for_red(api_main_timeline):
    """A red-side puuid lost; winner_side stays Blue."""
    timeline = load_fixture("riot_match_timeline.json")
    result = build_timeline_prediction(_detail(), timeline, RED_PUUID)
    assert result["actual"]["winner_side"] == "Blue Team"
    assert result["actual"]["player_won"] is False


def test_build_prediction_raises_for_too_short_game(api_main_timeline):
    """A <5-min game (3 frames) cannot be charted -> TimelineReconstructionError."""
    timeline = copy.deepcopy(load_fixture("riot_match_timeline.json"))
    timeline["info"]["frames"] = timeline["info"]["frames"][:3]
    with pytest.raises(TimelineReconstructionError):
        build_timeline_prediction(_detail(), timeline, BLUE_PUUID)


# ──────────────────────────────────────────
# GET /riot/match/{matchId}/timeline-prediction route
# ──────────────────────────────────────────

def _route_client(api_main, handler, monkeypatch, api_key="TEST-KEY"):
    monkeypatch.setenv("RIOT_API_KEY", api_key)
    riot = RiotClient(api_key=api_key, transport=make_riot_transport(handler))
    api_main.app.dependency_overrides[api_main.get_riot_client] = lambda: riot
    return TestClient(api_main.app)


def _detail_and_timeline_handler():
    """Route detail-vs-timeline by URL path (timeline ends with /timeline)."""
    detail = _detail()
    timeline = load_fixture("riot_match_timeline.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Riot-Token")
        if request.url.path.endswith("/timeline"):
            return httpx.Response(200, json=timeline)
        return httpx.Response(200, json=detail)

    return handler


def test_route_returns_checkpoints_and_actual(api_main_timeline, monkeypatch):
    client = _route_client(
        api_main_timeline, _detail_and_timeline_handler(), monkeypatch
    )
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/timeline-prediction",
            params={"puuid": BLUE_PUUID, "region": "euw1"},
        )
    finally:
        api_main_timeline.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["match_id"] == MATCH_ID
    assert body["puuid"] == BLUE_PUUID
    assert body["platform"] == "euw1"
    assert body["game_duration"] == 1010

    minutes = [cp["minute"] for cp in body["checkpoints"]]
    assert minutes == [5, 10, 15]
    for cp in body["checkpoints"]:
        assert cp["predicted"]["winner"] in ("Blue Team", "Red Team")
        assert cp["predicted"]["blue_win_probability"] + cp["predicted"][
            "red_win_probability"
        ] == pytest.approx(1.0)
        assert "gold_diff" in cp

    assert body["actual"]["winner_side"] == "Blue Team"
    assert body["actual"]["player_won"] is True


def test_route_404_when_match_not_found(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/timeline-prediction",
            params={"puuid": BLUE_PUUID},
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
            f"/riot/match/{MATCH_ID}/timeline-prediction",
            params={"puuid": BLUE_PUUID},
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 429


def test_route_503_when_key_unset(api_main, monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    client = TestClient(api_main.app)
    resp = client.get(
        f"/riot/match/{MATCH_ID}/timeline-prediction", params={"puuid": BLUE_PUUID}
    )
    assert resp.status_code == 503
    assert "detail" in resp.json()


def test_route_502_upstream(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"status": {"status_code": 500}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/timeline-prediction",
            params={"puuid": BLUE_PUUID},
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 502


def test_route_422_for_too_short_game(api_main, monkeypatch):
    """A timeline with no frame at minute 5+ -> 422 (not a misleading empty body)."""
    detail = _detail()
    timeline = copy.deepcopy(load_fixture("riot_match_timeline.json"))
    timeline["info"]["frames"] = timeline["info"]["frames"][:3]  # <5 min

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/timeline"):
            return httpx.Response(200, json=timeline)
        return httpx.Response(200, json=detail)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            f"/riot/match/{MATCH_ID}/timeline-prediction",
            params={"puuid": BLUE_PUUID},
        )
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_route_400_when_puuid_missing(api_main):
    client = TestClient(api_main.app)
    resp = client.get(f"/riot/match/{MATCH_ID}/timeline-prediction")
    assert resp.status_code == 422  # FastAPI validation (required query param)
