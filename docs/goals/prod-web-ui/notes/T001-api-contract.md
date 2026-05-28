# T001 — Prod API contract (Scout)

## Summary
FastAPI service on port 8000, 6 unauthenticated JSON endpoints. The UI-relevant one is `POST /predict/draft`. Models are plain joblib `.pkl` files loaded from a shared Docker volume (`/app/models`); MLflow registry exists but logging is optional/NO-OP and the API never reads it. Two blockers for a browser UI: no CORS, no champion-list endpoint.

## Primary endpoint for the UI
`POST /predict/draft` — `api/app/main.py:226-237, 254-261, 339-405`
- Request (all `str`, champion names, flexible casing e.g. `'Lee Sin'`/`'leesin'`):
  `blue_top, blue_jungle, blue_mid, blue_adc, blue_support, red_top, red_jungle, red_mid, red_adc, red_support`
- Response: `winner: str ('Blue Team'|'Red Team')`, `blue_win_probability: float`, `red_win_probability: float`, `confidence: float`, `model_used: 'draft'`, `model_accuracy: float|null (~0.54)`

## Other endpoints
- `POST /predict/at/{minute}` (minute in {5,10,15,20}) — gold-diff based live prediction. `main.py:240-251, 408-462`
- `GET /models` — per-model availability/accuracy/type/n_features. `main.py:286-303`
- `GET /health` — status, DB, models map. `main.py:267-283`
- `GET /stats/overview` — DB-backed match stats (503 if DB down). `main.py:465-490`
- `GET /metrics` — Prometheus text. `main.py:69-107`

## Model serving / versioning
Joblib-pickled dicts `{model, scaler, feature_columns, features, metadata, external_data, synergy_data}` written by training to `MODELS_DIR`, loaded/cached by API from shared volume `models:/app/models` (`main.py:34,137-171`; `docker-compose.yml:83-84`). `MODEL_FILES` maps 5 fixed keys to filenames (`main.py:139-145`). MLflow names `lol_draft_at{minute}` registered during training (`train_all_models.py:336-340`) but tracking is NO-OP unless `MLFLOW_TRACKING_URI` set; API never queries MLflow. No version field in metadata (only `trained_at`, `accuracy`).

## Domain inputs
Draft model needs 10 champion picks, one per role (top/jungle/mid/adc/support) per team, blue=team_100 / red=team_200 (`main.py:306-336`, `feature_builder.py:33`). Names resolved via static `api/app/champion_id_map.json` — 172 entries, normalized-name -> `{id, name (Data-Dragon form)}`. This file is the UI's valid champion option source but is NOT exposed by any endpoint. Streamlit uses Data Dragon CDN icons (`streamlit/app/config.py:14-16`).

## Run
- `docker compose up -d` → api host port 8000, streamlit 8501, mlflow 5001 (`docker-compose.yml:6-14,76-77`)
- API base: in-network `http://api:8000`; host `http://localhost:8000`

## Gaps the UI must handle
1. **No CORS middleware** in `api/app/main.py` — browser app can't call API directly without it (or a proxy).
2. No auth on any endpoint (open API).
3. **No endpoint returns the champion list** — bundle `champion_id_map.json` into the UI or add an endpoint.
4. Streamlit does NOT call the API; it loads `.pkl` directly (`streamlit/app/model_loader.py:24-59`) — so it's not a runtime example of the HTTP contract.
5. Unknown champion names degrade silently to neutral features (no validation error) — UI should constrain input to the 172 known names.
6. Draft model accuracy ~0.54 (`main.py:363`) — UI should set realistic expectations.

## Key files
`api/app/main.py`, `api/app/feature_builder.py`, `api/app/champion_id_map.json`, `docker-compose.yml`, `streamlit/app/model_loader.py`, `training/scripts/train_all_models.py`
