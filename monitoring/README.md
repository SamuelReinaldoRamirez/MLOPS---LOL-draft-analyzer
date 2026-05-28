# Monitoring & Maintenance (Phase 4)

Observability + drift detection + automated model updates for the LoL Draft
Predictor stack.

## Layout

```
monitoring/
├── prometheus/
│   └── prometheus.yml                  # scrape config (api /metrics + self)
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/prometheus.yml  # Prometheus datasource (auto)
│   │   └── dashboards/dashboards.yml   # dashboard provider (auto)
│   └── dashboards/
│       └── lol_api_overview.json       # API + prediction dashboard
└── drift/
    └── reports/                        # generated Evidently reports (git-ignored)
```

## Stack

| Service     | Port  | What                                                     |
|-------------|-------|----------------------------------------------------------|
| `prometheus`| 9090  | Scrapes `api:8000/metrics` every 15s                     |
| `grafana`   | 3000  | Provisioned datasource + dashboard (admin creds via env) |

Bring them up:

```bash
docker compose up -d prometheus grafana   # or: make monitoring-up
```

- Prometheus: <http://localhost:9090>  (try `lol_predictions_total`)
- Grafana:    <http://localhost:3000>  (login with `GRAFANA_ADMIN_USER` /
  `GRAFANA_ADMIN_PASSWORD` from your `.env`)

## Metrics exposed by the API

`prometheus-fastapi-instrumentator` exports default HTTP request count/latency
histograms (`http_requests_total`, `http_request_duration_seconds_*`) plus a
custom business counter:

- `lol_predictions_total{model="draft|at5|at10|at15|at20"}` — predictions served.

Instrumentation is fail-safe: if the Prometheus packages are absent the API and
its tests still run, and `/metrics` degrades to a small stub.

## Drift detection

See [`../training/scripts/drift_report.py`](../training/scripts/drift_report.py)
and the [Phase 4 docs](../docs/PHASE4.md). Reports run on **synthetic data** by
default (no 747 MB dump needed) and are written under `drift/reports/`.
