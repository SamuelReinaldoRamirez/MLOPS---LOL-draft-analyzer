# Phase 2 — Suivi d'expériences & versioning (MLflow)

La **Phase 2** ajoute le *experiment tracking* et le *versioning* au-dessus de
la base reproductible de la Phase 1, **sans casser** la stack ni la suite de
tests (qui tourne toujours sans Docker ni serveur MLflow).

## 1. Objectifs

| # | Objectif                                                                 | Statut |
|---|--------------------------------------------------------------------------|--------|
| 1 | Service **MLflow** (tracking server) dans le `docker-compose.yml`        | OK     |
| 2 | Instrumentation de `train_all_models.py` (params / metrics / artefact)   | OK     |
| 3 | **Model Registry** : enregistrement versionné des modèles               | OK     |
| 4 | **Data versioning** avec **DVC** : dump + modèles + pipeline `dvc.yaml`  | OK     |
| 5 | Dégradation **NO-OP** propre si MLflow indisponible (tests/CI intacts)   | OK     |

Le **KPI Phase 2** est la *traçabilité reproductible* : chaque entraînement
produit un run MLflow comparable (mêmes params/metrics) et une version de
modèle enregistrée, **sans** rendre l'entraînement dépendant d'un serveur.

## 2. Service MLflow (Docker Compose)

```yaml
# docker-compose.yml (extrait)
mlflow:
  build: ./mlflow            # image python:3.11-slim + mlflow + client psql
  ports: ["5001:5000"]        # UI: http://localhost:5001 (5000 clashe avec macOS AirPlay)
  depends_on: { postgres: { condition: service_healthy } }
  healthcheck: GET http://localhost:5000/health
```

- **Backend store** : PostgreSQL — réutilise le service `postgres` existant
  dans une base dédiée `mlflow`. `mlflow/entrypoint.sh` crée cette base de façon
  **idempotente** au premier démarrage (aucune modification de l'image
  `database/`).
- **Artifact store** : volume local `lol_draft_mlflow_artifacts` monté sur
  `/mlflow/artifacts`, servi par le serveur (`--serve-artifacts`).
- **Réseau / dépendances** : même réseau `lol-net`, `depends_on` postgres avec
  `condition: service_healthy`, healthcheck cohérent avec les autres services.

### Démarrer le serveur

```bash
cp .env.example .env           # contient MLFLOW_PORT / MLFLOW_DB / MLFLOW_TRACKING_URI
docker compose up -d mlflow    # démarre postgres (dépendance) + mlflow
open http://localhost:5001     # UI MLflow
```

## 3. Instrumentation de l'entraînement

`training/scripts/train_all_models.py` utilise le wrapper
`training/scripts/mlflow_tracking.py` (`MLflowTracker`). Pour chaque modèle
`@5/@10/@15/@20` :

- **un run** par modèle (`run_name=model_at{minute}`, tags `minute/stage/phase`) ;
- **params** : `model_type`, `minute`, `n_features`, tailles de splits, et tous
  les hyper-paramètres (`hp_*`) ;
- **metrics** : `accuracy`, `roc_auc`, `val_accuracy` ;
- **artefact modèle** : `mlflow.sklearn.log_model(...)` + le bundle `.pkl`
  complet loggé en artefact (`pkl_bundle/`) pour la traçabilité.

### Garantie NO-OP (critique)

Le wrapper est **désactivé** (tout devient NO-OP silencieux) si :
1. `MLFLOW_TRACKING_URI` est absent/vide, **ou**
2. le paquet `mlflow` n'est pas installé, **ou**
3. le serveur est injoignable.

**Dégradation rapide (fast-fail)** : quand `MLFLOW_TRACKING_URI` est défini mais
que le serveur est injoignable, MLflow réessaie par défaut avec backoff et peut
**bloquer plusieurs minutes**. Le wrapper évite ce piège : à l'import il force
des défauts courts (`MLFLOW_HTTP_REQUEST_MAX_RETRIES=1`,
`MLFLOW_HTTP_REQUEST_TIMEOUT=3`, via `setdefault` pour respecter un override
opérateur) et effectue un pré-check TCP rapide (~3 s) sur l'hôte:port de l'URI.
Résultat : un serveur down échoue en **quelques secondes** (≈0,2 s) au lieu de
bloquer >120 s, et le `try/except` le convertit en no-op propre.

Toute erreur de logging est capturée (WARNING) sans jamais lever d'exception.
De plus, `train_all_models.py` enveloppe même l'import du wrapper dans un
`try/except` qui retombe sur un objet no-op inline — l'entraînement et les
tests fonctionnent donc **sans** serveur MLflow. C'est prouvé par
`training/tests/test_mlflow_tracking.py` (dont un test qui vérifie le fast-fail
contre un port refusé).

## 4. Model versioning — MLflow Model Registry

Chaque run enregistre une **nouvelle version** dans le Model Registry via
`registered_model_name="lol_draft_at{minute}"` (un modèle registry par minute).
Approche :

- À chaque entraînement, une nouvelle **version** est créée automatiquement.
- Les **tags** de run (`minute`, `stage`, `phase`) et les metrics permettent de
  comparer les versions dans l'UI (onglet *Models*).
- **Promotion de stage** (Staging / Production) : opération manuelle dans l'UI
  MLflow (ou via `MlflowClient.transition_model_version_stage`) une fois la
  version validée — laissée manuelle pour ne pas auto-promouvoir en CI.
