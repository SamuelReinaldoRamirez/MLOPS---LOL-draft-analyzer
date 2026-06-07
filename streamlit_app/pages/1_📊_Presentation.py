"""
Page 1 - Présentation du projet
"""
import streamlit as st
import sys
from pathlib import Path

STREAMLIT_APP_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(STREAMLIT_APP_DIR))

from config import COLORS, html

st.set_page_config(page_title="Présentation - LoL Draft Predictor", page_icon="🎮", layout="wide")

st.title("🎮 League of Legends – Draft Predictor")

st.markdown("""
## Prédiction de victoire basée sur le Draft et l'Early Game

**Projet DataScientest – Machine Learning Engineer**
""")

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    **Auteurs :** Aïssam, Samuel, Guilhem

    **Date :** Janvier 2026
    """)
with col2:
    st.markdown("""
    **Formation :** Data Scientist – Promotion Juin MLE25

    **Encadrant :** DataScientest
    """)

st.markdown("---")

# ============================
# 1. Introduction
# ============================
st.header("1. Introduction & Contexte")

st.subheader("1.1 League of Legends – Présentation du jeu")

st.markdown("""
**League of Legends** (LoL) est un jeu vidéo de type **MOBA** (Multiplayer Online Battle Arena) développé par **Riot Games**.
C'est l'un des esports les plus populaires au monde :
""")

st.markdown("""
- 📊 **180+ millions** de joueurs actifs mensuels
- 🏆 **Championnats du monde** regardés par **100M+** de spectateurs
- 💰 **Prize pools** dépassant les **2M$** par tournoi majeur
""")

st.markdown("### Principe du jeu")

st.markdown("""
- **2 équipes de 5 joueurs** s'affrontent sur une carte asymétrique
- Chaque joueur contrôle **1 champion** parmi **160+ personnages uniques**
- **Objectif** : Détruire le **Nexus adverse**
- **Durée moyenne** : **25–35 minutes**
""")

st.markdown("### Les 5 rôles")

roles_df = {
    "Rôle": ["Top", "Jungle", "Mid", "ADC", "Support"],
    "Lane": ["Top Lane", "Jungle", "Mid Lane", "Bot Lane", "Bot Lane"],
    "Description": [
        "Tank ou Bruiser – Frontline",
        "Ganker – Contrôle des objectifs",
        "Mage ou Assassin – Burst damage",
        "Marksman – Dégâts soutenus",
        "Utilitaire – Protection de l'ADC",
    ],
}
st.table(roles_df)

# ============================
# 1.2 Draft
# ============================
st.subheader("1.2 La phase de Draft")

st.markdown("""
Avant chaque partie, les équipes passent par une **phase de draft cruciale** :

1. **Bans** : Chaque équipe bannit **5 champions**
2. **Picks** : Sélection alternée des **10 champions**
3. **Durée** : ~**5 minutes**
""")

st.info("""
Le draft représente **40–60% de l'issue du match** selon les joueurs professionnels.
""")

st.markdown("""
- ✅ **Synergies** : Combinaisons puissantes (ex : *Yasuo + Malphite*)
- ✅ **Counter-picks** : Champions qui dominent d'autres (ex : *Fiora vs Tanks*)
- ✅ **Composition d'équipe** : Damage, tankiness, CC, utility
- ✅ **Matchups de lane**
- ✅ **Meta du patch**
""")

# ============================
# 1.3 Problématique ML
# ============================
st.subheader("1.3 Problématique Machine Learning")

st.success("""
**Peut-on prédire l'issue d'un match League of Legends à partir du draft et des données d'early game ?**
""")

st.markdown("### Objectifs")

st.markdown("""
1. 🎯 **Prédire la victoire** (classification binaire) à différents instants du match
2. 📊 **Identifier les facteurs clés** de victoire (draft, gold, objectifs)
3. 🔍 **Analyser les synergies** et counter-picks de champions
4. ⏱️ **Mesurer l'évolution** de la précision selon le temps de jeu
""")

st.markdown("### Défis")

st.warning("""
- ⚠️ **160+ champions** → espace combinatoire énorme
- ⚠️ **Meta évolutive** (patch toutes les 2 semaines)
- ⚠️ **Facteur humain non observé** (skill individuel, communication)
- ⚠️ **Données temporelles** (timeline) pas toujours disponibles
""")

st.markdown("### Approche multi-modèles")

st.code("""
Data Collection  →  Feature Engineering  →  5 Modeles ML  →  Predictions
     ↓                      ↓                     ↓               ↓
API Riot             Draft features          Draft only      54.0%
dpm.lol Scraping     Winrates externes       @5min gold      65.4%
CommunityDragon      Matchups par lane       @10min gold+CS  72.0%
                     Synergies/Counters      @15min gold     78.0%
                     Summoner stats temp.    @20min gold     79.9%
                     Timeline gold/CS
""", language=None)

st.markdown("### Données")

try:
    from utils.data_loader import get_match_count, get_timeline_match_count
    match_count = get_match_count()
    timeline_count = get_timeline_match_count()
    match_str = f"{match_count:,}"
    timeline_str = f"{timeline_count:,}"
except Exception:
    match_str = "305,000+"
    timeline_str = "164,000+"

st.markdown(f"""
- 📦 **{match_str} matchs** collectés
- ⏱️ **{timeline_str} matchs** avec données timeline
- 🌍 **Région** : EUW (Europe West)
- 🏅 **Elo** : Diamond+ → Challenger
- 📅 **Saison 15 (2025)** – Ranked Solo/Duo
- 🔧 **Sources** : Riot Games API, OP.GG, CommunityDragon
""")
