"""Tests for match-history summarisation + the GET /riot/matches route.

Two layers, both offline (httpx.MockTransport — NO respx, NO live key):
  * ``summarize_match_for_player`` is exercised as a PURE function on the
    recorded match-detail fixture (champion / win / queue / duration / date).
  * ``GET /riot/matches`` is exercised through a TestClient with the Riot client
    dependency overridden, including 404/429/503 mapping and the SR-5v5 filter.
"""

import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.match_history import (
    SR_5V5_QUEUE_IDS,
    is_sr_5v5_queue,
    summarize_match_for_player,
    summarize_matches_for_player,
)
from app.riot_client import RiotClient
from fixtures import load_fixture, make_riot_transport

TARGET_PUUID = "AbCdEf_recorded-fixture-puuid-0123456789abcdef0123456789abcdef0123456789abcd"


# ──────────────────────────────────────────
# Pure summarisation
# ──────────────────────────────────────────

def test_summarize_extracts_player_fields():
    detail = load_fixture("riot_match_detail.json")
    summary = summarize_match_for_player(detail, TARGET_PUUID)

    assert summary is not None
    assert summary.match_id == "EUW1_6000000001"
    # championId 266 resolves to display name "Aatrox" via the shared index.
    assert summary.champion_name == "Aatrox"
    assert summary.win is True  # target is on the winning blue team
    assert summary.queue_id == 420
    assert summary.game_duration == 1834
    assert summary.game_creation == 1716600000000
    assert summary.game_mode == "CLASSIC"


def test_summarize_uses_the_correct_participant_row():
    """A red-side participant must report win=False and their own champion."""
    detail = load_fixture("riot_match_detail.json")
    red_puuid = "puuid-red-mid-000000000000000000000000000000000000000000000000000000000000000"
    summary = summarize_match_for_player(detail, red_puuid)
    assert summary is not None
    assert summary.win is False
    assert summary.champion_name == "Orianna"  # championId 61


def test_summarize_returns_none_for_unknown_puuid():
    detail = load_fixture("riot_match_detail.json")
    assert summarize_match_for_player(detail, "not-in-this-match") is None


def test_summarize_falls_back_to_riot_champion_name():
    """An unknown/zero championId falls back to Riot's championName string."""
    detail = copy.deepcopy(load_fixture("riot_match_detail.json"))
    target = detail["info"]["participants"][0]
    target["championId"] = 0  # not in the static map
    target["championName"] = "BrandNewChampion"
    summary = summarize_match_for_player(detail, TARGET_PUUID)
    assert summary is not None
    assert summary.champion_name == "BrandNewChampion"


def test_is_sr_5v5_queue():
    assert SR_5V5_QUEUE_IDS == frozenset({400, 420, 430, 440})
    assert is_sr_5v5_queue(420) is True
    assert is_sr_5v5_queue("400") is True  # tolerant of string ids
    assert is_sr_5v5_queue(450) is False  # ARAM
    assert is_sr_5v5_queue(None) is False


def test_summarize_matches_filters_non_sr_5v5():
    sr = load_fixture("riot_match_detail.json")
    aram = copy.deepcopy(sr)
    aram["metadata"]["matchId"] = "EUW1_6000000002"
    aram["info"]["queueId"] = 450  # ARAM — should be filtered out
    aram["info"]["gameMode"] = "ARAM"

    summaries = summarize_matches_for_player([sr, aram], TARGET_PUUID, sr_5v5_only=True)
    assert [s.match_id for s in summaries] == ["EUW1_6000000001"]

    # Without the filter, both are kept (order preserved).
    all_summaries = summarize_matches_for_player(
        [sr, aram], TARGET_PUUID, sr_5v5_only=False
    )
    assert [s.match_id for s in all_summaries] == ["EUW1_6000000001", "EUW1_6000000002"]


# ──────────────────────────────────────────
# GET /riot/matches route
# ──────────────────────────────────────────

