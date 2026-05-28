# Documentation index — LoL Draft Predictor (MLOps)

Project documentation for the **League of Legends draft / early-game win-
probability analyzer** and its MLOps stack. Start at the root
[`../README.md`](../README.md) for the project front door.

## Contents

| Doc | What it covers |
|---|---|
| [`../README.md`](../README.md) | Project front door: summary, architecture (6 services), quick start, demo URLs, tests, phase table |
| [`PRESENTATION.md`](PRESENTATION.md) | Soutenance/defense outline — each of the 4 phases mapped to repo deliverables (live vs documented) + what's next |
| [`DEMO.md`](DEMO.md) | Step-by-step demo runbook: prerequisites, ordered commands, expected results, verification, teardown |
| [`PHASE1.md`](PHASE1.md) | Phase 1 — reproducible base, inference API, tests, model KPIs |
| [`PHASE2.md`](PHASE2.md) | Phase 2 — MLflow experiment tracking + model/data versioning |
| [`PHASE3.md`](PHASE3.md) | Phase 3 — GitHub Actions CI, `Makefile` orchestration, K8s skeleton |
| [`PHASE4.md`](PHASE4.md) | Phase 4 — Prometheus/Grafana monitoring, Evidently drift, auto-retrain hook |

## Quick links

- **Presenting?** → [`PRESENTATION.md`](PRESENTATION.md)
- **Running the live demo?** → [`DEMO.md`](DEMO.md)
- **Phase deep-dives?** → [`PHASE1.md`](PHASE1.md) · [`PHASE2.md`](PHASE2.md) · [`PHASE3.md`](PHASE3.md) · [`PHASE4.md`](PHASE4.md)
