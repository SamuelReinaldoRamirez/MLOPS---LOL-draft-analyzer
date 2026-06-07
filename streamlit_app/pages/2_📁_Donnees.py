"""
Page 2 - Présentation des données
"""
import streamlit as st
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

STREAMLIT_APP_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(STREAMLIT_APP_DIR))
sys.path.insert(1, str(STREAMLIT_APP_DIR.parent / "src" / "collect_data"))

from config import COLORS, html, PROJECT_ROOT

st.set_page_config(page_title="Données - LoL Draft Predictor", page_icon="📁", layout="wide")

st.title("📁 Présentation des Données")

# ============================
# Charger les données
# ============================
from utils.data_loader import (
    get_match_count,
    get_timeline_match_count,
    get_winrate_by_side,
    get_average_game_duration,
    get_database_tables_info,
    load_test_with_summoner,
    load_timeline_data_parquet,
)

tab1, tab2, tab3 = st.tabs(["📋 Vue d'ensemble", "🔍 Exploration", "📊 Visualisations"])

# ============================
# TAB 1 - Vue d'ensemble
# ============================
with tab1:
    st.header("Vue d'ensemble du dataset")

    # Métriques globales
    try:
        match_count = get_match_count()
        timeline_count = get_timeline_match_count()
        side_stats = get_winrate_by_side()
        avg_duration = get_average_game_duration()
        data_ok = True
    except Exception as e:
        st.error(f"Erreur chargement BDD : {e}")
        data_ok = False

    if data_ok:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Matchs totaux", f"{match_count:,}")
        with col2:
            coverage = timeline_count / match_count * 100 if match_count > 0 else 0
            st.metric("Matchs avec timeline", f"{timeline_count:,}", delta=f"{coverage:.0f}% couverture")
        with col3:
            st.metric("Blue Side WR", f"{side_stats['blue_winrate']*100:.1f}%")
        with col4:
            st.metric("Durée moyenne", f"{avg_duration:.1f} min")

    st.markdown("---")

    # Structure de la BDD
    st.subheader("Structure de la base de données")

    try:
        tables_info = get_database_tables_info()

        table_summary = pd.DataFrame([
            {"Table": name, "Lignes": f"{info['row_count']:,}", "Colonnes": len(info["columns"])}
            for name, info in tables_info.items()
        ])
        st.dataframe(table_summary, use_container_width=True, hide_index=True)

        with st.expander("Détail des colonnes par table"):
            for name, info in tables_info.items():
                st.markdown(f"**{name}** ({info['row_count']:,} lignes, {len(info['columns'])} colonnes)")
                st.code(", ".join(info["columns"]), language=None)
    except Exception as e:
        st.warning(f"Impossible de charger les infos BDD : {e}")

    st.markdown("---")

    # Fichiers de données traités
    st.subheader("Fichiers de données traités")

    processed_dir = PROJECT_ROOT / "data" / "processed"
    if processed_dir.exists():
        files = sorted(processed_dir.glob("*.parquet"))
        file_info = []
        for f in files:
            size_mb = f.stat().st_size / (1024 * 1024)
            file_info.append({"Fichier": f.name, "Taille": f"{size_mb:.1f} MB"})
        if file_info:
            st.dataframe(pd.DataFrame(file_info), use_container_width=True, hide_index=True)

