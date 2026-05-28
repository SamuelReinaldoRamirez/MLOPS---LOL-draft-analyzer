"""
Phase 2 — DVC pipeline structure tests.

Verifies the layout the rest of the project relies on:
- `dvc.yaml` parses, defines exactly the expected stages,
- each stage declares the dump as a dep, references `params.yaml`,
- `params.yaml` exposes the keys those stages name,
- `train_all_models._load_params()` reads the file and `_apply_params()`
  overlays it onto the in-process hyper-param dicts.

These tests are pure-Python: no Docker, no DVC binary, no DB.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DVC_YAML = REPO_ROOT / "dvc.yaml"
PARAMS_YAML = REPO_ROOT / "params.yaml"

EXPECTED_STAGES = {"train_at5", "train_at10", "train_at15", "train_at20"}


# Module under test lives in training/scripts; ensure it is importable like in
# the existing training/tests modules.
TRAINING_SCRIPTS = REPO_ROOT / "training" / "scripts"
if str(TRAINING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TRAINING_SCRIPTS))


def _load_yaml(path: Path) -> dict:
    pytest.importorskip("yaml")
    import yaml  # type: ignore

    with path.open("r") as f:
        return yaml.safe_load(f)


def test_dvc_yaml_parses_and_has_expected_stages():
    """`dvc.yaml` must parse and define exactly the 4 timeline stages."""
    data = _load_yaml(DVC_YAML)
    assert isinstance(data, dict), "dvc.yaml must be a mapping"
    assert "stages" in data, "missing top-level `stages:` block"
    stages = set(data["stages"].keys())
    assert stages == EXPECTED_STAGES, (
        f"dvc.yaml stages = {stages}, expected {EXPECTED_STAGES}"
    )


def test_each_stage_tracks_dump_and_params_and_outputs():
    """Every stage depends on the dump, reads params, and writes a .pkl + metrics."""
    data = _load_yaml(DVC_YAML)
    for name, stage in data["stages"].items():
        deps = stage.get("deps") or []
        outs = stage.get("outs") or []
        metrics = stage.get("metrics") or []
        params = stage.get("params") or []

        assert "database/lol_draft.dump" in deps, f"{name}: dump not in deps"
        assert any("train_all_models.py" in d for d in deps), f"{name}: training script not in deps"
        assert any(p == "train.xgb" or p.startswith("train.xgb") for p in params), \
            f"{name}: no train.xgb param"
        assert any(p == "train.lgb" or p.startswith("train.lgb") for p in params), \
            f"{name}: no train.lgb param"

        # One .pkl per stage, naming matches the stage's minute.
        minute = name.removeprefix("train_at")
        assert outs == [f"models/model_at{minute}.pkl"], f"{name}: outs={outs}"

        # Metrics is a list of one mapping ({path: {cache: false}})
        assert len(metrics) == 1, f"{name}: must declare exactly one metrics file"
        metric_entry = metrics[0]
        if isinstance(metric_entry, dict):
            metric_path = next(iter(metric_entry.keys()))
        else:
            metric_path = metric_entry
        assert metric_path == f"models/metrics_at{minute}.json", \
            f"{name}: metrics path={metric_path}"


def test_params_yaml_exposes_train_section():
    """`params.yaml` must contain the keys `dvc.yaml` stages reference."""
    data = _load_yaml(PARAMS_YAML)
    assert isinstance(data, dict)
    train = data.get("train")
    assert isinstance(train, dict), "params.yaml missing `train:` section"
    for key in ("seed", "test_size", "val_size", "xgb", "lgb", "minutes"):
        assert key in train, f"params.yaml: missing `train.{key}`"
    # Hyper-param dicts have the same shape as the in-code defaults.
    for hp in ("n_estimators", "max_depth", "learning_rate"):
        assert hp in train["xgb"], f"params.yaml: missing `train.xgb.{hp}`"
        assert hp in train["lgb"], f"params.yaml: missing `train.lgb.{hp}`"


def test_apply_params_overrides_in_process_dicts(monkeypatch):
    """`_apply_params()` must mutate the module's XGB_PARAMS / LGB_PARAMS in place."""
    import train_all_models as tam  # type: ignore

    # Snapshot baseline so we restore at the end.
    baseline_xgb = dict(tam.XGB_PARAMS)
    baseline_lgb = dict(tam.LGB_PARAMS)
    try:
        sentinel = 999
        tam._apply_params({
            "train": {
                "xgb": {"n_estimators": sentinel},
                "lgb": {"max_depth": sentinel + 1},
            }
        })
        assert tam.XGB_PARAMS["n_estimators"] == sentinel
        assert tam.LGB_PARAMS["max_depth"] == sentinel + 1
        # Other values remain (overlay, not replacement).
        assert tam.XGB_PARAMS["random_state"] == baseline_xgb["random_state"]
    finally:
        tam.XGB_PARAMS.clear()
        tam.XGB_PARAMS.update(baseline_xgb)
        tam.LGB_PARAMS.clear()
        tam.LGB_PARAMS.update(baseline_lgb)


def test_apply_params_is_noop_on_empty_input():
    """Empty / None / unrelated params do not mutate the dicts."""
    import train_all_models as tam  # type: ignore

    baseline_xgb = dict(tam.XGB_PARAMS)
    baseline_lgb = dict(tam.LGB_PARAMS)
    tam._apply_params(None)
    tam._apply_params({})
    tam._apply_params({"unrelated": {"foo": 1}})
    assert tam.XGB_PARAMS == baseline_xgb
    assert tam.LGB_PARAMS == baseline_lgb


def test_load_params_returns_none_when_missing(tmp_path, monkeypatch):
    """`_load_params(nonexistent)` returns None instead of crashing."""
    import train_all_models as tam  # type: ignore

    # Use a tmp_path that exists but does not contain params.yaml; the helper
    # then falls back to the repo-root path which DOES exist, so to truly test
    # the missing case we point at an invented file.
    fake = tmp_path / "definitely-not-here.yaml"
    # We also have to neutralize the fallback to repo-root — patch __file__.
    monkeypatch.setattr(tam, "__file__", str(tmp_path / "stub.py"))
    assert tam._load_params(fake) is None


def test_emit_metrics_json_writes_expected_shape(tmp_path, monkeypatch):
    """The metrics file is JSON with the keys DVC `metrics show` will display."""
    import train_all_models as tam  # type: ignore

    monkeypatch.setattr(tam, "MODELS_DIR", tmp_path)
    tam._emit_metrics_json(10, test_acc=0.8, test_auc=0.9, val_acc=0.78,
                           model_type="XGBoost")
    out = tmp_path / "metrics_at10.json"
    assert out.exists(), "metrics file was not created"
    payload = json.loads(out.read_text())
    assert payload == {
        "minute": 10,
        "model_type": "XGBoost",
        "accuracy": 0.8,
        "roc_auc": 0.9,
        "val_accuracy": 0.78,
    }
