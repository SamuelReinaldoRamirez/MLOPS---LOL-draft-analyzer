"""
LoL Draft Predictor — Data-drift detection (Phase 4).

Builds an Evidently data-drift report comparing a *reference* dataset (the data
the model was trained on) against a *current* dataset (recent / production-like
data), and writes an HTML + JSON report under ``monitoring/drift/reports/``.

Design goals (mirrors the Phase-2 MLflow NO-OP contract)
--------------------------------------------------------
* **Runnable WITHOUT the 747 MB dump.** When no DB is configured (or the load
  fails), :func:`load_reference_current` falls back to two small *synthetic*
  frames, so the whole pipeline — and its unit test — runs anywhere.
* **Fail-safe heavy import.** ``evidently`` is imported lazily inside the
  functions that need it. The module always imports cleanly so the core test
  suite never breaks if ``evidently`` is absent.
* **Decision-friendly output.** :func:`compute_drift` returns a small dict
  (``drift_share`` / ``n_drifted`` / ``drifted`` / ``report``) that the
  auto-retrain hook consumes to decide whether to retrain.

Usage
-----
    python scripts/drift_report.py                 # synthetic if no DB
    python scripts/drift_report.py --drift          # force a drifted current set
    python scripts/drift_report.py --out-dir /tmp/r # custom output dir
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

# Numeric feature columns used for the drift comparison. These mirror the
# @10min timeline schema the served models use, so a real run can pull the same
# columns straight out of PostgreSQL.
DRIFT_FEATURES = [
    "gold_diff_at_10",
    "top_gold_diff_at_10",
    "jungle_gold_diff_at_10",
    "mid_gold_diff_at_10",
    "adc_gold_diff_at_10",
    "support_gold_diff_at_10",
]

DEFAULT_OUT_DIR = Path(
    os.getenv("DRIFT_OUT_DIR", "monitoring/drift/reports")
)


# ──────────────────────────────────────────
# Data loading (synthetic fallback)
# ──────────────────────────────────────────

def make_synthetic_frames(
    n: int = 400, drift: bool = False, seed: int = 0
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Build (reference, current) synthetic frames for the drift comparison.

    With ``drift=False`` both frames are drawn from the same distribution (no
    drift expected). With ``drift=True`` the current frame is shifted/scaled so
    Evidently flags drift — this is what the auto-retrain decision test relies
    on.
    """
    rng = np.random.default_rng(seed)

    def _frame(shift: float, scale: float) -> pd.DataFrame:
        data = {}
        for i, col in enumerate(DRIFT_FEATURES):
            base = rng.normal(0.0 + shift, 1000.0 * scale, n)
            # Per-position diffs are smaller in magnitude than the team total.
            data[col] = base if i == 0 else base * 0.3
        return pd.DataFrame(data)

    reference = _frame(shift=0.0, scale=1.0)
    if drift:
        # Large mean shift + variance change -> clearly drifted distribution.
        current = _frame(shift=4000.0, scale=2.0)
    else:
        current = _frame(shift=0.0, scale=1.0)
    return reference, current


# Seconds to wait for a TCP handshake to the DB before giving up and degrading
# to synthetic data. Kept small so a down/unreachable DB degrades in seconds
# rather than blocking on psycopg2's (unbounded) default connect.
DB_REACHABLE_TIMEOUT = float(os.getenv("DRIFT_DB_REACHABLE_TIMEOUT", "3"))


