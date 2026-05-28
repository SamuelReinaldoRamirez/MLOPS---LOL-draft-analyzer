# Phase 3 — CI, orchestration end-to-end & Kubernetes complet

La **Phase 3** ajoute l'**automatisation** au-dessus des Phases 1 (stack + API +
tests) et 2 (MLflow + DVC) : une **CI GitHub Actions**, une **orchestration
locale** du pipeline complet (via un `Makefile`) et un **déploiement
Kubernetes production-ready** (StatefulSet Postgres, PVCs, HPA, Ingress TLS,
NetworkPolicies). Rien ne casse la stack ni la suite de tests existante.

## 1. Objectifs

| # | Objectif                                                                       | Statut |
|---|--------------------------------------------------------------------------------|--------|
| 1 | **CI** : lint + `pytest` + `docker compose build` sur push / PR                | OK     |
| 2 | **Orchestration e2e** locale (`Makefile`) avec le dump existant (pas de Riot)  | OK     |
| 3 | **Kubernetes complet** : Postgres `StatefulSet`+PVC, API/Streamlit `Deployment`+HPA, MLflow `Deployment`+PVC, Prometheus/Grafana, Ingress TLS, NetworkPolicies | OK |
| 4 | **Documentation** : ce fichier + section README + `k8s/README.md`              | OK     |

Le **KPI Phase 3** est l'**automatisation reproductible** : la CI prouve à
chaque push que les tests passent et que les images se construisent ; le
`Makefile` rejoue le pipeline complet en une commande à partir du **dump
existant** (aucune collecte live Riot).

## 2. CI — GitHub Actions

Fichier : [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). Déclenché
sur **push** (toutes branches), **pull_request** et `workflow_dispatch`.
Trois jobs, qui réutilisent les commandes qui marchent déjà en local :

| Job     | Fait quoi                                                            | Bloquant ? |
|---------|----------------------------------------------------------------------|------------|
| `lint`  | `ruff check . --exit-zero` (config `.ruff.toml`)                      | NON (1er passage) |
| `test`  | `pip install -r api/requirements.txt -r training/requirements.txt` puis `python -m pytest -q` | OUI |
| `build` | `docker compose build` (toutes les images) — dépend de `test`        | OUI        |

Points clés :

