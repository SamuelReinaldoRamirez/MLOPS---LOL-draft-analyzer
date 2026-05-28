"""
LoL Draft Predictor — Training pipeline (Docker version)

Trains all 5 models (draft, @5, @10, @15, @20) from PostgreSQL data
and saves them as .pkl files in /app/models/.

Usage:
    python scripts/train_all_models.py
    python scripts/train_all_models.py --model at10   # Train single model
"""

import os
import sys
import json
import argparse
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

from db_utils import read_sql, fetchone, get_connection

# Phase 2: experiment tracking + model versioning via MLflow.
# The wrapper degrades to a NO-OP when MLFLOW_TRACKING_URI is unset/unreachable,
# so importing this module and running training never require an MLflow server.
try:
    from mlflow_tracking import get_tracker
except Exception:  # pragma: no cover - keep training importable no matter what
    def get_tracker(experiment=None):
        from contextlib import nullcontext

        class _Noop:
            enabled = False

            def run(self, *a, **k):
                return nullcontext()

            def log_params(self, *a, **k):
                pass

            def log_metrics(self, *a, **k):
                pass

            def set_tags(self, *a, **k):
                pass

            def log_artifact(self, *a, **k):
                pass

            def log_model(self, *a, **k):
                pass

        return _Noop()

warnings.filterwarnings("ignore")

MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))

# XGBoost hyper-parameters (kept in one place so they can be logged to MLflow).
# These values are the in-code defaults; they are overridden at runtime by
# `params.yaml` when present (Phase 2 — DVC pipeline reproducibility).
XGB_PARAMS = dict(
    n_estimators=200, max_depth=6, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    random_state=42, n_jobs=-1, eval_metric="logloss",
)
LGB_PARAMS = dict(
    n_estimators=200, max_depth=6, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    random_state=42, n_jobs=-1, verbose=-1,
)


# ──────────────────────────────────────────
# Phase 2 — DVC pipeline: params.yaml + metrics JSON
# ──────────────────────────────────────────

def _load_params(path: str | os.PathLike | None = None) -> dict | None:
    """Read DVC's ``params.yaml`` if available, else return ``None``.

    Lazy import of PyYAML so the training script stays importable in
    environments where PyYAML is not installed (DVC pulls it transitively in
    the training image; otherwise the load is just skipped).
    """
    candidate = Path(path) if path else Path("/app/params.yaml")
    if not candidate.exists():
        candidate = Path(__file__).resolve().parents[2] / "params.yaml"
    if not candidate.exists():
        return None
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        with candidate.open("r") as f:
            return yaml.safe_load(f) or None
    except Exception:
        return None


def _apply_params(params: dict | None) -> None:
    """Overlay ``params.yaml`` values onto the in-process hyper-param dicts.

    Mutates ``XGB_PARAMS`` and ``LGB_PARAMS`` in place so the existing
    training code path is unchanged. NO-OP when ``params`` is falsy or
    missing the ``train`` section.
    """
    if not params:
        return
    train_section = params.get("train") or {}
    xgb_overrides = train_section.get("xgb") or {}
    lgb_overrides = train_section.get("lgb") or {}
    XGB_PARAMS.update({k: v for k, v in xgb_overrides.items() if v is not None})
    LGB_PARAMS.update({k: v for k, v in lgb_overrides.items() if v is not None})


