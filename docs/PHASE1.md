# Phase 1 — Base reproductible : objectifs, KPIs et setup

Ce document décrit le périmètre de la **Phase 1** du projet *LoL Draft
Predictor* : établir une base **reproductible** (infra + tests) au-dessus des
modèles existants.

## 1. Objectifs

| # | Objectif                                                              | Statut |
|---|-----------------------------------------------------------------------|--------|
| 1 | Stack reproductible via Docker Compose + `.env.example`               | OK     |
| 2 | API d'inférence FastAPI (`/health`, `/models`, `/predict/*`, stats)   | OK     |
| 3 | Suite de tests qui tourne **sans Docker ni DB** (modèle/DB mockés)    | OK     |
| 4 | Hygiène dépôt : pas de secrets en clair, dump volumineux séparé       | OK     |

Le **KPI applicatif Phase 1** est la *reproductibilité* : la stack démarre et
`python -m pytest -q` est vert, sans dépendance à des données live ou à un
secret. L'amélioration des métriques modèles n'est pas un objectif Phase 1.

## 2. KPIs modèles (baseline)

Métriques de référence des modèles servis (source : `model_*.pkl` + README) :

| Modèle  | Accuracy | AUC   | Type     |
|---------|----------|-------|----------|
| Draft   | 54.0%    | 0.555 | XGBoost  |
| @5min   | 65.4%    | 0.719 | LightGBM |
| @10min  | 72.0%    | 0.797 | XGBoost  |
| @15min  | 78.0%    | 0.864 | XGBoost  |
| @20min  | 79.9%    | 0.885 | XGBoost  |

Les modèles `@min` s'améliorent logiquement avec le temps de jeu (plus
d'information disponible). Le modèle `draft` (pré-game) est volontairement
proche du hasard : prédire l'issue depuis le seul draft est difficile.

## 3. Environnement reproductible

### Prérequis
- Docker + Docker Compose
- (Pour les tests) Python 3.11+ avec les dépendances de `api/requirements.txt`

### Démarrage

```bash
cp .env.example .env                 # placeholders -> éditer en local
docker compose up -d                 # postgres + streamlit + api
./scripts/seed_models.sh             # copie les modèles depuis le projet source
```

### Fichiers d'environnement
- `.env.example` et `database/.env.example` ne contiennent que des
  **placeholders** (ex. `change_me_in_local_env`). Ne jamais committer de
  vrais secrets ; les vrais `.env` sont locaux et git-ignorés.
- `RIOT_API_KEY` est laissé **vide** dans `.env.example`. Il n'est nécessaire
  que pour la **collecte de données live**, qui est **hors périmètre Phase 1**.

### Données
- Le dump PostgreSQL `database/lol_draft.dump` (~747 Mo) est **fourni
  séparément et git-ignoré**. Placez-le dans `database/` avant de démarrer le
  service `postgres` (le service `restore.sh` le restaure automatiquement).
- Le service DB est défini **uniquement** dans le `docker-compose.yml` racine
  (l'ancien `database/docker-compose.yml` redondant a été supprimé).

## 4. Tests

La suite tourne **sans Docker ni base de données** : le chargement des modèles
est remplacé par un petit modèle *fixture* en mémoire, et le helper DB est
monkeypatché.

```bash
pip install -r api/requirements.txt   # inclut pytest + httpx
python -m pytest -q
```

Couverture :
- `api/tests/` — `/health` (DB up/down), `/models`, `/predict/at/{minute}`
  (succès, minute invalide, modèle absent), `/predict/draft` (succès,
  validation, modèle absent).
- `training/tests/` — `build_timeline_features` : forme des features, valeurs
  dérivées, gestion des valeurs manquantes, importabilité du module.

## 5. Endpoint `/predict/draft` — features réelles (câblé)

La route `POST /predict/draft` charge le modèle via le même chemin que les
autres routes (`MODEL_FILES["draft"]`) et respecte le contrat documenté
(`DraftPredictionRequest` : 10 noms de champions).

**Câblé :** la route construit désormais les **vraies features côté champions**
au lieu de tout remplir à `0`. Le mapping blue → `team_100`, red → `team_200`
est appliqué, les noms de champions sont normalisés et résolus en `champion_id`
via un fichier statique `api/app/champion_id_map.json` (généré **une fois**
depuis la DB ; aucune DB ni clé Riot n'est requise à l'inférence). La ligne
obtenue passe dans `app.feature_builder.add_all_model_features(df, model_data)`,
qui dérive — depuis les tables de lookup embarquées **dans** `model_draft.pkl`
(`external_data.wr_dict` / `matchup_dict`, `synergy_data.synergy_wr` /
`counter_wr`) — les features suivantes :

- winrate / tier / pickrate externes par lane + agrégats et différentiels ;
- winrate de matchup par lane + avantage moyen/min/max ;
- scores de synergie et de counter par équipe + `synergy_diff`, `counter_diff`,
  `draft_advantage`.

Soit **~69 des 153 features** désormais réelles. La prédiction **varie** avec la
composition (ex. deux drafts distincts → 0.536 vs 0.725 de probabilité côté
bleu), au lieu d'être constante.

**Limite assumée :** les **~84 features niveau invocateur** (winrate par rôle,
mastery, streaks, winrate récent par champion, …) nécessitent les **PUUID par
joueur** qu'une requête de draft ne porte pas. Elles restent donc à leurs
**valeurs neutres par défaut** — exactement ce que fait le flux Streamlit
d'origine en l'absence de PUUID (`_add_summoner_stats_defaults`). L'accuracy
propre du modèle de draft est **~0.54** par nature (prédire l'issue depuis le
seul draft est difficile).

### Suivi Phase 1 (follow-up)
- L'image API en production doit être reconstruite (`docker compose build api`)
  pour servir cette logique câblée.
- Ajouter dans `train_all_models.py` la fonction d'entraînement du modèle de
  draft (actuellement seuls les modèles `@min` y sont entraînés).