- **Pas de secret ni de dump requis.** La suite de tests est entièrement mockée
  (modèle fixture + DB monkeypatchée → voir `conftest.py`/`pytest.ini`), donc la
  CI n'a **pas besoin** du `database/lol_draft.dump` (747 Mo, git-ignoré). Le
  `docker compose build` ne copie pas le dump (il n'est dans aucun contexte
  d'image).
- **`.env`** est généré depuis `.env.example` (placeholders) pour que
  l'interpolation `${VAR}` de `docker compose` n'émette pas d'avertissement.
- **Lint non bloquant (1er passage)** : `--exit-zero` rapporte la dette de lint
  Phase 1/2 **sans** faire échouer la CI — on ne réécrit pas le code existant
  pour satisfaire le linter (durcissement = phase ultérieure, en retirant
  `--exit-zero`).
- **Pas d'exécution distante ici** : on ne peut pas lancer GitHub Actions depuis
  ce poste. Le YAML est **validé localement** (`yaml.safe_load`) et chaque étape
  référence une commande réelle déjà éprouvée en local.

## 3. Orchestration end-to-end — `Makefile`

Fichier : [`../Makefile`](../Makefile). Des **wrappers fins** au-dessus des
commandes `docker compose` / scripts existants. Aucune collecte live Riot :
le pipeline part du **dump existant** (`database/lol_draft.dump`).

| Cible          | Commande sous-jacente                                  | Rôle |
|----------------|--------------------------------------------------------|------|
| `make help`    | (liste les cibles)                                     | Aide |
| `make env`     | `cp .env.example .env` (si absent)                     | Variables d'env (placeholders) |
| `make up`      | `docker compose up -d`                                 | Démarre toute la stack |
| `make up-db`   | `docker compose up -d postgres`                        | Postgres seul |
| `make restore` | `up-db` + attente *healthy* (restore auto au 1er boot via `database/restore.sh`) | Restaure la DB depuis le dump |
| `make seed`    | `./scripts/seed_models.sh`                             | Copie les `model_*.pkl` dans le conteneur api |
| `make train`   | `docker compose up -d mlflow` + `docker compose run --rm training` | Entraîne (log MLflow si dispo, NO-OP sinon) |
| `make demo`    | `env → up-db → restore → up → seed → train`            | **Pipeline complet** |
| `make test`    | `python -m pytest -q`                                  | Tests (sans Docker/DB) |
| `make lint`    | `ruff check . --exit-zero`                             | Lint (non bloquant) |
| `make build`   | `docker compose build`                                 | Build des images |
| `make logs`    | `docker compose logs -f`                               | Logs |
| `make ps`      | `docker compose ps`                                    | Services actifs |
| `make down`    | `docker compose down`                                  | Arrêt (garde les données) |
| `make clean`   | `docker compose down -v`                               | Arrêt + suppression des volumes |

### Rejouer le pipeline e2e en local

```bash
# Pré-requis : Docker dispo + database/lol_draft.dump présent (git-ignoré, 747 Mo)
#              + projet source en sibling pour `seed` (cf. scripts/seed_models.sh)

make demo        # env -> db -> restore -> stack up -> seed models -> train
# Accès :
#   Streamlit : http://localhost:8501
#   API       : http://localhost:8000  (docs: /docs)
#   MLflow    : http://localhost:5001
```

> **Collecte live Riot = optionnelle, hors démo.** L'orchestration utilise
> uniquement le dump fourni. Une collecte live nécessiterait un `RIOT_API_KEY`
> dans un `.env` local (laissé vide dans `.env.example`) ; elle reste **hors
> périmètre** du pipeline e2e démontré ici.

## 4. Déploiement Kubernetes (production-ready)

Dossier : [`../k8s/`](../k8s/) — voir [`k8s/README.md`](../k8s/README.md). La
démo locale tourne toujours sur Docker Compose, mais le tree `k8s/` est
désormais **un déploiement complet déployable** (kustomize, 32 ressources)
plutôt qu'un squelette.

### 4.1 Arborescence

```
k8s/
├── kustomization.yaml        # root: agrège base + monitoring + ingress
├── base/                     # workloads applicatifs
│   ├── namespace.yaml        # ns: lol-draft
│   ├── configmap.yaml        # env non-secret (mirroir du .env.example)
│   ├── secret.yaml           # template (POSTGRES_PASSWORD, GRAFANA_*, RIOT_API_KEY)
│   ├── models-pvc.yaml       # PVC RWX partagé api+streamlit (/app/models)
│   ├── mlflow-pvc.yaml       # PVC RWO pour /mlflow/artifacts
│   ├── postgres-statefulset.yaml  # StatefulSet 1 réplica + volumeClaimTemplate 10 Gi
│   ├── api-deployment.yaml   # 2 répliques, securityContext durci, /metrics annoté
│   ├── api-service.yaml      # ClusterIP
│   ├── api-hpa.yaml          # HPA 2→6 (CPU 70%, mémoire 80%, behavior tuning)
│   ├── streamlit-deployment.yaml  # Deployment + Service + HPA 2→4
│   └── mlflow-deployment.yaml     # Deployment + Service ClusterIP
├── monitoring/               # observabilité Phase 4 sur K8s
│   ├── prometheus-configmap.yaml  # scrape api+mlflow par DNS du Service
│   ├── prometheus-pvc.yaml        # TSDB 5 Gi, rétention 14 j
│   ├── prometheus-deployment.yaml # Deployment + Service ClusterIP
│   ├── grafana-configmap.yaml     # datasource auto + provider dashboards
│   ├── grafana-pvc.yaml           # état Grafana 1 Gi
│   └── grafana-deployment.yaml    # creds via secretKeyRef, dashboards depuis ConfigMap
└── ingress/                  # exposition externe + lockdown réseau
    ├── ingress.yaml          # nginx-ingress + cert-manager (Let's Encrypt HTTP-01)
    └── networkpolicy.yaml    # default-deny + 6 allow rules ciblées
```

### 4.2 Points clés

- **Configuration centralisée** : un seul `ConfigMap` (`lol-draft-config`) +
  `Secret` (`lol-draft-secrets`), injectés via `envFrom:` dans chaque
  Deployment — pas de duplication, pas de plaintext.
- **Persistence** : Postgres en `StatefulSet` avec `volumeClaimTemplate` 10 Gi
  (RWO), PVC RWX 1 Gi pour les modèles partagés api↔streamlit, 5 Gi pour le
  TSDB Prometheus, 5 Gi pour les artefacts MLflow.
- **Scaling automatique** : `HorizontalPodAutoscaler` sur l'API (2→6 répliques,
  cibles CPU 70% + mémoire 80%, avec stabilisation `scaleDown` de 300 s pour
  éviter le yo-yo) ; HPA sur Streamlit 2→4.
