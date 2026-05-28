#!/usr/bin/env python3
"""
LoL Draft Predictor — automated model update hook (Phase 4).

Cleaned-up, MLOps-friendly successor to the source project's
``scripts/wait_and_retrain.py``: instead of polling a backfill PID and doing a
heavyweight re-export, this hook is a small, idempotent *decision + trigger*:

    1. Run drift detection (Evidently) on reference vs current data.
    2. IF the drifted-column share exceeds a threshold -> trigger retraining
       by invoking the EXISTING training entrypoint.
    3. Otherwise -> NO-OP (nothing to do).

Safety / verifiability
----------------------
* **No live DB required to import or unit-test.** The drift step falls back to
  synthetic data (see ``training/scripts/drift_report.py``), and the retrain
  trigger is injectable, so :func:`decide_and_retrain` is fully testable with a
  mocked trainer.
* **Idempotent + safe.** When drift is below threshold the hook does nothing.
  When ``evidently`` is unavailable it degrades to "no decision" (no retrain),
  never raising. The real retrain shells out to the training profile and is the
  only step that needs a live DB.

Usage
-----
    python scripts/auto_retrain.py                 # synthetic data, real check
    python scripts/auto_retrain.py --force-drift   # demo: force drift -> retrain
    python scripts/auto_retrain.py --threshold 0.3
    python scripts/auto_retrain.py --dry-run       # decide only, never retrain
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# Make training/scripts importable when run from the repo root, so we can reuse
# the drift detection module without duplicating it.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TRAINING_SCRIPTS = _REPO_ROOT / "training" / "scripts"
if str(_TRAINING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TRAINING_SCRIPTS))


def default_threshold() -> float:
    """Drift share above which retraining is triggered (env-overridable)."""
    try:
        return float(os.getenv("DRIFT_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


# ──────────────────────────────────────────
# Decision logic (pure + unit-testable)
# ──────────────────────────────────────────

def should_retrain(drift_summary: Optional[dict], threshold: float) -> bool:
    """Return True iff the drifted-column share strictly exceeds ``threshold``.

    A ``None`` summary (e.g. evidently unavailable / drift step skipped) yields
    ``False`` — we never retrain on missing evidence.
    """
    if not drift_summary:
        return False
    share = drift_summary.get("drift_share")
    if share is None:
        return False
    return float(share) > float(threshold)


def trigger_retrain_subprocess() -> int:
    """Trigger retraining via the EXISTING training entrypoint (compose profile).

    This is the only step that needs a live DB / the dump, so it is isolated
    behind a callable that the unit tests replace with a mock. Returns the
    subprocess return code.
    """
    cmd = [
        "docker", "compose", "run", "--rm", "training",
        "python", "scripts/train_all_models.py",
    ]
    print(f"  [auto-retrain] triggering: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(_REPO_ROOT))
    return proc.returncode


# ──────────────────────────────────────────
# Orchestration (drift -> decide -> maybe retrain)
# ──────────────────────────────────────────

def decide_and_retrain(
    threshold: Optional[float] = None,
    force_drift: bool = False,
    dry_run: bool = False,
    drift_fn: Optional[Callable[..., Optional[dict]]] = None,
    retrain_fn: Optional[Callable[[], int]] = None,
) -> dict:
    """Run drift detection, decide, and (optionally) trigger retraining.

    Parameters
    ----------
    threshold : drift share above which to retrain (default: env/0.5).
    force_drift : feed the drift step a synthetic *drifted* current set (demo).
    dry_run : decide only — never invoke the retrain trigger.
    drift_fn : injectable drift function returning a summary dict (or None).
               Defaults to running Evidently on reference/current data.
    retrain_fn : injectable retrain trigger returning a return code. Defaults
                 to :func:`trigger_retrain_subprocess`.

    Returns a result dict: ``drift_share`` / ``decision`` / ``retrained`` /
    ``returncode`` / ``reason``.
    """
    threshold = default_threshold() if threshold is None else threshold
    drift_fn = drift_fn or _default_drift_fn
    retrain_fn = retrain_fn or trigger_retrain_subprocess

    summary = drift_fn(force_drift=force_drift)

    result = {
        "threshold": threshold,
        "drift_share": (summary or {}).get("drift_share"),
        "source": (summary or {}).get("source"),
        "decision": False,
        "retrained": False,
        "returncode": None,
        "reason": None,
    }

    if summary is None:
        result["reason"] = "drift unavailable (evidently missing/skipped) — no retrain"
        return result

    decision = should_retrain(summary, threshold)
    result["decision"] = decision

    if not decision:
        result["reason"] = (
            f"drift_share {summary.get('drift_share')} <= threshold {threshold} — no-op"
        )
        return result

    result["reason"] = (
        f"drift_share {summary.get('drift_share')} > threshold {threshold} — retrain"
    )
    if dry_run:
        result["reason"] += " (dry-run: skipped)"
        return result

    rc = retrain_fn()
    result["retrained"] = rc == 0
    result["returncode"] = rc
    return result


def _default_drift_fn(force_drift: bool = False) -> Optional[dict]:
    """Default drift step: run Evidently on reference vs current data.

    Returns the drift summary dict, or ``None`` when evidently is unavailable
    so the caller treats it as "no decision" rather than crashing.
    """
    try:
        import drift_report as dr
    except Exception as exc:  # pragma: no cover - module import guard
        print(f"  [auto-retrain] drift module import failed ({exc}); skipping.")
        return None

    if not dr.evidently_available():
        print("  [auto-retrain] evidently unavailable; skipping drift check.")
        return None

    ref, cur, source = dr.load_reference_current(drift=force_drift)
    return dr.compute_drift(ref, cur, source=source, write_reports=True)


# ──────────────────────────────────────────
# CLI
# ──────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drift-gated automated model update hook"
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help=f"Drift share to trigger retrain (default: env DRIFT_THRESHOLD or {default_threshold()}).",
    )
    parser.add_argument(
        "--force-drift", action="store_true",
        help="Use a synthetic *drifted* current set (demo: forces a retrain decision).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Decide only — never invoke the training entrypoint.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("LoL Draft Predictor — auto-retrain hook (Phase 4)")
    print("=" * 60)

    result = decide_and_retrain(
        threshold=args.threshold,
        force_drift=args.force_drift,
        dry_run=args.dry_run,
    )

    print(f"Drift share : {result['drift_share']}  (source: {result['source']})")
    print(f"Threshold   : {result['threshold']}")
    print(f"Decision    : {'RETRAIN' if result['decision'] else 'NO-OP'}")
    print(f"Reason      : {result['reason']}")
    if result["retrained"]:
        print("Retrain     : completed")
    elif result["decision"] and not args.dry_run:
        print(f"Retrain     : FAILED (rc={result['returncode']})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