def _detail_for(match_id: str, queue_id: int = 420):
    """A copy of the recorded detail re-stamped with a match id / queue."""
    detail = copy.deepcopy(load_fixture("riot_match_detail.json"))
    detail["metadata"]["matchId"] = match_id
    detail["info"]["queueId"] = queue_id
    return detail


def _route_client(api_main, handler, monkeypatch, api_key="TEST-KEY"):
    monkeypatch.setenv("RIOT_API_KEY", api_key)
    riot = RiotClient(api_key=api_key, transport=make_riot_transport(handler))
    api_main.app.dependency_overrides[api_main.get_riot_client] = lambda: riot
    return TestClient(api_main.app)


def test_matches_route_returns_summaries(api_main, monkeypatch):
    ids = ["EUW1_6000000001", "EUW1_6000000002"]
    details = {mid: _detail_for(mid) for mid in ids}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Riot-Token")
        path = request.url.path
        if path.endswith("/ids"):
            return httpx.Response(200, json=ids)
        mid = path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=details[mid])

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            "/riot/matches", params={"puuid": TARGET_PUUID, "region": "euw1", "count": 5}
        )
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["puuid"] == TARGET_PUUID
    assert body["platform"] == "euw1"
    assert body["count"] == 2
    assert [m["match_id"] for m in body["matches"]] == ids
    first = body["matches"][0]
    assert first["champion_name"] == "Aatrox"
    assert first["win"] is True
    assert first["queue_id"] == 420
    assert first["game_duration"] == 1834


def test_matches_route_filters_non_sr_5v5_by_default(api_main, monkeypatch):
    """An ARAM match in the pool is dropped when no explicit queue is given."""
    ids = ["EUW1_6000000001", "EUW1_ARAM_2", "EUW1_6000000003"]
    details = {
        "EUW1_6000000001": _detail_for("EUW1_6000000001", queue_id=420),
        "EUW1_ARAM_2": _detail_for("EUW1_ARAM_2", queue_id=450),  # ARAM
        "EUW1_6000000003": _detail_for("EUW1_6000000003", queue_id=400),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/ids"):
            # No queue param should be forwarded when the caller omits it.
            assert "queue" not in dict(request.url.params)
            return httpx.Response(200, json=ids)
        mid = path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=details[mid])

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/matches", params={"puuid": TARGET_PUUID, "count": 10})
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    returned = [m["match_id"] for m in resp.json()["matches"]]
    assert returned == ["EUW1_6000000001", "EUW1_6000000003"]
    assert "EUW1_ARAM_2" not in returned


def test_matches_route_explicit_queue_is_trusted(api_main, monkeypatch):
    """With an explicit queue, Riot filters at source and we skip SR narrowing."""
    ids = ["EUW1_ARAM_1"]
    aram = _detail_for("EUW1_ARAM_1", queue_id=450)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/ids"):
            # The queue must be forwarded to Riot's /ids endpoint.
            assert dict(request.url.params).get("queue") == "450"
            return httpx.Response(200, json=ids)
        return httpx.Response(200, json=aram)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get(
            "/riot/matches", params={"puuid": TARGET_PUUID, "queue": 450, "count": 5}
        )
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    # ARAM is kept because the caller explicitly asked for queue 450.
    assert [m["match_id"] for m in body["matches"]] == ["EUW1_ARAM_1"]
    assert body["matches"][0]["queue_id"] == 450


def test_matches_route_empty_history(api_main, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/matches", params={"puuid": TARGET_PUUID})
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["matches"] == []


def test_matches_route_404(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/matches", params={"puuid": "nobody"})
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_matches_route_429(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(429)

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/matches", params={"puuid": TARGET_PUUID})
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 429


def test_matches_route_503_when_key_unset(api_main, monkeypatch):
    # No dependency override: REAL get_riot_client with no key -> clean 503.
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    client = TestClient(api_main.app)
    resp = client.get("/riot/matches", params={"puuid": TARGET_PUUID})
    assert resp.status_code == 503
    assert "detail" in resp.json()


def test_matches_route_502_upstream(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"status": {"status_code": 500}})

    client = _route_client(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/matches", params={"puuid": TARGET_PUUID})
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 502
