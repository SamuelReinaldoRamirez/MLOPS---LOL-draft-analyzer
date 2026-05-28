"""Unit tests for the async Riot client (app.riot_client).

All offline: an ``httpx.MockTransport`` (NOT respx) serves recorded account-v1
and summoner-v4 fixtures or error statuses. No live key, no network.
"""

import asyncio

import httpx
import pytest

from app.riot_client import (
    RiotClient,
    RiotKeyMissingError,
    RiotNotFoundError,
    RiotRateLimitError,
    RiotUpstreamError,
    regional_for_platform,
)
from fixtures import load_fixture, make_riot_transport


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────
# platform -> regional mapping
# ──────────────────────────────────────────

def test_regional_for_platform_known():
    assert regional_for_platform("euw1") == "europe"
    assert regional_for_platform("eun1") == "europe"
    assert regional_for_platform("na1") == "americas"
    assert regional_for_platform("br1") == "americas"
    assert regional_for_platform("kr") == "asia"
    assert regional_for_platform("jp1") == "asia"
    assert regional_for_platform("oc1") == "sea"  # documented SEA choice
    assert regional_for_platform("vn2") == "sea"


def test_regional_for_platform_unknown_defaults_to_europe():
    assert regional_for_platform("zz9") == "europe"
    assert regional_for_platform("") == "europe"


def test_regional_for_platform_case_insensitive():
    assert regional_for_platform("EUW1") == "europe"
    assert regional_for_platform(" KR ") == "asia"


# ──────────────────────────────────────────
# happy path: account-v1 + summoner-v4
# ──────────────────────────────────────────

def test_get_account_and_summoner_happy_path():
    account = load_fixture("riot_account_v1.json")
    summoner = load_fixture("riot_summoner_v4.json")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["token"] = request.headers.get("X-Riot-Token")
        if "/riot/account/v1/accounts/by-riot-id/" in request.url.path:
            return httpx.Response(200, json=account)
        return httpx.Response(200, json=summoner)

    client = RiotClient(api_key="TEST-KEY", transport=make_riot_transport(handler))

    acc = _run(client.get_account_by_riot_id("Faker", "KR1", platform="kr"))
    assert acc["puuid"] == account["puuid"]
    # account-v1 must hit the REGIONAL cluster for kr (asia).
    assert seen["host"] == "asia.api.riotgames.com"
    assert seen["token"] == "TEST-KEY"

    summ = _run(client.get_summoner_by_puuid(acc["puuid"], platform="kr"))
    assert summ["summonerLevel"] == summoner["summonerLevel"]
    assert summ["profileIconId"] == summoner["profileIconId"]
    # summoner-v4 uses PLATFORM routing.
    assert seen["host"] == "kr.api.riotgames.com"


def test_riot_id_with_space_is_percent_encoded():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(200, json={"puuid": "p", "gameName": "Hide on bush", "tagLine": "EUW"})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    _run(client.get_account_by_riot_id("Hide on bush", "EUW", platform="euw1"))
    # The space must be percent-encoded in the request path (no raw spaces).
    assert "Hide%20on%20bush" in captured["raw_path"]
    assert " " not in captured["raw_path"]


def test_account_uses_regional_summoner_uses_platform_for_euw():
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if "account/v1" in request.url.path:
            return httpx.Response(200, json={"puuid": "p", "gameName": "G", "tagLine": "T"})
        return httpx.Response(200, json={"summonerLevel": 30, "profileIconId": 1})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    _run(client.get_account_by_riot_id("G", "T", platform="euw1"))
    _run(client.get_summoner_by_puuid("p", platform="euw1"))
    assert hosts == ["europe.api.riotgames.com", "euw1.api.riotgames.com"]


# ──────────────────────────────────────────
# error mapping
# ──────────────────────────────────────────

def test_404_maps_to_not_found():
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotNotFoundError) as ei:
        _run(client.get_account_by_riot_id("Nobody", "0000"))
    assert ei.value.status == 404


