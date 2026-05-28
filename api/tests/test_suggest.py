"""Route tests for GET /riot/suggest (local-DB fuzzy name autocomplete).

All tests run WITHOUT a real database. Two complementary mocking styles are
used, both mirroring the conftest philosophy of stubbing the DB so no real
PostgreSQL connection is attempted:

  * monkeypatch the ``_fetch_suggestions`` helper to return canned rows (the
    fast, behaviour-focused path); and
  * monkeypatch ``psycopg2.connect`` with a tiny fake connection/cursor (the
    "mock the DB cursor" path) so the helper's own SQL plumbing is exercised
    end-to-end offline.

The endpoint must: return an empty list for a short query (no DB hit), map DB
rows to the ``PlayerSuggestion`` schema ranked as the DB returns them, clamp the
limit, and degrade to an empty list on any DB error (never 500).
"""

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────
# Fake DB cursor / connection (no real PostgreSQL) — conftest "stub the DB" style.
# ──────────────────────────────────────────


class _FakeCursor:
    """Minimal psycopg2-cursor stand-in: records executes, returns canned rows."""

    def __init__(self, rows, executed):
        self._rows = rows
        self._executed = executed

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        # Record (sql, params) so a test can assert the threshold SET ran and the
        # fuzzy query was parameterized (no string interpolation of user input).
        self._executed.append((query, params))

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows, executed):
        self._rows = rows
        self._executed = executed
        self.closed = False

    def cursor(self):
        return _FakeCursor(self._rows, self._executed)

    def close(self):
        self.closed = True


# ──────────────────────────────────────────
# Short-query guard: no DB hit, empty list.
# ──────────────────────────────────────────


@pytest.mark.parametrize("q", ["", " ", "a", " x "])
def test_suggest_short_query_returns_empty_without_db(api_main, monkeypatch, q):
    """q shorter than 2 trimmed chars -> empty list, and the DB is NEVER touched."""

    def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("DB must not be queried for a short query")

    monkeypatch.setattr(api_main, "_fetch_suggestions", boom)
    client = TestClient(api_main.app)

    resp = client.get("/riot/suggest", params={"q": q})
    assert resp.status_code == 200
    assert resp.json() == {"suggestions": []}


def test_suggest_missing_q_param_defaults_empty(api_main, monkeypatch):
    """Omitting q entirely defaults to "" -> empty list (no DB hit)."""

    def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("DB must not be queried")

    monkeypatch.setattr(api_main, "_fetch_suggestions", boom)
    client = TestClient(api_main.app)

    resp = client.get("/riot/suggest")
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []


# ──────────────────────────────────────────
# Fuzzy query: rows mapped to the model, ranking preserved.
# ──────────────────────────────────────────


def test_suggest_maps_rows_to_model(api_main, monkeypatch):
    """A fuzzy query returns the (mocked) rows mapped to PlayerSuggestion order."""
    # (riot_id_name, riot_id_tagline, games, sim) — exactly the helper's shape.
    rows = [
        ("zChooke", "EUW", 2, 0.66),
        ("New Hook", "KSN", 39, 0.23),
        ("HOOK MAN", "kr07", 3, 0.23),
    ]
    monkeypatch.setattr(api_main, "_fetch_suggestions", lambda q, limit: rows)
    client = TestClient(api_main.app)

    resp = client.get("/riot/suggest", params={"q": "zchook", "limit": 5})
    assert resp.status_code == 200
    out = resp.json()["suggestions"]
    assert len(out) == 3
    # Order preserved (the DB ranks; the route must not reorder).
    assert out[0] == {"game_name": "zChooke", "tag_line": "EUW", "games": 2}
    assert out[1]["game_name"] == "New Hook"
    assert out[1]["games"] == 39
    # `sim` is a ranking-only column and must NOT leak into the response.
    assert "sim" not in out[0]