- Si le serveur n'est pas joignable au moment du run, `log_model` est un NO-OP :
  l'enregistrement se fera lors d'un run effectué serveur disponible (le `.pkl`
  reste produit localement dans tous les cas).

## 5. Data + Model versioning — DVC

DVC apporte un versioning **content-addressed** (hash MD5) du jeu de données
(`database/lol_draft.dump`, 747 Mo, git-ignoré) et des modèles produits
(`models/model_at{5,10,15,20}.pkl`), avec une **pipeline reproductible**
`dvc.yaml` qui relie les deux à `params.yaml`. Le lien dataset ↔ modèle ↔
hyper-params est donc rétabli **à partir d'un seul `dvc repro`**.

### 5.1 Layout

```
dvc.yaml                     # 4 stages: train_at{5,10,15,20}
params.yaml                  # train.seed/test_size/val_size + xgb/lgb dicts
.dvc/config                  # remote par défaut: local-storage → ./.dvc-storage
.dvcignore                   # caches/IDE/screenshots ignorés
.dvc-storage/                # remote local (git-ignoré)
database/lol_draft.dump.dvc  # pointer (hash MD5 + taille) — commité
models/                      # outputs des stages: model_at{n}.pkl (ignoré) +
                             #                    metrics_at{n}.json (commité)
scripts/dvc_train.sh         # shim docker compose run → bind-mount ./models
```

### 5.2 Pipeline `dvc.yaml`

Chaque stage `train_at{5,10,15,20}` :

- **deps** : `train_all_models.py`, `db_utils.py`, `mlflow_tracking.py`,
  `database/lol_draft.dump` (suivi DVC) ;
- **params** : `train.seed`, `train.test_size`, `train.val_size`,
  `train.xgb`, `train.lgb` (les hashes des sous-arbres déclenchent un re-run
  ciblé si seuls ces blocs changent) ;
- **outs** : `models/model_at{n}.pkl` (cache DVC) ;
- **metrics** : `models/metrics_at{n}.json` (`cache: false`, commité).

L'override de `params.yaml` au runtime se fait dans `train_all_models._apply_params()`
(NO-OP si PyYAML absent ou fichier introuvable → l'entraînement direct sans DVC
reste identique aux Phases 1/2 antérieures).

### 5.3 Workflow

```bash
# Une fois — tracker le dump (au stand-up du projet, ou après refresh du dump)
make dvc-track-data           # = dvc add database/lol_draft.dump
git add database/lol_draft.dump.dvc dvc.yaml params.yaml

# Reproduire la pipeline (utilise scripts/dvc_train.sh ↔ docker compose training)
make dvc-repro                # = dvc repro (n'exécute que les stages dirty)
make dvc-metrics              # = dvc metrics show — accuracy + AUC par run
make dvc-dag                  # graphe ASCII de dépendances

# Distribuer
make dvc-push                 # → .dvc-storage (par défaut). S3/GCS possible
make dvc-pull                 # rejoue les artefacts depuis le remote
```

### 5.4 Remote

`.dvc/config` pointe par défaut sur `local-storage = ./.dvc-storage`
(git-ignoré). Pour utiliser un remote distant :

```bash
# S3
dvc remote add -d s3-storage s3://my-bucket/lol-draft-dvc
dvc remote modify s3-storage region eu-west-3

# GCS
dvc remote add -d gcs-storage gs://my-bucket/lol-draft-dvc
```

Les credentials suivent les chaînes standards (`~/.aws/credentials`, ADC, …).

### 5.5 Articulation MLflow ↔ DVC

| Aspect                | MLflow                              | DVC                                       |
|-----------------------|-------------------------------------|-------------------------------------------|
| Que suit-on ?         | run (params/metrics/artefact)       | fichiers (dump + .pkl) + DAG de stages    |
| Versioning            | Model Registry (entité métier)      | Content-addressed (hash MD5)              |
| Lieu                  | UI MLflow (5001)                    | Repo Git (.dvc files) + remote DVC        |
| Reproductibilité      | « ré-utiliser un modèle déjà entraîné » | « ré-entraîner exactement le même »   |
| Réutilisable hors DVC | OUI                                 | NON (mais re-générable)                   |

Les deux coexistent : MLflow garde la **traçabilité business** (qui a entraîné
quoi quand, quelle metric), DVC garde la **traçabilité technique** (sur quelles
données exactes + quels hyper-params, comment reproduire).

## 6. Étapes de démo

```bash
# 1. Lancer le serveur de tracking
docker compose up -d mlflow
open http://localhost:5001                 # UI vide au départ

# 2. Lancer un entraînement instrumenté (postgres + dump requis)
docker compose run --rm training python scripts/train_all_models.py --model at10

# 3. Dans l'UI MLflow :
#    - Experiment "lol-draft-timeline" -> 1 run "model_at10"
#      params (model_type, minute, hp_*), metrics (accuracy, roc_auc)
#    - onglet "Models" -> "lol_draft_at10" version 1 enregistrée

# 4. Démontrer le NO-OP (sans serveur) :
MLFLOW_TRACKING_URI= python -m pytest training/tests/test_mlflow_tracking.py -q
#    -> tous verts ; l'entraînement marcherait aussi sans MLflow.
```

## 7. Vérification (sans Docker)

```bash
python -m pytest -q                         # 24 tests verts (16 + 8 Phase 2)
python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"
```
