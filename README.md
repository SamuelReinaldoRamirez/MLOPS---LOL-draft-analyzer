# LoL Draft Predictor — MLOps Infrastructure

Prédiction de l'issue des matchs **League of Legends** par Machine Learning, à
partir du **draft** et des données d'**early game** (timeline). Le projet
emballe ces modèles dans une **stack MLOps reproductible et observable** : 6
services Docker, une API d'inférence FastAPI testée, un tracking MLflow, une CI
GitHub Actions, du monitoring Prometheus/Grafana et un hook de ré-entraînement
gated par le drift.

**Projet DataScientest — Aïssam, Samuel, Guilhem — 2026**

---

## Aperçu architecture (6 services)

Orchestrés par [`docker-compose.yml`](docker-compose.yml) sur le réseau
`lol-net` (volumes nommés `lol_draft_*`) :

| Service      | Port  | Rôle                                                        |
|--------------|-------|-------------------------------------------------------------|
| `postgres`   | 5434  | PostgreSQL 16 — données matchs/timeline (dump restauré)     |
| `streamlit`  | 8501  | Interface web multi-pages                                   |
| `api`        | 8000  | API REST FastAPI — inférence + `/metrics`                   |
| `mlflow`     | 5001  | Serveur de tracking MLflow (backend Postgres)               |
| `prometheus` | 9090  | Scrape des métriques de l'API                               |
| `grafana`    | 3000  | Dashboards (datasource + dashboard provisionnés)            |
| `training`   | —     | Entraînement ML (profil on-demand, log vers MLflow)         |

## Démarrage rapide

```bash
cp .env.example .env          # placeholders -> éditer en local (mots de passe)
make demo                     # pipeline complet : db -> restore -> up -> seed -> train
# ou, manuellement :
docker compose up -d          # postgres + streamlit + api + mlflow (+ prometheus + grafana)
```

> Le dump PostgreSQL `database/lol_draft.dump` (~783 Mo) est **git-ignoré** mais
> **téléchargé automatiquement** depuis DagsHub (md5 vérifié) par
> `scripts/fetch_dump.sh` lors d'un `make demo` / `make restore` — un clone neuf
> n'a donc **rien à placer à la main**. Les modèles `model_*.pkl` (~14,5 Mo) sont
> de même **git-ignorés** mais **DVC-trackés sur DagsHub** et téléchargés
> automatiquement par `scripts/fetch_models.sh` (`make fetch-models`, appelé par
> `make demo`) ; seuls les pointeurs `api/models/*.pkl.dvc` sont commités. Les
> **tests** et la **CI** n'ont besoin ni du dump ni des modèles.

**URLs de démo** (une fois la stack démarrée) :

- Streamlit : http://localhost:8501
- API : http://localhost:8000 — docs : http://localhost:8000/docs — health : http://localhost:8000/health — metrics : http://localhost:8000/metrics
- MLflow : http://localhost:5001
- Prometheus : http://localhost:9090
- Grafana : http://localhost:3000

## Lancer les tests (sans Docker ni DB)

```bash
pip install -r api/requirements.txt -r training/requirements.txt
python -m pytest -q           # 47 tests — modèles + DB mockés, aucun conteneur requis
```

## Les 4 phases MLOps

| Phase | Thème                                   | Doc                          |
|-------|------------------------------------------|------------------------------|
| 1     | Base reproductible + API d'inférence + tests | [`docs/PHASE1.md`](docs/PHASE1.md) |
| 2     | Tracking d'expériences & versioning (MLflow) | [`docs/PHASE2.md`](docs/PHASE2.md) |
| 3     | CI GitHub Actions, orchestration `Makefile`, squelette K8s | [`docs/PHASE3.md`](docs/PHASE3.md) |
| 4     | Monitoring (Prometheus/Grafana), drift (Evidently), auto-retrain | [`docs/PHASE4.md`](docs/PHASE4.md) |

**Pour la soutenance :** [`docs/PRESENTATION.md`](docs/PRESENTATION.md) (mapping
phases → livrables) et [`docs/DEMO.md`](docs/DEMO.md) (runbook de démo pas à
pas). Index complet : [`docs/README.md`](docs/README.md).

---

## Phase 1 — Objectifs & KPIs

