# Player real-games walkthrough — operator runbook

How to run the LIVE real-data flow: search a Riot ID → see real recent games →
view predicted-vs-actual for a past game → check for a live game.

## 1. Prerequisite: a Riot API key

You need a Riot Games API key (https://developer.riotgames.com). Add it to the
**live `.env`** at the repo root (NOT just `.env.example` — the `api` container
reads `.env` via `env_file`):

```dotenv
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RIOT_PLATFORM=euw1      # your account's platform, e.g. euw1 / na1 / oc1
RIOT_REGION=europe      # regional cluster, e.g. europe / americas / asia / sea
```

- The key is **server-side only**. Never prefix it with `NEXT_PUBLIC_`, and never
  commit it. `.env` is gitignored; `.env.example` carries placeholders only.

## 2. Run it

```bash
docker compose up
```

This starts the API (with the key from `.env`) and serves the frontend. Use the
existing local dev commands if you prefer running services directly.

## 3. Walkthrough (what you should see)

1. Open the UI. The top nav has **"Find my games"** (and the home page has an
   **"Analyze your real games →"** button) — click either.
2. On **/search**, enter a Riot ID as `gameName#tagLine` and pick the region.
3. Select the resolved player → routes to **/games**.
4. **/games** lists the player's real recent Summoner's Rift matches.
5. Click **"Analyze →"** on a game → **/match/[matchId]** shows the model's
   predicted win probability vs the **ACTUAL** result, with a correct/incorrect
   indicator.
6. Click **"Check live game"** → **/live** shows a live prediction if the player
   is currently in a game, otherwise a graceful "No live game right now".

## 4. Caveats

- **OCE (`oc1`)** routes via the **`sea`** regional cluster for account-v1 (Riot
  ID lookup); set `RIOT_REGION=sea` for OCE accounts.
- **Live/spectator games** show a **"lanes approximate"** note — spectator data
  has no role positions, so lanes are inferred.
- **Personal dev keys** are heavily rate-limited and **expire ~24h**; regenerate
  the key and update `.env` if calls start failing.

## 5. Troubleshooting

- **503 from the API / "Riot API key not configured"** → `RIOT_API_KEY` is
  missing from the **live `.env`**. Add it and restart (`docker compose up`).
- **Rate-limited** → wait a moment and retry; dev keys have tight limits.
- **Player not found** → check the Riot ID spelling and that the region matches
  the account's platform/cluster (see the OCE caveat above).
