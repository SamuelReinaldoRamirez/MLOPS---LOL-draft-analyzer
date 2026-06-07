"""
Page 4 - Présentation des modèles
"""
import streamlit as st
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

STREAMLIT_APP_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(STREAMLIT_APP_DIR))
sys.path.insert(1, str(STREAMLIT_APP_DIR.parent / "src" / "collect_data"))

from config import COLORS, html, VECTOR_TYPES, MODEL_BENCHMARKS

st.set_page_config(page_title="Modèles - LoL Draft Predictor", page_icon="🤖", layout="wide")

st.title("🤖 Modèles de Prédiction")

# ============================
# Sidebar selector (for independent access)
# ============================
if "vector_type" not in st.session_state:
    st.session_state.vector_type = "draft"

with st.sidebar:
    st.markdown("### Vecteur d'entrée")
    vector_options = list(VECTOR_TYPES.keys())
    sidebar_labels = [VECTOR_TYPES[k]["name"] for k in vector_options]
    current_idx = vector_options.index(st.session_state.vector_type)
    sidebar_selection = st.selectbox(
        "Sélection rapide",
        sidebar_labels,
        index=current_idx,
        key="sidebar_vector_modeles",
    )
    st.session_state.vector_type = vector_options[sidebar_labels.index(sidebar_selection)]

vector_type = st.session_state.vector_type
vt = VECTOR_TYPES[vector_type]
bm = MODEL_BENCHMARKS[vector_type]

# ============================
# Section 1 - Algorithmes
# ============================
st.header("1. Algorithmes utilisés")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("XGBoost")
    st.markdown("""
    **eXtreme Gradient Boosting**

    - Boosting d'arbres de decision
    - Regularisation L1/L2 renforcee
    - Early stopping (50 rounds)
    - Draft : max_depth=4, lr=0.01, strong reg
    - Utilise pour : **Draft** (regularisation forte)
    """)

with col2:
    st.subheader("LightGBM")
    st.markdown("""
    **Light Gradient Boosting Machine**

    - Variante optimisee du gradient boosting
    - Croissance par feuille (leaf-wise)
    - max_depth=6, lr=0.03, early stopping
    - Utilise pour : **@5min** (XGBoost pour @10-@20)
    """)

with col3:
    st.subheader("Approche V3")
    st.markdown("""
    **Pipeline avec summoner stats temporelles**

    1. StandardScaler sur les features
    2. **Split temporel** pour tous les modeles
    3. Validation 15% + test 20% (temporel)
    4. Metriques : Accuracy, AUC-ROC
    5. **Summoner stats temporelles** (93 features)
    6. **Aucun champion ID** ordinal
    """)

st.markdown("---")

# ============================
# Section 2 - Modèle sélectionné
# ============================
st.header(f"2. Modèle sélectionné : {vt['name']}")

from utils.model_loader import load_production_model

model_data = load_production_model(vector_type)

if model_data is not None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Algorithme", model_data.get("model_name", "N/A"))
    with col2:
        st.metric("Accuracy test", f"{model_data.get('test_accuracy', 0)*100:.1f}%")
    with col3:
        st.metric("Accuracy validation", f"{model_data.get('val_accuracy', 0)*100:.1f}%")
    with col4:
        st.metric("Nb features", len(model_data.get("features", [])))

    # Overfitting check
    val_acc = model_data.get("val_accuracy", 0)
    test_acc = model_data.get("test_accuracy", 0)
    if val_acc > 0 and test_acc > 0:
        diff = (val_acc - test_acc) * 100
        if diff > 10:
            st.warning(f"⚠️ Écart validation/test de {diff:.1f}% — possible overfitting")
        elif diff > 5:
            st.info(f"ℹ️ Écart validation/test de {diff:.1f}% — attendu pour le draft (meta shift entre periodes)")
        else:
            st.success(f"✅ Écart validation/test de {diff:.1f}% — bonne généralisation")
else:
    st.error("Impossible de charger le modèle sélectionné.")

st.markdown("---")

# ============================
# Section 3 - Comparaison des 5 modèles
# ============================
st.header("3. Comparaison des 5 modèles")

bench_df = pd.DataFrame([
    {
        "Vecteur": MODEL_BENCHMARKS[k]["name"],
        "Accuracy": MODEL_BENCHMARKS[k]["accuracy"],
        "Algorithme": MODEL_BENCHMARKS[k]["model_type"],
    }
    for k in vector_options
])

fig = go.Figure()

colors = [COLORS["gold_accent"] if k == vector_type else COLORS["text_secondary"] for k in vector_options]

fig.add_trace(go.Bar(
    x=bench_df["Vecteur"],
    y=bench_df["Accuracy"] * 100,
    marker_color=colors,
    text=[f"{a*100:.1f}%" for a in bench_df["Accuracy"]],
    textposition="auto",
    hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.1f}%<extra></extra>",
))

