"""
Model loading and prediction utilities — Docker version.

Loads trained ML models from the shared /app/models volume.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import joblib


MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))


# =============================================================================
# PRODUCTION MODEL LOADING
# =============================================================================

@st.cache_resource
def load_production_model(vector_type: str) -> Optional[Dict[str, Any]]:
    """
    Load a production model by vector type.

    Args:
        vector_type: One of 'draft', 'at5', 'at10', 'at15', 'at20'
    """
    from config import VECTOR_TYPES

    vt = VECTOR_TYPES.get(vector_type)
    if vt is None:
        st.error(f"Type de vecteur inconnu : {vector_type}")
        return None

    filepath = MODELS_DIR / vt["model_file"]
    if not filepath.exists():
        st.warning(f"Modele introuvable : {filepath}")
        return None

    try:
        data = joblib.load(filepath)
        if "features" not in data and "feature_columns" in data:
            data["features"] = data["feature_columns"]
        elif "feature_columns" not in data and "features" in data:
            data["feature_columns"] = data["features"]
        if "metadata" in data:
            meta = data["metadata"]
            if "test_accuracy" not in data and "accuracy" in meta:
                data["test_accuracy"] = meta["accuracy"]
            if "val_accuracy" not in data and "val_accuracy" in meta:
                data["val_accuracy"] = meta["val_accuracy"]
        return data
    except Exception as e:
        st.error(f"Erreur chargement modele : {e}")
        return None


def get_tree_feature_importance(model, features: List[str]) -> pd.DataFrame:
    """Get feature importance from tree-based models."""
    if model is None:
        return pd.DataFrame(columns=["feature", "importance"])

    try:
        importances = model.feature_importances_
    except AttributeError:
        if hasattr(model, "coef_"):
            importances = np.abs(model.coef_[0])
        else:
            return pd.DataFrame(columns=["feature", "importance"])

    return (
        pd.DataFrame({"feature": features[: len(importances)], "importance": importances})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def safe_transform(scaler, X):
    """Apply scaler.transform if fitted, otherwise return X as-is."""
    if scaler is not None and hasattr(scaler, "mean_"):
        return scaler.transform(X)
    return X.values if hasattr(X, "values") else X


# =============================================================================
# TIME-BASED MODEL LOADING
# =============================================================================

@st.cache_resource
def load_time_based_model(minute: int) -> Tuple[Any, Any, List[str], Dict]:
    """Load a time-based prediction model."""
    filepath = MODELS_DIR / f"time_based_{minute}min_model.pkl"
    if not filepath.exists():
        # Try production model format
        prod = load_production_model(f"at{minute}")
        if prod:
            return prod.get("model"), prod.get("scaler"), prod.get("feature_columns", []), prod.get("metadata", {})
        st.warning(f"Model for @{minute}min not found at {filepath}")
        return None, None, [], {}

    try:
        data = joblib.load(filepath)
        return data["model"], data["scaler"], data.get("feature_columns", []), data.get("metadata", {})
    except Exception as e:
        st.error(f"Error loading model: {e}")
        return None, None, [], {}


def get_available_minutes() -> List[int]:
    """Get list of minutes for which trained models are available."""
    available = []
    for minute in [5, 10, 15, 20, 25]:
        filepath = MODELS_DIR / f"time_based_{minute}min_model.pkl"
        prod_filepath = MODELS_DIR / f"model_at{minute}.pkl"
        if filepath.exists() or prod_filepath.exists():
            available.append(minute)
    return available


def get_available_models_info() -> Dict[str, Any]:
    """Get information about all available models."""
    from config import MODEL_BENCHMARKS

    info = {}
    for key, bench in MODEL_BENCHMARKS.items():
        model_file = f"model_{key}.pkl"
        filepath = MODELS_DIR / model_file
        info[key] = {
            "available": filepath.exists(),
            "accuracy": bench["accuracy"],
            "auc_roc": bench["auc_roc"],
            "model_type": bench["model_type"],
            "file": str(filepath),
        }
    return info
