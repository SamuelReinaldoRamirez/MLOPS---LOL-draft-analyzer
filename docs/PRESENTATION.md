# Soutenance — LoL Draft Predictor (MLOps)

Defense/presentation outline. Maps each of the **4 MLOps phases** to **concrete
deliverables in this repo** (file paths) and flags what is **demonstrable live**
vs **documented**. The live runbook is [`DEMO.md`](DEMO.md).

> Project in one line: a **League of Legends match win-probability analyzer**
> (draft + early-game timeline) wrapped in a reproducible, observable MLOps
> stack — 6 Docker services, a tested FastAPI inference API, MLflow tracking,
> GitHub Actions CI, Prometheus/Grafana monitoring and a drift-gated retrain hook.

---

## 0. Headline facts (accurate to the repo)

- **6 services** in [`docker-compose.yml`](../docker-compose.yml): `postgres`
  (5434), `streamlit` (8501), `api` (8000), `mlflow` (5001), `prometheus`
  (9090), `grafana` (3000) + an on-demand `training` profile. Network `lol-net`.
- **47 tests** pass via `python -m pytest -q` — **no Docker, no DB, no dump**
  required (models + DB are mocked / synthetic).
- **Data**: `database/lol_draft.dump` (~747 MB) is **git-ignored** and provided
  separately; it is **not** needed for tests or CI.
- Optional integrations (MLflow, Prometheus, Evidently) are **fail-safe NO-OP**
  when their dependency/server is absent — inference and tests never break.

---

## 1. Phase 1 — Reproducible base + inference API

**Goal:** a reproducible stack and a tested inference API over the existing models.

| Deliverable | Path | Live / Documented |
|---|---|---|
| Reproducible stack | [`docker-compose.yml`](../docker-compose.yml), [`.env.example`](../.env.example) | Live |
| FastAPI inference API | [`api/app/main.py`](../api/app/main.py) | Live |
| Routes: `/health`, `/models`, `/predict/at/{minute}`, `/predict/draft`, `/stats/overview`, `/metrics` | [`api/app/main.py`](../api/app/main.py) | Live |
| Test suite (no Docker/DB) | [`api/tests/`](../api/tests/), [`training/tests/`](../training/tests/) | Live (`pytest`) |
| Phase doc | [`PHASE1.md`](PHASE1.md) | Documented |

**Demonstrable live:** `make demo` brings the stack up; `curl /health`,
`curl /models`, and a real `POST /predict/at/10` (the timeline model is fully
wired to its features) return predictions; `pytest` runs the 47 tests offline.

**Draft endpoint (now meaningful):** `POST /predict/draft` builds the **real
champion-side features** — external winrate / tier / pickrate, lane matchups,
team synergy + counter scores and the derived draft advantage (**~69 of 153
features**) — from the lookup tables shipped *inside* `model_draft.pkl`
(`external_data` + `synergy_data`). Champion names are normalized and resolved
to ids via a static `api/app/champion_id_map.json` (no DB / Riot key at request
time). The prediction now **varies with the draft** (e.g. two different drafts →
0.536 vs 0.725 blue-win probability) instead of being constant. The **~84
summoner-level features** (per-player role winrate, mastery, streaks, recent
champion winrate) stay at neutral defaults because a draft request carries **no
player identity** — exactly what the original Streamlit flow does with no PUUID.
The draft model's own accuracy is **~0.54 by nature**. Documented in
[`PHASE1.md`](PHASE1.md) §5.

**Model KPIs (baseline served — not a Phase-1 improvement target):**

| Model | Accuracy | AUC | Type |
|---|---|---|---|
| Draft | 54.0% | 0.555 | XGBoost |
| @5min | 65.4% | 0.719 | LightGBM |
| @10min | 72.0% | 0.797 | XGBoost |
| @15min | 78.0% | 0.864 | XGBoost |
| @20min | 79.9% | 0.885 | XGBoost |

---

## 2. Phase 2 — Experiment tracking & versioning (MLflow)

**Goal:** track experiments and version models without breaking the stack/tests.

| Deliverable | Path | Live / Documented |
|---|---|---|
| MLflow tracking server (host port 5001, Postgres backend) | [`docker-compose.yml`](../docker-compose.yml), [`mlflow/`](../mlflow/) | Live |
| Instrumented training (params/metrics/artifact) | [`training/scripts/train_all_models.py`](../training/scripts/train_all_models.py) | Live (needs DB) |
| Fail-safe MLflow wrapper (NO-OP, fast-fail) | [`training/scripts/mlflow_tracking.py`](../training/scripts/mlflow_tracking.py) | Live + tested |
| Model Registry (`lol_draft_at{5,10,15,20}`) | MLflow UI | Live after a run |
| Data versioning — dump tag convention `lol_draft__<date>__<n>__<sha8>.dump` | [`PHASE2.md`](PHASE2.md) | Documented |
| Phase doc | [`PHASE2.md`](PHASE2.md) | Documented |

**Demonstrable live:** open MLflow at `http://localhost:5001`; after
`make train` (or `docker compose run --rm training`) the run appears under the
`lol-draft-timeline` experiment with params + metrics, and registered model
versions appear under "Models". Tested by
[`training/tests/test_mlflow_tracking.py`](../training/tests/test_mlflow_tracking.py)
(11 tests) including the NO-OP/fast-fail behaviour when the server is down.

