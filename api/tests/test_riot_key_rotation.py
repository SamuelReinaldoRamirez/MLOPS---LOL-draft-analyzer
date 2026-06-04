"""Unit tests for multi-key round-robin + failover in the Riot client.

All offline: an ``httpx.MockTransport`` inspects the outbound ``X-Riot-Token``
header to know which key was used, and returns 401/403 to simulate an expired
key. ``RiotClient(api_key="K1,K2,...")`` injects several keys without env vars.
"""

import asyncio

import httpx
import pytest

import app.riot_client as rc
from app.riot_client import RiotClient, RiotUpstreamError
from fixtures import make_riot_transport


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_rotation():
    """Module-level rotation state persists across requests — isolate each test."""
    rc._KEY_ROTATION_INDEX = 0
    rc._DEAD_KEYS.clear()
    yield
    rc._KEY_ROTATION_INDEX = 0
    rc._DEAD_KEYS.clear()


SUMMONER = {"puuid": "p", "id": "x", "summonerLevel": 30}


def test_expired_key_fails_over_to_next():
    """A 403 on the first key transparently retries with the next key."""
    used = []

    def handler(request):
        key = request.headers["X-Riot-Token"]
        used.append(key)
        if key == "DEAD":
            return httpx.Response(403, json={"status": {"status_code": 403}})
        return httpx.Response(200, json=SUMMONER)

    client = RiotClient(api_key="DEAD,GOOD", transport=make_riot_transport(handler))
    out = _run(client.get_summoner_by_puuid("p", platform="euw1"))

    assert out == SUMMONER
    assert used == ["DEAD", "GOOD"]      # failed over to the live key
    assert "DEAD" in rc._DEAD_KEYS       # expired key retired


def test_dead_key_is_skipped_on_next_request():
    """Once retired, a dead key is not retried first on the following request."""
    used = []

    def handler(request):
        key = request.headers["X-Riot-Token"]
        used.append(key)
        if key == "DEAD":
            return httpx.Response(401, json={"status": {"status_code": 401}})
        return httpx.Response(200, json=SUMMONER)

    transport = make_riot_transport(handler)
    # First (per-request) client retires DEAD and succeeds on GOOD.
    _run(RiotClient(api_key="DEAD,GOOD", transport=transport).get_summoner_by_puuid("p", platform="euw1"))
    used.clear()
    # Second request must skip the now-dead key entirely.
    _run(RiotClient(api_key="DEAD,GOOD", transport=transport).get_summoner_by_puuid("p", platform="euw1"))

    assert used == ["GOOD"]


def test_round_robin_spreads_requests_across_keys():
    """Consecutive successful requests advance the shared rotation pointer."""
    used = []

    def handler(request):
        used.append(request.headers["X-Riot-Token"])
        return httpx.Response(200, json=SUMMONER)

    transport = make_riot_transport(handler)
    for _ in range(4):
        _run(RiotClient(api_key="A,B,C", transport=transport).get_summoner_by_puuid("p", platform="euw1"))

    assert used == ["A", "B", "C", "A"]  # round-robin wraps after the 3rd key


def test_all_keys_expired_raises_upstream():
    """When every configured key is rejected, surface a 502 upstream error."""
    def handler(request):
        return httpx.Response(403, json={"status": {"status_code": 403}})

    client = RiotClient(api_key="K1,K2", transport=make_riot_transport(handler))
    with pytest.raises(RiotUpstreamError) as ei:
        _run(client.get_summoner_by_puuid("p", platform="euw1"))
    assert ei.value.status == 502
