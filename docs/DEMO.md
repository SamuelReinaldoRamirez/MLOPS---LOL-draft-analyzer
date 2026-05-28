# Demo Runbook — LoL Draft Predictor

Step-by-step runbook to prove the demo end to end. Each step lists the **exact
command**, the **expected result**, and a **verification command**. Run from the
project root: `MLOPS/MLOPS---LOL-draft-analyzer/`.

Service URLs once up:

- Streamlit: http://localhost:8501
- API:       http://localhost:8000  (docs: http://localhost:8000/docs)
- MLflow:    http://localhost:5001
- Prometheus:http://localhost:9090
- Grafana:   http://localhost:3000

---

## 0. Prerequisites

- **Docker + Docker Compose** installed and running.
- **Python 3.11+** with deps for the offline test step (`pip install -r
  api/requirements.txt -r training/requirements.txt`).
- **The data dump** `database/lol_draft.dump` (~747 MB, git-ignored, provided
  separately) **placed in `database/`** — required for the DB / training /
  MLflow / DB-backed steps. The tests and the drift step do **not** need it.

Verify prerequisites:

```bash
docker --version && docker compose version
test -f database/lol_draft.dump && echo "dump present" || echo "DUMP MISSING — DB/train steps will not work"
```

> **macOS port-5000 gotcha:** MLflow's host port defaults to **5001** because
> port 5000 is grabbed by macOS ControlCenter/AirPlay (`docker compose up` would
> otherwise abort with "port 5000 address already in use"). Override at any time:
> `MLFLOW_PORT=5000 docker compose up -d` (or set `MLFLOW_PORT` in `.env`). The
> MLflow URL below uses the 5001 default.

---

## 1. Offline tests (no Docker, no DB, no dump)

```bash
python -m pytest -q
```

- **Expected:** `47 passed` (models + DB mocked; runs in seconds).
- **Verify:** `python -m pytest -q | tail -1` shows the passing summary.

---

## 2. Configure environment

```bash
cp .env.example .env
```

- **Expected:** `.env` created from the placeholder template. Edit it to set a
  real `GRAFANA_ADMIN_PASSWORD` (and `POSTGRES_PASSWORD`) for the demo.
- **Verify:** `test -f .env && echo ".env present"`.

> `make demo` / `make up` run `make env` first, so this is also done for you.

---

## 3. Build all images

```bash
docker compose build
# or: make build
```

- **Expected:** images for `postgres`, `streamlit`, `api`, `mlflow`, `training`
  build successfully (Prometheus/Grafana use upstream images, pulled on `up`).
- **Verify:** `docker compose config --services` lists all services.

---

## 4. Start the database and restore the dump

```bash
make up-db      # docker compose up -d postgres
make restore    # waits for healthy; dump auto-restores on first boot
```

- **Expected:** `postgres` becomes healthy; the dump is restored automatically
  on first boot via `database/restore.sh`.
- **Verify:**
  ```bash
  docker compose ps postgres
  docker exec -it lol_draft_db psql -U lol_admin -d lol_draft -c "SELECT COUNT(*) FROM matches;"
  ```
  Expect a non-zero match count.

---

## 5. Start the full stack

```bash
docker compose up -d        # or: make up
```

- **Expected:** `postgres`, `streamlit`, `api`, `mlflow` running (Prometheus +
  Grafana start too on full `up`).
- **Verify:** `docker compose ps` shows the services as `running`/`healthy`.

---

## 6. Seed models into the running stack

```bash
./scripts/seed_models.sh    # or: make seed
```

- **Expected:** `model_draft.pkl`, `model_at5/10/15/20.pkl` placed into the
  shared `lol_draft_models` volume used by `api` + `streamlit`.
- **Verify:**
  ```bash
  curl -s http://localhost:8000/models
  ```
  Expect each model `"available": true`.

> **Source models location:** `seed_models.sh` auto-detects the original project
> at `<repo>/../datascientest-lol-draft_analyzer/models` (sibling layout) or
> `<repo>/../../datascientest-lol-draft_analyzer/models` (when this clean project
> is nested, e.g. under `MLOPS/MLOPS---LOL-draft-analyzer/`). If it lives
> elsewhere, point it explicitly:
> `SOURCE_MODELS_DIR=/path/to/models ./scripts/seed_models.sh`.