**Honest caveat:** a real training run needs the DB / 747 MB dump. Without it,
MLflow degrades to NO-OP — the wiring is provable via tests + `--dry-run`, the
populated experiment requires `make demo` first. Stage promotion
(Staging/Production) is manual in the UI. DVC is deliberately deferred (tag-only
data versioning).

---

## 3. Phase 3 — CI, end-to-end orchestration & K8s skeleton

**Goal:** automate on top of Phases 1–2.

| Deliverable | Path | Live / Documented |
|---|---|---|
| GitHub Actions CI (lint / test / build) | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Live on push/PR |
| Lint config (ruff) | [`.ruff.toml`](../.ruff.toml) | Live |
| e2e orchestration | [`Makefile`](../Makefile) | Live |
| Make targets: `help env up up-db restore seed train demo test lint build logs ps down clean` (+ Phase-4 `monitoring-up/down metrics drift retrain`) | [`Makefile`](../Makefile) | Live |
| Kubernetes skeleton ("for later") | [`k8s/`](../k8s/) | Documented |
| Phase doc | [`PHASE3.md`](PHASE3.md) | Documented |

**Demonstrable live:** `make help` lists every target; `make test` runs the 47
tests; `make build` builds all images; CI runs the same three jobs on push/PR
without secrets or the dump.

**Honest caveat:** lint is **non-blocking** (`ruff check . --exit-zero`) on
purpose — we report pre-existing debt without rewriting working code. The
**K8s manifests are a skeleton** ("for later"): they are not part of the demo,
which runs on Docker Compose. Validate K8s via `kubectl apply --dry-run`, not a
live cluster.

---

## 4. Phase 4 — Monitoring, drift & automated updates

**Goal:** observability, drift detection and a drift-gated retrain hook.

| Deliverable | Path | Live / Documented |
|---|---|---|
| API Prometheus instrumentation + `/metrics` | [`api/app/main.py`](../api/app/main.py) | Live + tested |
| Custom metric `lol_predictions_total{model}` | [`api/app/main.py`](../api/app/main.py) | Live |
| Prometheus service (9090) | [`docker-compose.yml`](../docker-compose.yml), [`monitoring/prometheus/prometheus.yml`](../monitoring/prometheus/prometheus.yml) | Live |
| Grafana (3000) + provisioned datasource & dashboard | [`monitoring/grafana/`](../monitoring/grafana/) | Live |
| Evidently drift report (synthetic fallback) | [`training/scripts/drift_report.py`](../training/scripts/drift_report.py) | Live (synthetic) + tested |
| Drift-gated auto-retrain hook | [`scripts/auto_retrain.py`](../scripts/auto_retrain.py) | Live (decision) + tested |
| Phase doc | [`PHASE4.md`](PHASE4.md) | Documented |

**Demonstrable live:** `make monitoring-up`; query `lol_predictions_total` in
Prometheus at `http://localhost:9090`; open the **"LoL Draft Predictor — API &
Predictions"** dashboard in Grafana at `http://localhost:3000`; `make drift`
builds an Evidently report on synthetic data (no dump); `make retrain`
(dry-run) prints the drift-gated decision. Tested by
[`api/tests/test_metrics.py`](../api/tests/test_metrics.py),
[`training/tests/test_drift_report.py`](../training/tests/test_drift_report.py)
(8) and [`training/tests/test_auto_retrain.py`](../training/tests/test_auto_retrain.py) (9).

**Honest caveat:** drift runs on **synthetic data by default**. DB-backed drift
(`DRIFT_USE_DB=1`) is **documented but not demoed** without the dump. The
auto-retrain hook makes a real **decision** live, but actually shelling out to
training (`--force-drift` without `--dry-run`) needs the demo stack + dump.

---

## 5. What we'd do next (honest backlog)

- **Summoner-level draft features** are still neutral defaults (no PUUID in a
  draft request); a future identity-aware endpoint could wire the remaining ~84
  features. The ~69 champion-side features are already real (see §3 draft
  endpoint). Rebuild the API image (`docker compose build api`) to serve the
  wired logic, and add draft-model training to `train_all_models.py`.
- **Promote K8s from skeleton to running** (image registry, Postgres + Secret,
  models via PVC/initContainer) — currently "for later".
- **DB-backed drift in the demo** (`DRIFT_USE_DB=1` against a restored dump) and
  wire the auto-retrain trigger end-to-end on the live stack.
- **Lint hardening**: progressively fix ruff findings and flip CI lint from
  `--exit-zero` (non-blocking) to blocking.
- **Live Riot collection** (`RIOT_API_KEY`) for fresh data — intentionally out
  of scope for the defense demo (uses the existing dump).

---

## 6. Suggested defense flow (10–15 min)

1. **Context** — what the analyzer predicts; the 6-service architecture (README).
2. **Phase 1** — `pytest` (47 green, offline) + `curl /health` + a live
   `POST /predict/at/10`; mention the honest draft-feature caveat.
3. **Phase 2** — MLflow UI: experiment run + registered model versions.
4. **Phase 3** — `make help`, the CI run on GitHub, K8s skeleton note.
5. **Phase 4** — Grafana dashboard moving as you hit `/predict`, Prometheus
   query, `make drift`, `make retrain` decision.
6. **Next steps** — §5 backlog.

Full step-by-step commands and expected outputs: [`DEMO.md`](DEMO.md).
