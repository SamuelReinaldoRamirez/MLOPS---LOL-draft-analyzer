"""Shared fixtures for the API test suite.

Everything here runs WITHOUT Docker or a real database:
  * a tiny in-memory sklearn model is built and saved as a fixture .pkl in the
    same dict schema the API expects (model / scaler / feature_columns / metadata);
  * ``MODELS_DIR`` and the module-level model cache are monkeypatched;
  * the DB ``fetchone`` helper is monkeypatched.
"""

import importlib
import sys
from pathlib import Path

# Make this directory importable so the recorded-fixture helpers in the
# ``fixtures`` package resolve from both conftest and the test modules
# (importlib import-mode does not guarantee api/tests is on sys.path yet when
# this conftest is first loaded).
_TESTS_DIR = Path(__file__).parent.resolve()
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import httpx
import joblib
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from fixtures import load_fixture, make_riot_transport


# Feature columns for the tiny timeline fixture model (@10min schema).
TIMELINE_FEATURES_AT10 = [
    "gold_diff_at_10",
    "first_blood_team_100",
    "first_tower_team_100",
    "first_dragon_team_100",
    "first_herald_team_100",
    "top_gold_diff_at_10",
    "jungle_gold_diff_at_10",
    "mid_gold_diff_at_10",
    "adc_gold_diff_at_10",
    "support_gold_diff_at_10",
]

# Feature columns for the tiny draft fixture model. Like the production
# model_draft.pkl, these are NUMERIC features (the route fills them with neutral
# defaults — champion names are not mapped into the numeric feature space).
DRAFT_FEATURES = [
    "draft_advantage",
    "synergy_diff",
    "counter_diff",
    "ext_wr_diff",
    "team_100_synergy_score",
    "team_200_synergy_score",
]


def _make_model_bundle(feature_columns, fit_with_scaler=True, seed=0):
    """Build a tiny fitted LogisticRegression bundle in the API's dict schema."""
    rng = np.random.default_rng(seed)
    n = 60
    n_feat = len(feature_columns)
    X = rng.normal(size=(n, n_feat))
    # Separable-ish target so predict_proba is well defined.
    y = (X[:, 0] + rng.normal(scale=0.1, size=n) > 0).astype(int)

    scaler = StandardScaler().fit(X) if fit_with_scaler else StandardScaler()
    X_in = scaler.transform(X) if fit_with_scaler else X

    model = LogisticRegression(max_iter=500).fit(X_in, y)

    return {
        "model": model,
        "scaler": scaler,
        "feature_columns": list(feature_columns),
        "features": list(feature_columns),
        "metadata": {
            "model_type": "LogisticRegression",
            "accuracy": 0.66,
            "auc_roc": 0.70,
        },
    }


@pytest.fixture()
def fixture_models_dir(tmp_path):
    """Create a temp models dir containing tiny draft + @10 fixture models."""
    joblib.dump(_make_model_bundle(DRAFT_FEATURES, seed=1), tmp_path / "model_draft.pkl")
    joblib.dump(_make_model_bundle(TIMELINE_FEATURES_AT10, seed=2), tmp_path / "model_at10.pkl")
    return tmp_path


@pytest.fixture()
def api_main(fixture_models_dir, monkeypatch):
    """Import api.app.main with MODELS_DIR pointed at the fixture dir.

    The module-level model cache is cleared and the DB helper is stubbed so no
    real PostgreSQL connection is ever attempted.
    """
    from app import main as main_module

    importlib.reload(main_module)

    monkeypatch.setattr(main_module, "MODELS_DIR", fixture_models_dir)
    main_module._model_cache.clear()

    # Stub the DB helper: default to "connected" (returns a row).
    monkeypatch.setattr(main_module, "fetchone", lambda *a, **k: (1,))

    return main_module


@pytest.fixture()
def client(api_main):
    from fastapi.testclient import TestClient

    return TestClient(api_main.app)


# ──────────────────────────────────────────
# Riot client mocking (httpx.MockTransport — NO respx, NO network, NO live key)
# ``load_fixture`` / ``make_riot_transport`` live in the ``fixtures`` package so
# the test modules can import them directly (importlib mode puts api/tests on
# sys.path). Re-exported here implicitly via the import above for fixtures use.
# ──────────────────────────────────────────


@pytest.fixture()
def riot_happy_transport():
    """MockTransport serving recorded account-v1 + summoner-v4 happy-path JSON."""
    account = load_fixture("riot_account_v1.json")
    summoner = load_fixture("riot_summoner_v4.json")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # Auth header must always be present on Riot calls.
        assert request.headers.get("X-Riot-Token")
        if "/riot/account/v1/accounts/by-riot-id/" in path:
            return httpx.Response(200, json=account)
        if "/lol/summoner/v4/summoners/by-puuid/" in path:
            return httpx.Response(200, json=summoner)
        return httpx.Response(404, json={"status": {"status_code": 404}})

    return make_riot_transport(handler)
