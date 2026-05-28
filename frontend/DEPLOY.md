# Deploying the Web UI publicly (Vercel + PaaS)

A step-by-step runbook to put the LoL Draft Predictor UI live on the public
internet. No deep DevOps knowledge required — follow the numbered steps and
copy-paste the commands, replacing every `<placeholder>`.

You will end up with two public URLs:

- a **frontend** URL on Vercel (the page people visit), and
- an **API** URL on a PaaS (the prediction backend the browser calls).

---

## 1. Architecture overview

The browser loads the Next.js app from Vercel, then makes a **cross-origin
`fetch`** directly from the user's browser to the public API hosted on a PaaS.
The two run on **different origins** (different domains), so the API **must**
allow the Vercel domain via CORS or the browser will block every request.

```
                    cross-origin fetch
                 (browser -> public API)
  ┌──────────┐   GET  /health             ┌────────────────────────┐
  │  Browser │ ─────────────────────────▶ │  API (FastAPI) on PaaS  │
  │          │   POST /predict/draft      │  Render / Railway / Fly │
  │ loads UI │ ◀───────────────────────── │  / Cloud Run            │
  └────┬─────┘     JSON prediction         └───────────┬────────────┘
       │                                               │
       │ HTML / JS / CSS                               │ reads
       ▼                                               ▼
  ┌──────────────────┐                       ┌──────────────────────┐
  │ Next.js on Vercel│                       │ Postgres + model .pkl │
  └──────────────────┘                       └──────────────────────┘
```

> The API base URL is **baked into the browser bundle at build time** via
> `NEXT_PUBLIC_API_BASE_URL`. It is public and not a secret — but it must point
> at the **public** API URL, never `localhost`.

---

## 2. Prerequisites / operator inputs

Gather these before you start. Items marked **decision** need a human choice.

- [ ] **Vercel account** (free tier is fine) connected to this Git repo.
- [ ] **A PaaS account** for the API container — Render, Railway, Fly.io, or
      Google Cloud Run. This runbook uses **Render** as the worked example;
      the others are analogous (point them at `api/Dockerfile`, set the same
      env vars).
- [ ] **A managed Postgres** database — either a standalone managed instance or
      the PaaS's Postgres add-on. The API uses it for the `/stats/*` endpoints.
      You will need its host, port, database name, user, and password.
- [ ] **The trained model files** (`model_draft.pkl`, and optionally
      `model_at5.pkl` … `model_at20.pkl`). Locally these are injected into a
      Docker `models` volume by `scripts/seed_models.sh`. **That volume does NOT
      exist on a PaaS** — see Step A for how to get the `.pkl` files into the
      container.
