"""
MLflow tracking wrapper for the training pipeline (Phase 2).

Design goals
------------
* **Safe by default**: if ``MLFLOW_TRACKING_URI`` is unset/empty, or the
  ``mlflow`` package is missing, or the server is unreachable, every method is a
  silent **NO-OP**. Training (and the unit-test suite / CI) must NEVER break
  because of experiment tracking.
* **Single entry point**: ``MLflowTracker`` wraps run lifecycle, params,
  metrics, model logging and optional Model Registry registration.

Usage
-----
    tracker = MLflowTracker(experiment="lol-draft-timeline")
    with tracker.run(run_name="model_at10"):
        tracker.log_params({"minute": 10, "model_type": "XGBoost"})
        tracker.log_metrics({"accuracy": 0.72, "roc_auc": 0.80})
        tracker.log_model(model, artifact_path="model",
                          registered_model_name="lol_at10")

When tracking is disabled the same code runs untouched — the context manager
and methods just do nothing.

Fast-fail degradation
---------------------
If ``MLFLOW_TRACKING_URI`` points at an **unreachable** server, MLflow's default
REST client retries with backoff and can block for minutes. To keep the NO-OP
promise honest, this module sets short HTTP retry/timeout defaults *before* the
first network call, so an unreachable server fails in seconds and the
``try/except`` converts it to a clean no-op. A quick socket pre-check is also
performed as belt-and-suspenders.
"""

import os
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Keep degradation FAST: an unreachable MLflow server must fail in seconds, not
# hang for minutes on REST retry/backoff. These are set before any MLflow call
# and use setdefault so an explicit operator override still wins.
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "3")

# Seconds to wait on the belt-and-suspenders TCP pre-check.
_SOCKET_PRECHECK_TIMEOUT = 3.0


def _mlflow_enabled() -> bool:
    """Tracking is enabled only when a tracking URI is configured."""
    return bool(os.getenv("MLFLOW_TRACKING_URI", "").strip())


def _server_reachable(uri: str, timeout: float = _SOCKET_PRECHECK_TIMEOUT) -> bool:
    """Best-effort TCP reachability check for an http(s) tracking URI.

    Returns ``True`` for non-http schemes (file://, local paths, etc.) so we
    never block those. For http(s) URIs, attempts a short TCP connect to the
    host:port; on any failure returns ``False`` (the caller degrades to no-op).
    """
    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https"):
        return True
    host = parsed.hostname
    if not host:
        return True
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class _NullRun:
    """Context manager used when tracking is disabled (NO-OP)."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class MLflowTracker:
    """Thin, fail-safe wrapper around MLflow.

    The wrapper is considered *active* only when:
      1. ``MLFLOW_TRACKING_URI`` is set, AND
      2. the ``mlflow`` package imports successfully.

    Any error during setup or logging disables the tracker for the rest of its
    lifetime and is logged at WARNING level — it never raises.
    """

    def __init__(self, experiment: str | None = None,
                 tracking_uri: str | None = None):
        self.enabled = False
        self._mlflow = None
        self.experiment = experiment or os.getenv(
            "MLFLOW_EXPERIMENT", "lol-draft-timeline"
        )
        self.tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI", "").strip()

        if not self.tracking_uri:
            logger.info("MLflow disabled: MLFLOW_TRACKING_URI not set (no-op).")
            return

        # Belt-and-suspenders: bail out fast if the server can't even be
        # reached over TCP, before MLflow's REST client gets a chance to retry.
        if not _server_reachable(self.tracking_uri):
            logger.warning(
                "MLflow disabled (server unreachable, no-op): uri=%s",
                self.tracking_uri,
            )
            self.enabled = False
            self._mlflow = None
            return

        try:
            import mlflow  # noqa: WPS433 (lazy import so unset env = no dep needed)

            mlflow.set_tracking_uri(self.tracking_uri)
            mlflow.set_experiment(self.experiment)
            self._mlflow = mlflow
            self.enabled = True
            logger.info(
                "MLflow enabled: uri=%s experiment=%s",
                self.tracking_uri, self.experiment,
            )
        except Exception as exc:  # pragma: no cover - depends on server/pkg
            logger.warning("MLflow disabled (setup failed): %s", exc)
            self.enabled = False
            self._mlflow = None

    # ── run lifecycle ──────────────────────────────────────────────
    def run(self, run_name: str | None = None, tags: dict | None = None):
        """Return a context manager for an MLflow run (NO-OP if disabled)."""
        if not self.enabled:
            return _NullRun()
        try:
            return self._mlflow.start_run(run_name=run_name, tags=tags)
        except Exception as exc:  # pragma: no cover
            logger.warning("MLflow start_run failed, disabling: %s", exc)
            self.enabled = False
            return _NullRun()

    # ── logging helpers (all NO-OP + fail-safe) ────────────────────
    def log_params(self, params: dict) -> None:
        if not self.enabled:
            return
        try:
            self._mlflow.log_params(params)
        except Exception as exc:  # pragma: no cover
            logger.warning("MLflow log_params failed: %s", exc)

    def log_metrics(self, metrics: dict) -> None:
        if not self.enabled:
            return
        try:
            self._mlflow.log_metrics(metrics)
        except Exception as exc:  # pragma: no cover
            logger.warning("MLflow log_metrics failed: %s", exc)

    def set_tags(self, tags: dict) -> None:
        if not self.enabled:
            return
        try:
            self._mlflow.set_tags(tags)
        except Exception as exc:  # pragma: no cover
            logger.warning("MLflow set_tags failed: %s", exc)

    def log_artifact(self, local_path: str, artifact_path: str | None = None) -> None:
        if not self.enabled:
            return
        try:
            self._mlflow.log_artifact(local_path, artifact_path=artifact_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("MLflow log_artifact failed: %s", exc)

    def log_model(self, model, artifact_path: str = "model",
                  registered_model_name: str | None = None) -> None:
        """Log a sklearn-compatible model and (optionally) register a version.

        Registration in the Model Registry only happens when a name is given
        AND the tracking server backs a registry (the compose server does).
        Falls back to ``log_artifact`` of a pickled file if sklearn flavour
        logging is unavailable.
        """
        if not self.enabled:
            return
        try:
            self._mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path=artifact_path,
                registered_model_name=registered_model_name,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("MLflow log_model failed: %s", exc)


def get_tracker(experiment: str | None = None) -> MLflowTracker:
    """Factory used by the training pipeline."""
    return MLflowTracker(experiment=experiment)