- **Sécurité** :
  - `securityContext` pod + container : `runAsNonRoot`, `allowPrivilegeEscalation: false`,
    `readOnlyRootFilesystem`, `capabilities: drop ALL`.
  - **NetworkPolicies** : default-deny en ingress dans `lol-draft`, puis 6
    règles d'allow ciblées (postgres ← api/streamlit/mlflow, api ← nginx+
    prometheus+streamlit, etc.). Bloque toute communication latérale non
    déclarée — Calico/Cilium requis pour effet.
  - TLS automatisé par cert-manager (annotation `cluster-issuer:
    letsencrypt-prod`) ; HTTP redirigé 308.
- **Observabilité préservée** : Prometheus scrape le Service K8s
  `lol-draft-api.lol-draft.svc.cluster.local:8000` ; Grafana auto-provisionné
  (datasource + dashboard `lol_api_overview.json` mounted from a
  `configMapGenerator` qui lit le JSON existant `monitoring/grafana/dashboards/`
  — aucune duplication).
- **GitOps-friendly** : kustomization à 3 niveaux (root → base/monitoring/
  ingress), `labels:` partagés (modern), un seul `kubectl apply -k k8s` suffit.

### 4.3 Validation offline (sans cluster)

```bash
make k8s-validate                                # kubeconform-based (32/32 OK)
# ou explicite :
kubectl kustomize --load-restrictor=LoadRestrictionsNone k8s | \
  kubeconform -summary -strict -ignore-missing-schemas
```

### 4.4 Déploiement réel (pré-requis)

```bash
# Pré-requis cluster (une fois) :
# 1. ingress-nginx           → controller pour les Ingress
# 2. cert-manager            → ClusterIssuer letsencrypt-prod
# 3. metrics-server          → pour les HPA
# 4. CNI avec NetworkPolicy  → Calico, Cilium, Antrea, …

# Pré-requis projet :
# - Pousser les images vers un registry et mettre à jour `image:` dans chaque
#   Deployment (overlay kustomize recommandé).
# - Charger le dump dans Postgres : `kubectl cp database/lol_draft.dump
#   <postgres-pod>:/tmp/ && kubectl exec <pod> -- pg_restore ...`.

make k8s-apply                # confirme le contexte + applique
make k8s-status               # pods, services, ingress, hpa, pvc
make k8s-delete               # supprime tout (avec confirmation)
```

## 5. Vérification (sans Docker)

```bash
# Validité YAML des workflows
python -c "import glob,yaml; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.y*ml')]; print('workflows YAML OK')"

# Les workflows référencent bien pytest + docker
grep -nE "pytest|docker" .github/workflows/*.y*ml

# La suite de tests passe toujours (27)
python -m pytest -q

# Le compose reste valide
docker compose config >/dev/null && echo "compose valid"

# Le Makefile expose ses cibles
grep -nE "^[a-zA-Z_-]+:" Makefile | head
```
