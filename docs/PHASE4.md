# Phase 4 — Monitoring & Maintenance

Phase 4 adds **observability**, **data-drift detection** and an **automated
model-update hook** on top of Phases 1–3, **without breaking** the stack or the
test suite. As in Phase 2's MLflow NO-OP contract, all of the new machinery is
**fail-safe**: instrumentation and drift detection degrade gracefully when their
optional dependencies are absent, and the 27 core tests stay green.

---

## 1. Prometheus metrics on the API

[`api/app/main.py`](../api/app/main.py) is instrumented with
[`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator).

- **Default HTTP metrics** — request count + latency histograms, e.g.
  `http_requests_total`, `http_request_duration_seconds_bucket`, labelled by
  `handler`/`method`/`status`.
- **Custom business metric** — `lol_predictions_total{model="..."}`: a counter
  incremented on every successful `/predict/draft` and `/predict/at/{minute}`
  call, labelled by the model used.
- **Endpoint** — `GET /metrics` returns Prometheus exposition text.

**Fail-safe.** If the Prometheus packages are not installed, the API still boots
and `/metrics` falls back to a small `prometheus_client` (or stub) response, and
`_record_prediction()` becomes a NO-OP. Inference and tests never break.

Test: [`api/tests/test_metrics.py`](../api/tests/test_metrics.py) asserts
`/metrics` returns 200 + Prometheus text and that a prediction registers on the
`lol_predictions_total` counter (no Docker/DB — same fixtures as the API suite).

```bash
make metrics          # curl http://localhost:8000/metrics  (api must be up)
```

---

## 2. Prometheus + Grafana services

Wired into the root [`docker-compose.yml`](../docker-compose.yml) on the shared
`lol-net` network, with healthchecks consistent with the other services.

| Service     | Port  | Notes                                                |
|-------------|-------|------------------------------------------------------|
| `prometheus`| 9090  | Scrapes `api:8000/metrics` every 15s                 |
| `grafana`   | 3000  | Provisioned datasource + dashboard; creds via `.env` |

- **Prometheus config**:
  [`monitoring/prometheus/prometheus.yml`](../monitoring/prometheus/prometheus.yml)
  — jobs `lol-api` (the API) and `prometheus` (self).
- **Grafana datasource** (auto-provisioned):
  [`monitoring/grafana/provisioning/datasources/prometheus.yml`](../monitoring/grafana/provisioning/datasources/prometheus.yml)
  → `http://prometheus:9090`.
- **Grafana dashboard** (auto-provisioned):
  [`monitoring/grafana/dashboards/lol_api_overview.json`](../monitoring/grafana/dashboards/lol_api_overview.json)
  — panels for API request rate, p95 latency, prediction rate by model, and
  total predictions served.
- **Credentials** come from `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in
  `.env` (placeholders only in `.env.example`) — **never hardcoded**.

```bash
cp .env.example .env       # set GRAFANA_ADMIN_PASSWORD locally
make monitoring-up         # docker compose up -d api prometheus grafana
# Prometheus : http://localhost:9090   (query: lol_predictions_total)
# Grafana    : http://localhost:3000   (login with .env creds)
#   → Dashboards → "LoL Draft Predictor — API & Predictions"
```

---

## 3. Evidently data-drift detection

[`training/scripts/drift_report.py`](../training/scripts/drift_report.py) builds
an [Evidently](https://github.com/evidentlyai/evidently) `DataDriftPreset`
report comparing a **reference** dataset (training-time distribution) against a
**current** dataset (recent / production-like).

- **Output**: an **HTML** report + a compact **JSON** summary under
  `monitoring/drift/reports/` (git-ignored; regenerated on demand).
- **Summary dict**: `drift_share`, `n_drifted`, `n_columns`, `drifted`,
  `source` — consumed by the auto-retrain hook.
- **Runs without the 747 MB dump.** `load_reference_current()` only queries
  PostgreSQL when `DRIFT_USE_DB=1`. Before connecting it runs a short **TCP
  reachability pre-check** (~3s, `DRIFT_DB_REACHABLE_TIMEOUT`) and the DSN
  carries a `connect_timeout` (5s); if the host is down/unreachable/refused it
  **logs and degrades to synthetic data in seconds** instead of hanging on
  psycopg2's default (effectively unbounded) connect. With no `DRIFT_USE_DB` it
  uses two small **synthetic** frames directly, so the script and its test run
  anywhere — and the function never hangs or raises just because the DB is down.
- **Fail-safe import.** `evidently` is imported lazily; the module always
  imports cleanly. `evidently_available()` gates the heavy path.

```bash
make drift                                   # synthetic reference vs current
python training/scripts/drift_report.py --drift   # force a drifted current set (demo)
```

Test: [`training/tests/test_drift_report.py`](../training/tests/test_drift_report.py)
exercises the synthetic-data helpers, the no-DB fallback, the
"evidently-missing raises" guard, and (when `evidently` is installed) asserts
drift is **detected on a shifted synthetic set** and **absent on an identical
distribution**. If `evidently` is unavailable the Evidently-backed cases SKIP
(never faked).

---

## 4. Automated model-update hook

[`scripts/auto_retrain.py`](../scripts/auto_retrain.py) is a cleaned-up,
MLOps-friendly successor to the source project's `scripts/wait_and_retrain.py`.
Instead of polling a backfill PID and re-exporting everything, it is a small,
idempotent **decide + trigger**:

1. Run drift detection (synthetic by default).
2. **If** `drift_share > DRIFT_THRESHOLD` → trigger retraining via the
   **existing** training entrypoint
   (`docker compose run --rm training python scripts/train_all_models.py`).
3. **Else** → NO-OP.

Key properties:

- **Pure decision predicate** `should_retrain(summary, threshold)` — strictly
  greater-than; a missing/`None` summary never retrains.
- **Injectable** drift + retrain functions, so the logic is unit-tested with a
  mocked trainer — **no live DB is required to import or test**.
- **Safe & idempotent** — no-op below threshold; `--dry-run` decides without
  triggering; degrades to "no decision" when `evidently` is unavailable.

```bash
python scripts/auto_retrain.py                 # synthetic data, real check
python scripts/auto_retrain.py --force-drift   # demo: forces a retrain decision
python scripts/auto_retrain.py --dry-run       # decide only, never retrain
make retrain                                    # dry-run wrapper
```

Test: [`training/tests/test_auto_retrain.py`](../training/tests/test_auto_retrain.py)
covers the predicate (above/below/at-threshold, `None`), the orchestration
(drift>threshold ⇒ retrain called once; below ⇒ never called; dry-run; drift
unavailable; non-zero retrain return code) with the trainer **mocked**.

> **Real retrain run** (out of the test scope): the trigger needs a live DB /
> the 747 MB dump. Validate the *wiring* via `docker compose config`, the
> synthetic-data tests, and `--dry-run`; perform a real run only on the demo
> stack with `make demo` followed by `python scripts/auto_retrain.py
> --force-drift` (which then shells out to the training profile).

---

## Make targets (Phase 4)

```bash
make monitoring-up     # api + prometheus + grafana
make monitoring-down   # stop just prometheus + grafana
make metrics           # curl the API /metrics endpoint
make drift             # build a synthetic-data drift report
make retrain           # drift-gated auto-retrain hook (dry-run)
```

## NO-OP / fail-safe guarantees (tests + CI intact)

- Prometheus packages absent → `/metrics` stub + NO-OP counter; API + tests fine.
- `evidently` absent → drift module still imports; Evidently tests SKIP; the
  auto-retrain hook treats "no drift summary" as **no retrain**.
- No live DB / dump needed to import or test anything in this phase: drift uses
  synthetic data and the retrain trigger is mocked in tests.

The full suite (`python -m pytest -q`) stays green: **27 core tests** plus the
Phase-4 additions (metrics, drift, auto-retrain).