def _emit_metrics_json(minute: int, *, test_acc: float, test_auc: float,
                       val_acc: float, model_type: str) -> None:
    """Write a small DVC-friendly metrics file alongside the .pkl bundle.

    Path: ``MODELS_DIR / metrics_at{minute}.json`` (declared as a `metrics:`
    output in ``dvc.yaml``; visible via `dvc metrics show`). Best-effort: any
    I/O error is swallowed so a host-side filesystem hiccup never fails
    training.
    """
    try:
        path = MODELS_DIR / f"metrics_at{minute}.json"
        payload = {
            "minute": minute,
            "model_type": model_type,
            "accuracy": float(test_acc),
            "roc_auc": float(test_auc),
            "val_accuracy": float(val_acc),
        }
        with path.open("w") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def ensure_models_dir() -> None:
    """Create the models output directory if it does not exist.

    Kept out of module scope so the module can be imported (e.g. for unit
    tests of feature engineering) without touching the filesystem.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────
# Data loading from PostgreSQL
# ──────────────────────────────────────────

def load_draft_data() -> pd.DataFrame:
    """Load draft data: champion picks + team stats for each match."""
    print("Loading draft data from PostgreSQL...")

    query = """
        SELECT
            m.match_id,
            m.team_100_win,
            m.game_duration,
            m.game_version,
            -- Player picks
            p.team_id,
            p.position,
            p.champion_id,
            p.champion_name,
            p.kills,
            p.deaths,
            p.assists,
            p.gold_earned,
            p.total_minions_killed,
            p.vision_score,
            p.kda
        FROM matches m
        INNER JOIN player_stats p ON m.match_id = p.match_id
        WHERE m.game_duration >= 600
        ORDER BY m.match_id, p.team_id, p.position
    """
    df = read_sql(query)
    print(f"  Loaded {len(df)} player rows for {df['match_id'].nunique()} matches")
    return df


def load_timeline_data(minute: int) -> pd.DataFrame:
    """Load timeline (gold) data at a given minute."""
    print(f"Loading timeline data at @{minute}min...")

    query = f"""
        SELECT
            m.match_id,
            m.team_100_win,
            mt.gold_diff,
            mt.team_100_gold,
            mt.team_200_gold,
            mt.team_100_top_gold,
            mt.team_100_jungle_gold,
            mt.team_100_mid_gold,
            mt.team_100_adc_gold,
            mt.team_100_support_gold,
            mt.team_200_top_gold,
            mt.team_200_jungle_gold,
            mt.team_200_mid_gold,
            mt.team_200_adc_gold,
            mt.team_200_support_gold,
            -- Team stats (firsts)
            t100.first_blood,
            t100.first_tower,
            t100.first_dragon,
            t100.first_rift_herald as first_herald
        FROM matches m
        INNER JOIN match_timeline mt
            ON m.match_id = mt.match_id AND mt.minute = {minute}
        LEFT JOIN team_stats t100
            ON m.match_id = t100.match_id AND t100.team_id = 100
        WHERE m.game_duration >= 600
    """
    df = read_sql(query)
    print(f"  Loaded {len(df)} matches with @{minute}min data")
    return df


# ──────────────────────────────────────────
# Feature engineering
# ──────────────────────────────────────────

def build_timeline_features(df: pd.DataFrame, minute: int) -> tuple:
    """Build features for a timeline model at a given minute."""
    features = []
    targets = []

    for _, row in df.iterrows():
        feat = {}
        feat[f"gold_diff_at_{minute}"] = row.get("gold_diff", 0) or 0
        feat["first_blood_team_100"] = 1 if row.get("first_blood") else 0
        feat["first_tower_team_100"] = 1 if row.get("first_tower") else 0
        feat["first_dragon_team_100"] = 1 if row.get("first_dragon") else 0
        feat["first_herald_team_100"] = 1 if row.get("first_herald") else 0

        # Per-position gold diffs
        positions = ["top", "jungle", "mid", "adc", "support"]
        for pos in positions:
            g100 = row.get(f"team_100_{pos}_gold", 0) or 0
            g200 = row.get(f"team_200_{pos}_gold", 0) or 0
            feat[f"{pos}_gold_diff_at_{minute}"] = g100 - g200

        # Derived: gold advantage percentage
        total_gold = (row.get("team_100_gold", 0) or 0) + (row.get("team_200_gold", 0) or 0)
        gold_diff = row.get("gold_diff", 0) or 0
        feat[f"gold_advantage_pct_at_{minute}"] = gold_diff / total_gold if total_gold > 0 else 0

        # Derived: early lead score
        gold_norm = gold_diff / 5000.0
        fb = feat["first_blood_team_100"]
        ft = feat["first_tower_team_100"]
        fd = feat["first_dragon_team_100"]
        fh = feat["first_herald_team_100"]
        feat[f"early_lead_score_at_{minute}"] = (
            gold_norm * 0.6
            + (fb * 2 - 1) * 0.15
            + (ft * 2 - 1) * 0.1
            + (fd * 2 - 1) * 0.1
            + (fh * 2 - 1) * 0.05
        )

        features.append(feat)
        targets.append(1 if row["team_100_win"] else 0)

    X = pd.DataFrame(features).fillna(0)
    y = np.array(targets)
    return X, y


# ──────────────────────────────────────────
# Model training
# ──────────────────────────────────────────

def train_best_model(X_train, y_train, X_val, y_val):
    """Train multiple models and return the best one."""
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)

    models = {}
    hyperparams = {}

    if HAS_XGB:
        models["XGBoost"] = xgb.XGBClassifier(**XGB_PARAMS)
        hyperparams["XGBoost"] = XGB_PARAMS

    if HAS_LGB:
        models["LightGBM"] = lgb.LGBMClassifier(**LGB_PARAMS)
        hyperparams["LightGBM"] = LGB_PARAMS

    if not models:
        from sklearn.ensemble import GradientBoostingClassifier
        gb_params = dict(
            n_estimators=150, max_depth=6, learning_rate=0.1, random_state=42
        )
        models["GradientBoosting"] = GradientBoostingClassifier(**gb_params)
        hyperparams["GradientBoosting"] = gb_params

    best_score = 0
    best_name = None
    best_model = None

    for name, model in models.items():
        model.fit(X_train_scaled, y_train)
        val_score = model.score(X_val_scaled, y_val)
        y_val_proba = model.predict_proba(X_val_scaled)[:, 1]
        auc = roc_auc_score(y_val, y_val_proba)
        print(f"  {name}: accuracy={val_score:.4f}, AUC={auc:.4f}")

        if val_score > best_score:
            best_score = val_score
            best_name = name
            best_model = model

    print(f"  → Best: {best_name} (accuracy={best_score:.4f})")
    return best_model, scaler, best_name, best_score, hyperparams.get(best_name, {})


def train_timeline_model(minute: int, tracker=None):
    """Train and save a timeline model for a given minute.

    When ``tracker`` (an :class:`mlflow_tracking.MLflowTracker`) is provided and
    MLflow is configured, the run logs params, metrics and the model artifact,
    and registers the model in the MLflow Model Registry. The tracker is a
    NO-OP when MLflow is not configured, so training is unchanged in that case.
    """
    print(f"\n{'='*60}")
    print(f"Training model @{minute}min")
    print(f"{'='*60}")

    if tracker is None:
        tracker = get_tracker()

    df = load_timeline_data(minute)
    if len(df) < 100:
        print(f"  ⚠️ Not enough data ({len(df)} rows), skipping.")
        return

    X, y = build_timeline_features(df, minute)

    # Train/val/test split (temporal-ish: just random here)
    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_trainval, y_trainval, test_size=0.15, random_state=42, stratify=y_trainval
    )

    with tracker.run(
        run_name=f"model_at{minute}",
        tags={"minute": str(minute), "stage": "timeline", "phase": "2"},
    ):
        model, scaler, model_name, val_acc, hyperparams = train_best_model(
            X_train, y_train, X_val, y_val
        )

        # Test evaluation
        X_test_scaled = scaler.transform(X_test)
        y_pred = model.predict(X_test_scaled)
        y_proba = model.predict_proba(X_test_scaled)[:, 1]
        test_acc = accuracy_score(y_test, y_pred)
        test_auc = roc_auc_score(y_test, y_proba)

        print(f"\n  Test: accuracy={test_acc:.4f}, AUC={test_auc:.4f}")
        print(classification_report(y_test, y_pred, target_names=["Red Win", "Blue Win"]))

        # Phase 2 — DVC: emit a tiny per-stage metrics JSON next to the .pkl so
        # `dvc metrics show` exposes accuracy/AUC across runs.
        _emit_metrics_json(
            minute, test_acc=test_acc, test_auc=test_auc,
            val_acc=val_acc, model_type=model_name,
        )

        # ── MLflow logging (NO-OP if disabled) ──────────────────────
        tracker.log_params({
            "model_type": model_name,
            "minute": minute,
            "n_features": len(X.columns),
            "n_train_samples": len(X_train),
            "n_test_samples": len(X_test),
            **{f"hp_{k}": v for k, v in hyperparams.items()},
        })
        tracker.log_metrics({
            "accuracy": float(test_acc),
            "roc_auc": float(test_auc),
            "val_accuracy": float(val_acc),
        })
        # Model versioning: register a new version in the MLflow Model Registry.
        tracker.log_model(
            model,
            artifact_path="model",
            registered_model_name=f"lol_draft_at{minute}",
        )

        # Save model (.pkl + metadata — unchanged behaviour)
        ensure_models_dir()
        output_path = MODELS_DIR / f"model_at{minute}.pkl"
        joblib.dump({
            "model": model,
            "scaler": scaler,
            "feature_columns": list(X.columns),
            "features": list(X.columns),
            "metadata": {
                "model_type": model_name,
                "accuracy": float(test_acc),
                "auc_roc": float(test_auc),
                "val_accuracy": float(val_acc),
                "n_train_samples": len(X_train),
                "n_test_samples": len(X_test),
                "n_features": len(X.columns),
                "minute": minute,
                "trained_at": datetime.now().isoformat(),
            },
        }, output_path)
        print(f"  ✅ Saved to {output_path}")
        # Also log the serialized bundle as a run artifact for traceability.
        tracker.log_artifact(str(output_path), artifact_path="pkl_bundle")


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Train LoL Draft Predictor models")
    parser.add_argument("--model", type=str, default=None,
                       help="Train single model: draft, at5, at10, at15, at20")
    args = parser.parse_args()

    print("=" * 60)
    print("LoL Draft Predictor — Training Pipeline")
    print(f"Models dir: {MODELS_DIR}")
    print("=" * 60)

    # Phase 2 — DVC: overlay hyper-params from params.yaml when present.
    params = _load_params()
    if params:
        _apply_params(params)
        print(f"DVC params.yaml loaded — XGB n_estimators={XGB_PARAMS['n_estimators']}, "
              f"max_depth={XGB_PARAMS['max_depth']}, lr={XGB_PARAMS['learning_rate']}")
    else:
        print("DVC params.yaml not found — using in-code defaults")

    ensure_models_dir()

    # Phase 2: experiment tracking. NO-OP when MLFLOW_TRACKING_URI is unset.
    tracker = get_tracker()
    if tracker.enabled:
        print(f"MLflow tracking: ON ({os.getenv('MLFLOW_TRACKING_URI')})")
    else:
        print("MLflow tracking: OFF (MLFLOW_TRACKING_URI unset/unreachable) — no-op")

    # Check DB connection
    try:
        row = fetchone("SELECT COUNT(*) FROM matches")
        print(f"Database connected: {row[0]} matches available")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)

    minutes_to_train = [5, 10, 15, 20]

    if args.model:
        if args.model.startswith("at"):
            minute = int(args.model[2:])
            train_timeline_model(minute, tracker=tracker)
        else:
            print(f"Unknown model: {args.model}")
    else:
        # Train all timeline models
        for minute in minutes_to_train:
            train_timeline_model(minute, tracker=tracker)

    print("\n" + "=" * 60)
    print("Training complete!")
    print(f"Models saved to: {MODELS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