def test_suggest_passes_query_and_clamped_limit_to_helper(api_main, monkeypatch):
    """The trimmed query and a clamped limit (1..25) reach the DB helper."""
    seen = {}

    def fake_fetch(q, limit):
        seen["q"] = q
        seen["limit"] = limit
        return []

    monkeypatch.setattr(api_main, "_fetch_suggestions", fake_fetch)
    client = TestClient(api_main.app)

    # limit=999 must be clamped to 25; q is trimmed before the DB call.
    resp = client.get("/riot/suggest", params={"q": "  Faker ", "limit": 999})
    assert resp.status_code == 200
    assert seen["q"] == "Faker"
    assert seen["limit"] == 25


def test_suggest_skips_blank_names(api_main, monkeypatch):
    """Rows with a null/blank name are dropped; a missing tag becomes None."""
    rows = [
        ("Faker", "AP90", 20, 0.9),
        (None, "X", 5, 0.4),      # dropped (null name)
        ("   ", "Y", 5, 0.4),     # dropped (blank name)
        ("Solo", "", 7, 0.3),     # empty tag -> tag_line None
    ]
    monkeypatch.setattr(api_main, "_fetch_suggestions", lambda q, limit: rows)
    client = TestClient(api_main.app)

    out = client.get("/riot/suggest", params={"q": "fak"}).json()["suggestions"]
    names = [s["game_name"] for s in out]
    assert names == ["Faker", "Solo"]
    assert out[1]["tag_line"] is None


# ──────────────────────────────────────────
# Graceful degradation: DB errors never break the page.
# ──────────────────────────────────────────


def test_suggest_db_error_degrades_to_empty(api_main, monkeypatch):
    """Any DB error (e.g. matview missing) -> empty list, HTTP 200 (not 500)."""

    def boom(q, limit):
        raise RuntimeError("relation player_name_suggestions does not exist")

    monkeypatch.setattr(api_main, "_fetch_suggestions", boom)
    client = TestClient(api_main.app)

    resp = client.get("/riot/suggest", params={"q": "faker"})
    assert resp.status_code == 200
    assert resp.json() == {"suggestions": []}


# ──────────────────────────────────────────
# Helper plumbing via a faked psycopg2 connection (mock the DB cursor).
# ──────────────────────────────────────────


def test_fetch_suggestions_sets_threshold_and_parameterizes(api_main, monkeypatch):
    """_fetch_suggestions sets the trigram threshold, parameterizes, returns rows.

    Uses a fake psycopg2 connection/cursor (no real DB) to assert the helper:
      * issues a `SET pg_trgm.similarity_threshold` first,
      * passes q/limit as bound params (never string-formats user input),
      * returns the cursor rows and closes the connection.
    """
    executed = []
    rows = [("zChooke", "EUW", 2, 0.66)]

    monkeypatch.setattr(
        api_main.psycopg2,
        "connect",
        lambda *a, **k: _FakeConn(rows, executed),
    )

    result = api_main._fetch_suggestions("zchook", 8)
    assert result == rows

    # First execute is the per-session similarity threshold SET.
    assert "similarity_threshold" in executed[0][0]
    # Second execute is the fuzzy query, parameterized with q + limit (a dict).
    query, params = executed[1]
    assert "player_name_suggestions" in query
    assert params == {"q": "zchook", "limit": 8}
    # The raw user string must NOT be interpolated into the SQL text.
    assert "zchook" not in query


def test_suggest_route_end_to_end_with_fake_connection(api_main, monkeypatch):
    """End-to-end route test through the REAL helper backed by a fake connection."""
    executed = []
    rows = [
        ("zChooke", "EUW", 2, 0.66),
        ("Zchwaeppe", "NoEUW", 14, 0.21),
    ]
    monkeypatch.setattr(
        api_main.psycopg2,
        "connect",
        lambda *a, **k: _FakeConn(rows, executed),
    )
    client = TestClient(api_main.app)

    out = client.get("/riot/suggest", params={"q": "zchook"}).json()["suggestions"]
    assert [s["game_name"] for s in out] == ["zChooke", "Zchwaeppe"]
    assert out[0]["games"] == 2
