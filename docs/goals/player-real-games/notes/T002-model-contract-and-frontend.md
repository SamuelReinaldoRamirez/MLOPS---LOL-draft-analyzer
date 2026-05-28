# T002: Model contract + match→draft mapping + frontend

Task: `T002`
Kind: `scout`
Status: `current`

## Summary

The model is served at `POST /predict/draft` taking **10 champion display NAMES by team+role** (blue→team_100, red→team_200), returning winner / blue+red win probabilities / confidence / model_used / model_accuracy. A `match-v5` detail maps cleanly to it by reverse-mapping each participant's `championId` → display name via `champion_id_map.json` (172 champs, byte-identical copy bundled in `frontend/`), with `teamId` 100=blue / 200=red. **Critical gaps**: the request requires per-role slots but match-v5 gives no reliable lane order (and spectator-v5 gives none at all), and the model takes NAMES not IDs. Live spectator reconstruction is identical minus win/result.

## Predict contract

- Route: `POST /predict/draft` (`api/app/main.py:354`); also `POST /predict/at/{minute}` (main.py:423).
- Request `DraftPredictionRequest` (main.py:241-252): 10 required **str** = champion DISPLAY NAMES (not IDs): `blue_top, blue_jungle, blue_mid, blue_adc, blue_support, red_top, red_jungle, red_mid, red_adc, red_support`. Blue→team_100, Red→team_200 (main.py:346). **No bans field. No PUUID/player field.** Names normalized (lowercase, strip non-alnum) → canonical name+id via static map (main.py:203-234). Unknown name degrades to neutral defaults (no error).
- Response `PredictionResponse` (main.py:269-276): `winner` ("Blue Team"|"Red Team"), `blue_win_probability` float, `red_win_probability` float, `confidence` float (=max prob), `model_used` str, `model_accuracy` Optional[float] (~0.54).

## champion_id_map

- `api/app/champion_id_map.json`: keyed by normalized_name (e.g. `leesin`) → `{id:int (Riot championId e.g. 266), name:str (Data-Dragon display e.g. 'LeeSin')}`. 172 entries. No model-index. Loaded/cached at main.py:199-221; used per-pick via `_resolve_champion` (main.py:224).
- Frontend copy: `frontend/src/data/champion_id_map.json` (byte-identical); `frontend/src/data/champions.ts:9-25` builds `CHAMPION_NAMES` + `isValidChampion`.
- **For match→draft you need a REVERSE index** id→name (the map is keyed by name).

## Match → draft mapping

For each of 10 participants in match-v5 `InfoDto.participants`: read `championId` + `teamId`. Reverse-map `championId`→display name. `teamId` 100→`blue_*`, 200→`red_*`. Assign role slot via `participant.teamPosition` (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY) → model `adc`←BOTTOM, `support`←UTILITY. Send 10 NAMES. Compare `response.blue_win_probability` vs ACTUAL result (`participant.win` / team-100 win flag). **Bans** (`InfoDto.teams[].bans[].championId`) are NOT used by the model (no ban field) — display-only.

### Mismatches / risks
1. Request needs NAMES; match gives `championId` → reverse-map required.
2. **ROLE ORDER is the central risk**: request demands explicit top/jgl/mid/adc/sup per team; match-v5 participant order is not guaranteed lane order. Use `teamPosition`/`individualPosition` — can be empty/UNKNOWN.
3. Queue filtering: only SR 5v5 (queueId 400/420/430/440) has a real 5-role draft; ARAM/Arena (450/1700+) break role mapping.
4. Remakes / early surrenders: valid but unrepresentative — `gameDuration` filter advisable.
5. Champion not in 172-set degrades SILENTLY to neutral defaults (no error) — looks valid but unreliable.

## Live (spectator-v5) → draft

Same reconstruction: `CurrentGameInfo.participants` carry `championId` + `teamId` (100/200) + `bannedChampions`. Build the same 10-name request. Differences: (a) **no win/result** (in progress) — show predicted prob only; (b) **no teamPosition/lane field at all** → role assignment even less certain (slot order arbitrary); (c) champions are locked by the time spectator data is available.

## Frontend

- Framework: **Next.js 14.2.35 App Router** (`frontend/src/app/`; `layout.tsx`+`page.tsx`), `output:'standalone'` (`frontend/next.config.mjs`).
- API client: `frontend/src/lib/api.ts` (`predictDraft` at :52; types :22-44). API base env: `NEXT_PUBLIC_API_BASE_URL` (api.ts:9-10, default http://localhost:8000).
- Existing screens: `frontend/src/app/page.tsx` (single draft-input screen, 'use client'); components `ChampionPicker.tsx`, `ResultPanel.tsx`; data `champions.ts`. No routing beyond root `/`. No Riot/search/history code.
- Extension points: add App-Router routes under `frontend/src/app/` (e.g. `app/search`, `app/games`, `app/match/[id]`). **Riot key must stay server-side** — either a FastAPI backend route (recommended, reuses champion map + predict) or a Next route handler proxy; never `NEXT_PUBLIC`.

## Two load-bearing facts

1. Model takes champion **display names**, not IDs → every match/spectator `championId` must be reverse-mapped through `champion_id_map.json`.
2. `DraftPredictionRequest` mandates explicit per-role slots while match-v5/spectator-v5 give unreliable or absent lane positions → **role-assignment is the central reconstruction risk**.