def _db_reachable(timeout: float = DB_REACHABLE_TIMEOUT) -> bool:
    """Quick TCP pre-check: is ``POSTGRES_HOST:POSTGRES_PORT`` accepting?

    Opens a short-timeout socket so an unreachable / refused / firewalled DB
    fails in ``timeout`` seconds instead of hanging on psycopg2's default
    (effectively unbounded) connect. Returns ``True`` only when the TCP
    handshake succeeds; any failure (refused, timeout, DNS) returns ``False``.
    """
    host = os.getenv("POSTGRES_HOST", "postgres")
    try:
        port = int(os.getenv("POSTGRES_PORT", "5432"))
    except (TypeError, ValueError):
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def load_reference_current(
    drift: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Return (reference, current, source).

    Tries PostgreSQL when ``DRIFT_USE_DB=1`` is set, but guards the connect
    with a short TCP reachability pre-check (``DB_REACHABLE_TIMEOUT`` ~3s) so an
    unreachable / refused DB degrades to synthetic frames in *seconds* rather
    than blocking on psycopg2's default (effectively unbounded) connect. The DB
    DSN also carries a ``connect_timeout`` as a second layer of defence.

    ``source`` is ``"db"`` or ``"synthetic"`` for logging/report metadata. The
    DB path is best-effort: a real run needs the dump, but the function never
    raises — and never hangs — just because the DB is down or absent.
    """
    if os.getenv("DRIFT_USE_DB", "0") == "1":
        if not _db_reachable():
            print(
                "  [drift] DB unreachable within "
                f"{DB_REACHABLE_TIMEOUT:.0f}s; using synthetic data."
            )
        else:
            try:  # pragma: no cover - requires a live DB / the 747 MB dump
                ref, cur = _load_from_db()
                if ref is not None and cur is not None and len(ref) and len(cur):
                    return ref, cur, "db"
            except Exception as exc:  # pragma: no cover - DB optional
                print(f"  [drift] DB load failed ({exc}); using synthetic data.")

    ref, cur = make_synthetic_frames(drift=drift)
    return ref, cur, "synthetic"


def _load_from_db():  # pragma: no cover - requires live DB
    """Load reference (older matches) vs current (recent matches) @10 timelines.

    Temporal split on ``match_id`` ordering as a stand-in for collection time.
    Only used when ``DRIFT_USE_DB=1`` and the DB is reachable.
    """
    from db_utils import read_sql

    query = """
        SELECT
            mt.gold_diff                                   AS gold_diff_at_10,
            (mt.team_100_top_gold     - mt.team_200_top_gold)     AS top_gold_diff_at_10,
            (mt.team_100_jungle_gold  - mt.team_200_jungle_gold)  AS jungle_gold_diff_at_10,
            (mt.team_100_mid_gold     - mt.team_200_mid_gold)     AS mid_gold_diff_at_10,
            (mt.team_100_adc_gold     - mt.team_200_adc_gold)     AS adc_gold_diff_at_10,
            (mt.team_100_support_gold - mt.team_200_support_gold) AS support_gold_diff_at_10,
            mt.match_id
        FROM match_timeline mt
        WHERE mt.minute = 10
        ORDER BY mt.match_id
    """
    df = read_sql(query).drop(columns=["match_id"]).fillna(0)
    if len(df) < 200:
        return None, None
    split = int(len(df) * 0.7)
    return df.iloc[:split].copy(), df.iloc[split:].copy()


# ──────────────────────────────────────────
# Drift computation (Evidently)
# ──────────────────────────────────────────

def evidently_available() -> bool:
    """True when the ``evidently`` package can be imported in this env."""
    try:  # pragma: no cover - trivial probe
        import evidently  # noqa: F401

        return True
    except Exception:  # pragma: no cover
        return False


def compute_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    out_dir: Optional[Path] = None,
    source: str = "synthetic",
    write_reports: bool = True,
) -> dict:
    """Run an Evidently data-drift report and return a compact summary dict.

    Returns
    -------
    dict with keys:
        ``drift_share``  float share of drifted columns (0..1)
        ``n_drifted``    int  number of drifted columns
        ``n_columns``    int  number of compared columns
        ``drifted``      bool drift_share > 0 (any column drifted)
        ``source``       str  "db" | "synthetic"
        ``html_path`` / ``json_path``  written report paths (or None)

    Raises
    ------
    RuntimeError if ``evidently`` is not importable — callers that want a
    NO-OP should gate on :func:`evidently_available` first.
    """
    if not evidently_available():
        raise RuntimeError(
            "evidently is not installed; cannot compute drift. "
            "Install training/requirements.txt or gate on evidently_available()."
        )

    from evidently import Report
    from evidently.presets import DataDriftPreset

    report = Report(metrics=[DataDriftPreset()])
    snapshot = report.run(reference_data=reference, current_data=current)

    summary = _parse_drift_summary(snapshot)
    summary["source"] = source

    html_path = json_path = None
    if write_reports:
        out_dir = Path(out_dir or DEFAULT_OUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / "drift_report.html"
        json_path = out_dir / "drift_summary.json"
        try:
            snapshot.save_html(str(html_path))
        except Exception as exc:  # pragma: no cover - rendering optional
            print(f"  [drift] HTML render failed ({exc}); JSON still written.")
            html_path = None
        json_path.write_text(json.dumps(summary, indent=2, default=str))

    summary["html_path"] = str(html_path) if html_path else None
    summary["json_path"] = str(json_path) if json_path else None
    return summary


def _parse_drift_summary(snapshot) -> dict:
    """Extract drifted-column share/count from an Evidently snapshot dict.

    Works across the metric layout of Evidently 0.4–0.7: it reads the
    ``DriftedColumnsCount`` metric (``value.count`` / ``value.share``) and
    falls back to counting per-column ``ValueDrift`` p-values below 0.05.
    """
    try:
        data = snapshot.dict()
    except Exception:  # pragma: no cover - defensive
        data = {}

    metrics = data.get("metrics", []) if isinstance(data, dict) else []

    share = None
    n_drifted = None
    n_pvalue_cols = 0
    n_pvalue_drifted = 0

    for m in metrics:
        name = str(m.get("metric_name", ""))
        value = m.get("value", {})
        if name.startswith("DriftedColumnsCount") and isinstance(value, dict):
            n_drifted = value.get("count")
            share = value.get("share")
        elif name.startswith("ValueDrift"):
            n_pvalue_cols += 1
            # ValueDrift value is the K-S p-value; <0.05 => drifted.
            try:
                if float(value) < 0.05:
                    n_pvalue_drifted += 1
            except (TypeError, ValueError):
                pass

    if share is None or n_drifted is None:
        # Fall back to the per-column p-value tally.
        n_drifted = n_pvalue_drifted
        share = (n_pvalue_drifted / n_pvalue_cols) if n_pvalue_cols else 0.0

    n_columns = int(n_pvalue_cols) if n_pvalue_cols else int(n_drifted or 0)
    n_drifted = int(n_drifted or 0)
    share = float(share or 0.0)

    return {
        "drift_share": share,
        "n_drifted": n_drifted,
        "n_columns": n_columns,
        "drifted": share > 0.0,
    }


# ──────────────────────────────────────────
# CLI
# ──────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Build an Evidently drift report")
    parser.add_argument(
        "--drift", action="store_true",
        help="Force a drifted current set (synthetic) — useful for demos/tests.",
    )
    parser.add_argument(
        "--out-dir", type=str, default=None,
        help=f"Report output dir (default: {DEFAULT_OUT_DIR}).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("LoL Draft Predictor — Data-drift report (Phase 4)")
    print("=" * 60)

    if not evidently_available():
        print("evidently not installed — cannot build the report.")
        print("Install it via: pip install -r training/requirements.txt")
        return 2

    ref, cur, source = load_reference_current(drift=args.drift)
    print(f"Reference rows: {len(ref)}  Current rows: {len(cur)}  Source: {source}")

    summary = compute_drift(
        ref, cur, out_dir=args.out_dir, source=source, write_reports=True
    )
    print(
        f"Drift: share={summary['drift_share']:.2f} "
        f"({summary['n_drifted']}/{summary['n_columns']} columns)"
    )
    if summary.get("html_path"):
        print(f"HTML report : {summary['html_path']}")
    if summary.get("json_path"):
        print(f"JSON summary: {summary['json_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