fig.update_layout(
    title="Accuracy des modèles sur le jeu de test",
    yaxis_title="Accuracy (%)",
    yaxis_range=[40, 90],
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    showlegend=False,
    height=400,
)

# Add 50% baseline
fig.add_hline(y=50, line_dash="dash", line_color=COLORS["red_team"],
              annotation_text="Aléatoire (50%)", annotation_position="bottom right")

st.plotly_chart(fig, use_container_width=True)

st.markdown("""
**Observations (V3 — split temporel, summoner stats temporelles) :**
- Le modele **draft-only** atteint **54.0%** (153 features) → le draft seul ne suffit pas en solo queue
- L'ajout de donnees **@5min** fait bondir l'accuracy a **65.4%** → le gold early est tres predictif
- La progression continue jusqu'a **79.9%** a **@20min** (AUC-ROC = 0.885)
- Le gain marginal diminue au fil du temps (@5→@10 = +6.6%, @15→@20 = +1.9%)
- Ecart val/test < 7% pour le draft (attendu), < 1% pour les modeles in-game → **bonne generalisation**
- Les summoner stats (role_winrate, streak, KDA, etc.) sont reintegrees avec **calcul temporel** (pas de fuite)
- XGBoost domine LightGBM sur les modeles in-game (@10, @15, @20) en V3
""")

# ============================
# Section 3b - Distribution Beta des winrates
# ============================
st.header("Distribution Beta des winrates")
st.markdown(
    "La **distribution Beta** permet de modeliser l'incertitude sur le winrate reel d'un champion "
    "a partir de son nombre de victoires et de defaites. Plus un champion a de parties jouees, "
    "plus la distribution est resserree autour de son winrate observe."
)
st.image("streamlit_app/image.png", caption="Distribution Beta combinee des winrates (zoom 0.40 – 0.60)")

st.markdown("---")

# ============================
# Section 3c - Analyse de confiance (Draft XGBoost)
# ============================
st.header("Analyse de confiance — Draft (XGBoost)")
st.markdown(
    "Plus le modele est **confiant** dans sa prediction (probabilite loin de 50%), "
    "plus il est precis — mais il couvre moins de matchs. "
    "Les tableaux ci-dessous montrent ce compromis **accuracy vs couverture**."
)

# --- Data: XGBoost par defaut ---
xgb_default_data = {
    "x (%)": list(range(21)),
    "threshold_low": [0.50 - i/100 for i in range(21)],
    "threshold_high": [0.50 + i/100 for i in range(21)],
    "accuracy": [
        0.532206, 0.540267, 0.545727, 0.551457, 0.557619,
        0.564313, 0.571234, 0.582152, 0.582356, 0.593542,
        0.606335, 0.612328, 0.601527, 0.611174, 0.600352,
        0.595687, 0.593985, 0.558140, 0.532710, 0.529412,
        0.541667,
    ],
    "coverage": [
        1.000000, 0.833843, 0.676299, 0.533559, 0.409181,
        0.306139, 0.222313, 0.158114, 0.110730, 0.074947,
        0.051121, 0.034929, 0.023310, 0.015605, 0.010107,
        0.006601, 0.004733, 0.003060, 0.001904, 0.001210,
        0.000854,
    ],
    "n_predictions": [
        56200, 46862, 38008, 29986, 22996,
        17205, 12494, 8886, 6223, 4212,
        2873, 1963, 1310, 877, 568,
        371, 266, 172, 107, 68, 48,
    ],
}

# --- Data: XGBoost Bayesian Search ---
xgb_bayes_data = {
    "x (%)": list(range(21)),
    "accuracy": [
        0.535142, 0.541183, 0.548698, 0.555216, 0.563048,
        0.570874, 0.582355, 0.599455, 0.606954, 0.610059,
        0.625760, 0.636526, 0.631424, 0.608696, 0.578740,
        0.555556, 0.559140, 0.527273, 0.393939, 0.458333,
        0.384615,
    ],
    "coverage": [
        1.000000, 0.820267, 0.651299, 0.500142, 0.371263,
        0.265747, 0.184947, 0.124075, 0.080854, 0.051655,
        0.032189, 0.019875, 0.012117, 0.007367, 0.004520,
        0.002562, 0.001655, 0.000979, 0.000587, 0.000427,
        0.000231,
    ],
    "n_samples": [
        56200, 46099, 36603, 28108, 20865,
        14935, 10394, 6973, 4544, 2903,
        1809, 1117, 681, 414, 254,
        144, 93, 55, 33, 24, 13,
    ],
}

df_default = pd.DataFrame(xgb_default_data)
df_bayes = pd.DataFrame(xgb_bayes_data)

# --- Graphique comparatif accuracy vs coverage ---
fig_conf = go.Figure()

