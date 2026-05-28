"""Phase 4 — Evidently data-drift detection tests.

Run WITHOUT Docker, a DB, or the 747 MB dump: the drift function is exercised
on small SYNTHETIC frames. The heavy ``evidently`` import is guarded — if it is
not installed in this environment the Evidently-dependent tests are SKIPPED
(never faked), while the pure helpers (synthetic data, summary parsing,
no-DB fallback) still run so the module stays covered.
"""

import time

import pytest

import drift_report as dr


# ──────────────────────────────────────────
# Pure helpers (no evidently needed)
# ──────────────────────────────────────────

def test_make_synthetic_frames_shapes_and_columns():
    ref, cur = dr.make_synthetic_frames(n=120, drift=False, seed=1)
    assert len(ref) == 120 and len(cur) == 120
    assert list(ref.columns) == dr.DRIFT_FEATURES
    assert list(cur.columns) == dr.DRIFT_FEATURES


def test_drift_synthetic_frames_shift_distribution():
    """The drifted current frame must have a clearly shifted mean."""
    ref, cur = dr.make_synthetic_frames(n=400, drift=True, seed=2)
    # gold_diff_at_10 reference is ~0-centered; drifted current is shifted +4000.
    assert cur["gold_diff_at_10"].mean() - ref["gold_diff_at_10"].mean() > 2000


def test_load_reference_current_falls_back_to_synthetic(monkeypatch):
    """With no DB configured, loading returns synthetic frames (source tag)."""
    monkeypatch.delenv("DRIFT_USE_DB", raising=False)
    ref, cur, source = dr.load_reference_current(drift=False)
    assert source == "synthetic"
    assert len(ref) > 0 and len(cur) > 0


def test_load_reference_current_degrades_fast_when_db_down(monkeypatch):
    """With DRIFT_USE_DB=1 but the DB unreachable, the load must degrade to
    synthetic data *quickly* (seconds) and never hang or raise.

    The TCP reachability pre-check is mocked to report 'unreachable', proving
    the fast-fail path without depending on real network timing.
    """
    monkeypatch.setenv("DRIFT_USE_DB", "1")
    monkeypatch.setattr(dr, "_db_reachable", lambda *a, **k: False)

    t0 = time.time()
    ref, cur, source = dr.load_reference_current(drift=False)
    elapsed = time.time() - t0

    assert source == "synthetic"
    assert len(ref) > 0 and len(cur) > 0
    assert elapsed < 5, f"degrade took {elapsed:.2f}s, expected fast fail"


def test_db_reachable_false_for_unreachable_host(monkeypatch):
    """The TCP pre-check returns False (within its short timeout) for an
    unroutable host:port — i.e. it never blocks the way psycopg2 would."""
    monkeypatch.setenv("POSTGRES_HOST", "10.255.255.1")
    monkeypatch.setenv("POSTGRES_PORT", "5999")

    t0 = time.time()
    reachable = dr._db_reachable(timeout=2)
    elapsed = time.time() - t0

    assert reachable is False
    assert elapsed < 5, f"reachability probe took {elapsed:.2f}s, expected fast"


def test_compute_drift_requires_evidently(monkeypatch):
    """When evidently is unavailable, compute_drift raises a clear error."""
    monkeypatch.setattr(dr, "evidently_available", lambda: False)
    ref, cur = dr.make_synthetic_frames(n=50)
    with pytest.raises(RuntimeError):
        dr.compute_drift(ref, cur, write_reports=False)


# ──────────────────────────────────────────
# Evidently-backed tests (skipped if the package is absent)
# ──────────────────────────────────────────

requires_evidently = pytest.mark.skipif(
    not dr.evidently_available(),
    reason="evidently not installed in this environment",
)


@requires_evidently
def test_compute_drift_detects_drift_on_synthetic(tmp_path):
    ref, cur = dr.make_synthetic_frames(n=400, drift=True, seed=3)
    summary = dr.compute_drift(ref, cur, out_dir=tmp_path, write_reports=True)

    assert summary["drifted"] is True
    assert summary["drift_share"] > 0.0
    assert summary["n_drifted"] >= 1
    # JSON summary is always written; HTML when rendering succeeds.
    assert summary["json_path"] is not None
    assert (tmp_path / "drift_summary.json").exists()


@requires_evidently
def test_compute_drift_no_drift_on_identical_distribution(tmp_path):
    ref, cur = dr.make_synthetic_frames(n=400, drift=False, seed=4)
    summary = dr.compute_drift(ref, cur, out_dir=tmp_path, write_reports=False)
    # Same distribution -> low/zero drift share (well below the 0.5 threshold).
    assert summary["drift_share"] <= 0.5