Phase 1 établit une **base reproductible** (Docker Compose + `.env.example`),
une **API d'inférence FastAPI** et une **suite de tests** qui tourne **sans
Docker ni base de données** (chargement modèle et DB mockés).

**Objectifs Phase 1**

- Stack reproductible : `docker compose up -d` + `.env.example` → `.env`.
- API d'inférence : `/health`, `/models`, `/predict/draft`, `/predict/at/{min}`,
  `/stats/overview`.
- Tests unitaires exécutables hors Docker (`pytest`), couvrant l'API et le
  feature engineering d'entraînement.
- Hygiène du dépôt : pas de secrets dans les `.env.example`, dump volumineux
  fourni séparément (git-ignoré).

**KPIs modèles (baseline actuelle)**

| Modèle  | Accuracy | AUC   | Type     | Cible Phase 1                |
|---------|----------|-------|----------|------------------------------|
| Draft   | 54.0%    | 0.555 | XGBoost  | Reproduire / servir          |
| @5min   | 65.4%    | 0.719 | LightGBM | Reproduire / servir          |
| @10min  | 72.0%    | 0.797 | XGBoost  | Reproduire / servir          |
| @15min  | 78.0%    | 0.864 | XGBoost  | Reproduire / servir          |
| @20min  | 79.9%    | 0.885 | XGBoost  | Reproduire / servir          |

> Le KPI applicatif Phase 1 est la **reproductibilité** (stack + tests verts),
> pas l'amélioration des métriques modèles.

### Environnement reproductible

```bash
# 1. Variables d'environnement (placeholders only — éditer en local)
cp .env.example .env
cp database/.env.example database/.env   # si utilisé

# 2. Lancer la stack
docker compose up -d            # postgres + streamlit + api
```

Le dump PostgreSQL volumineux (`database/lol_draft.dump`, ~783 Mo) est
**git-ignoré** mais **téléchargé automatiquement** depuis DagsHub par
`make demo`/`make restore` (ou `make fetch-dump` / `./scripts/fetch_dump.sh`
directement). La **collecte de données live** nécessite un
`RIOT_API_KEY` dans un `.env` local (laissé vide dans `.env.example`) et
**sort du périmètre Phase 1**.

### Lancer les tests (sans Docker ni DB)

```bash
# Depuis la racine du projet
pip install -r api/requirements.txt        # inclut pytest + httpx
python -m pytest -q
```

Les tests mockent le chargement des modèles (petit modèle fixture) et la base
de données : aucun conteneur ni PostgreSQL réel n'est requis.

Détails Phase 1 : voir [`docs/PHASE1.md`](docs/PHASE1.md).

---

## Phase 2 — Suivi d'expériences & versioning (MLflow)

La Phase 2 ajoute un **serveur MLflow** pour le *experiment tracking* et le
*model versioning*, **sans casser** la stack ni les tests (qui tournent
toujours sans Docker ni MLflow grâce à un *fallback NO-OP*).

### Lancer MLflow

```bash
cp .env.example .env           # MLFLOW_PORT / MLFLOW_DB / MLFLOW_TRACKING_URI
docker compose up -d mlflow    # démarre postgres (dépendance) + mlflow
```

- **UI MLflow** : http://localhost:5001
- **Backend store** : PostgreSQL (base dédiée `mlflow`, créée au 1er boot).
- **Artifact store** : volume `lol_draft_mlflow_artifacts`.

### Voir les expériences

```bash
docker compose run --rm training python scripts/train_all_models.py --model at10
# Puis dans l'UI (http://localhost:5001) :
#  - Experiment "lol-draft-timeline" : 1 run par modèle (params + metrics)
#  - Onglet "Models" : modèles registry "lol_draft_at{5,10,15,20}" versionnés
```

### Versioning

- **Modèles** : chaque entraînement enregistre une nouvelle **version** dans le
  MLflow Model Registry (`lol_draft_at{minute}`). La promotion de stage
  (Staging/Production) est manuelle dans l'UI.
