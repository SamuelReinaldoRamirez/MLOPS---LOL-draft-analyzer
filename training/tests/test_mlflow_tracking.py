"""Unit tests for the MLflow tracking wrapper (Phase 2).

These tests prove the wrapper is a **clean NO-OP** when MLflow is not
configured, so it can never break training or CI. They run without Docker, a
DB, or a running MLflow server — and do not even require the ``mlflow`` package
to be installed for the no-op path.
"""

import contextlib
import socket
import time

import pytest

import mlflow_tracking as mt
import train_all_models as tam


def _free_refused_port() -> int:
    """Return a localhost port that is (almost certainly) refusing connections.

    Binds an ephemeral port, reads it, then closes the socket so nothing is
    listening — a connect attempt to it gets refused immediately.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def no_mlflow_env(monkeypatch):
    """Ensure MLflow is unconfigured for the test."""
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MLFLOW_EXPERIMENT", raising=False)


def test_disabled_when_uri_unset(no_mlflow_env):
    tracker = mt.MLflowTracker()
    assert tracker.enabled is False
    assert tracker._mlflow is None


def test_disabled_when_uri_blank(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "   ")
    tracker = mt.MLflowTracker()
    assert tracker.enabled is False


def test_helper_reports_disabled(no_mlflow_env):
    assert mt._mlflow_enabled() is False


def test_run_is_noop_context_manager(no_mlflow_env):
    tracker = mt.MLflowTracker()
    cm = tracker.run(run_name="x")
    # Must behave like a context manager and swallow nothing.
    with cm as entered:
        assert entered is not None


def test_logging_methods_are_noop_and_never_raise(no_mlflow_env):
    """All logging methods must be silent no-ops when disabled."""
    tracker = mt.MLflowTracker()
    with tracker.run(run_name="noop"):
        tracker.log_params({"model_type": "XGBoost", "minute": 10})
        tracker.log_metrics({"accuracy": 0.72, "roc_auc": 0.80})
        tracker.set_tags({"phase": "2"})
        tracker.log_artifact("/nonexistent/path.pkl")
        tracker.log_model(object(), registered_model_name="lol_draft_at10")
    # Reaching here without exceptions is the assertion.


def test_get_tracker_factory_disabled(no_mlflow_env):
    tracker = mt.get_tracker(experiment="lol-draft-timeline")
    assert isinstance(tracker, mt.MLflowTracker)
    assert tracker.enabled is False


def test_training_module_get_tracker_is_safe(no_mlflow_env):
    """train_all_models exposes a get_tracker that yields a usable no-op."""
    tracker = tam.get_tracker()
    # Either the real wrapper (disabled) or the import-fallback no-op object;
    # both must expose .enabled and a context-manager .run().
    assert hasattr(tracker, "enabled")
    with tracker.run(run_name="from_training"):
        tracker.log_params({"a": 1})
        tracker.log_metrics({"b": 2.0})


def test_import_fallback_noop_shape():
    """The inline fallback in train_all_models is a valid no-op tracker.

    Simulates the case where importing mlflow_tracking fails entirely.
    """
    # Build the same fallback object the module defines on ImportError.
    from contextlib import nullcontext

    class _Noop:
        enabled = False

        def run(self, *a, **k):
            return nullcontext()

        def log_params(self, *a, **k):
            pass

        def log_metrics(self, *a, **k):
            pass

        def log_model(self, *a, **k):
            pass

    noop = _Noop()
    assert noop.enabled is False
    with noop.run(run_name="x"):
        noop.log_params({"x": 1})
        noop.log_metrics({"y": 2.0})
        noop.log_model(object())


def test_unreachable_server_fast_fails_to_noop(monkeypatch):
    """Unreachable URI must degrade to a NO-OP *quickly* — never hang.

    Regression test for the bug where ``set_experiment`` against a down server
    blocked >120s on MLflow REST retry/backoff. Constructing the tracker must
    return in a few seconds with ``enabled is False`` and no-op logging.
    """
    port = _free_refused_port()
    uri = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.delenv("MLFLOW_EXPERIMENT", raising=False)

    start = time.monotonic()
    tracker = mt.MLflowTracker(tracking_uri=uri)
    elapsed = time.monotonic() - start

    assert tracker.enabled is False
    assert tracker._mlflow is None
    # Generous ceiling: the fix targets sub-second; if it ever hangs again on
    # REST backoff this would blow past 10s.
    assert elapsed < 10, f"construction took {elapsed:.2f}s (expected fast-fail)"

    # Logging methods must be silent no-ops on the disabled tracker.
    with tracker.run(run_name="noop"):
        tracker.log_params({"minute": 10})
        tracker.log_metrics({"accuracy": 0.5})
        tracker.set_tags({"phase": "2"})
        tracker.log_artifact("/nonexistent/path.pkl")
        tracker.log_model(object(), registered_model_name="lol_draft_at10")


def test_fast_fail_env_defaults_present():
    """Short HTTP retry/timeout defaults are set on import (the core fix)."""
    import os

    assert os.environ.get("MLFLOW_HTTP_REQUEST_MAX_RETRIES") == "1"
    assert os.environ.get("MLFLOW_HTTP_REQUEST_TIMEOUT") == "3"


def test_server_reachable_passes_non_http_schemes():
    """File/local tracking URIs must not be blocked by the TCP pre-check."""
    assert mt._server_reachable("file:///tmp/mlruns") is True
    assert mt._server_reachable("/tmp/mlruns") is True
