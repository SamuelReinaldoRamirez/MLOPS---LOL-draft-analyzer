"""
Page 5 - Résultats et prédiction interactive
"""
import streamlit as st
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_curve,
    auc,
)

STREAMLIT_APP_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(STREAMLIT_APP_DIR))
sys.path.insert(1, str(STREAMLIT_APP_DIR.parent / "src" / "collect_data"))

from config import COLORS, html, VECTOR_TYPES, MODEL_BENCHMARKS

st.set_page_config(page_title="Résultats - LoL Draft Predictor", page_icon="🎯", layout="wide")

st.title("🎯 Résultats & Prédiction")

# ============================
# Sidebar selector
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
        key="sidebar_vector_resultats",
    )
    st.session_state.vector_type = vector_options[sidebar_labels.index(sidebar_selection)]

vector_type = st.session_state.vector_type
vt = VECTOR_TYPES[vector_type]
bm = MODEL_BENCHMARKS[vector_type]

st.info(f"Vecteur selectionne : **{vt['name']}** ({vt['nb_features']} features, {bm['model_type']})")

# ============================
# Load model and data
# ============================
from utils.model_loader import load_production_model, safe_transform
from utils.data_loader import (
    load_test_with_summoner,
    load_train_with_summoner,
    load_timeline_data_parquet,
)

model_data = load_production_model(vector_type)
if model_data is None:
    st.error("Impossible de charger le modèle. Vérifiez les fichiers pkl.")
    st.stop()

model = model_data["model"]
scaler = model_data["scaler"]
features = model_data["features"]

tab_a, tab_b = st.tabs(["📈 Résultats sur le dataset", "🔮 Prédiction interactive"])


# ============================
# Helper: merge timeline data with summoner data
# ============================
def _merge_with_timeline(df, df_timeline):
    """Merge summoner stats with timeline data, preferring timeline values for overlapping columns."""
    df = df.merge(df_timeline, on="match_id", how="inner", suffixes=("_base", "_tl"))
    for col in list(df.columns):
        if col.endswith("_tl"):
            base_col = col[:-3]
            base_version = base_col + "_base"
            if base_version in df.columns:
                if base_col == "team_100_win":
                    df.rename(columns={base_version: base_col}, inplace=True)
                    df.drop(columns=[col], inplace=True)
                else:
                    df.drop(columns=[base_version], inplace=True, errors="ignore")
                    df.rename(columns={col: base_col}, inplace=True)
            else:
                df.rename(columns={col: base_col}, inplace=True)
    for col in list(df.columns):
        if col.endswith("_base"):
            base_col = col[:-5]
            if base_col not in df.columns:
                df.rename(columns={col: base_col}, inplace=True)
    return df


# ============================
# Helper: prepare evaluation data
# ============================
@st.cache_data
def prepare_eval_data(_vector_type, _features, _model_data_key=None):
    """Prepare X, y for evaluation based on vector type.

    For draft model: uses the test set (56k unseen matches).
    For timeline models: merges train + timeline, uses temporal last 20%.

    Returns:
        X, y, df, is_test_set (bool)
    """
    from utils.feature_builder import add_all_model_features

    # Load model data for external features
    _md = load_production_model(_vector_type)

    if _vector_type == "draft":
        df = load_test_with_summoner()
        if df.empty:
            return None, None, None, True
        is_test = True
    else:
        # Test set has no timeline data (temporal split).
        # Use temporal split from train + timeline data.
        df_train = load_train_with_summoner()
        df_timeline = load_timeline_data_parquet()
        if df_train.empty or df_timeline.empty:
            return None, None, None, False
        df = _merge_with_timeline(df_train, df_timeline)
        if df.empty:
            return None, None, None, False

        # Temporal split: use last 20% as evaluation
        minute = {'at5': 5, 'at10': 10, 'at15': 15, 'at20': 20}.get(_vector_type, 10)
        gdiff_col = f'gold_diff_at_{minute}'
        if gdiff_col in df.columns:
            df = df[df[gdiff_col].notna()]
        if 'game_creation' in df.columns:
            df = df.sort_values('game_creation')
            n_test = int(len(df) * 0.2)
            df = df.iloc[-n_test:].reset_index(drop=True)
        elif len(df) > 10000:
            df = df.sample(n=10000, random_state=42).reset_index(drop=True)
        is_test = False

    if "team_100_win" not in df.columns:
        return None, None, None, is_test

    # Add external features (V2 models need them)
    if _md is not None:
        df = add_all_model_features(df, _md)

    y = df["team_100_win"].astype(int)

    for f in _features:
        if f not in df.columns:
            df[f] = 0

    X = df[_features].fillna(0)
    return X, y, df, is_test


