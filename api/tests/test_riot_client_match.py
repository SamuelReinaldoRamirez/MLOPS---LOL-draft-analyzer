"""Unit tests for the match-v5 methods of the async Riot client.

All offline: an ``httpx.MockTransport`` (NOT respx) serves recorded match-id /
match-detail fixtures or error statuses. No live key, no network.
"""

import asyncio

import httpx
import pytest

from app.riot_client import (
    RiotClient,
    RiotNotFoundError,
    RiotRateLimitError,
    RiotUpstreamError,
)
from fixtures import load_fixture, make_riot_transport

TARGET_PUUID = "AbCdEf_recorded-fixture-puuid-0123456789abcdef0123456789abcdef0123456789abcd"


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────
# get_match_ids_by_puuid
# ──────────────────────────────────────────

def test_get_match_ids_happy_path_uses_regional_routing():
    match_ids = load_fixture("riot_match_ids.json")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["token"] = request.headers.get("X-Riot-Token")
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=match_ids)

    client = RiotClient(api_key="TEST-KEY", transport=make_riot_transport(handler))
    ids = _run(client.get_match_ids_by_puuid(TARGET_PUUID, platform="euw1", count=3))

    assert ids == match_ids
    assert all(isinstance(i, str) for i in ids)
    # match-v5 lives on the REGIONAL cluster (euw1 -> europe), not the platform.
    assert seen["host"] == "europe.api.riotgames.com"
    assert "/lol/match/v5/matches/by-puuid/" in seen["path"]
    assert seen["path"].endswith("/ids")
    assert seen["token"] == "TEST-KEY"
    # start/count are sent; queue omitted when None.
    assert seen["params"]["count"] == "3"
    assert seen["params"]["start"] == "0"
    assert "queue" not in seen["params"]


def test_get_match_ids_passes_queue_and_clamps_count():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    ids = _run(
        client.get_match_ids_by_puuid(
            TARGET_PUUID, platform="kr", count=999, queue=420, start=5
        )
    )
    assert ids == []
    # count clamps to Riot's max of 100; queue/start forwarded.
    assert captured["params"]["count"] == "100"
    assert captured["params"]["queue"] == "420"
    assert captured["params"]["start"] == "5"


def test_get_match_ids_non_list_body_is_upstream_error():
    def handler(request):
        return httpx.Response(200, json={"unexpected": "object"})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotUpstreamError):
        _run(client.get_match_ids_by_puuid(TARGET_PUUID, platform="euw1"))


def test_get_match_ids_404_maps_to_not_found():
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotNotFoundError) as ei:
        _run(client.get_match_ids_by_puuid("nobody", platform="euw1"))
    assert ei.value.status == 404


def test_get_match_ids_429_maps_to_rate_limited():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "10"})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotRateLimitError) as ei:
        _run(client.get_match_ids_by_puuid("busy", platform="euw1"))
    assert ei.value.status == 429


# ──────────────────────────────────────────
# get_match_detail
# ──────────────────────────────────────────

def test_get_match_detail_happy_path_returns_full_payload():
    detail = load_fixture("riot_match_detail.json")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        return httpx.Response(200, json=detail)

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    got = _run(client.get_match_detail("EUW1_6000000001", platform="euw1"))

    # Regional routing again (europe), and the FULL payload comes back intact so
    # T006 can reconstruct the draft from info.participants + teams/bans.
    assert seen["host"] == "europe.api.riotgames.com"
    assert seen["path"].endswith("/lol/match/v5/matches/EUW1_6000000001")
    assert got["metadata"]["matchId"] == "EUW1_6000000001"
    assert len(got["info"]["participants"]) == 10
    assert got["info"]["queueId"] == 420
    # Shared-shape guarantees for the prediction path:
    p0 = got["info"]["participants"][0]
    assert {"championId", "teamId", "teamPosition", "win"} <= set(p0)
    assert got["info"]["teams"][0]["bans"]


def test_get_match_detail_404_maps_to_not_found():
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotNotFoundError) as ei:
        _run(client.get_match_detail("EUW1_does_not_exist", platform="euw1"))
    assert ei.value.status == 404


def test_get_match_detail_429_maps_to_rate_limited():
    def handler(request):
        return httpx.Response(429)

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotRateLimitError) as ei:
        _run(client.get_match_detail("EUW1_6000000001", platform="euw1"))
    assert ei.value.status == 429
