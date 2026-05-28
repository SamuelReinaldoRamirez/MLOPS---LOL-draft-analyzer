# MLflow service

MLflow **tracking server** for the LoL Draft Predictor (Phase 2 — experiment
tracking & model versioning).

## What it does

- Runs `mlflow server` on port **5000** (UI: http://localhost:5000).
- **Backend store**: PostgreSQL — reuses the existing `postgres` service in a
  dedicated `mlflow` database. `entrypoint.sh` creates that database
  idempotently on first boot, so the `database/` image is left untouched.
- **Artifact store**: a local volume mounted at `/mlflow/artifacts`
  (docker volume `lol_draft_mlflow_artifacts`), served by the tracking server
  (`--serve-artifacts`), so clients never need direct filesystem access.

## Files

| File             | Purpose                                              |
|------------------|------------------------------------------------------|
| `Dockerfile`     | Python 3.11 image with mlflow + psql client          |
| `requirements.txt` | `mlflow` + `psycopg2-binary`                       |
| `entrypoint.sh`  | Waits for Postgres, creates `mlflow` DB, starts server |

## Run

```bash
# From the repo root
docker compose up -d mlflow      # starts postgres (dependency) + mlflow
# UI:
open http://localhost:5000
```

Training logs to it automatically when `MLFLOW_TRACKING_URI` is set
(see root `README.md` and `docs/PHASE2.md`). When the variable is unset or the
server is unreachable, training degrades to a **no-op** and still works.
