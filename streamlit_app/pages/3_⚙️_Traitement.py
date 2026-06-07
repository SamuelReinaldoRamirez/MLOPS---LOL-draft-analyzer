"""
Page 3 - Traitement des donnees + selecteur de vecteur d'entree
"""
import streamlit as st
import sys
from pathlib import Path

STREAMLIT_APP_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(STREAMLIT_APP_DIR))

from config import COLORS, html, VECTOR_TYPES, MODEL_BENCHMARKS

st.set_page_config(page_title="Traitement - LoL Draft Predictor", page_icon="⚙️", layout="wide")

st.title("⚙️ Traitement des Donnees")

# ============================
# Section 1 - Pipeline
# ============================
st.header("1. Pipeline de donnees")

st.markdown("""
Le pipeline transforme les donnees brutes en vecteurs de features pour les modeles ML,
en combinant nos donnees de matchs avec des statistiques externes de dpm.lol.
""")

st.code("""
┌──────────────┐     ┌────────────────────┐     ┌──────────────┐     ┌──────────────┐
│ Base SQLite  │ ──► │ Feature Engineering│ ──► │   Vecteur    │ ──► │  Modele ML   │
│ (305k matchs)│     │                    │     │  d'entree    │     │  (XGBoost/   │
│  7 tables    │     │ • Winrates externes│     │  (153-186    │     │   LightGBM)  │
│              │     │ • Matchups par lane│     │   features)  │     │              │
│  dpm.lol     │     │ • Synergies/Counter│     │              │     │  Prediction  │
│  (winrates)  │     │ • Summoner stats   │     │              │     │  Win/Loss    │
│              │     │ • Timeline gold/CS │     │              │     │              │
└──────────────┘     └────────────────────┘     └──────────────┘     └──────────────┘
""", language=None)

st.markdown("""
**Etapes cles :**
1. **Export** des donnees brutes depuis SQLite (matchs, joueurs, timelines)
2. **Enrichissement** avec les winrates externes de dpm.lol (winrates simples, matchups, synergies)
3. **Feature engineering** : creation de 153 a 186 features selon le vecteur choisi (V3)
4. **Standardisation** (`StandardScaler`) avant entrainement
5. **Split temporel** : train (80%) / test (20%) pour **tous** les modeles
""")

st.markdown("---")

# ============================
# Section 2 - Feature Engineering
# ============================
st.header("2. Feature Engineering")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Features Draft (V3)")
    st.markdown("""
    **Winrates externes (dpm.lol) :**
    - **ext_wr** : winrate du champion dans ce role (10 features)
    - **ext_tier** : tier encode S+=6...D=1 (10 features)
    - **ext_pickrate** : popularite du champion (10 features)
    - **ext_avg_wr/tier** : moyennes par equipe (4 features)
    - **ext_wr_diff, ext_tier_diff** : ecarts entre equipes

    **Summoner stats temporelles (93 features) :**
    - **role_pct/winrate** : specialisation et winrate par role (20)
    - **role_kda/vision** : KDA et vision score par role (20)
    - **streak/mastery** : series et maitrise champion (20)
    - **champ_recent_wr** : winrate recent sur le champion (10)
    - **Agregats equipe** et **differentiels** (14)
    - Calculees uniquement sur les matchs **anterieurs** (temporel)
    """)

    st.subheader("⚔️ Features Matchup")
    st.markdown("""
    - **matchup_wr_{pos}** : WR du duel par lane (5 features)
    - **matchup_advantage_{pos}** : WR - 0.5 (5 features)
    - **avg/max/min_matchup_advantage** : agregats
    """)

with col2:
    st.subheader("🤝 Features Synergies / Counters")
    st.markdown("""
    - **Synergy score** : synergie intra-equipe (nos 305k matchs, min 30 games)
    - **Counter score** : counter-pick inter-equipes
    - **Draft advantage** : synergy_diff + counter_diff
    - **ext_synergy** : synergies depuis dpm.lol (34k paires)
    """)

    st.subheader("⏱️ Features Timeline (in-game)")
    st.markdown("""
    - **Gold par role** a @5, @10, @15 ou @20 min (10 features)
    - **Gold diff par role** a chaque timestamp (5 features)
    - **Gold diff total** a chaque timestamp
    - **CS par role** a @10 min (pour @10 et au-dela)
    - **CS diff par role** (5 features derivees)
    """)

st.markdown("---")

# ============================
# Section 2b - Winrates externes (NEW)
# ============================
st.header("3. Donnees externes (dpm.lol)")

st.markdown("""
Les modeles integrent desormais des statistiques de winrate scrappees depuis **dpm.lol**,
une source de donnees communautaire couvrant des millions de parties.
""")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("📈 Winrates simples")
    st.markdown("""
    Pour chaque champion dans son role :
    - **Winrate** global (ex: Jinx ADC = 51.6%)
    - **Tier** (S+, S, A, B, C, D)
    - **Pickrate** et nombre de games
    - Source : `TOUT/TOUT` (tous rangs, tous serveurs)
    - **212 champion-role** entries chargees
    """)

with col2:
    st.subheader("⚔️ Matchups par lane")
    st.markdown("""
    Winrate specifique de chaque duel par lane :
    - Top vs Top, Mid vs Mid, etc.
    - Ex: Darius vs Garen = 55.97% pour Darius
    - Couvre les **5 lanes** (top, jungle, mid, adc, support)
    - **41,145 matchups** charges
    """)