- [ ] **decision — API exposure:** the API ships **public and
      unauthenticated**. Decide before going live whether to keep it open or
      add an API key / rate limiting / put it behind the same domain. See the
      [Security note](#6-security-note).
- [ ] *(optional)* **Custom domains** for the frontend and/or API.

---

## 3. Step A — Deploy the API to a PaaS (Render example)

### A.1 Create the service from the API Dockerfile

1. In Render, **New → Web Service** and connect this repository.
2. Set **Root Directory** to `api/`. Render will detect and use
   `api/Dockerfile` (which runs `uvicorn app.main:app` on port `8000`).
3. Choose an instance size and region, then create the service. You will get a
   public URL like `https://<your-api-host>.onrender.com`.

### A.2 Set the API environment variables

Set these on the API service. The **only** name you must set verbatim for the
browser to work is `CORS_ALLOW_ORIGINS`; the rest are read by the API at
startup.

```bash
# CORS — comma-separated list of origins allowed to call the API from a browser.
# Set this to your Vercel URL(s). You can fill the real value in Step C once you
# know the Vercel domain; use a placeholder for now.
CORS_ALLOW_ORIGINS=https://<your-vercel-domain>

# PostgreSQL connection (read by api/app/main.py at startup).
POSTGRES_HOST=<db-host>
POSTGRES_PORT=<db-port>            # 5432 on most managed Postgres
POSTGRES_DB=<db-name>
POSTGRES_USER=<db-user>
POSTGRES_PASSWORD=<db-password>

# Where the API looks for model .pkl files (default /app/models — see A.3).
MODELS_DIR=/app/models
```

> **Confirm the exact var names** against `api/app/main.py` and the repo
> `.env.example` before deploying. (At time of writing the API reads
> `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
> `POSTGRES_PASSWORD`, `CORS_ALLOW_ORIGINS`, and `MODELS_DIR`.)

**MLflow vars are optional / no-op for serving.** The inference API does not
need MLflow; leave any `MLFLOW_*` vars unset.

### A.3 Get the model `.pkl` files into `/app/models`

The API loads joblib models from `MODELS_DIR` (default `/app/models`). The
local docker-compose `models` **volume does not exist on a PaaS**, so the
models must be **baked into the image**. `api/Dockerfile` already does this:
after copying `app/`, it runs `COPY models/ /app/models/`, so any
`model_*.pkl` staged into the build context at `api/models/` lands in
`/app/models`. Stage them **before** the build:

```bash
# Copies model_*.pkl from the source project into api/models/ (gitignored).
# Same source detection as seed_models.sh (SOURCE_MODELS_DIR, then the sibling
# project); fails clearly if no source models are found.
./scripts/stage_models_for_image.sh
# (or manually: cp /path/to/model_*.pkl api/models/)
```

Then build/deploy normally — on Render, set Root Directory to `api/` and it
builds `api/Dockerfile`, baking the staged models to `/app/models`. The
`.pkl` files are **never committed** (they are gitignored under `api/models/`);
only the `.gitkeep` is tracked so the build-context folder always exists and
the `COPY` never fails, even with no models staged.

> The build context is `./api`, so models **must** sit under `api/models/`
> (not elsewhere) to be copied. Locally this is harmless: the docker-compose
> `models` volume shadows `/app/models`, so the volume seeded by
> `scripts/seed_models.sh` still wins and local behavior is unchanged.

*Alternative — fetch from object storage on startup.* Store the `.pkl` files in
S3 / GCS and have the container download them into `MODELS_DIR` before serving.

Either way, `model_draft.pkl` must be present for `/predict/draft` to work.

### A.4 Verify the API is live

```bash
# Should return {"status":"healthy", "database": ..., "models": {...}}
curl https://<your-api-host>/health

# Draft model must show "available": true
curl https://<your-api-host>/models
```

If `/models` shows `"draft": {"available": false}`, the `.pkl` files did not
reach `/app/models` — revisit A.3.

---

## 4. Step B — Deploy the frontend to Vercel

1. In Vercel, **Add New… → Project** and import this repository.
2. Set the **Root Directory** to `frontend/`. Vercel auto-detects Next.js — no
   custom build or output command is needed. (`frontend/vercel.json` pins the
   framework to `nextjs` for clarity; nothing else is required.)
3. Add the environment variable, for **both Production and Preview**:

   ```bash
   NEXT_PUBLIC_API_BASE_URL=https://<your-api-host>
   ```

   > This is **build-time / public** — it is inlined into the browser bundle, so
   > it must be the **public** API URL, **not** `http://localhost:8000`. If you
   > change it later, you must **redeploy** for the new value to take effect.

4. Deploy. Vercel gives you a Production URL like
   `https://<your-vercel-domain>.vercel.app`.

---

## 5. Step C — Wire CORS (do this after both URLs exist)

The browser calls the API from the Vercel origin, so the API must explicitly
allow that origin.

1. Go back to the API service (Render) env vars and set:

   ```bash
   CORS_ALLOW_ORIGINS=https://<your-vercel-domain>.vercel.app
   ```

   To also allow Vercel preview deployments, add their origins comma-separated
   (no spaces required, the API trims them):

   ```bash
   CORS_ALLOW_ORIGINS=https://<your-vercel-domain>.vercel.app,https://<preview-domain>.vercel.app
   ```

2. **Redeploy / restart the API** so it picks up the new value.
3. Open the deployed UI, submit a draft, and confirm a prediction returns with
   **no CORS error** in the browser console (DevTools → Console / Network). A
   blocked request shows as a CORS error and means the origin above does not
   exactly match the Vercel URL.

---

## 6. Security note

> **The API is currently public and UNAUTHENTICATED.** Anyone who learns the
> API URL can call `/predict/*` and `/stats/*` directly. Before a truly public
> launch you should, at minimum:
>
> - add **rate limiting** on the PaaS / a gateway in front of the API, and
> - consider an **API key** (require a header the frontend sends) **or** put the
>   API behind the same domain as the frontend (e.g. a Vercel rewrite / reverse
>   proxy) so it is not independently reachable.
>
> Treat this as a required decision, not an afterthought.

---

## 7. Quick verification checklist

Run these against your live URLs.

```bash
# 1. API health
curl https://<your-api-host>/health

# 2. Draft model available
curl https://<your-api-host>/models

# 3. Sample prediction (10 champions: 5 blue + 5 red)
curl -X POST https://<your-api-host>/predict/draft \
  -H "Content-Type: application/json" \
  -d '{
    "blue_top": "Aatrox",
    "blue_jungle": "LeeSin",
    "blue_mid": "Ahri",
    "blue_adc": "Jinx",
    "blue_support": "Thresh",
    "red_top": "Darius",
    "red_jungle": "Vi",
    "red_mid": "Syndra",
    "red_adc": "Caitlyn",
    "red_support": "Lulu"
  }'
# Expect: {"winner": "...", "blue_win_probability": ..., "red_win_probability": ...,
#          "confidence": ..., "model_used": "draft", "model_accuracy": ...}
```

- [ ] `/health` returns `"status": "healthy"`.
- [ ] `/models` shows `"draft": {"available": true}`.
- [ ] The sample `/predict/draft` curl returns a JSON prediction.
- [ ] **Browser walkthrough:** open `https://<your-vercel-domain>.vercel.app`,
      pick the 10 champions, submit, and see a prediction render — with **no
      CORS error** in the browser console.
- [ ] You have made (and documented) the [public/unauthenticated decision](#6-security-note).