fig_conf.add_trace(go.Scatter(
    x=df_default["coverage"], y=df_default["accuracy"].apply(lambda x: x * 100),
    mode="lines+markers",
    name="XGBoost (defaut)",
    line=dict(color=COLORS["text_secondary"], width=2),
    marker=dict(size=5),
    text=[f"x={r}% | n={n:,}" for r, n in zip(df_default["x (%)"], df_default["n_predictions"])],
    hovertemplate="%{text}<br>Coverage: %{x:.1%}<br>Accuracy: %{y:.1f}%<extra></extra>",
))
fig_conf.add_trace(go.Scatter(
    x=df_bayes["coverage"], y=df_bayes["accuracy"].apply(lambda x: x * 100),
    mode="lines+markers",
    name="XGBoost (Bayesian)",
    line=dict(color=COLORS["gold_accent"], width=2),
    marker=dict(size=5),
    text=[f"x={r}% | n={n:,}" for r, n in zip(df_bayes["x (%)"], df_bayes["n_samples"])],
    hovertemplate="%{text}<br>Coverage: %{x:.1%}<br>Accuracy: %{y:.1f}%<extra></extra>",
))

fig_conf.add_hline(y=50, line_dash="dash", line_color=COLORS["red_team"],
                   annotation_text="Aleatoire (50%)")

fig_conf.update_layout(
    title="Accuracy vs Couverture selon le seuil de confiance",
    xaxis_title="Couverture (% des matchs predits)",
    yaxis_title="Accuracy (%)",
    xaxis=dict(tickformat=".0%", autorange="reversed"),
    yaxis_range=[45, 70],
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    legend=dict(x=0.02, y=0.98),
    height=450,
)
st.plotly_chart(fig_conf, use_container_width=True)

# --- Tableaux detailles ---
col_t1, col_t2 = st.columns(2)

with col_t1:
    st.markdown("**XGBoost — parametres par defaut**")
    st.caption(
        "`n_estimators=300, max_depth=6, lr=0.05, subsample=0.8, colsample=0.8`"
    )
    display_default = df_default.copy()
    display_default["accuracy"] = display_default["accuracy"].apply(lambda x: f"{x*100:.1f}%")
    display_default["coverage"] = display_default["coverage"].apply(lambda x: f"{x*100:.1f}%")
    display_default["n_predictions"] = display_default["n_predictions"].apply(lambda x: f"{x:,}")
    display_default.columns = ["Seuil (%)", "Seuil bas", "Seuil haut", "Accuracy", "Couverture", "N predictions"]
    st.dataframe(display_default, use_container_width=True, hide_index=True, height=300)

with col_t2:
    st.markdown("**XGBoost — Bayesian Search (150 iter, CV=3)**")
    st.caption(
        "`n_estimators=1000, max_depth=3, lr=0.028, subsample=0.6, colsample=1.0, eval=auc`"
    )
    display_bayes = df_bayes.copy()
    display_bayes["accuracy"] = display_bayes["accuracy"].apply(lambda x: f"{x*100:.1f}%")
    display_bayes["coverage"] = display_bayes["coverage"].apply(lambda x: f"{x*100:.1f}%")
    display_bayes["n_samples"] = display_bayes["n_samples"].apply(lambda x: f"{x:,}")
    display_bayes.columns = ["Seuil (%)", "Accuracy", "Couverture", "N predictions"]
    st.dataframe(display_bayes, use_container_width=True, hide_index=True, height=300)

st.markdown(
    "> **Lecture** : a seuil 10%, on ne predit que les matchs ou le modele donne >60% ou <40% de chance "
    "a la Blue team. L'accuracy monte mais on couvre moins de matchs. "
    "Le Bayesian Search atteint **63.7% d'accuracy** sur les 2% de matchs les plus confiants."
)

st.markdown("---")

# ============================
# Section 4 - Feature importance
# ============================
st.header("4. Feature Importance")

if model_data is not None:
    from utils.model_loader import get_tree_feature_importance

    model = model_data.get("model")
    features = model_data.get("features", [])

    fi_df = get_tree_feature_importance(model, features)

    if not fi_df.empty:
        n_features = st.slider("Nombre de features à afficher", 5, min(50, len(fi_df)), 20)
        top_fi = fi_df.head(n_features)

        fig = px.bar(
            top_fi,
            x="importance",
            y="feature",
            orientation="h",
            title=f"Top {n_features} Feature Importance – {vt['name']}",
            color="importance",
            color_continuous_scale="YlOrRd",
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed"),
            height=max(400, n_features * 25),
            showlegend=False,
        )
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Tableau complet"):
            display_df = fi_df.copy()
            display_df["importance"] = display_df["importance"].round(6)
            display_df["% total"] = (display_df["importance"] / display_df["importance"].sum() * 100).round(2)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.warning("Impossible d'extraire le feature importance pour ce modèle.")
else:
    st.warning("Modèle non chargé – impossible d'afficher le feature importance.")
