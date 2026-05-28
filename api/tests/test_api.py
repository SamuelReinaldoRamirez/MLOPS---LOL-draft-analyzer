"""Unit tests for the FastAPI inference API.

All tests run WITHOUT Docker or a real database. Model loading is backed by a
tiny fixture .pkl (see conftest) and the DB helper is monkeypatched.
"""

import pytest


# ──────────────────────────────────────────
# /health
# ──────────────────────────────────────────

def test_health_db_connected(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
    # Models present in the fixture dir report True.
    assert body["models"]["draft"] is True
    assert body["models"]["at10"] is True
    # Models not present report False.
    assert body["models"]["at5"] is False


def test_health_db_disconnected(api_main, monkeypatch):
    from fastapi.testclient import TestClient

    def boom(*a, **k):
        raise RuntimeError("no db")

    monkeypatch.setattr(api_main, "fetchone", boom)
    client = TestClient(api_main.app)

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["database"] == "disconnected"


# ──────────────────────────────────────────
# /models
# ──────────────────────────────────────────

def test_models_lists_available(client):
    resp = client.get("/models")
    assert resp.status_code == 200
    body = resp.json()

    assert body["draft"]["available"] is True
    assert body["draft"]["accuracy"] == pytest.approx(0.66)
    assert body["draft"]["model_type"] == "LogisticRegression"
    assert body["draft"]["n_features"] == 6

    assert body["at10"]["available"] is True
    assert body["at5"]["available"] is False


# ──────────────────────────────────────────
# /predict/at/{minute}
# ──────────────────────────────────────────

def test_predict_at_10_ok(client):
    resp = client.post(
        "/predict/at/10",
        json={
            "gold_diff": 2500,
            "first_blood": True,
            "first_dragon": True,
            "top_gold_diff": 500,
            "jungle_gold_diff": 800,
            "mid_gold_diff": 400,
            "adc_gold_diff": 600,
            "support_gold_diff": 200,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_used"] == "at10"
    assert body["winner"] in ("Blue Team", "Red Team")
    assert 0.0 <= body["blue_win_probability"] <= 1.0
    assert 0.0 <= body["red_win_probability"] <= 1.0
    assert body["blue_win_probability"] + body["red_win_probability"] == pytest.approx(1.0)
    assert body["model_accuracy"] == pytest.approx(0.66)


def test_predict_at_invalid_minute(client):
    resp = client.post("/predict/at/7", json={"gold_diff": 0})
    assert resp.status_code == 400


def test_predict_at_missing_model(client):
    # at20 is not present in the fixture dir -> 404.
    resp = client.post("/predict/at/20", json={"gold_diff": 0})
    assert resp.status_code == 404


# ──────────────────────────────────────────
# /predict/draft
# ──────────────────────────────────────────

def _draft_payload():
    return {
        "blue_top": "Aatrox",
        "blue_jungle": "LeeSin",
        "blue_mid": "Ahri",
        "blue_adc": "Jinx",
        "blue_support": "Thresh",
        "red_top": "Darius",
        "red_jungle": "Elise",
        "red_mid": "Zed",
        "red_adc": "Caitlyn",
        "red_support": "Lulu",
    }


def test_predict_draft_ok(client):
    resp = client.post("/predict/draft", json=_draft_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_used"] == "draft"
    assert body["winner"] in ("Blue Team", "Red Team")
    assert body["blue_win_probability"] + body["red_win_probability"] == pytest.approx(1.0)
    assert 0.0 <= body["confidence"] <= 1.0


def test_predict_draft_validation_error(client):
    # Missing required champion field -> 422 from pydantic validation.
    payload = _draft_payload()
    del payload["blue_top"]
    resp = client.post("/predict/draft", json=payload)
    assert resp.status_code == 422


def test_predict_draft_missing_model(api_main, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    # Point at a fresh EMPTY dir (the fixture wrote models into tmp_path itself)
    # so the draft model is absent -> 404.
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()
    monkeypatch.setattr(api_main, "MODELS_DIR", empty_dir)
    api_main._model_cache.clear()
    client = TestClient(api_main.app)

    resp = client.post("/predict/draft", json=_draft_payload())
    assert resp.status_code == 404
