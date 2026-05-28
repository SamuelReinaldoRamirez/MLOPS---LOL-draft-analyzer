"""
LoL Draft Predictor — FastAPI Inference API

Endpoints:
  GET  /health              Health check
  GET  /models              List available models
  POST /predict/draft       Predict from draft composition
  POST /predict/at/{minute} Predict with early-game data
  GET  /stats/overview      Database overview stats
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, List, Any

import joblib
import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.draft_reconstruction import DraftReconstructionError
from app.feature_builder import POSITIONS, add_all_model_features
from app.match_history import summarize_matches_for_player
from app.match_prediction import build_live_prediction, build_match_prediction
from app.riot_client import DEFAULT_PLATFORM, RiotClient, RiotError
from app.riot_models import (
    LivePredictionResponse,
    MatchActualResult,
    MatchHistoryResponse,
    MatchPrediction,
    MatchPredictionResponse,
    MatchTimelinePredictionResponse,
    PlayerSuggestion,
    PlayerSuggestionsResponse,
    SummonerResult,
    TimelineCheckpoint,
)
from app.timeline_features import (
    TimelineReconstructionError,
    build_timeline_prediction,
)

app = FastAPI(
    title="LoL Draft Predictor API",
    description="ML-powered League of Legends match outcome prediction",
    version="1.0.0",
)

# Allow the web UI (browser) to call the API cross-origin. Origins come from the
# comma-separated CORS_ALLOW_ORIGINS env var (defaults to the local Next.js dev
# server). Follows the existing os.getenv pattern; ships with fastapi (no new dep).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))

# ──────────────────────────────────────────
# Phase 4: Prometheus monitoring
#
# Instrumentation is FAIL-SAFE by design. If
# ``prometheus-fastapi-instrumentator`` / ``prometheus_client`` are not
# installed (e.g. a minimal env), the API and its 27-test suite keep working —
# the /metrics endpoint just degrades to a small 200 stub. This mirrors the
# Phase-2 MLflow NO-OP contract: monitoring must never break inference.
# ──────────────────────────────────────────

# Custom business metric: a counter of predictions served, labelled by model.
PREDICTIONS_TOTAL = None
try:  # pragma: no cover - exercised indirectly by the /metrics test
    from prometheus_client import Counter

    PREDICTIONS_TOTAL = Counter(
        "lol_predictions_total",
        "Total number of match-outcome predictions served by the API.",
        ["model"],
    )
except Exception:  # pragma: no cover - prometheus_client absent
    PREDICTIONS_TOTAL = None


def _record_prediction(model: str) -> None:
    """Increment the prediction counter (NO-OP if prometheus_client absent)."""
    if PREDICTIONS_TOTAL is not None:
        try:
            PREDICTIONS_TOTAL.labels(model=model).inc()
        except Exception:  # pragma: no cover - never let metrics break inference
            pass


def _setup_metrics(app_: FastAPI) -> None:
    """Wire request count/latency metrics + expose /metrics on ``app_``.

    Uses ``prometheus-fastapi-instrumentator`` (default HTTP request/latency
    histograms + the custom ``lol_predictions_total`` counter registered
    above). If the package is unavailable, registers a tiny fallback /metrics
    route so the contract (200 + Prometheus text) still holds.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
        ).instrument(app_).expose(app_, endpoint="/metrics", include_in_schema=True)
        return
    except Exception:  # pragma: no cover - instrumentator absent
        pass

    # Fallback: still serve Prometheus-format text so monitoring/tests work.
    @app_.get("/metrics", include_in_schema=True)
    def _metrics_fallback():  # pragma: no cover - only on minimal envs
        from fastapi.responses import PlainTextResponse

        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            return PlainTextResponse(
                generate_latest(), media_type=CONTENT_TYPE_LATEST
            )
        except Exception:
            return PlainTextResponse(
                "# prometheus_client unavailable\n"
                "lol_metrics_stub 1\n",
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )


_setup_metrics(app)

# ──────────────────────────────────────────
# Database helpers
# ──────────────────────────────────────────

def get_dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'lol_draft')} "
        f"user={os.getenv('POSTGRES_USER', 'lol_admin')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'changeme')}"
    )