# ============================
# TAB 2 - Exploration
# ============================
with tab2:
    st.header("Exploration du dataset")

    dataset_choice = st.selectbox(
        "Choisir un dataset à explorer",
        ["Test set (summoner stats)", "Timeline multi-timestamp"],
    )

    if dataset_choice == "Test set (summoner stats)":
        df = load_test_with_summoner()
    else:
        df = load_timeline_data_parquet()

    if df.empty:
        st.warning("Dataset vide ou introuvable.")
    else:
        st.markdown(f"**Shape** : `{df.shape[0]:,}` lignes × `{df.shape[1]}` colonnes")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Types de données**")
            type_counts = df.dtypes.value_counts()
            type_df = pd.DataFrame({
                "Type": [str(t) for t in type_counts.index],
                "Nombre": type_counts.values,
            })
            st.dataframe(type_df, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("**Valeurs manquantes**")
            missing = df.isnull().sum()
            missing_pct = (missing / len(df) * 100)
            missing_df = pd.DataFrame({
                "Colonne": missing[missing > 0].index,
                "Manquantes": missing[missing > 0].values,
                "%": missing_pct[missing > 0].values.round(2),
            })
            if missing_df.empty:
                st.success("Aucune valeur manquante !")
            else:
                st.dataframe(missing_df.head(20), use_container_width=True, hide_index=True)

        st.markdown("---")

        st.subheader("Aperçu (5 premières lignes)")
        st.dataframe(df.head(), use_container_width=True)

        st.subheader("Statistiques descriptives")
        # Show only numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) > 20:
            selected = st.multiselect(
                "Sélectionner les colonnes à décrire",
                numeric_cols,
                default=numeric_cols[:10],
            )
        else:
            selected = numeric_cols

        if selected:
            st.dataframe(df[selected].describe().T, use_container_width=True)

# ============================
# TAB 3 - Visualisations
# ============================
with tab3:
    st.header("Visualisations")

    # Load test data for visualizations
    df_test = load_test_with_summoner()
    if df_test.empty:
        st.warning("Données test introuvables.")
        st.stop()

    viz_choice = st.selectbox(
        "Choisir une visualisation",
        [
            "Win rate par côté (Blue vs Red)",
            "Distribution de la durée des matchs",
            "Champions les plus joués",
            "Corrélation des features principales",
        ],
    )

    if viz_choice == "Win rate par côté (Blue vs Red)":
        try:
            side_stats = get_winrate_by_side()
            fig = go.Figure(data=[
                go.Bar(
                    x=["Blue Side", "Red Side"],
                    y=[side_stats["blue_winrate"] * 100, side_stats["red_winrate"] * 100],
                    marker_color=[COLORS["blue_team"], COLORS["red_team"]],
                    text=[f"{side_stats['blue_winrate']*100:.1f}%", f"{side_stats['red_winrate']*100:.1f}%"],
                    textposition="auto",
                )
            ])
            fig.update_layout(
                title="Win Rate par côté",
                yaxis_title="Win Rate (%)",
                yaxis_range=[45, 55],
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Erreur : {e}")

    elif viz_choice == "Distribution de la durée des matchs":
        if "game_duration" in df_test.columns:
            duration_min = df_test["game_duration"] / 60
            fig = px.histogram(
                duration_min,
                nbins=50,
                title="Distribution de la durée des matchs",
                labels={"value": "Durée (minutes)", "count": "Nombre de matchs"},
                color_discrete_sequence=[COLORS["gold_accent"]],
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Durée min", f"{duration_min.min():.1f} min")
            with col2:
                st.metric("Durée médiane", f"{duration_min.median():.1f} min")
            with col3:
                st.metric("Durée max", f"{duration_min.max():.1f} min")

    elif viz_choice == "Champions les plus joués":
        # Count champion occurrences across all roles
        champ_cols = [c for c in df_test.columns if "champion_id" in c and ("team_100" in c or "team_200" in c)]
        if champ_cols:
            all_champs = pd.concat([df_test[c] for c in champ_cols], ignore_index=True)
            top_champs = all_champs.value_counts().head(20)
            fig = px.bar(
                x=top_champs.values,
                y=[str(c) for c in top_champs.index],
                orientation="h",
                title="Top 20 Champions les plus joués (par ID)",
                labels={"x": "Nombre d'apparitions", "y": "Champion ID"},
                color_discrete_sequence=[COLORS["gold_accent"]],
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Colonnes champion_id non trouvées dans le dataset.")

    elif viz_choice == "Corrélation des features principales":
        # Identify key features for correlation
        key_features = [
            "team_100_win",
            "role_winrate_diff",
            "mastery_diff",
            "streak_momentum_diff",
            "role_specialization_diff",
        ]
        available = [f for f in key_features if f in df_test.columns]

        if len(available) >= 2:
            corr = df_test[available].corr()
            fig = px.imshow(
                corr,
                text_auto=".2f",
                title="Matrice de corrélation (features principales)",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                width=700,
                height=500,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Pas assez de features clés disponibles pour la corrélation.")
