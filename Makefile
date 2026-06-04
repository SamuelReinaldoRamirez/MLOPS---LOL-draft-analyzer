# ─────────────────────────────────────────────────────────────────────────────
# LoL Draft Predictor — local orchestration (Phase 3)
#
# Thin wrappers over the EXISTING docker compose / script commands. No live Riot
# collection: the pipeline uses the existing database/lol_draft.dump (git-ignored,
# ~747 MB, placed in database/ before `make demo`/`make restore`).
#
# Quick start (full local pipeline):  make demo
# Run tests (no Docker/DB):           make test
# See every target:                   make help
# ─────────────────────────────────────────────────────────────────────────────

COMPOSE := docker compose
DUMP    := database/lol_draft.dump
DB_CONTAINER := lol_draft_db

.DEFAULT_GOAL := help

.PHONY: help env up up-db down clean test lint build restore seed train demo logs ps \
        monitoring-up monitoring-down metrics drift retrain \
        dvc-install dvc-status dvc-track-data dvc-push dvc-pull dvc-repro dvc-dag dvc-metrics \
        k8s-validate k8s-apply k8s-delete k8s-status

## help: List available targets
help:
	@echo "LoL Draft Predictor — make targets"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed -e 's/## //' | awk -F': ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Full local pipeline: make demo  (needs $(DUMP) present)"

## env: Create .env from .env.example if missing (placeholders only)
env:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")
	@test -f .env && echo ".env present"

## up: Start the full stack (postgres + api + streamlit + mlflow)
up: env
	$(COMPOSE) up -d --build

## up-db: Start PostgreSQL only
up-db: env
	$(COMPOSE) up -d postgres

## restore: Restore the DB from the existing dump (idempotent; only loads when DB is empty on first boot)
restore: up-db
	@test -f $(DUMP) || { echo "ERROR: $(DUMP) not found. Place the (git-ignored) dump in database/ first."; exit 1; }
	@echo "Waiting for postgres to be healthy..."
	@until [ "$$($(COMPOSE) ps -q postgres | xargs -r docker inspect -f '{{.State.Health.Status}}' 2>/dev/null)" = "healthy" ]; do sleep 2; done
	@echo "Postgres healthy. The dump is auto-restored on first boot via database/restore.sh"
	@echo "(To force a fresh restore: 'make clean' then 'make restore'.)"

## seed: Seed model_*.pkl into the running api container (needs source project as sibling)
seed:
	./scripts/seed_models.sh

## train: Run the training profile against the DB (logs to MLflow if up; NO-OP otherwise)
train: env
	$(COMPOSE) up -d mlflow
	$(COMPOSE) run --rm training

## demo: Full local pipeline — db -> restore -> seed -> train -> api+streamlit+mlflow up
demo: env up-db restore up seed train
	@echo ""
	@echo "Demo stack is up:"
	@echo "  Streamlit : http://localhost:8501"
	@echo "  API       : http://localhost:8000 (docs: /docs)"
	@echo "  MLflow    : http://localhost:5000"

## test: Run the pytest suite (no Docker/DB; models + DB are mocked)
test:
	python -m pytest -q

## lint: Run ruff (non-blocking; reports pre-existing debt without failing)
lint:
	ruff check . --exit-zero

## build: Build all service Docker images
build: env
	$(COMPOSE) build

## logs: Tail logs for all services
logs:
	$(COMPOSE) logs -f

## ps: Show running services
ps:
	$(COMPOSE) ps

# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Monitoring & Maintenance
# ─────────────────────────────────────────────────────────────────────────────

## monitoring-up: Start Prometheus (:9090) + Grafana (:3000) (needs api up)
monitoring-up: env
	$(COMPOSE) up -d api prometheus grafana
	@echo ""
	@echo "Prometheus : http://localhost:$${PROMETHEUS_PORT:-9090}"
	@echo "Grafana    : http://localhost:$${GRAFANA_PORT:-3000} (admin creds from .env)"

## monitoring-down: Stop only the monitoring services (keep the rest of the stack)
monitoring-down:
	$(COMPOSE) stop prometheus grafana

