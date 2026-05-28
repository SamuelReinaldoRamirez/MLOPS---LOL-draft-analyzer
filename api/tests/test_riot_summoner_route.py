"""Route tests for GET /riot/summoner (account-v1 + summoner-v4 wiring).

Offline: the Riot client dependency is overridden with a client wired to an
``httpx.MockTransport`` (no respx, no network). The no-key case exercises the
REAL dependency with the env var unset so the route returns a clear 503.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.riot_client import RiotClient
from fixtures import load_fixture, make_riot_transport


def _client_with_transport(api_main, handler, monkeypatch, api_key="TEST-KEY"):
    """Build a TestClient with the Riot client dependency overridden."""
    monkeypatch.setenv("RIOT_API_KEY", api_key)
    riot = RiotClient(api_key=api_key, transport=make_riot_transport(handler))
    api_main.app.dependency_overrides[api_main.get_riot_client] = lambda: riot
    return TestClient(api_main.app)


def test_summoner_200_maps_puuid_and_profile(api_main, monkeypatch):
    account = load_fixture("riot_account_v1.json")
    summoner = load_fixture("riot_summoner_v4.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if "account/v1" in request.url.path:
            return httpx.Response(200, json=account)
        return httpx.Response(200, json=summoner)

    client = _client_with_transport(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/summoner", params={"gameName": "Faker", "tagLine": "KR1", "region": "kr"})
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["puuid"] == account["puuid"]
    assert body["game_name"] == "Faker"
    assert body["tag_line"] == "KR1"
    assert body["platform"] == "kr"
    assert body["summoner_level"] == summoner["summonerLevel"]
    assert body["profile_icon_id"] == summoner["profileIconId"]


def test_summoner_defaults_region_when_omitted(api_main, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if "account/v1" in request.url.path:
            return httpx.Response(200, json={"puuid": "p", "gameName": "G", "tagLine": "T"})
        return httpx.Response(200, json={"summonerLevel": 30, "profileIconId": 1})

    client = _client_with_transport(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/summoner", params={"gameName": "G", "tagLine": "T"})
    finally:
        api_main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    # Defaults to RIOT_PLATFORM (euw1) when region is omitted.
    assert resp.json()["platform"] == "euw1"


def test_summoner_404_not_found(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"status": {"status_code": 404}})

    client = _client_with_transport(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/summoner", params={"gameName": "Nobody", "tagLine": "0000"})
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_summoner_429_rate_limited(api_main, monkeypatch):
    def handler(request):
        return httpx.Response(429)

    client = _client_with_transport(api_main, handler, monkeypatch)
    try:
        resp = client.get("/riot/summoner", params={"gameName": "Busy", "tagLine": "EUW"})
    finally:
        api_main.app.dependency_overrides.clear()
    assert resp.status_code == 429


def test_summoner_503_when_key_unset(api_main, monkeypatch):
    # No dependency override: the REAL get_riot_client runs with no key set,
    # so the route returns a clean 503 (a real "key not configured" state).
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    client = TestClient(api_main.app)
    resp = client.get("/riot/summoner", params={"gameName": "G", "tagLine": "T"})
    assert resp.status_code == 503
    assert "detail" in resp.json()


def test_summoner_400_when_missing_query(api_main):
    client = TestClient(api_main.app)
    # tagLine missing -> FastAPI 422 (required query param).
    resp = client.get("/riot/summoner", params={"gameName": "G"})
    assert resp.status_code == 422