def test_429_maps_to_rate_limited():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "10"})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotRateLimitError) as ei:
        _run(client.get_account_by_riot_id("Busy", "EUW"))
    assert ei.value.status == 429


def test_other_5xx_maps_to_upstream():
    def handler(request):
        return httpx.Response(503, json={"status": {"status_code": 503}})

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotUpstreamError) as ei:
        _run(client.get_summoner_by_puuid("p", platform="euw1"))
    assert ei.value.status == 502


def test_network_error_maps_to_upstream():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = RiotClient(api_key="K", transport=make_riot_transport(handler))
    with pytest.raises(RiotUpstreamError):
        _run(client.get_account_by_riot_id("G", "T"))


# ──────────────────────────────────────────
# no key
# ──────────────────────────────────────────

def test_missing_key_raises_key_missing(monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)

    def handler(request):  # pragma: no cover - never reached without a key
        return httpx.Response(200, json={})

    client = RiotClient(transport=make_riot_transport(handler))
    with pytest.raises(RiotKeyMissingError) as ei:
        _run(client.get_account_by_riot_id("G", "T"))
    assert ei.value.status == 503


def test_empty_key_raises_key_missing(monkeypatch):
    monkeypatch.setenv("RIOT_API_KEY", "   ")
    client = RiotClient(transport=make_riot_transport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(RiotKeyMissingError):
        _run(client.get_summoner_by_puuid("p"))


# ──────────────────────────────────────────
# transient-failure retry (opt-in; default retries=0 is fail-fast)
# ──────────────────────────────────────────

def _counting_handler(responses):
    """Handler returning successive ``responses`` (last one repeats), counting calls."""
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = min(state["n"], len(responses) - 1)
        state["n"] += 1
        return responses[i]

    return handler, state


def test_retry_recovers_from_transient_5xx():
    handler, state = _counting_handler(
        [httpx.Response(503, json={}), httpx.Response(200, json={"summonerLevel": 30, "profileIconId": 7})]
    )
    client = RiotClient(
        api_key="K", transport=make_riot_transport(handler), retries=2, backoff_base=0.0
    )
    summ = _run(client.get_summoner_by_puuid("p", platform="euw1"))
    assert summ["summonerLevel"] == 30
    assert state["n"] == 2  # first 503 retried, second attempt 200


def test_retry_recovers_from_burst_429_with_retry_after():
    handler, state = _counting_handler(
        [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"puuid": "p", "gameName": "G", "tagLine": "T"}),
        ]
    )
    client = RiotClient(
        api_key="K", transport=make_riot_transport(handler), retries=2, backoff_base=0.0
    )
    acc = _run(client.get_account_by_riot_id("G", "T"))
    assert acc["puuid"] == "p"
    assert state["n"] == 2


def test_retry_exhausted_surfaces_upstream():
    handler, state = _counting_handler([httpx.Response(502, json={})])
    client = RiotClient(
        api_key="K", transport=make_riot_transport(handler), retries=2, backoff_base=0.0
    )
    with pytest.raises(RiotUpstreamError) as ei:
        _run(client.get_summoner_by_puuid("p"))
    assert ei.value.status == 502
    assert state["n"] == 3  # 1 initial + 2 retries


def test_retries_default_zero_is_fail_fast():
    handler, state = _counting_handler([httpx.Response(503, json={})])
    client = RiotClient(api_key="K", transport=make_riot_transport(handler))  # retries=0
    with pytest.raises(RiotUpstreamError):
        _run(client.get_summoner_by_puuid("p"))
    assert state["n"] == 1  # no retry


def test_404_is_never_retried():
    handler, state = _counting_handler([httpx.Response(404, json={})])
    client = RiotClient(
        api_key="K", transport=make_riot_transport(handler), retries=3, backoff_base=0.0
    )
    with pytest.raises(RiotNotFoundError):
        _run(client.get_summoner_by_puuid("p"))
    assert state["n"] == 1  # terminal — a retry won't change it