def fetchone(query: str, params=None):
    conn = psycopg2.connect(get_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()
    finally:
        conn.close()


# Trigram similarity floor for fuzzy name matching. 0.2 keeps short, partial and
# slightly-misspelled queries matching (e.g. "zchook" -> "zChooke") while still
# filtering out unrelated names. Set per-session before the suggest query so the
# `%` operator + GIN index behave consistently regardless of server defaults.
_SUGGEST_SIMILARITY_THRESHOLD = 0.2

# Fuzzy + prefix player-name lookup against the `player_name_suggestions`
# materialized view (see database/migrations/003_player_suggestions.sql). Matches
# case-insensitively via lower(name); ranks exact match first, then trigram
# similarity, then popularity (games). Fully parameterized (no SQL injection).
_SUGGEST_QUERY = """
    SELECT riot_id_name,
           riot_id_tagline,
           games,
           similarity(lower(riot_id_name), lower(%(q)s)) AS sim
    FROM player_name_suggestions
    WHERE lower(riot_id_name) %% lower(%(q)s)
       OR lower(riot_id_name) LIKE lower(%(q)s) || '%%'
    ORDER BY (lower(riot_id_name) = lower(%(q)s)) DESC,
             sim DESC,
             games DESC
    LIMIT %(limit)s
"""


def _fetch_suggestions(q: str, limit: int):
    """Return ranked fuzzy player-name rows for ``q`` from the matview.

    Opens a short-lived connection (same pattern as :func:`fetchone`), sets the
    per-session trigram threshold, runs the parameterized fuzzy query and returns
    a list of ``(riot_id_name, riot_id_tagline, games, sim)`` tuples. Kept as a
    standalone helper so tests can monkeypatch it (or patch ``psycopg2.connect``)
    and exercise the route WITHOUT a real database.
    """
    conn = psycopg2.connect(get_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SET pg_trgm.similarity_threshold = %s",
                (_SUGGEST_SIMILARITY_THRESHOLD,),
            )
            cur.execute(_SUGGEST_QUERY, {"q": q, "limit": limit})
            return cur.fetchall()
    finally:
        conn.close()


# ──────────────────────────────────────────
# Model loading (cached at startup)
# ──────────────────────────────────────────

_model_cache: Dict[str, Any] = {}

MODEL_FILES = {
    "draft": "model_draft.pkl",
    "at5": "model_at5.pkl",
    "at10": "model_at10.pkl",
    "at15": "model_at15.pkl",
    "at20": "model_at20.pkl",
}


def _load_model(key: str) -> Optional[Dict]:
    """Load and cache a model."""
    if key in _model_cache:
        return _model_cache[key]

    filename = MODEL_FILES.get(key)
    if not filename:
        return None

    filepath = MODELS_DIR / filename
    if not filepath.exists():
        return None

    try:
        data = joblib.load(filepath)
        # Normalize keys
        if "features" not in data and "feature_columns" in data:
            data["features"] = data["feature_columns"]
        elif "feature_columns" not in data and "features" in data:
            data["feature_columns"] = data["features"]
        _model_cache[key] = data
        return data
    except Exception:
        return None


# ──────────────────────────────────────────
# Champion name -> id resolution (DB-free at request time)
#
# ``champion_id_map.json`` was generated ONCE from the live DB
# (champion_synergies + champion_matchups). It maps a *normalized* champion name
# (lowercase, alphanumerics only) to the champion's numeric id and its canonical
# Data-Dragon string form ("MissFortune", "LeeSin", ...). The draft route reads
# this static file so it never needs a DB or Riot key at inference time.
# ──────────────────────────────────────────

_CHAMPION_MAP_PATH = Path(__file__).parent / "champion_id_map.json"
_champion_map: Optional[Dict[str, Dict[str, Any]]] = None


def _normalize_champion_name(name: str) -> str:
    """Normalize a champion name for lookup (lowercase, alphanumerics only).

    Mirrors the form used to build ``champion_id_map.json`` so request strings
    like "Lee Sin", "leesin" or "Miss Fortune" all resolve to the same key.
    """
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _load_champion_map() -> Dict[str, Dict[str, Any]]:
    """Load and cache the static champion name->id map."""
    global _champion_map
    if _champion_map is None:
        try:
            with open(_CHAMPION_MAP_PATH, "r", encoding="utf-8") as fh:
                _champion_map = json.load(fh)
        except Exception:  # pragma: no cover - file ships with the package
            _champion_map = {}
    return _champion_map


def _resolve_champion(name: str):
    """Resolve a champion name to (canonical_name, champion_id).

    Falls back gracefully to ``(stripped_name, None)`` for unknown champions so
    the feature builder lands on its neutral defaults instead of crashing.
    """
    cmap = _load_champion_map()
    entry = cmap.get(_normalize_champion_name(name))
    if entry:
        return entry.get("name", str(name).strip()), entry.get("id")
    return str(name).strip(), None


# ──────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────

class DraftPredictionRequest(BaseModel):
    """Request body for draft-based prediction."""
    blue_top: str = Field(..., description="Blue team top champion name")
    blue_jungle: str = Field(..., description="Blue team jungle champion name")
    blue_mid: str = Field(..., description="Blue team mid champion name")
    blue_adc: str = Field(..., description="Blue team ADC champion name")
    blue_support: str = Field(..., description="Blue team support champion name")
    red_top: str = Field(..., description="Red team top champion name")
    red_jungle: str = Field(..., description="Red team jungle champion name")
    red_mid: str = Field(..., description="Red team mid champion name")
    red_adc: str = Field(..., description="Red team ADC champion name")
    red_support: str = Field(..., description="Red team support champion name")


class TimelinePredictionRequest(BaseModel):
    """Request body for timeline-based prediction."""
    gold_diff: float = Field(..., description="Total gold difference (blue - red)")
    top_gold_diff: float = 0
    jungle_gold_diff: float = 0
    mid_gold_diff: float = 0
    adc_gold_diff: float = 0
    support_gold_diff: float = 0
    first_blood: bool = False
    first_tower: bool = False
    first_dragon: bool = False
    first_herald: bool = False


class PredictionResponse(BaseModel):
    winner: str
    blue_win_probability: float
    red_win_probability: float
    confidence: float
    model_used: str
    model_accuracy: Optional[float] = None


# ──────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────

@app.get("/health")
def health():
    """Health check endpoint."""
    db_ok = False
    try:
        row = fetchone("SELECT 1")
        db_ok = row is not None
    except Exception:
        pass

    models_available = {k: (MODELS_DIR / v).exists() for k, v in MODEL_FILES.items()}

    return {
        "status": "healthy",
        "database": "connected" if db_ok else "disconnected",
        "models": models_available,
    }


@app.get("/models")
def list_models():
    """List all available models and their metadata."""
    result = {}
    for key, filename in MODEL_FILES.items():
        filepath = MODELS_DIR / filename
        if filepath.exists():
            data = _load_model(key)
            meta = data.get("metadata", {}) if data else {}
            result[key] = {
                "available": True,
                "accuracy": meta.get("accuracy"),
                "model_type": meta.get("model_type"),
                "n_features": len(data.get("feature_columns", [])) if data else 0,
            }
        else:
            result[key] = {"available": False}
    return result


def _build_draft_feature_row(req: "DraftPredictionRequest") -> pd.DataFrame:
    """Build a 1-row DataFrame of champion picks from a draft request.

    Blue team maps to ``team_100`` and red to ``team_200`` (matching the
    training schema). Each pick contributes a ``champion_name`` (canonical
    Data-Dragon form) and a ``champion_id`` resolved via the static map.
    Unknown champions degrade to ``(stripped_name, None)`` so the feature
    builder falls back to its neutral defaults rather than failing.
    """
    blue = {
        "top": req.blue_top,
        "jungle": req.blue_jungle,
        "mid": req.blue_mid,
        "adc": req.blue_adc,
        "support": req.blue_support,
    }
    red = {
        "top": req.red_top,
        "jungle": req.red_jungle,
        "mid": req.red_mid,
        "adc": req.red_adc,
        "support": req.red_support,
    }

    row: Dict[str, Any] = {}
    for team, picks in (("team_100", blue), ("team_200", red)):
        for pos in POSITIONS:
            canon, cid = _resolve_champion(picks[pos])
            row[f"{team}_{pos}_champion_name"] = canon
            row[f"{team}_{pos}_champion_id"] = cid
    return pd.DataFrame([row])


def predict_draft_from_names(
    names: "DraftPredictionRequest | Dict[str, Any]",
) -> PredictionResponse:
    """Predict a match outcome from the 10 champion-NAME slots (CORE, reusable).

    This is the extracted prediction core shared by the ``POST /predict/draft``
    route and the past-game per-match prediction (T006). It accepts either a
    :class:`DraftPredictionRequest` or a plain ``dict`` carrying the 10
    ``blue_top .. red_support`` champion-name keys (extra keys such as
    ``fallback_used``/``warnings`` from :func:`reconstruct_draft` are ignored).

    Behaviour is byte-identical to the original inline route logic:

    * Loads the draft model via ``MODEL_FILES["draft"]``; raises HTTP 404 if it
      is unavailable and HTTP 503 if it has no feature schema (so the existing
      route's error contract is preserved).
    * Blue picks map to ``team_100`` and red to ``team_200``; champion names are
      resolved to ids via the static ``champion_id_map.json`` (no DB / Riot at
      request time), then the REAL champion-side features are built and the
      model schema is neutral-filled — falling back to an all-zero row if the
      builder hiccups.
    * Records the prediction metric and returns the same
      :class:`PredictionResponse`.
    """
    req = names if isinstance(names, DraftPredictionRequest) else DraftPredictionRequest(
        blue_top=names["blue_top"],
        blue_jungle=names["blue_jungle"],
        blue_mid=names["blue_mid"],
        blue_adc=names["blue_adc"],
        blue_support=names["blue_support"],
        red_top=names["red_top"],
        red_jungle=names["red_jungle"],
        red_mid=names["red_mid"],
        red_adc=names["red_adc"],
        red_support=names["red_support"],
    )

    model_data = _load_model("draft")
    if model_data is None:
        raise HTTPException(404, "Draft model not available.")

    model = model_data["model"]
    scaler = model_data.get("scaler")
    feature_columns = model_data.get("feature_columns", [])
    metadata = model_data.get("metadata", {})

    if not feature_columns:
        raise HTTPException(503, "Draft model has no feature schema.")

    # Fail-safe feature construction: build the real champion-side features, but
    # never let a builder hiccup break inference — fall back to a neutral fill.
    try:
        df = _build_draft_feature_row(req)
        df = add_all_model_features(df, model_data)
        # Reindex to the model schema. Any column the builder didn't produce
        # (the summoner family is already defaulted above; this also covers
        # timeline columns the draft model doesn't use) is neutral-filled.
        X = df.reindex(columns=feature_columns, fill_value=0)
    except Exception:
        X = pd.DataFrame([{col: 0 for col in feature_columns}])[feature_columns]

    # Apply scaler if fitted (same guard as /predict/at).
    if scaler is not None and hasattr(scaler, "mean_"):
        X_input = scaler.transform(X)
    else:
        X_input = X.values

    prediction = model.predict(X_input)[0]
    probability = model.predict_proba(X_input)[0]

    _record_prediction("draft")
    return PredictionResponse(
        winner="Blue Team" if prediction == 1 else "Red Team",
        blue_win_probability=float(probability[1]),
        red_win_probability=float(probability[0]),
        confidence=float(max(probability)),
        model_used="draft",
        model_accuracy=metadata.get("accuracy"),
    )


@app.post("/predict/draft", response_model=PredictionResponse)
def predict_draft(req: DraftPredictionRequest):
    """Predict match outcome from the draft composition (champion picks).

    Loads the draft model via ``MODEL_FILES["draft"]`` (the same loading path
    used by the other routes) and predicts the winner from the 10 champion
    picks supplied in :class:`DraftPredictionRequest`.

    Feature construction (now WIRED):
        Blue picks map to ``team_100`` and red to ``team_200``. Champion names
        are normalized and resolved to ids via the static
        ``champion_id_map.json`` (no DB / Riot at request time). The 1-row
        DataFrame is passed to :func:`app.feature_builder.add_all_model_features`,
        which derives the REAL champion-side features — external winrate / tier /
        pickrate, lane matchups, team synergy + counter scores and the derived
        draft advantage — from the lookup tables that ship inside
        ``model_draft.pkl`` (``external_data`` + ``synergy_data``).

        The ~84 summoner-level features (per-player role winrate, mastery,
        streaks, champion recent winrate, ...) require per-player PUUIDs that a
        draft request cannot carry, so they stay at the SOURCE neutral defaults
        (exactly what the original Streamlit flow does with no PUUID). The draft
        model's own accuracy is ~0.54 by nature; the prediction now varies with
        the champions instead of being constant.

    The prediction itself is delegated to :func:`predict_draft_from_names` so
    the same core is reused by the past-game per-match prediction route.
    """
    return predict_draft_from_names(req)


def predict_timeline_at(minute: int, features: Dict[str, Any]) -> PredictionResponse:
    """Run the ``at{minute}`` model on a pre-built feature dict (CORE, reusable).

    This is the extracted timeline-prediction core shared by the
    ``POST /predict/at/{minute}`` route and the past-game timeline-progression
    prediction (T-timeline). It loads the ``at{minute}`` model, neutral-fills the
    model's feature schema with the supplied ``features`` (any column not present
    is filled with 0 — the documented contract), applies the fitted scaler if
    present, predicts, records the metric and returns a :class:`PredictionResponse`.

    Behaviour is byte-identical to the original inline route logic so the
    existing ``/predict/at`` tests stay green. ``features`` must already carry
    the minute-suffixed keys (``gold_diff_at_{minute}`` etc.) and the four
    ``first_*_team_100`` flags as 0/1 integers; the caller owns that mapping.

    Raises
    ------
    HTTPException
        * 400 — ``minute`` is not one of 5/10/15/20.
        * 404 — the ``at{minute}`` model is unavailable.
    """
    if minute not in [5, 10, 15, 20]:
        raise HTTPException(400, f"Invalid minute: {minute}. Must be 5, 10, 15, or 20.")

    model_key = f"at{minute}"
    model_data = _load_model(model_key)
    if model_data is None:
        raise HTTPException(404, f"Model for @{minute}min not available.")

    model = model_data["model"]
    scaler = model_data.get("scaler")
    feature_columns = model_data.get("feature_columns", [])
    metadata = model_data.get("metadata", {})

    # Work on a copy so the caller's dict is never mutated by the neutral-fill.
    features = dict(features)
    # Fill missing features with 0
    for col in feature_columns:
        if col not in features:
            features[col] = 0

    X = pd.DataFrame([features])[feature_columns]

    # Apply scaler if fitted
    if scaler is not None and hasattr(scaler, "mean_"):
        X_scaled = scaler.transform(X)
    else:
        X_scaled = X.values

    prediction = model.predict(X_scaled)[0]
    probability = model.predict_proba(X_scaled)[0]

    _record_prediction(model_key)
    return PredictionResponse(
        winner="Blue Team" if prediction == 1 else "Red Team",
        blue_win_probability=float(probability[1]),
        red_win_probability=float(probability[0]),
        confidence=float(max(probability)),
        model_used=model_key,
        model_accuracy=metadata.get("accuracy"),
    )


@app.post("/predict/at/{minute}", response_model=PredictionResponse)
def predict_at_minute(minute: int, req: TimelinePredictionRequest):
    """Predict match outcome at a specific game minute.

    Builds the timeline feature dict from the request body (minute-suffixed gold
    diffs + the four objective flags as 0/1) and delegates to
    :func:`predict_timeline_at` — the same core the past-game timeline route
    uses. The minute validation lives in the core so an invalid minute is still
    a 400 here.
    """
    if minute not in [5, 10, 15, 20]:
        raise HTTPException(400, f"Invalid minute: {minute}. Must be 5, 10, 15, or 20.")

    # Build features
    features = {
        f"gold_diff_at_{minute}": req.gold_diff,
        "first_blood_team_100": 1 if req.first_blood else 0,
        "first_tower_team_100": 1 if req.first_tower else 0,
        "first_dragon_team_100": 1 if req.first_dragon else 0,
        "first_herald_team_100": 1 if req.first_herald else 0,
        f"top_gold_diff_at_{minute}": req.top_gold_diff,
        f"jungle_gold_diff_at_{minute}": req.jungle_gold_diff,
        f"mid_gold_diff_at_{minute}": req.mid_gold_diff,
        f"adc_gold_diff_at_{minute}": req.adc_gold_diff,
        f"support_gold_diff_at_{minute}": req.support_gold_diff,
    }

    return predict_timeline_at(minute, features)


@app.get("/stats/overview")
def stats_overview():
    """Get database overview statistics."""
    try:
        match_count = fetchone("SELECT COUNT(*) FROM matches")[0]
        timeline_count = fetchone("SELECT COUNT(DISTINCT match_id) FROM match_timeline")[0]

        side_row = fetchone("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN team_100_win = true THEN 1 ELSE 0 END) as blue_wins
            FROM matches
        """)
        total = side_row[0] or 1
        blue_wins = side_row[1] or 0

        avg_dur = fetchone("SELECT AVG(game_duration) FROM matches WHERE game_duration > 0")[0]

        return {
            "match_count": match_count,
            "timeline_count": timeline_count,
            "blue_winrate": round(blue_wins / total, 4),
            "red_winrate": round((total - blue_wins) / total, 4),
            "avg_game_duration_min": round((avg_dur or 0) / 60, 1),
        }
    except Exception as e:
        raise HTTPException(503, f"Database error: {e}")


# ──────────────────────────────────────────
# Riot summoner search (account-v1 + summoner-v4)
#
# Additive surface for the player-real-games feature. The Riot key stays
# SERVER-SIDE (read via os.getenv inside RiotClient). Provided through a FastAPI
# dependency so tests can override it with a client wired to httpx.MockTransport
# (no live key, no network). With no key the client raises RiotKeyMissingError
# and this route returns a clear 503 — a real state, not a mock.
# ──────────────────────────────────────────

def get_riot_client() -> RiotClient:
    """Dependency returning a Riot client (overridable in tests).

    Reads ``RIOT_API_KEY`` lazily on each call, so a key set after startup is
    still honoured. Tests override this via ``app.dependency_overrides`` to
    inject an ``httpx.MockTransport``-backed client.

    The app client opts into a small retry budget (``RIOT_MAX_RETRIES``, default
    2) so a transient Riot blip (network/timeout, 5xx, or a short burst 429)
    self-heals instead of surfacing a 502. Tests construct their own client
    (retries default 0), so they stay fail-fast.
    """
    return RiotClient(retries=int(os.getenv("RIOT_MAX_RETRIES", "2")))


@app.get("/riot/summoner", response_model=SummonerResult)
async def riot_summoner(
    gameName: str,
    tagLine: str,
    region: Optional[str] = None,
    riot: RiotClient = Depends(get_riot_client),
):
    """Resolve a Riot ID (``gameName#tagLine``) to a summoner profile.

    Calls account-v1 (regional routing) to get the ``puuid``, then summoner-v4
    (platform routing) for level + profile icon. ``region`` is the platform
    routing value (e.g. ``euw1``); it defaults to ``RIOT_PLATFORM``.

    Riot client errors are mapped to clean HTTP responses (404 not found, 429
    rate limited, 503 no key, 502 upstream) so the UI can show a real state.
    """
    platform = (region or DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM
    game_name = gameName.strip()
    tag_line = tagLine.strip()
    if not game_name or not tag_line:
        raise HTTPException(400, "Both gameName and tagLine are required.")

    try:
        account = await riot.get_account_by_riot_id(game_name, tag_line, platform)
        puuid = account.get("puuid")
        if not puuid:
            raise HTTPException(502, "Riot account response missing puuid.")
        summoner = await riot.get_summoner_by_puuid(puuid, platform)
    except RiotError as exc:
        raise HTTPException(exc.status, str(exc))

    return SummonerResult(
        puuid=puuid,
        game_name=account.get("gameName", game_name),
        tag_line=account.get("tagLine", tag_line),
        platform=platform,
        summoner_level=summoner.get("summonerLevel"),
        profile_icon_id=summoner.get("profileIconId"),
    )


# ──────────────────────────────────────────
# Local-DB fuzzy player-name autocomplete (GET /riot/suggest)
#
# Typo-tolerant name suggestions drawn from the LOCAL Postgres
# `player_name_suggestions` materialized view (distinct real
# (riot_id_name, riot_id_tagline) pairs from player_stats, trigram-indexed —
# see database/migrations/003_player_suggestions.sql). This is NOT a Riot call
# and needs NO Riot key: it just helps the user type a real name. Selecting a
# suggestion still runs the real /riot/summoner lookup.
#
# Contract:
#   * q shorter than 2 (trimmed) chars  -> {"suggestions": []} (no DB hit).
#   * Any DB error (e.g. matview not yet created) -> {"suggestions": []}, so a
#     missing migration degrades the autocomplete gracefully instead of 500-ing
#     the page. limit is clamped to 1..25.
# ──────────────────────────────────────────

# Minimum trimmed query length before we hit the DB. Below this the trigram
# match is too noisy to be useful, so we return an empty list cheaply.
_SUGGEST_MIN_CHARS = 2


@app.get("/riot/suggest", response_model=PlayerSuggestionsResponse)
def riot_suggest(q: str = "", limit: int = 8):
    """Suggest real player names (fuzzy) from the local DB for ``q``.

    Query params:
        * ``q``     — the partial name typed by the user. Trimmed; if it is
          shorter than 2 chars an empty list is returned without touching the DB.
        * ``limit`` — max suggestions to return (clamped to 1..25, default 8).

    Returns :class:`PlayerSuggestionsResponse`. Matching is case-insensitive and
    typo-tolerant (pg_trgm), ranked exact-first, then by similarity, then by the
    per-name game count. DB errors degrade to an empty list (never a 500/503) so
    autocomplete can never break the search screen.
    """
    query = (q or "").strip()
    if len(query) < _SUGGEST_MIN_CHARS:
        return PlayerSuggestionsResponse(suggestions=[])

    want = max(1, min(25, int(limit)))

    try:
        rows = _fetch_suggestions(query, want)
    except Exception:
        # Matview missing / DB down / bad row: degrade to no suggestions rather
        # than erroring the page. The real /riot/summoner search still works.
        return PlayerSuggestionsResponse(suggestions=[])

    suggestions = []
    for row in rows or []:
        name = row[0]
        if name is None or str(name).strip() == "":
            continue
        tag = row[1] if len(row) > 1 else None
        games = row[2] if len(row) > 2 and row[2] is not None else 0
        suggestions.append(
            PlayerSuggestion(
                game_name=str(name).strip(),
                tag_line=(str(tag).strip() if tag not in (None, "") else None),
                games=int(games),
            )
        )

    return PlayerSuggestionsResponse(suggestions=suggestions)


# ──────────────────────────────────────────
# Riot match history (match-v5)
#
# Additive, server-side surface for Slice 2. Resolves a player's recent
# Summoner's Rift 5v5 matches into compact per-player summaries. ``RiotClient``
# is supplied via the same ``get_riot_client`` dependency as /riot/summoner so
# tests override it with an httpx.MockTransport (no live key, no network).
#
# Queue-filter contract (documented):
#   * If the caller passes ``queue=<id>`` we ask Riot to filter at the source
#     (match-v5 ``queue`` param) and trust that queue.
#   * Otherwise we over-fetch a pool of recent ids, fetch each detail, and keep
#     only SR 5v5 queues (400/420/430/440) — because match-v5's ``/ids``
#     endpoint can't filter to "any of several queues" in one call. This keeps
#     the history aligned with the queues the draft model is trained on.
# ──────────────────────────────────────────

# How many recent ids to over-fetch when no explicit queue filter is given, so
# the SR-5v5 filter can still return a useful page. Bounded so we never fan out
# an unreasonable number of detail requests on a single history view.
_MATCH_POOL_MAX = 40
# Bounded concurrency for the per-match detail fan-out: faster than serial (one
# blocking request per match) while staying well under Riot's per-second rate
# limit. Overridable via env.
_MATCH_DETAIL_CONCURRENCY = max(1, int(os.getenv("RIOT_MATCH_CONCURRENCY", "4")))


@app.get("/riot/matches", response_model=MatchHistoryResponse)
async def riot_matches(
    puuid: str,
    region: Optional[str] = None,
    count: int = 20,
    queue: Optional[int] = None,
    riot: RiotClient = Depends(get_riot_client),
):
    """List a player's recent Summoner's Rift 5v5 matches (match-v5).

    Fetches recent match ids for ``puuid`` (regional routing), then each match's
    detail, and returns compact per-player summaries (champion, win, queue,
    duration, date) newest-first.

    Query params:
        * ``region`` — platform routing value (e.g. ``euw1``); defaults to
          ``RIOT_PLATFORM``.
        * ``count``  — desired number of summaries (1..20).
        * ``queue``  — optional Riot queueId. When given, Riot filters at the
          source and that queue is trusted; when omitted, recent matches are
          fetched and filtered to SR 5v5 (400/420/430/440) after detail fetch.

    Riot client errors map to clean HTTP responses (404 not found, 429 rate
    limited, 503 no key, 502 upstream) so the UI can show a real state.
    """
    platform = (region or DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM
    puuid = (puuid or "").strip()
    if not puuid:
        raise HTTPException(400, "puuid is required.")

    want = max(1, min(20, int(count)))
    # When the caller pins a queue, Riot filters at the source so we only need
    # `want` ids. Otherwise over-fetch a pool and apply the SR-5v5 filter here.
    explicit_queue = queue is not None
    fetch_count = want if explicit_queue else min(_MATCH_POOL_MAX, max(want * 2, want))

    try:
        match_ids = await riot.get_match_ids_by_puuid(
            puuid, platform=platform, count=fetch_count, queue=queue
        )
        # Fetch each match's detail with bounded concurrency (preserves order;
        # the first upstream error propagates and maps to a clean HTTP status).
        sem = asyncio.Semaphore(_MATCH_DETAIL_CONCURRENCY)

        async def _detail(mid: str) -> Dict[str, Any]:
            async with sem:
                return await riot.get_match_detail(mid, platform=platform)

        details: List[Dict[str, Any]] = list(
            await asyncio.gather(*(_detail(mid) for mid in match_ids))
        )
    except RiotError as exc:
        raise HTTPException(exc.status, str(exc))

    # If a queue was pinned, Riot already filtered — trust it and skip the
    # SR-5v5 narrowing so e.g. queue=450 (ARAM) still works for power users.
    summaries = summarize_matches_for_player(
        details, puuid, sr_5v5_only=not explicit_queue
    )[:want]

    return MatchHistoryResponse(
        puuid=puuid,
        platform=platform,
        count=len(summaries),
        matches=summaries,
    )


# ──────────────────────────────────────────
# Riot per-game draft prediction (match-v5 + the draft model) — Slice 3 CORE.
#
# Fetches one finished match's full detail, reconstructs its 10-pick draft,
# runs the SAME draft model as POST /predict/draft, and returns the PREDICTED
# outcome alongside the ACTUAL result so the UI can show "model was right/wrong".
# The Riot key stays SERVER-SIDE (via get_riot_client); tests override the
# client with an httpx.MockTransport (no live key, no network).
#
# Error mapping:
#   * Riot client errors keep their carried status (404 / 429 / 503 / 502).
#   * A non-SR / non-5v5 / unknown-champion match raises
#     DraftReconstructionError -> 422 with a clear detail (the draft cannot be
#     reconstructed for this game), rather than a misleading prediction.
# ──────────────────────────────────────────


@app.get("/riot/match/{matchId}/prediction", response_model=MatchPredictionResponse)
async def riot_match_prediction(
    matchId: str,
    puuid: str,
    region: Optional[str] = None,
    riot: RiotClient = Depends(get_riot_client),
):
    """Predict a finished match's outcome and compare it to what really happened.

    Fetches the full match-v5 detail for ``matchId`` (regional routing derived
    from ``region``), reconstructs the 10-champion draft, runs the draft model,
    and returns the predicted winner + blue/red probabilities + confidence
    alongside the ACTUAL ``winner_side`` and whether the target ``puuid``'s team
    won. ``fallback_used`` flags approximate lane assignment.

    Query params:
        * ``puuid``  — the player to scope ``actual.player_won`` to (required).
        * ``region`` — platform routing value (e.g. ``euw1``); defaults to
          ``RIOT_PLATFORM``.

    Errors map to clean HTTP responses: Riot 404->404, 429->429, no key->503,
    other upstream->502; a non-Summoner's-Rift / unmappable match (cannot
    reconstruct a 5v5 draft) -> 422.
    """
    platform = (region or DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM
    match_id = (matchId or "").strip()
    puuid = (puuid or "").strip()
    if not match_id:
        raise HTTPException(400, "matchId is required.")
    if not puuid:
        raise HTTPException(400, "puuid is required.")

    try:
        detail = await riot.get_match_detail(match_id, platform=platform)
    except RiotError as exc:
        raise HTTPException(exc.status, str(exc))

    try:
        result = build_match_prediction(detail, puuid)
    except DraftReconstructionError as exc:
        # Non-SR game, a side without exactly 5 players, or an unknown champion:
        # the draft cannot be reconstructed, so this is a clear 422 rather than
        # a misleading prediction.
        raise HTTPException(
            422,
            f"Cannot reconstruct a draft for this match: {exc}",
        )

    predicted = result["predicted"]
    actual = result["actual"]

    return MatchPredictionResponse(
        match_id=result["match_id"] or match_id,
        puuid=puuid,
        platform=platform,
        draft=result["draft"],
        predicted=MatchPrediction(
            winner=predicted.winner,
            blue_win_probability=predicted.blue_win_probability,
            red_win_probability=predicted.red_win_probability,
            confidence=predicted.confidence,
            model_used=predicted.model_used,
            model_accuracy=predicted.model_accuracy,
        ),
        actual=MatchActualResult(
            winner_side=actual["winner_side"],
            player_won=actual["player_won"],
        ),
        fallback_used=result["fallback_used"],
        warnings=result["warnings"],
    )


# ──────────────────────────────────────────
# Riot per-game TIMELINE prediction (match-v5 timeline + the at{minute} models).
#
# Fetches one finished match's detail (for the per-role mapping + the actual
# result) AND its match-v5 timeline, reconstructs the game state at minutes
# 5/10/15/20, runs the matching at{minute} win-prob model at each, and returns
# the PREDICTED progression alongside the ACTUAL result so the UI can chart how
# the favoured side shifts and mark which checkpoints called the winner right.
# The Riot key stays SERVER-SIDE (via get_riot_client); tests override the
# client with an httpx.MockTransport (no live key, no network).
#
# Error mapping (same shape as the draft route):
#   * Riot client errors keep their carried status (404 / 429 / 503 / 502).
#   * A game with no usable timeline frame at minute 5+ (too short / non-SR /
#     missing timeline) raises TimelineReconstructionError -> 422 with a clear
#     detail, rather than a misleading empty progression.
# ──────────────────────────────────────────


@app.get(
    "/riot/match/{matchId}/timeline-prediction",
    response_model=MatchTimelinePredictionResponse,
)
async def riot_match_timeline_prediction(
    matchId: str,
    puuid: str,
    region: Optional[str] = None,
    riot: RiotClient = Depends(get_riot_client),
):
    """Chart a finished match's win-probability progression (timeline models).

    Fetches the match-v5 detail (for the per-role mapping + the actual result)
    and the match-v5 timeline (regional routing derived from ``region``),
    reconstructs the game state at minutes 5/10/15/20, runs each matching
    ``at{minute}`` model, and returns one checkpoint per available minute
    (``minute`` + ``gold_diff`` + the model's ``predicted`` block) plus the
    ACTUAL ``winner_side`` and whether the target ``puuid``'s team won.

    Query params:
        * ``puuid``  — the player to scope ``actual.player_won`` to (required).
        * ``region`` — platform routing value (e.g. ``euw1``); defaults to
          ``RIOT_PLATFORM``.

    Errors map to clean HTTP responses: Riot 404->404, 429->429, no key->503,
    other upstream->502; a game with no usable timeline frame at minute 5+
    (too short / no timeline) -> 422.
    """
    platform = (region or DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM
    match_id = (matchId or "").strip()
    puuid = (puuid or "").strip()
    if not match_id:
        raise HTTPException(400, "matchId is required.")
    if not puuid:
        raise HTTPException(400, "puuid is required.")

    try:
        detail = await riot.get_match_detail(match_id, platform=platform)
        timeline = await riot.get_match_timeline(match_id, platform=platform)
    except RiotError as exc:
        raise HTTPException(exc.status, str(exc))

    try:
        result = build_timeline_prediction(detail, timeline, puuid)
    except TimelineReconstructionError as exc:
        # No usable timeline frame at minute 5+ (too short / no timeline): a
        # clear 422 rather than an empty/misleading progression.
        raise HTTPException(
            422,
            f"Cannot chart a timeline progression for this match: {exc}",
        )

    actual = result["actual"]
    checkpoints = [
        TimelineCheckpoint(
            minute=cp["minute"],
            gold_diff=cp["gold_diff"],
            predicted=MatchPrediction(
                winner=cp["predicted"].winner,
                blue_win_probability=cp["predicted"].blue_win_probability,
                red_win_probability=cp["predicted"].red_win_probability,
                confidence=cp["predicted"].confidence,
                model_used=cp["predicted"].model_used,
                model_accuracy=cp["predicted"].model_accuracy,
            ),
        )
        for cp in result["checkpoints"]
    ]

    return MatchTimelinePredictionResponse(
        match_id=result["match_id"] or match_id,
        puuid=puuid,
        platform=platform,
        game_duration=result["game_duration"],
        actual=MatchActualResult(
            winner_side=actual["winner_side"],
            player_won=actual["player_won"],
        ),
        checkpoints=checkpoints,
    )


# ──────────────────────────────────────────
# Riot LIVE-game spectator prediction (spectator-v5 + the draft model) — Slice 4.
#
# Fetches the player's CURRENT in-progress game (spectator-v5, PLATFORM routing),
# reconstructs its 10-pick draft from participant order (spectator data carries
# NO lane info, so fallback_used is always true), runs the SAME draft model as
# POST /predict/draft, and returns the PREDICTED outcome. There is no actual
# result — the game is still being played. The Riot key stays SERVER-SIDE (via
# get_riot_client); tests override the client with an httpx.MockTransport.
#
# "Not in a game" is the normal case: spectator-v5 returns 404, which
# RiotClient.get_active_game_by_puuid maps to None, and this route turns into a
# clean 200 {in_game: false} — never a hard error.
#
# Error mapping (real failures only): Riot 429->429, no key->503, other
# upstream->502; a non-SR / non-5v5 / unknown-champion game raises
# DraftReconstructionError -> 422.
# ──────────────────────────────────────────


@app.get("/riot/live/{puuid}/prediction", response_model=LivePredictionResponse)
async def riot_live_prediction(
    puuid: str,
    region: Optional[str] = None,
    riot: RiotClient = Depends(get_riot_client),
):
    """Predict the player's CURRENT live game's outcome (spectator-v5).

    Fetches the player's active game (platform routing derived from ``region``).
    If they are not in a game, returns ``{in_game: false}`` (HTTP 200). Otherwise
    reconstructs the 10-champion draft from spectator participants — which carry
    no lane data, so ``fallback_used`` is always ``True`` (lanes approximate) —
    runs the draft model, and returns the predicted winner + blue/red
    probabilities + confidence. There is no actual result (the game is live).

    Query params:
        * ``region`` — platform routing value (e.g. ``euw1``); defaults to
          ``RIOT_PLATFORM``.

    Errors map to clean HTTP responses: Riot 429->429, no key->503, other
    upstream->502; a non-Summoner's-Rift / unmappable game (cannot reconstruct a
    5v5 draft, e.g. ARAM) -> 422. A player simply not in a game is NOT an error.
    """
    platform = (region or DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM
    puuid = (puuid or "").strip()
    if not puuid:
        raise HTTPException(400, "puuid is required.")

    try:
        current_game = await riot.get_active_game_by_puuid(puuid, platform=platform)
    except RiotError as exc:
        raise HTTPException(exc.status, str(exc))

    # Not in a live game (spectator-v5 404 -> None): a normal, non-error state.
    if current_game is None:
        return LivePredictionResponse(in_game=False, puuid=puuid, platform=platform)

    try:
        result = build_live_prediction(current_game, puuid)
    except DraftReconstructionError as exc:
        # Non-SR game, a side without exactly 5 players, or an unknown champion:
        # the draft cannot be reconstructed -> a clear 422 rather than a
        # misleading prediction.
        raise HTTPException(
            422,
            f"Cannot reconstruct a draft for this live game: {exc}",
        )

    predicted = result["predicted"]

    return LivePredictionResponse(
        in_game=True,
        puuid=puuid,
        platform=platform,
        game_id=result["game_id"],
        queue_id=result["queue_id"],
        draft=result["draft"],
        predicted=MatchPrediction(
            winner=predicted.winner,
            blue_win_probability=predicted.blue_win_probability,
            red_win_probability=predicted.red_win_probability,
            confidence=predicted.confidence,
            model_used=predicted.model_used,
            model_accuracy=predicted.model_accuracy,
        ),
        fallback_used=result["fallback_used"],
        warnings=result["warnings"],
    )
