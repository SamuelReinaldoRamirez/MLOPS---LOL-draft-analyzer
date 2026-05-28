"""
LoL Draft Predictor — Application Streamlit principale (Docker version)

Run with: streamlit run app/app.py
"""

import streamlit as st

from config import COLORS, COLORS_ALPHA, rgba, html, MODEL_BENCHMARKS

# Page configuration
st.set_page_config(
    page_title="LoL Draft Predictor",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "vector_type" not in st.session_state:
    st.session_state.vector_type = "draft"

# Custom CSS for LoL theme
st.markdown(
    html(f"""
    <style>
        .stApp {{
            background: linear-gradient(180deg, {COLORS['background']} 0%, {COLORS['background_light']} 100%);
        }}
        [data-testid="stSidebar"] {{
            background: {COLORS['background_light']};
            border-right: 1px solid {COLORS['gold_accent']}40;
        }}
        h1, h2, h3 {{
            color: {COLORS['text_primary']} !important;
        }}
        [data-testid="stMetric"] {{
            background: {COLORS['background_light']};
            border: 1px solid {COLORS['gold_accent']}40;
            border-radius: 10px;
            padding: 15px;
        }}
        [data-testid="stMetricLabel"] {{
            color: {COLORS['text_secondary']} !important;
        }}
        [data-testid="stMetricValue"] {{
            color: {COLORS['gold_accent']} !important;
        }}
        .stButton > button {{
            background: {COLORS['gold_accent']};
            color: {COLORS['background']};
            border: none;
            font-weight: bold;
        }}
        .stButton > button:hover {{
            background: {COLORS['text_primary']};
            color: {COLORS['background']};
        }}
        p, span, label {{
            color: {COLORS['text_secondary']};
        }}
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
    </style>
    """),
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    st.image(
        "https://brand.riotgames.com/static/a91000434ed683571f9c-lol-logo.svg",
        width=200,
    )
    st.markdown("---")
    st.markdown(
        html(f"""
        <h3 style='color: {COLORS["gold_accent"]}; margin-bottom: 10px;'>
            Draft Predictor
        </h3>
        <p style='color: {COLORS["text_secondary"]}; font-size: 0.9em;'>
            Prédiction de résultats de matchs LoL par Machine Learning.
        </p>
        """),
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(
        html(f"""
        <div style='color: {COLORS["text_secondary"]}; font-size: 0.8em;'>
            <p><strong>Sources de données :</strong></p>
            <ul>
                <li>Riot Games API</li>
                <li>dpm.lol (winrates/matchups)</li>
                <li>CommunityDragon</li>
            </ul>
            <p style='margin-top: 10px;'><strong>Infrastructure :</strong></p>
            <ul>
                <li>🐳 Docker Compose</li>
                <li>🐘 PostgreSQL 16</li>
                <li>🚀 FastAPI (inférence)</li>
            </ul>
        </div>
        """),
        unsafe_allow_html=True,
    )

# Main content
st.title("🎮 LoL Draft Predictor")

st.markdown(
    html(f"""
    <p style='color: {COLORS["text_secondary"]}; font-size: 1.1em; margin-bottom: 30px;'>
        Prédiction de l'issue des matchs <strong>League of Legends</strong> par Machine Learning,
        à partir du draft et des données d'early game.
    </p>
    """),
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────
# Dataset overview
# ──────────────────────────────────────────
st.markdown("### 📊 Dataset")

try:
    from data_loader import (
        get_match_count,
        get_timeline_match_count,
        get_winrate_by_side,
        get_average_game_duration,
    )

    match_count = get_match_count()
    timeline_count = get_timeline_match_count()
    side_stats = get_winrate_by_side()
    avg_duration = get_average_game_duration()
except Exception as e:
    st.warning(f"⚠️ Base de données indisponible : {e}")
    match_count = 305000
    timeline_count = 164000
    side_stats = {"blue_winrate": 0.505, "red_winrate": 0.495}
    avg_duration = 28.5

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Matchs collectés", f"{match_count:,}")
with col2:
    st.metric("Avec timeline", f"{timeline_count:,}")
with col3:
    st.metric("Blue Side WR", f"{side_stats['blue_winrate']*100:.1f}%")
with col4:
    st.metric("Durée moyenne", f"{avg_duration:.1f} min")

st.markdown(
    html(f"""
    <p style='color: {COLORS["text_secondary"]}; font-size: 0.85em; margin-top: 5px;'>
        Région EUW · Diamond+ → Challenger · Saison 15 · Ranked Solo/Duo
    </p>
    """),
    unsafe_allow_html=True,
)

st.markdown("---")

# ──────────────────────────────────────────
# Model performance
# ──────────────────────────────────────────
st.markdown("### 🤖 Performance des modèles")

col1, col2, col3, col4, col5 = st.columns(5)
metrics = [
    ("Draft", "draft"),
    ("@5min", "at5"),
    ("@10min", "at10"),
    ("@15min", "at15"),
    ("@20min", "at20"),
]
for col, (label, key) in zip([col1, col2, col3, col4, col5], metrics):
    with col:
        bench = MODEL_BENCHMARKS[key]
        st.metric(
            f"{label}",
            f"{bench['accuracy']*100:.1f}%",
            delta=f"AUC {bench['auc_roc']:.3f}",
        )
        st.caption(bench["model_type"])

st.markdown("---")

# ──────────────────────────────────────────
# Key findings
# ──────────────────────────────────────────
st.markdown("### 💡 Résultats clés")

st.markdown(
    html(f"""
    <div style='
        background: {COLORS["background_light"]};
        border-left: 4px solid {COLORS["gold_accent"]};
        padding: 15px 20px;
        margin-bottom: 15px;
    '>
        <p style='color: {COLORS["text_primary"]}; margin: 0;'>
            <strong>Le draft seul ne suffit pas.</strong>
            Malgré l'ajout des winrates externes, matchups et synergies,
            le modèle draft-only atteint ~54.0% (V3, avec summoner stats temporelles).
        </p>
    </div>

    <div style='
        background: {COLORS["background_light"]};
        border-left: 4px solid {COLORS["blue_team"]};
        padding: 15px 20px;
        margin-bottom: 15px;
    '>
        <p style='color: {COLORS["text_primary"]}; margin: 0;'>
            <strong>L'early game est déterminant.</strong>
            Dès 5 minutes, l'ajout du gold fait passer l'accuracy à 65.4%.
            À 20 minutes, le modèle atteint 79.9% (AUC 0.885).
        </p>
    </div>

    <div style='
        background: {COLORS["background_light"]};
        border-left: 4px solid {COLORS["success"]};
        padding: 15px 20px;
        margin-bottom: 15px;
    '>
        <p style='color: {COLORS["text_primary"]}; margin: 0;'>
            <strong>Validation rigoureuse.</strong>
            Split temporel sur tous les modèles. Summoner stats réintégrées en V3
            avec calcul temporel (pas de fuite).
        </p>
    </div>
    """),
    unsafe_allow_html=True,
)

st.markdown("---")

# ──────────────────────────────────────────
# Pipeline summary
# ──────────────────────────────────────────
st.markdown("### ⚙️ Pipeline")

st.markdown(
    html(f"""
    <div style='
        background: {COLORS["background_light"]};
        border: 1px solid {COLORS["gold_accent"]}40;
        border-radius: 10px;
        padding: 20px;
        font-family: monospace;
        font-size: 0.9em;
        color: {COLORS["text_primary"]};
        line-height: 1.8;
    '>
        <strong style='color: {COLORS["gold_accent"]};'>Collecte</strong> Riot API + dpm.lol + CommunityDragon<br>
        &nbsp;&nbsp;&nbsp;&nbsp;↓<br>
        <strong style='color: {COLORS["gold_accent"]};'>Features</strong> Winrates · Matchups · Synergies · Counters · Summoner stats · Timeline gold/CS<br>
        &nbsp;&nbsp;&nbsp;&nbsp;↓<br>
        <strong style='color: {COLORS["gold_accent"]};'>Modèles</strong> XGBoost (draft) · LightGBM (@5min → @20min)<br>
        &nbsp;&nbsp;&nbsp;&nbsp;↓<br>
        <strong style='color: {COLORS["gold_accent"]};'>Prédiction</strong> Victoire Blue / Red avec probabilité
    </div>
    """),
    unsafe_allow_html=True,
)

st.markdown("---")

st.markdown(
    html(f"""
    <p style='color: {COLORS["text_secondary"]}; font-size: 0.85em; text-align: center;'>
        Projet DataScientest – Aïssam, Samuel, Guilhem – 2026
        <br>
        Naviguez entre les pages via la barre latérale.
    </p>
    """),
    unsafe_allow_html=True,
)
