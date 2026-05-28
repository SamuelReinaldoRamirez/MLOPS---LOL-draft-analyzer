"""Recorded test fixtures + helpers for the Riot client / route tests.

Importable as ``tests.fixtures`` is NOT relied upon (the suite runs in
``--import-mode=importlib`` with ``api/`` on ``sys.path``). Tests import these
helpers directly from this package path. Helpers here keep no-network test
wiring (``httpx.MockTransport`` — NOT respx) in one place.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

_FIXTURES_DIR = Path(__file__).parent


def load_fixture(name: str) -> dict:
    """Load a recorded JSON fixture from this directory."""
    with open(_FIXTURES_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def make_riot_transport(handler) -> "httpx.MockTransport":
    """Wrap a request handler in an ``httpx.MockTransport`` for the Riot client.

    ``handler(httpx.Request) -> httpx.Response`` is invoked for every outbound
    request so tests can route by URL path to recorded account-v1 / summoner-v4
    fixtures or return error statuses (404 / 429 / ...).
    """
    return httpx.MockTransport(handler)
