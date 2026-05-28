"""
Configuration for the LoL Draft Predictor Streamlit App (Docker version).

Contains colors, paths, and other constants.
"""

import os
from pathlib import Path

# Project paths (inside container)
PROJECT_ROOT = Path(__file__).parent
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))

# Data Dragon CDN for champion icons
DDRAGON_VERSION = "15.2.1"
CHAMPION_ICON_URL = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/champion/{{champion_key}}.png"

# LoL Theme Colors
COLORS = {
    "blue_team": "#3498db",
    "red_team": "#e74c3c",
    "gold_accent": "#c8aa6e",
    "background": "#0a1428",
    "background_light": "#1e2328",
    "text_primary": "#f0e6d2",
    "text_secondary": "#a09b8c",
    "success": "#27ae60",
    "warning": "#f39c12",
    "danger": "#e74c3c",
}


def rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert hex color to rgba string for CSS."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def html(text: str) -> str:
    """Strip leading indentation from multiline HTML strings for Streamlit."""
    import textwrap
    return textwrap.dedent(text).strip()


# Pre-computed colors with alpha
COLORS_ALPHA = {
    "gold_accent_25": rgba(COLORS["gold_accent"], 0.25),
    "gold_accent_40": rgba(COLORS["gold_accent"], 0.40),
    "blue_team_25": rgba(COLORS["blue_team"], 0.25),
    "blue_team_40": rgba(COLORS["blue_team"], 0.40),
    "red_team_25": rgba(COLORS["red_team"], 0.25),
    "red_team_40": rgba(COLORS["red_team"], 0.40),
    "success_40": rgba(COLORS["success"], 0.40),
    "warning_40": rgba(COLORS["warning"], 0.40),
}

# Vector types for model selection (V3 — temporal summoner stats)
VECTOR_TYPES = {
    "draft": {
        "name": "Draft uniquement",
        "description": "Winrates externes + matchups + synergies/counters + summoner stats temporelles",
        "model_file": "model_draft.pkl",
        "nb_features": 153,
    },
    "at5": {
        "name": "Draft + @5min",
        "description": "Draft + summoner stats + gold par role a 5 minutes",
        "model_file": "model_at5.pkl",
        "nb_features": 171,
    },
    "at10": {
        "name": "Draft + @10min",
        "description": "Draft + summoner stats + gold/CS par role a 10 minutes",
        "model_file": "model_at10.pkl",
        "nb_features": 186,
    },
    "at15": {
        "name": "Draft + @15min",
        "description": "Draft + summoner stats + gold par role a 15 minutes",
        "model_file": "model_at15.pkl",
        "nb_features": 186,
    },
    "at20": {
        "name": "Draft + @20min",
        "description": "Draft + summoner stats + gold par role a 20 minutes",
        "model_file": "model_at20.pkl",
        "nb_features": 186,
    },
}

# Model accuracy benchmarks (V3)
MODEL_BENCHMARKS = {
    "draft": {
        "name": "Draft uniquement",
        "accuracy": 0.540,
        "auc_roc": 0.555,
        "model_type": "XGBoost",
        "description": "Winrates externes + matchups + synergies/counters + summoner stats temporelles",
    },
    "at5": {
        "name": "Draft + @5min",
        "accuracy": 0.654,
        "auc_roc": 0.719,
        "model_type": "LightGBM",
        "description": "Draft + summoner stats + gold par role a 5 minutes",
    },
    "at10": {
        "name": "Draft + @10min",
        "accuracy": 0.720,
        "auc_roc": 0.797,
        "model_type": "XGBoost",
        "description": "Draft + summoner stats + gold/CS par role a 10 minutes",
    },
    "at15": {
        "name": "Draft + @15min",
        "accuracy": 0.780,
        "auc_roc": 0.864,
        "model_type": "XGBoost",
        "description": "Draft + summoner stats + gold par role a 15 minutes",
    },
    "at20": {
        "name": "Draft + @20min",
        "accuracy": 0.799,
        "auc_roc": 0.885,
        "model_type": "XGBoost",
        "description": "Draft + summoner stats + gold par role a 20 minutes",
    },
}

# Feature descriptions for Feature Importance page
FEATURE_DESCRIPTIONS = {
    "draft_advantage": "Avantage global du draft (synergies + counters)",
    "synergy_diff": "Difference de score de synergie intra-equipe",
    "counter_diff": "Difference de score de counter-pick inter-equipes",
    "ext_wr_diff": "Difference de winrate externe moyenne (dpm.lol)",
    "ext_tier_diff": "Difference de tier moyen (dpm.lol)",
    "avg_matchup_advantage": "Avantage matchup moyen sur toutes les lanes",
    "ext_synergy_diff": "Difference de synergie externe (dpm.lol)",
    "gold_diff_at_5": "Difference de gold totale a 5 minutes",
    "gold_diff_at_10": "Difference de gold totale a 10 minutes",
    "gold_diff_at_15": "Difference de gold totale a 15 minutes",
    "gold_diff_at_20": "Difference de gold totale a 20 minutes",
    "role_winrate_diff": "Difference de winrate par role (temporel)",
    "role_specialization_diff": "Difference de specialisation de role",
    "streak_momentum_diff": "Difference de momentum de series (win/loss streaks)",
    "mastery_diff": "Difference de points de maitrise (log1p)",
}
