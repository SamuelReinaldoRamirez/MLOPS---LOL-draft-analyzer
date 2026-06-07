"""
Model loading and prediction utilities for Streamlit app.

This module provides functions to:
- Load trained ML models (production models, legacy time-based)
- Make predictions at different game minutes
- Get available models and their metadata
- Extract feature importance from tree-based models
"""
import os
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


# Default models directory (relative to project root)
def get_models_dir() -> Path:
    """Get the models directory path."""
    possible_paths = [
        Path(__file__).parent.parent.parent / 'models',
        Path('models'),
        Path(__file__).parent.parent / 'models',
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return possible_paths[0]


MODELS_DIR = get_models_dir()


# =============================================================================
# PRODUCTION MODEL LOADING (new pkl format)
# =============================================================================

@st.cache_resource
def load_production_model(vector_type: str) -> Dict[str, Any]:
    """
    Load a production model by vector type.

    Args:
        vector_type: One of 'draft', 'at5', 'at10', 'at15', 'at20'

    Returns:
        Dict with keys: model, scaler, model_name, val_accuracy,
        test_accuracy, features, feature_columns, synergy_data, external_data, metadata.
        Returns None if model not found.
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
        # Normalize: ensure 'features' key exists (may be 'feature_columns')
        if "features" not in data and "feature_columns" in data:
            data["features"] = data["feature_columns"]
        elif "feature_columns" not in data and "features" in data:
            data["feature_columns"] = data["features"]
        # Extract metadata fields to top level for backward compatibility
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
    """
    Get feature importance from tree-based models (XGBoost, LightGBM, RandomForest).

    Args:
        model: Trained tree-based model
        features: List of feature names

    Returns:
        DataFrame with columns: feature, importance (sorted descending)
    """
    if model is None:
        return pd.DataFrame(columns=["feature", "importance"])

    try:
        importances = model.feature_importances_
    except AttributeError:
        # Fallback for models without feature_importances_
        if hasattr(model, "coef_"):
            importances = np.abs(model.coef_[0])
        else:
            return pd.DataFrame(columns=["feature", "importance"])

    df = pd.DataFrame({
        "feature": features[:len(importances)],
        "importance": importances,
    }).sort_values("importance", ascending=False).reset_index(drop=True)

    return df


def safe_transform(scaler, X):
    """Apply scaler.transform if fitted, otherwise return X as-is.

    XGBoost/LightGBM don't require scaling, so models may have
    been saved with an unfitted StandardScaler placeholder.
    """
    if scaler is not None and hasattr(scaler, "mean_"):
        return scaler.transform(X)
    return X.values if hasattr(X, "values") else X


# =============================================================================
# TIME-BASED MODEL LOADING (legacy)
# =============================================================================

@st.cache_resource
def load_time_based_model(minute: int) -> Tuple[Any, Any, List[str], Dict]:
    """
    Load a time-based prediction model for a specific minute.

    Args:
        minute: Game minute (5, 10, 15, 20)

    Returns:
        Tuple of (model, scaler, feature_columns, metadata)
        Returns (None, None, [], {}) if model not found
    """
    filepath = MODELS_DIR / f'time_based_{minute}min_model.pkl'

    if not filepath.exists():
        st.warning(f"Model for @{minute}min not found at {filepath}")
        return None, None, [], {}

    try:
        data = joblib.load(filepath)
        return (
            data['model'],
            data['scaler'],
            data.get('feature_columns', []),
            data.get('metadata', {})
        )
    except Exception as e:
        st.error(f"Error loading model: {e}")
        return None, None, [], {}


@st.cache_resource
def load_early_game_model_from_file() -> Tuple[Any, Any, List[str], Dict]:
    """
    Load the early game @10min model (with CS data) from file.

    Returns:
        Tuple of (model, scaler, feature_columns, metadata)
    """
    filepath = MODELS_DIR / 'early_game_10min_model.pkl'

    if not filepath.exists():
        # Fall back to training a simple model
        return load_early_game_model()

    try:
        data = joblib.load(filepath)
        accuracy = data.get('metadata', {}).get('accuracy', 0.0)
        return (
            data['model'],
            data['scaler'],
            data.get('feature_columns', []),
            data.get('metadata', {})
        )
    except Exception as e:
        st.warning(f"Error loading early game model: {e}. Training new model...")
        return load_early_game_model()


def get_available_minutes() -> List[int]:
    """
    Get list of minutes for which trained models are available.

    Returns:
        List of integers (e.g., [5, 10, 15, 20])
    """
    available = []
    for minute in [5, 10, 15, 20, 25]:
        filepath = MODELS_DIR / f'time_based_{minute}min_model.pkl'
        if filepath.exists():
            available.append(minute)
    return available


def get_available_models_info() -> Dict[str, Any]:
    """
    Get information about all available models.

    Returns:
        Dict with model information:
        {
            'early_game_10min': {'available': True, 'accuracy': 0.72, ...},
            'time_based': {
                5: {'available': True, 'accuracy': 0.58, ...},
                10: {...},
                ...
            }
        }
    """
    info = {
        'early_game_10min': {'available': False},
        'time_based': {},
    }

    # Check early game model
    early_path = MODELS_DIR / 'early_game_10min_model.pkl'
    if early_path.exists():
        try:
            data = joblib.load(early_path)
            info['early_game_10min'] = {
                'available': True,
                'accuracy': data.get('metadata', {}).get('accuracy'),
                'trained_at': data.get('metadata', {}).get('trained_at'),
                'model_type': data.get('metadata', {}).get('model_type'),
            }
        except Exception:
            pass

    # Check time-based models
    for minute in [5, 10, 15, 20, 25]:
        filepath = MODELS_DIR / f'time_based_{minute}min_model.pkl'
        if filepath.exists():
            try:
                data = joblib.load(filepath)
                info['time_based'][minute] = {
                    'available': True,
                    'accuracy': data.get('metadata', {}).get('accuracy'),
                    'trained_at': data.get('metadata', {}).get('trained_at'),
                    'model_type': data.get('metadata', {}).get('model_type'),
                }
            except Exception:
                info['time_based'][minute] = {'available': False, 'error': 'Load failed'}
        else:
            info['time_based'][minute] = {'available': False}

    return info


# =============================================================================
# PREDICTION FUNCTIONS
# =============================================================================

def predict_at_minute(
    minute: int,
    gold_diff: float,
    first_blood: bool = False,
    first_tower: bool = False,
    first_dragon: bool = False,
    first_herald: bool = False,
    top_gold_diff: float = 0,
    jungle_gold_diff: float = 0,
    mid_gold_diff: float = 0,
    adc_gold_diff: float = 0,
    support_gold_diff: float = 0,
    cs_diff_at_10: Optional[float] = None,
    use_cached_model: bool = True,
) -> Dict[str, Any]:
    """
    Predict match outcome at a specific game minute.

    Args:
        minute: Game minute (5, 10, 15, or 20)
        gold_diff: Total gold difference (positive = blue team advantage)
        first_blood: Blue team got first blood
        first_tower: Blue team got first tower
        first_dragon: Blue team got first dragon
        first_herald: Blue team got first herald
        top_gold_diff: Top lane gold difference
        jungle_gold_diff: Jungle gold difference
        mid_gold_diff: Mid lane gold difference
        adc_gold_diff: ADC gold difference
        support_gold_diff: Support gold difference
        cs_diff_at_10: CS difference at 10 min (only used if minute=10)
        use_cached_model: Whether to use Streamlit cached model

    Returns:
        Dict with prediction results
    """
    # Load the appropriate model
    if use_cached_model:
        model, scaler, feature_columns, metadata = load_time_based_model(minute)
    else:
        # Direct load without caching
        filepath = MODELS_DIR / f'time_based_{minute}min_model.pkl'
        if filepath.exists():
            data = joblib.load(filepath)
            model = data['model']
            scaler = data['scaler']
            feature_columns = data.get('feature_columns', [])
            metadata = data.get('metadata', {})
        else:
            model, scaler, feature_columns, metadata = None, None, [], {}

    if model is None:
        return {
            'winner': 'Unknown',
            'blue_win_prob': 0.5,
            'red_win_prob': 0.5,
            'confidence': 0.0,
            'minute': minute,
            'model_used': None,
            'error': f'No model available for minute {minute}',
        }

    # Build feature dict
    features = {
        f'gold_diff_at_{minute}': gold_diff,
        'first_blood_team_100': 1 if first_blood else 0,
        'first_tower_team_100': 1 if first_tower else 0,
        'first_dragon_team_100': 1 if first_dragon else 0,
        'first_herald_team_100': 1 if first_herald else 0,
        f'top_gold_diff_at_{minute}': top_gold_diff,
        f'jungle_gold_diff_at_{minute}': jungle_gold_diff,
        f'mid_gold_diff_at_{minute}': mid_gold_diff,
        f'adc_gold_diff_at_{minute}': adc_gold_diff,
        f'support_gold_diff_at_{minute}': support_gold_diff,
    }

    # Add CS diff for minute 10
    if minute == 10 and cs_diff_at_10 is not None:
        features['cs_diff_at_10'] = cs_diff_at_10

    # Calculate derived features
    # Gold advantage percentage
    typical_gold_per_team = 20000 + (minute - 10) * 1500
    total_gold = 2 * typical_gold_per_team
    features[f'gold_advantage_pct_at_{minute}'] = gold_diff / total_gold if total_gold > 0 else 0

    # Early lead score
    gold_norm = gold_diff / 5000.0
    fb = 1 if first_blood else 0
    ft = 1 if first_tower else 0
    fd = 1 if first_dragon else 0
    fh = 1 if first_herald else 0
    features[f'early_lead_score_at_{minute}'] = (
        gold_norm * 0.6 +
        (fb * 2 - 1) * 0.15 +
        (ft * 2 - 1) * 0.1 +
        (fd * 2 - 1) * 0.1 +
        (fh * 2 - 1) * 0.05
    )

    # Create feature vector with only available columns
    available_features = {k: v for k, v in features.items() if k in feature_columns}

    # Fill missing features with 0
    for col in feature_columns:
        if col not in available_features:
            available_features[col] = 0

    # Build DataFrame in correct column order
    X = pd.DataFrame([available_features])[feature_columns]
    X_scaled = scaler.transform(X)

    # Predict
    prediction = model.predict(X_scaled)[0]
    probability = model.predict_proba(X_scaled)[0]

    return {
        'winner': 'Blue Team' if prediction == 1 else 'Red Team',
        'blue_win_prob': float(probability[1]),
        'red_win_prob': float(probability[0]),
        'confidence': float(max(probability)),
        'minute': minute,
        'model_used': f'time_based_{minute}min',
        'model_accuracy': metadata.get('accuracy'),
    }


# =============================================================================
# LEGACY FUNCTIONS (for backward compatibility)
# =============================================================================

@st.cache_resource
def load_early_game_model():
    """
    Load or train the early game prediction model.

    This is the legacy function that trains a simple model if no saved model exists.

    Returns:
        Tuple of (model, scaler, feature_names, accuracy)
    """
    # First try to load from file
    filepath = MODELS_DIR / 'early_game_10min_model.pkl'
    if filepath.exists():
        try:
            data = joblib.load(filepath)
            return (
                data['model'],
                data['scaler'],
                data.get('feature_columns', []),
                data.get('metadata', {}).get('accuracy', 0.0)
            )
        except Exception:
            pass  # Fall through to training

    # Train a simple model from database
    from utils.data_loader import get_matches_with_timeline, load_timeline_data
    import sqlite3
    from config import DATABASE_PATH

    # Get matches with timeline data
    conn = sqlite3.connect(str(DATABASE_PATH))

    # Query matches with @10min timeline data
    query = """
        SELECT
            m.match_id,
            m.team_100_win,
            mt.gold_diff as gold_diff_at_10,
            mt.team_100_gold,
            mt.team_200_gold,
            t100.first_blood as first_blood,
            t100.first_tower as first_tower,
            t100.first_dragon as first_dragon,
            t100.first_rift_herald as first_herald
        FROM matches m
        INNER JOIN match_timeline mt ON m.match_id = mt.match_id AND mt.minute = 10
        LEFT JOIN team_stats t100 ON m.match_id = t100.match_id AND t100.team_id = 100
        WHERE m.game_duration >= 600
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    if len(df) < 100:
        st.warning("Not enough matches with timeline data for training.")
        return None, None, [], 0.0

    # Calculate gold percentage
    total_gold = df["team_100_gold"] + df["team_200_gold"]
    df["gold_pct_at_10"] = df["team_100_gold"] / total_gold.replace(0, 1)

    # Prepare features
    feature_names = [
        "gold_diff_at_10",
        "gold_pct_at_10",
        "first_blood",
        "first_tower",
        "first_dragon",
        "first_herald",
    ]

    X = df[feature_names].fillna(0).astype(float)
    y = df["team_100_win"].astype(int)

    # Train-test split
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model
    model = LogisticRegression(random_state=42, max_iter=1000)
    model.fit(X_train_scaled, y_train)

    # Calculate accuracy
    accuracy = model.score(X_test_scaled, y_test)

    return model, scaler, feature_names, accuracy


def predict_win_probability(
    model,
    scaler,
    feature_names: list,
    gold_diff: float,
    gold_pct: float = None,
    first_blood: bool = False,
    first_tower: bool = False,
    first_dragon: bool = False,
    first_herald: bool = False,
) -> dict:
    """
    Predict win probability for Team 100 (Blue side).

    This is the legacy prediction function for backward compatibility.

    Args:
        model: Trained model
        scaler: Feature scaler
        feature_names: List of feature names
        gold_diff: Gold difference at 10 min (positive = blue advantage)
        gold_pct: Gold percentage for blue team (0.5 = even)
        first_blood: Whether blue team got first blood
        first_tower: Whether blue team got first tower
        first_dragon: Whether blue team got first dragon
        first_herald: Whether blue team got first herald

    Returns:
        Dict with prediction results
    """
    if model is None:
        return {
            "blue_win_prob": 0.5,
            "red_win_prob": 0.5,
            "prediction": "Unknown",
            "confidence": 0.0,
        }

    # Calculate gold_pct if not provided
    if gold_pct is None:
        # Assume average total gold at 10 min is ~40000 (20000 per team)
        avg_total = 40000
        blue_gold = (avg_total / 2) + (gold_diff / 2)
        gold_pct = blue_gold / avg_total

    # Create feature vector
    features = {
        "gold_diff_at_10": gold_diff,
        "gold_pct_at_10": gold_pct,
        "first_blood": 1.0 if first_blood else 0.0,
        "first_tower": 1.0 if first_tower else 0.0,
        "first_dragon": 1.0 if first_dragon else 0.0,
        "first_herald": 1.0 if first_herald else 0.0,
    }

    X = pd.DataFrame([features])[feature_names]
    X_scaled = scaler.transform(X)

    # Predict
    proba = model.predict_proba(X_scaled)[0]

    blue_win_prob = proba[1]
    red_win_prob = proba[0]

    return {
        "blue_win_prob": blue_win_prob,
        "red_win_prob": red_win_prob,
        "prediction": "Blue Team" if blue_win_prob > 0.5 else "Red Team",
        "confidence": max(blue_win_prob, red_win_prob),
    }


def get_feature_importance(model, feature_names: list) -> pd.DataFrame:
    """
    Get feature importance from the trained model.

    Args:
        model: Trained model
        feature_names: List of feature names

    Returns:
        DataFrame with feature importance
    """
    if model is None or not hasattr(model, "coef_"):
        return pd.DataFrame()

    # For logistic regression, use absolute coefficients as importance
    importance = np.abs(model.coef_[0])

    df = pd.DataFrame({
        "feature": feature_names,
        "importance": importance,
        "coefficient": model.coef_[0],
    }).sort_values("importance", ascending=False)

    return df