with col3:
    st.subheader("🤝 Synergies externes")
    st.markdown("""
    Winrate quand deux champions jouent ensemble :
    - Par role (top synergy, mid synergy, etc.)
    - Ex: Jinx + Nami = 54.2%
    - **34,314 synergies** chargees
    - Complemente nos synergies calculees sur nos matchs
    """)

st.markdown("---")

st.subheader("4. Features derivees")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Features par equipe/position :**")
    st.markdown("""
    - `ext_wr_{team}_{pos}` : winrate externe du champion a ce poste
    - `ext_tier_{team}_{pos}` : tier encode (S+=6, S=5, ..., D=1)
    - `ext_pickrate_{team}_{pos}` : popularite du champion
    - `matchup_wr_{pos}` : winrate du duel sur la lane
    - `matchup_advantage_{pos}` : avantage matchup (WR - 0.5)
    """)

with col2:
    st.markdown("**Features agregees :**")
    st.markdown("""
    - `ext_avg_wr_{team}` : winrate moyenne de l'equipe
    - `ext_wr_diff` : difference de WR externe entre equipes
    - `ext_tier_diff` : difference de tier moyen
    - `avg_matchup_advantage` : avantage matchup moyen sur 5 lanes
    - `ext_synergy_diff` : difference de synergie externe
    - `draft_advantage` : synergie + counter advantage
    - `{pos}_gold_diff_at_X` : avantage gold par lane
    """)

st.markdown("---")

# ============================
# Section - Fuite de données
# ============================
st.header("5. Audit des fuites de donnees et correction V3")

st.error("""
**Fuite detectee en V1, corrigee en V2, resolue en V3**

Les summoner stats (role_winrate_diff, streak, mastery, KDA, etc.) presentaient une **fuite de donnees massive** en V1 :
- Correlation avec la target : **0.81** (train) vs **0.02** (test)
- Les stats incluaient le resultat du match courant dans le calcul du winrate
- **V2** : les 93 features ont ete **retirees** du pipeline
- **V3** : les 93 features sont **reintegrees** avec un calcul **temporel** (seuls les matchs anterieurs sont utilises)
""")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("""
    **V1 — Fuite massive :**
    - `role_winrate_diff` corr=0.81 train, 0.02 test
    - `streak_momentum_diff` corr=0.37 train, 0.008 test
    - 93 features contaminant le modele
    - Draft accuracy : 83.9% (faux)
    """)

with col2:
    st.markdown("""
    **V2 — Suppression :**
    - 93 features retirees
    - Champion/Ban/Spell IDs retires
    - Split temporel pour **tous** les modeles
    - Regularisation renforcee
    - Draft accuracy : 53.6% (honnete)
    """)

with col3:
    st.markdown("""
    **V3 — Correction temporelle :**
    - 93 features **reintegrees**
    - Stats calculees par **bucket mensuel**
    - Seuls les matchs **anterieurs** au mois courant
    - Correlation train/test coherente
    - Draft accuracy : 54.0% (honnete + enrichi)
    """)

st.markdown("---")

# ============================
# Section - Selecteur de vecteur
# ============================
st.header("6. Selection du vecteur d'entree")

st.markdown("""
Choisissez le vecteur d'entree qui determine quelles donnees sont utilisees pour la prediction.
Ce choix impacte les pages **Modeles** et **Resultats**.
""")

# Initialize session state
if "vector_type" not in st.session_state:
    st.session_state.vector_type = "draft"

# Radio selector
vector_options = list(VECTOR_TYPES.keys())
vector_labels = [
    f"{VECTOR_TYPES[k]['name']} ({VECTOR_TYPES[k]['nb_features']} features) – {MODEL_BENCHMARKS[k]['accuracy']*100:.1f}% accuracy"
    for k in vector_options
]

selected_idx = vector_options.index(st.session_state.vector_type)

selected_label = st.radio(
    "Vecteur d'entree",
    vector_labels,
    index=selected_idx,
    help="Le vecteur determine les features utilisees par le modele.",
)

# Update session state
selected_key = vector_options[vector_labels.index(selected_label)]
st.session_state.vector_type = selected_key

# Display info about selected vector
vt = VECTOR_TYPES[selected_key]
bm = MODEL_BENCHMARKS[selected_key]

st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Vecteur selectionne", vt["name"])
with col2:
    st.metric("Nombre de features", vt["nb_features"])
with col3:
    st.metric("Accuracy test", f"{bm['accuracy']*100:.1f}%")

st.info(f"**Description** : {vt['description']}")
st.markdown(f"**Algorithme** : {bm['model_type']}")

# Show extra features for non-draft vectors
if vt["extra_features"]:
    with st.expander(f"Features additionnelles ({len(vt['extra_features'])} features)"):
        cols = st.columns(3)
        for i, feat in enumerate(vt["extra_features"]):
            with cols[i % 3]:
                st.code(feat, language=None)

st.markdown("---")

# Summary comparison table
st.subheader("Comparaison des vecteurs")

comparison_data = []
for key in vector_options:
    v = VECTOR_TYPES[key]
    b = MODEL_BENCHMARKS[key]
    comparison_data.append({
        "Vecteur": v["name"],
        "Features": v["nb_features"],
        "Algorithme": b["model_type"],
        "Accuracy": f"{b['accuracy']*100:.1f}%",
        "Description": v["description"],
    })

import pandas as pd
st.dataframe(pd.DataFrame(comparison_data), use_container_width=True, hide_index=True)

st.success(f"Vecteur **{vt['name']}** selectionne. Rendez-vous sur les pages **Modeles** et **Resultats** pour voir les details.")
