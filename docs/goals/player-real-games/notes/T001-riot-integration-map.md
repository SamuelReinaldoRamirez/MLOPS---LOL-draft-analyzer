# T001: Riot API integration — REAL state

Task: `T001`
Kind: `scout`
Status: `current`

## Summary

The operator's "Riot API is already integrated" claim is **FALSE**. There is no Riot Games API integration anywhere in the repo: no account-v1, no match-v5, no spectator endpoints, no calls to `api.riotgames.com`, no `X-Riot-Token` usage. The FastAPI app only serves ML win-prediction from manually-supplied champion names / timeline numbers against the local Postgres DB. `RIOT_API_KEY` exists only as a blank placeholder explicitly marked "OUT OF SCOPE for Phase 1". The entire `player-real-games` data path (search/select, history, past-game detail, live/spectator) is MISSING and must be built from scratch.

## Details

- **Riot endpoints**: all MISSING.
  - summoner/account lookup — none; `summoner` refs in `api/app/feature_builder.py:14,209` are ML feature-block names, not Riot lookups.
  - match-v5 history — none; `matches` at `api/app/main.py:484` is a local Postgres table.
  - match-v5 detail — none; draft data comes from the request body (`api/app/main.py:241-252`) or DB rows.
  - spectator-v4/v5 — none; repo-wide grep for `spectator`/`active-games` = 0 hits.
- **API key**: `RIOT_API_KEY` blank in `.env.example:52`; comment line 50 says "OUT OF SCOPE for Phase 1". Not in `docker-compose.yml`, `k8s/`, `database/.env.example`, `streamlit/app/config.py`, or any `api/` code. Never read by any code path.
- **Region/routing**: not handled anywhere (no platform `euw1` / regional `europe` constants).
- **Rate-limit handling**: none (no Riot calls exist).
- **HTTP client**: `httpx>=0.27.0` in `api/requirements.txt:19` but under "Test dependencies" (FastAPI TestClient transport, NOT a Riot client). No `requests`/`aiohttp`. No outbound HTTP client instantiated in `api/app/`.
- **Exposed routes today**: `GET /health` (main.py:282), `GET /models` (main.py:301), `POST /predict/draft` (main.py:354), `POST /predict/at/{minute}` (main.py:423), `GET /stats/overview` (main.py:480, local DB).

## Gaps vs feature

- search_select: **missing** — no Riot ID / summoner-name lookup, no puuid resolution route.
- match_history: **missing** — no endpoint returns match IDs by puuid.
- past_game_detail: **missing** — drafts are supplied manually; no path reconstructs a real game's draft/result.
- live_spectator: **missing** — no spectator integration at all.

## Implications

- Authority change: a **real Riot API key is now a required operator credential**, but only for live end-to-end verification. All client code + routes + draft reconstruction can be built and unit-tested against recorded fixtures without a live key.
- New backend surface needed: async Riot client (httpx), platform+regional routing config, `RIOT_API_KEY` wired server-side, rate-limit/backoff + caching, and new routes (summoner search, match history, past-game draft, live draft).

## Evidence

- `api/app/main.py:241,269,354,423,480` ; `api/app/main.py:196,365` (comments: no DB/Riot at request time)
- `api/app/feature_builder.py:13,71,209` ("No database access, no Riot API")
- `.env.example:50-52` (RIOT_API_KEY blank, out of scope)
- `api/requirements.txt:17-19` (httpx test-only)
- repo-wide grep `api.riotgames.com` / `X-Riot-Token` / `by-puuid` / `account/v1` / `match/v5` / `spectator` = 0 functional hits
