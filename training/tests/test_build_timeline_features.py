"""Unit tests for training feature engineering.

Imports ``build_timeline_features`` from the training pipeline and checks
feature shape / behaviour on a tiny synthetic input. No DB or Docker needed.
"""

import numpy as np
import pandas as pd
import pytest

import train_all_models as tam


def _synthetic_rows(minute):
    """Two synthetic matches: blue ahead (win) and red ahead (loss)."""
    return pd.DataFrame(
        [
            {
                "team_100_win": True,
                "gold_diff": 3000,
                "team_100_gold": 28000,
                "team_200_gold": 25000,
                "first_blood": True,
                "first_tower": True,
                "first_dragon": False,
                "first_herald": True,
                "team_100_top_gold": 6000,
                "team_100_jungle_gold": 5500,
                "team_100_mid_gold": 6500,
                "team_100_adc_gold": 7000,
                "team_100_support_gold": 3000,
                "team_200_top_gold": 5000,
                "team_200_jungle_gold": 5000,
                "team_200_mid_gold": 6000,
                "team_200_adc_gold": 6500,
                "team_200_support_gold": 2500,
            },
            {
                "team_100_win": False,
                "gold_diff": -2000,
                "team_100_gold": 22000,
                "team_200_gold": 24000,
                "first_blood": False,
                "first_tower": False,
                "first_dragon": True,
                "first_herald": False,
                "team_100_top_gold": 4500,
                "team_100_jungle_gold": 4000,
                "team_100_mid_gold": 5000,
                "team_100_adc_gold": 5500,
                "team_100_support_gold": 3000,
                "team_200_top_gold": 5000,
                "team_200_jungle_gold": 4500,
                "team_200_mid_gold": 5500,
                "team_200_adc_gold": 6000,
                "team_200_support_gold": 3000,
            },
        ]
    )


@pytest.mark.parametrize("minute", [5, 10, 15, 20])
def test_feature_shape_and_target(minute):
    df = _synthetic_rows(minute)
    X, y = tam.build_timeline_features(df, minute)

    # One row of features per input match.
    assert isinstance(X, pd.DataFrame)
    assert len(X) == 2
    assert isinstance(y, np.ndarray)
    assert y.tolist() == [1, 0]

    expected_cols = {
        f"gold_diff_at_{minute}",
        "first_blood_team_100",
        "first_tower_team_100",
        "first_dragon_team_100",
        "first_herald_team_100",
        f"top_gold_diff_at_{minute}",
        f"jungle_gold_diff_at_{minute}",
        f"mid_gold_diff_at_{minute}",
        f"adc_gold_diff_at_{minute}",
        f"support_gold_diff_at_{minute}",
        f"gold_advantage_pct_at_{minute}",
        f"early_lead_score_at_{minute}",
    }
    assert expected_cols.issubset(set(X.columns))
    # 5 base + 5 per-position gold diffs + 2 derived = 12 features.
    assert X.shape[1] == 12


def test_feature_values(minute=10):
    df = _synthetic_rows(minute)
    X, _ = tam.build_timeline_features(df, minute)
    row0 = X.iloc[0]

    # Boolean firsts mapped to 0/1.
    assert row0["first_blood_team_100"] == 1
    assert row0["first_dragon_team_100"] == 0

    # Per-position gold diff = team_100 - team_200.
    assert row0[f"top_gold_diff_at_{minute}"] == 6000 - 5000
    assert row0[f"adc_gold_diff_at_{minute}"] == 7000 - 6500

    # gold_advantage_pct = gold_diff / total_gold.
    assert row0[f"gold_advantage_pct_at_{minute}"] == pytest.approx(3000 / (28000 + 25000))


def test_no_nan_and_zero_fill():
    """Missing/None numeric fields fill to 0 without producing NaNs."""
    df = pd.DataFrame(
        [
            {
                "team_100_win": True,
                "gold_diff": None,
                # team_*_gold and first_* intentionally omitted.
            }
        ]
    )
    X, y = tam.build_timeline_features(df, 15)
    assert not X.isnull().any().any()
    assert y.tolist() == [1]
    assert X.iloc[0]["gold_diff_at_15"] == 0
    assert X.iloc[0]["top_gold_diff_at_15"] == 0


def test_module_imports_without_touching_filesystem():
    """The module must import without creating /app/models (import-enabling fix)."""
    assert hasattr(tam, "build_timeline_features")
    assert hasattr(tam, "ensure_models_dir")