---

## 7. Prove the API (health + a real prediction)

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/stats/overview
curl -s -X POST http://localhost:8000/predict/at/10 \
  -H "Content-Type: application/json" \
  -d '{"gold_diff":2500,"first_blood":true,"first_dragon":true,"top_gold_diff":500,"jungle_gold_diff":800,"mid_gold_diff":400,"adc_gold_diff":600,"support_gold_diff":200}'
```

- **Expected:** `/health` → `"status":"healthy"`, `"database":"connected"`;
  `/stats/overview` → match/timeline counts + winrates; `/predict/at/10` → a
  `PredictionResponse` (winner + blue/red probabilities + confidence).
- **Verify:** the prediction JSON contains `"model_used":"at10"`.

> Note: `POST /predict/draft` also runs, but its inputs are filled with neutral
> defaults (the 153-feature draft model is not yet wired to champion names) — it
> is **runnable, not yet meaningful**. See [`PHASE1.md`](PHASE1.md) §5.

---

## 8. Train + show MLflow (Phase 2)

```bash
make train      # starts mlflow, runs the training profile against the DB
```

- **Expected:** training runs against the restored DB and logs params/metrics +
  registers model versions to MLflow.
- **Verify:** open http://localhost:5001 → experiment `lol-draft-timeline` has a
  run per model; "Models" tab shows `lol_draft_at{5,10,15,20}` versions.

---

## 9. Monitoring: Prometheus + Grafana (Phase 4)

```bash
make monitoring-up      # api + prometheus + grafana (already up via step 5)
make metrics            # curl http://localhost:8000/metrics
```

Generate some traffic so the counter moves, then check the dashboards:

```bash
for i in $(seq 1 10); do \
  curl -s -X POST http://localhost:8000/predict/at/10 \
    -H "Content-Type: application/json" \
    -d '{"gold_diff":1500}' > /dev/null; done
```

- **Expected:** `/metrics` returns Prometheus text including
  `lol_predictions_total{model="at10"}` with a rising count.
- **Verify:**
  - Prometheus http://localhost:9090 → query `lol_predictions_total` → series
    increases.
  - Grafana http://localhost:3000 (login with `.env` creds) → Dashboards →
    **"LoL Draft Predictor — API & Predictions"** → request rate, p95 latency
    and prediction-rate panels show activity.

---

## 10. Drift + auto-retrain decision (Phase 4)

```bash
make drift                                          # synthetic reference vs current
python training/scripts/drift_report.py --drift     # force a drifted current set (demo)
make retrain                                        # drift-gated decision (dry-run)
python scripts/auto_retrain.py --force-drift --dry-run   # demo: forces a RETRAIN decision (no training)
```

- **Expected:** an Evidently HTML + JSON report is written under
  `monitoring/drift/reports/`; `make retrain` prints the decision; `--force-drift`
  prints a **RETRAIN** decision (dry-run does not trigger training).
- **Verify:** `ls monitoring/drift/reports/` shows generated report files.

> DB-backed drift (`DRIFT_USE_DB=1`) and a real retrain trigger (`--force-drift`
> **without** `--dry-run`) are **documented but optional**: they need the dump /
> live stack. The default demo path uses synthetic data and a dry-run decision.

---

## 11. Teardown

```bash
docker compose down        # stop, keep volumes/data  (or: make down)
# Full wipe (removes DB + models + mlflow artifacts + prometheus/grafana data):
docker compose down -v     # or: make clean
```

- **Expected:** `make down` stops containers but keeps the restored DB and
  models; `make clean` removes all named volumes for a clean re-run.
- **Verify:** `docker compose ps` shows no running services.

---

## One-shot pipeline (alternative to steps 2–8)

```bash
make demo     # env -> up-db -> restore -> up -> seed -> train
```

Brings the stack up end to end (needs the dump present), then prints the
Streamlit / API / MLflow URLs. Run steps 9–10 afterwards for the monitoring and
drift parts.
