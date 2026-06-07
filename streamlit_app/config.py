"""
Configuration for the LoL Draft Predictor Streamlit App

Contains colors, paths, and other constants.
"""
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "lol_matches.db"
MODELS_DIR = PROJECT_ROOT / "models"

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


# Pre-computed colors with alpha for CSS (40 hex = 0.25 alpha, 60 hex = 0.38 alpha)
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
        "extra_features": [
            "ext_wr_{team}_{pos}", "ext_tier_{team}_{pos}", "ext_pickrate_{team}_{pos}",
            "ext_avg_wr_{team}", "ext_avg_tier_{team}", "ext_wr_diff", "ext_tier_diff",
            "matchup_wr_{pos}", "matchup_advantage_{pos}", "avg_matchup_advantage",
            "ext_synergy_{team}", "ext_synergy_diff",
            "synergy_diff", "counter_diff", "draft_advantage",
            "{team}_{pos}_role_pct", "{team}_{pos}_role_winrate",
            "{team}_{pos}_mastery_points", "{team}_{pos}_streak_type",
            "{team}_{pos}_streak_length", "{team}_{pos}_role_kda",
            "{team}_{pos}_role_vision", "{team}_{pos}_champ_recent_wr",
            "{team}_avg_role_specialization", "{team}_min_role_specialization",
            "{team}_avg_role_winrate", "{team}_total_mastery_points",
            "{team}_streak_momentum",
            "role_winrate_diff", "role_specialization_diff",
            "streak_momentum_diff", "mastery_diff",
        ],
    },
    "at5": {
        "name": "Draft + @5min",
        "description": "Draft + summoner stats + gold par role a 5 minutes",
        "model_file": "model_at5.pkl",
        "nb_features": 171,
        "extra_features": [
            "gold_diff_at_5", "team_{team}_gold_at_5",
            "team_{team}_{pos}_gold_at_5", "{pos}_gold_diff_at_5",
        ],
    },
    "at10": {
        "name": "Draft + @10min",
        "description": "Draft + summoner stats + gold/CS par role a 10 minutes",
        "model_file": "model_at10.pkl",
        "nb_features": 186,
        "extra_features": [
            "gold_diff_at_10", "team_{team}_gold_at_10",
            "team_{team}_{pos}_gold_at_10", "{pos}_gold_diff_at_10",
            "team_{team}_{pos}_cs_at_10", "{pos}_cs_diff_at_10",
        ],
    },
    "at15": {
        "name": "Draft + @15min",
        "description": "Draft + summoner stats + gold par role a 15 minutes + CS@10",
        "model_file": "model_at15.pkl",
        "nb_features": 186,
        "extra_features": [
            "gold_diff_at_15", "team_{team}_gold_at_15",
            "team_{team}_{pos}_gold_at_15", "{pos}_gold_diff_at_15",
            "team_{team}_{pos}_cs_at_10", "{pos}_cs_diff_at_10",
        ],
    },
    "at20": {
        "name": "Draft + @20min",
        "description": "Draft + summoner stats + gold par role a 20 minutes + CS@10",
        "model_file": "model_at20.pkl",
        "nb_features": 186,
        "extra_features": [
            "gold_diff_at_20", "team_{team}_gold_at_20",
            "team_{team}_{pos}_gold_at_20", "{pos}_gold_diff_at_20",
            "team_{team}_{pos}_cs_at_10", "{pos}_cs_diff_at_10",
        ],
    },
}

# Model accuracy benchmarks (V3 — temporal summoner stats)
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
    "matchup_wr_top": "Winrate du matchup en top lane",
    "matchup_wr_mid": "Winrate du matchup en mid lane",
    "matchup_wr_jungle": "Winrate du matchup en jungle",
    "matchup_wr_adc": "Winrate du matchup en ADC",
    "matchup_wr_support": "Winrate du matchup en support",
    "support_gold_diff_at_5": "Avantage gold du support a 5 min",
    "jungle_gold_diff_at_5": "Avantage gold du jungler a 5 min",
    "top_gold_diff_at_5": "Avantage gold du top a 5 min",
    # V3: Summoner stats features
    "role_winrate_diff": "Difference de winrate par role (temporel)",
    "role_specialization_diff": "Difference de specialisation de role",
    "streak_momentum_diff": "Difference de momentum de series (win/loss streaks)",
    "mastery_diff": "Difference de points de maitrise (log1p)",
}

# Data sources info
DATA_SOURCES = {
    "winrates_simples": "data/winrates/les winrates simples/",
    "winrates_matchups": "data/winrates/les winrates matchups/",
    "database": "data/lol_matches.db",
}