## metrics: Curl the API Prometheus metrics endpoint (api must be up)
metrics:
	@curl -fsS http://localhost:$${API_PORT:-8000}/metrics | head -40 || \
	  echo "API not reachable on :$${API_PORT:-8000} — run 'make up' first."

## drift: Build an Evidently data-drift report on synthetic data (no DB needed)
drift:
	python training/scripts/drift_report.py
	@echo "Report written under monitoring/drift/reports/"

## retrain: Drift-gated auto-retrain hook (dry-run: decides, never triggers training)
retrain:
	python scripts/auto_retrain.py --dry-run

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Data + Model Versioning (DVC)
#
# Layout: dvc.yaml + params.yaml at repo root; default remote is the local
# directory `./.dvc-storage` (git-ignored, content-addressed). Switch to S3 /
# GCS / SSH by editing .dvc/config (see docs/PHASE2.md).
# ─────────────────────────────────────────────────────────────────────────────

## dvc-install: Install DVC on the host (pip; needed only for repro/push/pull)
dvc-install:
	pip install --quiet 'dvc>=3.0,<4.0'

## dvc-status: Show DVC pipeline + tracked-file status (no network)
dvc-status:
	dvc status

## dvc-track-data: One-off — track the DB dump with DVC (creates lol_draft.dump.dvc)
dvc-track-data:
	@test -f $(DUMP) || { echo "ERROR: $(DUMP) missing. Place the dump under database/ first."; exit 1; }
	dvc add $(DUMP)
	@echo "Tracked. Commit the new .dvc pointer: git add $(DUMP).dvc"

## dvc-push: Push tracked artefacts to the default remote (.dvc-storage by default)
dvc-push:
	dvc push

## dvc-pull: Restore tracked artefacts from the default remote
dvc-pull:
	dvc pull

## dvc-repro: Re-run the pipeline (calls scripts/dvc_train.sh per stage)
dvc-repro:
	dvc repro

## dvc-dag: Print the DVC pipeline DAG (text)
dvc-dag:
	dvc dag

## dvc-metrics: Show per-stage metrics (accuracy, roc_auc) across runs
dvc-metrics:
	dvc metrics show

# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Kubernetes (full manifests under k8s/)
# ─────────────────────────────────────────────────────────────────────────────

## k8s-validate: Offline schema validation (kubeconform; falls back to kubectl)
# kustomize needs --load-restrictor=LoadRestrictionsNone because the Grafana
# dashboard ConfigMap is generated from monitoring/grafana/dashboards/ which
# is outside the kustomize root k8s/. kubeconform schema-validates every
# resource against the upstream Kubernetes JSON Schemas — no cluster needed.
k8s-validate:
	@kubectl kustomize --load-restrictor=LoadRestrictionsNone k8s | \
	 ( command -v kubeconform >/dev/null \
	   && kubeconform -summary -strict -ignore-missing-schemas \
	   || kubectl apply --dry-run=client --validate=false -f - >/dev/null )
	@echo "k8s manifests OK"

## k8s-apply: Apply the full stack to the current kube-context (asks for confirmation)
k8s-apply:
	@read -p "Apply k8s/ to context '$$(kubectl config current-context)'? [y/N] " ans && [ "$$ans" = "y" ]
	kubectl apply -k k8s --load-restrictor=LoadRestrictionsNone

## k8s-delete: Delete the stack from the current context
k8s-delete:
	@read -p "DELETE k8s/ from context '$$(kubectl config current-context)'? [y/N] " ans && [ "$$ans" = "y" ]
	kubectl delete -k k8s --load-restrictor=LoadRestrictionsNone --ignore-not-found

## k8s-status: Show pod/service/ingress status in the lol-draft namespace
k8s-status:
	kubectl -n lol-draft get pods,svc,ingress,hpa,pvc

## down: Stop the stack (keep volumes/data)
down:
	$(COMPOSE) down

## clean: Stop the stack AND remove volumes (wipes DB + models + mlflow artifacts)
clean:
	$(COMPOSE) down -v
