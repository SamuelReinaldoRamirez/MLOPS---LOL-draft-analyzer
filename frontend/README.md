# LoL Draft Win Predictor — Web UI

A clean, non-technical-friendly web app for picking a League of Legends draft
(5 roles per team) and getting a win prediction from the prediction API.

## Prerequisites

- Node 20+ / npm 10+
- The prediction API running and reachable. The easiest way is via the repo's
  docker-compose stack:

  ```bash
  # from the repository root
  docker compose up -d api
  ```

  The API listens on `http://localhost:8000` by default.

## Run it locally

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:3000.

## Run it with Docker (compose)

The web UI is containerised (multi-stage Next.js standalone build) and wired
into the repo's `docker-compose.yml` as the `frontend` service.

```bash
# from the repository root
docker compose up -d --build frontend
```

Then open http://localhost:8080.

This is a **cross-origin** setup (mirroring a Vercel + PaaS production model):
the page is served from port 8080, but the prediction request runs in the
**browser** and goes directly to the API at `NEXT_PUBLIC_API_BASE_URL`
(default `http://localhost:8000`). Because the fetch is client-side, the API
URL is the host-reachable one, **not** the compose-internal `http://api:8000`.

Two consequences:

- The API must be running and reachable from your machine
  (`docker compose up -d api`).
- The API's CORS allow-list must include the UI origin. The compose `api`
  service sets `CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS:-http://localhost:8080,http://localhost:3000}`,
  which already covers `http://localhost:8080`. If you change ports or the API
  was already running with the old value, recreate it:
  `docker compose up -d --force-recreate api`.

`NEXT_PUBLIC_API_BASE_URL` is a **build arg** for the image (it is inlined into
the client bundle), so rebuild the `frontend` image after changing it.

## Configuration

The app reads the API base URL from `NEXT_PUBLIC_API_BASE_URL`, falling back to
`http://localhost:8000` if it is not set.

```bash
cp .env.local.example .env.local   # then edit if your API runs elsewhere
```

`NEXT_PUBLIC_API_BASE_URL` is read at build time and embedded into the client
bundle, so re-build/re-start `npm run dev` after changing it.

## How it works

1. Pick a champion for each of the 10 roles (Top, Jungle, Mid, ADC, Support for
   Blue and Red). Selectors are constrained to the 172 valid champions — the
   list is bundled from `api/app/champion_id_map.json`, so the dropdowns work
   without the API.
2. Click **Predict winner**. The app POSTs the 10 picks to
   `POST {API_BASE}/predict/draft`.
3. The result shows the favoured team, blue vs red win probabilities, the
   model's confidence, and its accuracy — with an honest note that the
   draft-only model is roughly baseline accuracy.

If the API is unreachable or returns an error, a friendly message is shown
instead of crashing.

## Scripts

```bash
npm run dev     # local dev server (http://localhost:3000)
npm run build   # production build (includes TypeScript typecheck)
npm run lint    # ESLint
npm run start   # serve the production build
```
