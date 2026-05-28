"""Phase 4 — auto-retrain decision-logic tests.

Run WITHOUT Docker or a DB: the drift step and the training trigger are both
INJECTED as mocks, so we test the pure decision logic (drift > threshold =>
retrain) and the safe NO-OP paths. No real training is ever invoked.
"""

import sys
from pathlib import Path

import pytest

# scripts/auto_retrain.py lives at the repo root /scripts (not on the default
# test path). Add it so we can import the hook under test.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import auto_retrain as ar  # noqa: E402


# ──────────────────────────────────────────
# Pure decision predicate
# ──────────────────────────────────────────

def test_should_retrain_above_threshold():
    assert ar.should_retrain({"drift_share": 0.8}, threshold=0.5) is True


def test_should_retrain_below_threshold():
    assert ar.should_retrain({"drift_share": 0.2}, threshold=0.5) is False


def test_should_retrain_equal_threshold_is_false():
    # Strictly greater-than: exactly-at-threshold does NOT retrain.
    assert ar.should_retrain({"drift_share": 0.5}, threshold=0.5) is False


def test_should_retrain_none_summary_is_false():
    assert ar.should_retrain(None, threshold=0.5) is False
    assert ar.should_retrain({}, threshold=0.5) is False
    assert ar.should_retrain({"drift_share": None}, threshold=0.5) is False


# ──────────────────────────────────────────
# Orchestration with injected drift + retrain
# ──────────────────────────────────────────

def test_decide_and_retrain_triggers_when_drifted():
    calls = {"n": 0}

    def fake_drift(force_drift=False):
        return {"drift_share": 0.9, "source": "synthetic"}

    def fake_retrain():
        calls["n"] += 1
        return 0

    result = ar.decide_and_retrain(
        threshold=0.5, drift_fn=fake_drift, retrain_fn=fake_retrain
    )

    assert result["decision"] is True
    assert result["retrained"] is True
    assert result["returncode"] == 0
    assert calls["n"] == 1  # training trigger called exactly once


def test_decide_and_retrain_noop_when_not_drifted():
    def fake_drift(force_drift=False):
        return {"drift_share": 0.1, "source": "synthetic"}

    def fake_retrain():
        raise AssertionError("retrain must NOT be called when below threshold")

    result = ar.decide_and_retrain(
        threshold=0.5, drift_fn=fake_drift, retrain_fn=fake_retrain
    )

    assert result["decision"] is False
    assert result["retrained"] is False


def test_decide_and_retrain_dry_run_decides_but_never_retrains():
    def fake_drift(force_drift=False):
        return {"drift_share": 0.9, "source": "synthetic"}

    def fake_retrain():
        raise AssertionError("retrain must NOT run in dry-run mode")

    result = ar.decide_and_retrain(
        threshold=0.5, dry_run=True, drift_fn=fake_drift, retrain_fn=fake_retrain
    )

    assert result["decision"] is True
    assert result["retrained"] is False
    assert "dry-run" in result["reason"]


def test_decide_and_retrain_safe_when_drift_unavailable():
    """A None drift summary (evidently missing) must NOT trigger retraining."""
    def fake_drift(force_drift=False):
        return None

    def fake_retrain():
        raise AssertionError("retrain must NOT run without drift evidence")

    result = ar.decide_and_retrain(
        threshold=0.5, drift_fn=fake_drift, retrain_fn=fake_retrain
    )

    assert result["decision"] is False
    assert result["retrained"] is False
    assert "unavailable" in result["reason"]


def test_decide_and_retrain_reports_failed_retrain_returncode():
    def fake_drift(force_drift=False):
        return {"drift_share": 0.9, "source": "synthetic"}

    def fake_retrain():
        return 1  # non-zero -> training failed

    result = ar.decide_and_retrain(
        threshold=0.5, drift_fn=fake_drift, retrain_fn=fake_retrain
    )

    assert result["decision"] is True
    assert result["retrained"] is False
    assert result["returncode"] == 1