- **Données + pipeline (DVC)** : `database/lol_draft.dump` est tracké par DVC
  (`database/lol_draft.dump.dvc`, hash MD5 — petit, commité), et `dvc.yaml`
  définit 4 stages reproductibles (`train_at5/10/15/20`) liés à `params.yaml`.
  Les modèles sortent comme outs DVC (`models/model_at{n}.pkl`) et un fichier
  metrics JSON (`models/metrics_at{n}.json`, `cache: false`) est exposé via
  `dvc metrics show`. Remote par défaut : `./.dvc-storage` (local, git-ignoré) ;
  S3/GCS configurables dans `.dvc/config`. Workflow :
  `make dvc-install dvc-track-data dvc-repro dvc-push dvc-metrics`.

### Garantie NO-OP (tests/CI intacts)

Si `MLFLOW_TRACKING_URI` est absent/vide, si `mlflow` n'est pas installé, ou si
le serveur est injoignable, le wrapper `mlflow_tracking.py` devient un **NO-OP**
silencieux : l'entraînement et `python -m pytest -q` fonctionnent sans serveur
MLflow. Cas serveur injoignable : le wrapper **fast-fail** (défauts courts
`MLFLOW_HTTP_REQUEST_MAX_RETRIES=1` / `MLFLOW_HTTP_REQUEST_TIMEOUT=3` + pré-check
TCP ~3 s) — il dégrade en no-op en quelques secondes au lieu de bloquer sur le
backoff REST de MLflow. Prouvé par `training/tests/test_mlflow_tracking.py`.

Détails Phase 2 : voir [`docs/PHASE2.md`](docs/PHASE2.md).

---

## Phase 3 — CI, orchestration e2e & Kubernetes complet

La **Phase 3** automatise par-dessus les Phases 1 et 2 : une **CI GitHub
Actions**, une **orchestration locale** du pipeline complet (`Makefile`) et un
**déploiement Kubernetes production-ready** (32 ressources, validé schema-side
par `kubeconform`).

### CI (GitHub Actions)

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) — sur **push / PR**,
trois jobs réutilisant les commandes locales :

- **lint** : `ruff check . --exit-zero` (config [`.ruff.toml`](.ruff.toml)) —
  non bloquant au 1er passage (on ne réécrit pas le code existant).
- **test** : install `api/requirements.txt` + `training/requirements.txt` puis
  `python -m pytest -q` (47 tests, **sans** Docker ni DB ni dump : tout est mocké).
- **build** : `docker compose build` (toutes les images) — dépend de `test`.

Aucun secret ni le dump de 747 Mo ne sont requis en CI.

### Orchestration e2e (`Makefile`)

Wrappers fins au-dessus de `docker compose` / scripts existants. Le pipeline
part du **dump existant** (pas de collecte live Riot).

```bash
make demo     # env -> db -> restore -> stack up -> seed models -> train
make test     # pytest (sans Docker/DB)
make up       # docker compose up -d
make down     # arrêt (garde les données) ;  make clean = + suppression volumes
make help     # liste toutes les cibles
```

Cibles : `env up up-db restore seed train demo test lint build logs ps down clean`.
Cibles **DVC** : `dvc-install dvc-status dvc-track-data dvc-push dvc-pull dvc-repro dvc-dag dvc-metrics`.
Cibles **Kubernetes** : `k8s-validate k8s-apply k8s-delete k8s-status`.
La **collecte live Riot** reste **optionnelle / hors démo** (clé `RIOT_API_KEY`
dans un `.env` local uniquement).

### Kubernetes complet (déployable)

[`k8s/`](k8s/) — **32 ressources** organisées en kustomize 3 niveaux
(`base` + `monitoring` + `ingress`) :

- **Workloads** : Postgres `StatefulSet`+PVC 10 Gi, API `Deployment`+HPA 2→6,
  Streamlit `Deployment`+HPA 2→4, MLflow `Deployment`+PVC 5 Gi.
- **Observabilité** : Prometheus (TSDB 5 Gi, scrape DNS Service) + Grafana
  (datasource + dashboard `lol_api_overview.json` auto-provisionnés via
  `configMapGenerator` qui lit le JSON existant — pas de duplication).