# ============================
# TAB A - Résultats sur le dataset
# ============================
with tab_a:
    st.header("Évaluation du modèle")

    result = prepare_eval_data(vector_type, features, _model_data_key=vector_type)
    X, y, df_eval, is_test_set = result[0], result[1], result[2], result[3]

    if X is None or y is None:
        st.error("Impossible de charger les données d'évaluation.")
    else:
        if is_test_set:
            st.markdown(f"**Jeu de test temporel** : {len(y):,} matchs (données non vues à l'entraînement)")
        else:
            st.info(
                f"Évaluation sur les **{len(y):,} derniers matchs** avec données timeline "
                f"(split temporel, 20% les plus récents). "
                f"Accuracy de référence : **{bm['accuracy']*100:.1f}%** (AUC-ROC {bm.get('auc_roc', 'N/A')})."
            )

        # Predict
        X_scaled = safe_transform(scaler, X)
        y_pred = model.predict(X_scaled)
        y_proba = model.predict_proba(X_scaled)

        # Metrics
        acc = accuracy_score(y, y_pred)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Accuracy", f"{acc*100:.1f}%")
        with col2:
            blue_precision = (y_pred[y == 1] == 1).mean() if (y == 1).sum() > 0 else 0
            st.metric("Précision (Blue win)", f"{blue_precision*100:.1f}%")
        with col3:
            blue_recall = (y_pred[y == 1] == 1).sum() / (y == 1).sum() if (y == 1).sum() > 0 else 0
            st.metric("Recall (Blue win)", f"{blue_recall*100:.1f}%")

        st.markdown("---")

        col_left, col_right = st.columns(2)

        # Confusion matrix
        with col_left:
            st.subheader("Matrice de confusion")
            cm = confusion_matrix(y, y_pred)
            fig = px.imshow(
                cm,
                text_auto=True,
                labels=dict(x="Prédit", y="Réel", color="Nombre"),
                x=["Red Win", "Blue Win"],
                y=["Red Win", "Blue Win"],
                color_continuous_scale=[[0, COLORS["background_light"]], [1, COLORS["gold_accent"]]],
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                width=400,
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

        # ROC Curve
        with col_right:
            st.subheader("Courbe ROC")
            fpr, tpr, _ = roc_curve(y, y_proba[:, 1])
            roc_auc = auc(fpr, tpr)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=fpr, y=tpr,
                mode="lines",
                name=f"ROC (AUC = {roc_auc:.3f})",
                line=dict(color=COLORS["gold_accent"], width=2),
            ))
            fig.add_trace(go.Scatter(
                x=[0, 1], y=[0, 1],
                mode="lines",
                name="Aléatoire",
                line=dict(color=COLORS["red_team"], width=1, dash="dash"),
            ))
            fig.update_layout(
                xaxis_title="Taux de faux positifs",
                yaxis_title="Taux de vrais positifs",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=400,
                legend=dict(x=0.6, y=0.1),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Classification report
        with st.expander("Classification Report détaillé"):
            report = classification_report(y, y_pred, target_names=["Red Win", "Blue Win"], output_dict=True)
            report_df = pd.DataFrame(report).T
            st.dataframe(report_df.round(3), use_container_width=True)

        st.markdown("---")

        # Comparison table of all 5 models
        st.subheader("Tableau comparatif des 5 modèles")

        comp_data = []
        for k in vector_options:
            b = MODEL_BENCHMARKS[k]
            v = VECTOR_TYPES[k]
            row = {
                "Vecteur": b["name"],
                "Algorithme": b["model_type"],
                "Features": v["nb_features"],
                "Accuracy Test": f"{b['accuracy']*100:.1f}%",
            }
            comp_data.append(row)

        comp_df = pd.DataFrame(comp_data)
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

        # Bar chart comparison
        fig = go.Figure()
        accs = [MODEL_BENCHMARKS[k]["accuracy"] * 100 for k in vector_options]
        names = [MODEL_BENCHMARKS[k]["name"] for k in vector_options]
        bar_colors = [COLORS["gold_accent"] if k == vector_type else COLORS["text_secondary"] for k in vector_options]

        fig.add_trace(go.Bar(
            x=names, y=accs,
            marker_color=bar_colors,
            text=[f"{a:.1f}%" for a in accs],
            textposition="auto",
        ))
        fig.add_hline(y=50, line_dash="dash", line_color=COLORS["red_team"],
                      annotation_text="Aléatoire (50%)")
        fig.update_layout(
            title="Progression de l'accuracy selon le vecteur",
            yaxis_title="Accuracy (%)",
            yaxis_range=[40, 90],
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================
# TAB B - Prédiction interactive
# ============================
with tab_b:
    st.header("Prédiction interactive")

    st.markdown("""
    Chargement d'un match aleatoire. Le modele predit le resultat et le compare au resultat reel.
    Les champions sont affiches par nom avec les matchups par lane.
    """)

    res_b = prepare_eval_data(vector_type, features)
    X_eval, y_eval, df_full = res_b[0], res_b[1], res_b[2]

    if X_eval is None:
        st.error("Données de test indisponibles.")
    else:
        # Random match button
        if st.button("🎲 Charger un match aléatoire", type="primary"):
            st.session_state.random_match_idx = np.random.randint(0, len(X_eval))

        if "random_match_idx" not in st.session_state:
            st.session_state.random_match_idx = 0

        idx = st.session_state.random_match_idx
        match_features = X_eval.iloc[idx:idx+1]
        true_label = int(y_eval.iloc[idx])
        match_id = df_full.iloc[idx].get("match_id", "N/A") if df_full is not None else "N/A"

        st.markdown(f"**Match ID** : `{match_id}`")

        # Show team composition with champion names
        roles = ["top", "jungle", "mid", "adc", "support"]
        role_labels = {"top": "TOP", "jungle": "JGL", "mid": "MID", "adc": "ADC", "support": "SUP"}

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🔵 Blue Team**")
            for role in roles:
                name_col = f"team_100_{role}_champion_name"
                id_col = f"team_100_{role}_champion_id"
                if name_col in df_full.columns and pd.notna(df_full.iloc[idx].get(name_col)):
                    champ_name = df_full.iloc[idx][name_col]
                    st.markdown(f"- **{role_labels[role]}** : {champ_name}")
                elif id_col in df_full.columns and pd.notna(df_full.iloc[idx].get(id_col)):
                    champ_id = int(df_full.iloc[idx][id_col])
                    st.markdown(f"- **{role_labels[role]}** : Champion #{champ_id}")
        with col2:
            st.markdown("**🔴 Red Team**")
            for role in roles:
                name_col = f"team_200_{role}_champion_name"
                id_col = f"team_200_{role}_champion_id"
                if name_col in df_full.columns and pd.notna(df_full.iloc[idx].get(name_col)):
                    champ_name = df_full.iloc[idx][name_col]
                    st.markdown(f"- **{role_labels[role]}** : {champ_name}")
                elif id_col in df_full.columns and pd.notna(df_full.iloc[idx].get(id_col)):
                    champ_id = int(df_full.iloc[idx][id_col])
                    st.markdown(f"- **{role_labels[role]}** : Champion #{champ_id}")

        # Show matchup info if available
        matchup_cols = [c for c in df_full.columns if c.startswith("matchup_wr_")]
        if matchup_cols:
            with st.expander("Matchups par lane (winrate externe)"):
                matchup_data = []
                for role in roles:
                    mc = f"matchup_wr_{role}"
                    if mc in df_full.columns:
                        wr = df_full.iloc[idx].get(mc, 0.5)
                        if pd.notna(wr) and wr != 0.5:
                            blue_name = df_full.iloc[idx].get(f"team_100_{role}_champion_name", "?")
                            red_name = df_full.iloc[idx].get(f"team_200_{role}_champion_name", "?")
                            adv = "🔵" if wr > 0.5 else "🔴" if wr < 0.5 else "="
                            matchup_data.append({
                                "Lane": role_labels[role],
                                "Blue": blue_name,
                                "Red": red_name,
                                "WR Blue": f"{wr*100:.1f}%",
                                "Avantage": adv,
                            })
                if matchup_data:
                    st.dataframe(pd.DataFrame(matchup_data), use_container_width=True, hide_index=True)
                else:
                    st.info("Donnees de matchup non disponibles pour ce match.")

        st.markdown("---")

        # For timeline models: show gold diffs with sliders
        gold_overrides = {}
        if vector_type != "draft":
            minute = vector_type.replace("at", "")
            st.subheader(f"Gold à @{minute} min")
            st.markdown("Ajustez les valeurs de gold pour voir l'impact sur la prédiction :")

            gold_diff_col = f"gold_diff_at_{minute}"
            if gold_diff_col in match_features.columns:
                original_gold = float(match_features[gold_diff_col].iloc[0])
                gold_overrides[gold_diff_col] = st.slider(
                    f"Gold diff total @{minute}min",
                    min_value=-10000,
                    max_value=10000,
                    value=int(original_gold),
                    step=100,
                    key="gold_diff_slider",
                )

            # Per-role gold sliders in expander
            roles = ["top", "jungle", "mid", "adc", "support"]
            with st.expander("Gold par rôle (avancé)"):
                for role in roles:
                    col_100 = f"team_100_{role}_gold_at_{minute}"
                    col_200 = f"team_200_{role}_gold_at_{minute}"
                    if col_100 in match_features.columns and col_200 in match_features.columns:
                        c1, c2 = st.columns(2)
                        with c1:
                            val_100 = float(match_features[col_100].iloc[0])
                            gold_overrides[col_100] = st.number_input(
                                f"Blue {role} gold", value=int(val_100), step=100, key=f"blue_{role}_gold"
                            )
                        with c2:
                            val_200 = float(match_features[col_200].iloc[0])
                            gold_overrides[col_200] = st.number_input(
                                f"Red {role} gold", value=int(val_200), step=100, key=f"red_{role}_gold"
                            )

        # Apply overrides
        match_input = match_features.copy()
        for col, val in gold_overrides.items():
            if col in match_input.columns:
                match_input[col] = val

        # Predict
        X_input_scaled = safe_transform(scaler, match_input)
        prediction = model.predict(X_input_scaled)[0]
        proba = model.predict_proba(X_input_scaled)[0]

        blue_win_prob = float(proba[1])
        red_win_prob = float(proba[0])
        predicted_winner = "Blue" if prediction == 1 else "Red"
        true_winner = "Blue" if true_label == 1 else "Red"

        st.markdown("---")

        # Results
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Prédiction", f"{predicted_winner} Win")
        with col2:
            st.metric("Résultat réel", f"{true_winner} Win")
        with col3:
            correct = predicted_winner == true_winner
            st.metric("Correct ?", "✅ Oui" if correct else "❌ Non")

        # Gauge
        from components.prediction_gauge import render_prediction_gauge
        render_prediction_gauge(blue_win_prob, title=f"Probabilité – {vt['name']}")

        # Confidence bar
        st.markdown(f"""
        | Équipe | Probabilité |
        |--------|-------------|
        | 🔵 Blue | **{blue_win_prob*100:.1f}%** |
        | 🔴 Red  | **{red_win_prob*100:.1f}%** |
        """)