- **Sécurité** : `Ingress` nginx + TLS cert-manager (Let's Encrypt),
  `NetworkPolicy` default-deny + 6 allows ciblées, pods en `runAsNonRoot` +
  `readOnlyRootFilesystem` + `capabilities: drop ALL`.
- **Config / secrets** : un `ConfigMap` + un `Secret` (template), injectés
  par `envFrom:` dans chaque Deployment — pas de plaintext, pas de duplication.

Validation offline (sans cluster) :
```bash
make k8s-validate   # kubeconform: 32/32 valid
```

Déploiement réel (pré-requis : ingress-nginx, cert-manager, metrics-server,
CNI avec NetworkPolicy ; images poussées en registry) :
```bash
make k8s-apply      # kubectl apply -k k8s/ (avec confirmation)
make k8s-status     # pods / services / ingress / hpa / pvc
```

Détails et runbooks dans [`k8s/README.md`](k8s/README.md). La **démo
Phase-3 continue de tourner sur Docker Compose** — K8s est l'option pour
l'environnement cible.

Détails Phase 3 : voir [`docs/PHASE3.md`](docs/PHASE3.md).

---

## Phase 4 — Monitoring, drift & mises à jour automatisées

La **Phase 4** ajoute l'**observabilité** (Prometheus + Grafana), la
**détection de drift** (Evidently) et un **hook de ré-entraînement automatisé**,
**sans casser** la stack ni les tests (tout dégrade en NO-OP si une dépendance
optionnelle manque).

### Métriques Prometheus sur l'API

L'API FastAPI est instrumentée (`prometheus-fastapi-instrumentator`) et expose
`GET /metrics` (format Prometheus) : compteur/latence des requêtes HTTP + un
compteur métier `lol_predictions_total{model="..."}` incrémenté à chaque
prédiction. L'instrumentation est **fail-safe** : si les paquets Prometheus sont
absents, l'API et les tests tournent quand même (route `/metrics` en fallback).

### Prometheus + Grafana

Services ajoutés au [`docker-compose.yml`](docker-compose.yml) sur `lol-net` :

```bash
cp .env.example .env          # GRAFANA_ADMIN_PASSWORD, PROMETHEUS_PORT, GRAFANA_PORT
make monitoring-up            # api + prometheus + grafana
# Prometheus : http://localhost:9090   (requête: lol_predictions_total)
# Grafana    : http://localhost:3000   (login = creds du .env)
#   → Dashboard "LoL Draft Predictor — API & Predictions"
```

- Prometheus scrape `api:8000/metrics` —
  [`monitoring/prometheus/prometheus.yml`](monitoring/prometheus/prometheus.yml).
- Grafana : datasource + dashboard **provisionnés**
  ([`monitoring/grafana/`](monitoring/grafana/)) ; identifiants admin **via env**
  (jamais en dur).

### Détection de drift (Evidently)

[`training/scripts/drift_report.py`](training/scripts/drift_report.py) construit
un rapport de data-drift Evidently (HTML + JSON sous
`monitoring/drift/reports/`). Il **tourne sur données synthétiques** par défaut
(pas besoin du dump de 747 Mo) ; la lecture PostgreSQL n'est tentée que si
`DRIFT_USE_DB=1` et que la base est joignable.

```bash
make drift                                       # référence vs current synthétiques
python training/scripts/drift_report.py --drift  # force un current "drifté" (démo)
```

### Hook de ré-entraînement automatisé

[`scripts/auto_retrain.py`](scripts/auto_retrain.py) (version nettoyée de
`wait_and_retrain.py`) : lance la détection de drift, et **si**
`drift_share > DRIFT_THRESHOLD`, déclenche le ré-entraînement via l'entrypoint
existant (`docker compose run --rm training ...`). Sinon : NO-OP. Idempotent,
sûr, et **importable/testable sans DB live** (trigger d'entraînement injecté/mocké).

```bash
python scripts/auto_retrain.py --force-drift   # démo: force la décision RETRAIN
python scripts/auto_retrain.py --dry-run       # décide sans entraîner
make retrain                                    # wrapper dry-run
```

Tests (sans Docker/DB, dans la suite pytest) : `api/tests/test_metrics.py`,
`training/tests/test_drift_report.py`, `training/tests/test_auto_retrain.py`.

Détails Phase 4 : voir [`docs/PHASE4.md`](docs/PHASE4.md).

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Docker Compose                         │
│                                                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐              │
│  │ Streamlit │  │  FastAPI   │  │ Training │              │
│  │  :8501    │  │  :8000    │  │ (on-demand)│             │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘            │
│        │              │              │                    │
│        ▼              ▼              ▼                    │
│  ┌──────────────────────────────────────┐                │
│  │         PostgreSQL 16  :5434         │                │
│  └──────────────────────────────────────┘                │
│        │              │              │                    │
│  ┌─────▼──────────────▼──────────────▼────┐              │
│  │       Volume: lol_draft_models         │              │
│  │  model_draft.pkl  model_at5.pkl  ...   │              │
│  └────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

## Services

| Service      | Port  | Description                              |
|-------------|-------|------------------------------------------|
| `postgres`  | 5434  | PostgreSQL 16 — base de données          |
| `streamlit` | 8501  | Interface Streamlit multi-pages          |
| `api`       | 8000  | API REST FastAPI (inférence + `/metrics`)|
| `mlflow`    | 5001  | MLflow tracking server (Phase 2)         |
| `training`  | —     | Entraînement ML (profil on-demand)       |
| `prometheus`| 9090  | Scraping des métriques API (Phase 4)     |
| `grafana`   | 3000  | Dashboards (Phase 4, creds via `.env`)   |

## Quick Start

### 1. Configurer l'environnement

```bash
cp .env.example .env
# Éditer .env si besoin (mot de passe, ports)
```

### 2. Lancer la base de données

```bash
# Télécharge lol_draft.dump depuis DagsHub s'il manque (md5 vérifié)
./scripts/fetch_dump.sh
docker compose up -d postgres
```

### 3. Lancer tous les services

```bash
docker compose up -d
```

### 4. Seed des modèles (première fois)

```bash
# Copie les modèles dans le conteneur API. Par défaut depuis api/models/
# (commités dans le repo) ; sinon depuis un projet source voisin si présent.
./scripts/seed_models.sh
```

### 5. Entraîner les modèles (optionnel)

```bash
# Entraîner tous les modèles
docker compose run --rm training

# Entraîner un seul modèle
docker compose run --rm training python scripts/train_all_models.py --model at10
```

## Accès

- **Streamlit**: http://localhost:8501
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **API Metrics**: http://localhost:8000/metrics (Phase 4)
- **MLflow UI**: http://localhost:5001 (Phase 2)
- **Prometheus**: http://localhost:9090 (Phase 4)
- **Grafana**: http://localhost:3000 (Phase 4)

## API Endpoints

| Méthode | Endpoint             | Description                    |
|---------|---------------------|--------------------------------|
| GET     | `/health`           | Health check (DB + models)     |
| GET     | `/models`           | Liste des modèles disponibles  |
| POST    | `/predict/draft`    | Prédiction depuis le draft     |
| POST    | `/predict/at/{min}` | Prédiction @5/10/15/20 min     |
| GET     | `/stats/overview`   | Statistiques de la base        |

> Note `/predict/draft` : la route construit désormais les **vraies features
> côté champions** (winrate / tier / pickrate externes, matchups par lane,
> scores de synergie et de counter, avantage de draft — **~69 des 153
> features**) à partir des tables de lookup embarquées dans `model_draft.pkl`
> (`external_data` + `synergy_data`). Les noms de champions sont normalisés et
> résolus en `champion_id` via le fichier statique
> `api/app/champion_id_map.json` (aucune DB ni clé Riot à l'inférence). La
> prédiction **varie** donc avec la composition (ex. deux drafts → 0.536 vs
> 0.725 de probabilité côté bleu). Les **~84 features niveau invocateur**
> (winrate par rôle, mastery, streaks, winrate récent par champion) restent à
> leurs **valeurs neutres par défaut** car une requête de draft ne porte aucune
> identité de joueur (PUUID) — exactement le comportement du flux Streamlit
> d'origine sans PUUID. L'accuracy propre du modèle de draft est **~0.54** par
> nature (voir [`docs/PHASE1.md`](docs/PHASE1.md) §5).

### Exemple d'appel API

```bash
curl -X POST http://localhost:8000/predict/at/10 \
  -H "Content-Type: application/json" \
  -d '{
    "gold_diff": 2500,
    "first_blood": true,
    "first_dragon": true,
    "top_gold_diff": 500,
    "jungle_gold_diff": 800,
    "mid_gold_diff": 400,
    "adc_gold_diff": 600,
    "support_gold_diff": 200
  }'
```

## Structure du projet

```
MLOPS---LOL-draft-analyzer/
├── docker-compose.yml          # Orchestration de tous les services
├── Makefile                    # Orchestration e2e locale (Phase 3)
├── .ruff.toml                  # Config lint (Phase 3)
├── .env                        # Variables d'environnement (local, non commité)
├── .env.example                # Template (placeholders only)
├── pytest.ini / conftest.py    # Config tests (sans Docker/DB)
├── .github/workflows/ci.yml    # CI : lint + pytest + docker build (Phase 3)
├── k8s/                        # Squelette Kubernetes « pour plus tard » (Phase 3)
├── docs/PHASE1.md              # Objectifs, KPIs, env reproductible
├── docs/PHASE2.md              # MLflow tracking + versioning (Phase 2)
├── docs/PHASE3.md              # CI + orchestration e2e + K8s (Phase 3)
├── docs/PHASE4.md              # Monitoring + drift + auto-retrain (Phase 4)
├── README.md
│
├── monitoring/                 # Observabilité + drift (Phase 4)
│   ├── prometheus/prometheus.yml         # scrape config (api /metrics)
│   ├── grafana/provisioning/             # datasource + dashboard provider (auto)
│   ├── grafana/dashboards/               # dashboard JSON (API + prédictions)
│   └── drift/reports/                    # rapports Evidently générés (git-ignorés)
│
├── mlflow/                     # Service MLflow (Phase 2)
│   ├── Dockerfile              # python:3.11-slim + mlflow + client psql
│   ├── requirements.txt        # mlflow + psycopg2-binary
│   ├── entrypoint.sh           # crée la DB `mlflow`, lance le tracking server
│   └── README.md
│
├── database/                   # Service PostgreSQL
│   ├── init.sql                # Schéma: 15 tables + index
│   ├── restore.sh              # Auto-restore du dump
│   ├── lol_draft.dump          # Dump (~783 MB, git-ignoré, auto-téléchargé depuis DagsHub)
│   └── .env.example
│
├── streamlit/                  # Service Streamlit
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .streamlit/config.toml
│   └── app/
│       ├── app.py              # Page principale
│       ├── config.py           # Configuration
│       ├── db_utils.py         # Connexion PostgreSQL
│       ├── data_loader.py      # Chargement données
│       └── model_loader.py     # Chargement modèles
│
├── api/                        # Service FastAPI
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py             # Endpoints inférence
│   └── tests/                  # Tests API (mock modèle + DB)
│
├── training/                   # Service entraînement
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── db_utils.py         # Connexion PostgreSQL
│   │   ├── mlflow_tracking.py  # Wrapper MLflow (NO-OP si non configuré)
│   │   ├── drift_report.py     # Détection de drift Evidently (synthétique) (Phase 4)
│   │   └── train_all_models.py # Pipeline d'entraînement (instrumenté MLflow)
│   └── tests/                  # Tests feature engineering + MLflow + drift + auto-retrain
│
└── scripts/
    ├── fetch_dump.sh           # Télécharge le dump DB depuis DagsHub (md5 vérifié)
    ├── seed_models.sh          # Seed modèles dans l'API (depuis api/models/ par défaut)
    └── auto_retrain.py         # Hook ré-entraînement gated par le drift (Phase 4)
```

## Modèles

| Modèle     | Accuracy | AUC   | Type     |
|-----------|----------|-------|----------|
| Draft     | 54.0%    | 0.555 | XGBoost  |
| @5min     | 65.4%    | 0.719 | LightGBM |
| @10min    | 72.0%    | 0.797 | XGBoost  |
| @15min    | 78.0%    | 0.864 | XGBoost  |
| @20min    | 79.9%    | 0.885 | XGBoost  |

## Commandes utiles

```bash
# Logs
docker compose logs -f streamlit
docker compose logs -f api

# Accès PostgreSQL
docker exec -it lol_draft_db psql -U lol_admin -d lol_draft

# Rebuild après modification
docker compose build streamlit api
docker compose up -d

# Tout arrêter
docker compose down

# Tout supprimer (y compris données)
docker compose down -v
```
