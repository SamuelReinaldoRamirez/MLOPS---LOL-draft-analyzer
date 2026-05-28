/**
 * Thin client for the LoL Draft Predictor API.
 *
 * The base URL comes from `NEXT_PUBLIC_API_BASE_URL` (exposed to the browser
 * because the prediction request is fired client-side from the draft board),
 * falling back to the local docker-compose default.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Role = "top" | "jungle" | "mid" | "adc" | "support";

export const ROLES: { key: Role; label: string }[] = [
  { key: "top", label: "Top" },
  { key: "jungle", label: "Jungle" },
  { key: "mid", label: "Mid" },
  { key: "adc", label: "ADC" },
  { key: "support", label: "Support" },
];

/** Request body matching the API's `DraftPredictionRequest`. */
export interface DraftPredictionRequest {
  blue_top: string;
  blue_jungle: string;
  blue_mid: string;
  blue_adc: string;
  blue_support: string;
  red_top: string;
  red_jungle: string;
  red_mid: string;
  red_adc: string;
  red_support: string;
}

/** Response body matching the API's `PredictionResponse`. */
export interface PredictionResponse {
  winner: "Blue Team" | "Red Team";
  blue_win_probability: number;
  red_win_probability: number;
  confidence: number;
  model_used: string;
  model_accuracy: number | null;
}

/**
 * POST the 10 champion picks to `/predict/draft`.
 *
 * Throws an `Error` with a friendly message on network failure or non-2xx
 * responses so the UI can render a clear, non-technical error state.
 */
export async function predictDraft(
  body: DraftPredictionRequest,
): Promise<PredictionResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/predict/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      `Could not reach the prediction service at ${API_BASE_URL}. ` +
        "Make sure the API is running (docker compose up -d api).",
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail =
        typeof data?.detail === "string" ? `: ${data.detail}` : "";
    } catch {
      // body wasn't JSON — ignore and use the generic message below.
    }
    throw new Error(
      `The prediction service returned an error (${res.status})${detail}.`,
    );
  }

  return (await res.json()) as PredictionResponse;
}

// ──────────────────────────────────────────
// Riot summoner search (calls the real backend route GET /riot/summoner).
//
// The Riot key lives SERVER-SIDE in the API; the browser only ever talks to
// our backend. This call hits the REAL route — it is never mocked. With no key
// configured the backend returns 503 and `searchSummoner` surfaces a typed
// `RiotErrorKind` of "no-key" so the UI can show a genuine state.
// ──────────────────────────────────────────

/** Response body matching the API's `SummonerResult`. */
export interface SummonerResult {
  puuid: string;
  game_name: string;
  tag_line: string;
  platform: string;
  summoner_level: number | null;
  profile_icon_id: number | null;
}

/** Distinct, renderable failure states for the search UI. */
export type RiotErrorKind =
  | "not-found"
  | "rate-limited"
  | "no-key"
  | "upstream"
  | "network"
  // Game whose draft cannot be reconstructed (non-SR / not 5v5) — only the
  // per-game prediction route (GET /riot/match/{id}/prediction) returns this.
  | "unsupported";

/** Typed error so the search screen can render a specific state per kind. */
export class SummonerSearchError extends Error {
  kind: RiotErrorKind;
  status?: number;

  constructor(kind: RiotErrorKind, message: string, status?: number) {
    super(message);
    this.name = "SummonerSearchError";
    this.kind = kind;
    this.status = status;
  }
}

function kindForStatus(status: number): RiotErrorKind {
  if (status === 404) return "not-found";
  if (status === 422) return "unsupported";
  if (status === 429) return "rate-limited";
  if (status === 503) return "no-key";
  return "upstream";
}

/**
 * Resolve a Riot ID (gameName#tagLine) to a summoner via `GET /riot/summoner`.
 *
 * @param gameName Riot ID name part (before the #).
 * @param tagLine  Riot ID tag part (after the #).
 * @param region   Optional platform routing value (e.g. "euw1"). Omitted ->
 *                 the backend default (RIOT_PLATFORM).
 *
 * Throws a {@link SummonerSearchError} with a typed `kind` on network failure
 * or a non-2xx response so the UI can render a precise, non-technical state.
 */
export async function searchSummoner(
  gameName: string,
  tagLine: string,
  region?: string,
): Promise<SummonerResult> {
  const params = new URLSearchParams({ gameName, tagLine });
  if (region && region.trim()) params.set("region", region.trim());

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/riot/summoner?${params.toString()}`);
  } catch {
    throw new SummonerSearchError(
      "network",
      `Could not reach the API at ${API_BASE_URL}. ` +
        "Make sure it is running (docker compose up -d api).",
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = typeof data?.detail === "string" ? data.detail : "";
    } catch {
      // body wasn't JSON — fall back to a generic message per kind.
    }
    throw new SummonerSearchError(
      kindForStatus(res.status),
      detail || `The API returned an error (${res.status}).`,
      res.status,
    );
  }

  return (await res.json()) as SummonerResult;
}

// ──────────────────────────────────────────
// Local-DB player-name autocomplete (calls GET /riot/suggest).
//
// These are typo-tolerant suggestions drawn from the LOCAL Postgres DB
// (distinct real player names from player_stats, fuzzy-matched via pg_trgm) —
// NOT a Riot call and needing no Riot key. They only help the user TYPE a real
// name; selecting one still runs the real searchSummoner() lookup. Suggestions
// must NEVER break the page, so this always resolves to an array — any network
// or parse error yields [].
// ──────────────────────────────────────────

/** One fuzzy name suggestion matching the API's `PlayerSuggestion`. */
export interface PlayerSuggestion {
  game_name: string;
  tag_line: string | null;
  games: number;
}

/**
 * Fetch fuzzy player-name suggestions from the local DB via `GET /riot/suggest`.
 *
 * @param q     The partial name the user has typed (backend ignores < 2 chars).
 * @param limit Optional max suggestions (backend clamps to 1..25, default 8).
 *
 * NEVER throws: returns `[]` on a short query, network failure, non-2xx
 * response or a malformed body, so the autocomplete dropdown can never break
 * the search screen.
 */
export async function suggestPlayers(
  q: string,
  limit?: number,
): Promise<PlayerSuggestion[]> {
  const query = (q ?? "").trim();
  if (query.length < 2) return [];

  const params = new URLSearchParams({ q: query });
  if (limit && limit > 0) params.set("limit", String(limit));

  try {
    const res = await fetch(`${API_BASE_URL}/riot/suggest?${params.toString()}`);
    if (!res.ok) return [];
    const data = (await res.json()) as { suggestions?: PlayerSuggestion[] };
    return Array.isArray(data?.suggestions) ? data.suggestions : [];
  } catch {
    // Suggestions are best-effort: swallow everything so the page keeps working.
    return [];
  }
}

// ──────────────────────────────────────────
// Riot match history (calls the real backend route GET /riot/matches).
//
// Same contract as the summoner search: the Riot key lives SERVER-SIDE, the
// browser only talks to our backend, and failures surface as a typed
// `RiotErrorKind` so the history screen can render a precise, real state
// (not-found / rate-limited / no-key / upstream / network).
// ──────────────────────────────────────────

/** One match row matching the API's `MatchSummary`. */
export interface MatchSummary {
  match_id: string;
  champion_name: string | null;
  win: boolean | null;
  queue_id: number | null;
  game_duration: number | null;
  /** Match start as a Unix epoch in MILLISECONDS, or null. */
  game_creation: number | null;
  game_mode: string | null;
}

/** Response body matching the API's `MatchHistoryResponse`. */
export interface MatchHistoryResponse {
  puuid: string;
  platform: string;
  count: number;
  matches: MatchSummary[];
}

/**
 * Fetch a player's recent Summoner's Rift 5v5 matches via `GET /riot/matches`.
 *
 * @param puuid  The player's globally-unique id (from {@link searchSummoner}).
 * @param region Optional platform routing value (e.g. "euw1"). Omitted -> the
 *               backend default (RIOT_PLATFORM).
 * @param count  Optional desired number of matches (backend clamps to 1..20).
 *
 * Throws a {@link SummonerSearchError} with a typed `kind` on network failure
 * or a non-2xx response so the UI can render a precise, non-technical state.
 */
export async function getMatchHistory(
  puuid: string,
  region?: string,
  count?: number,
): Promise<MatchHistoryResponse> {
  const params = new URLSearchParams({ puuid });
  if (region && region.trim()) params.set("region", region.trim());
  if (count && count > 0) params.set("count", String(count));

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/riot/matches?${params.toString()}`);
  } catch {
    throw new SummonerSearchError(
      "network",
      `Could not reach the API at ${API_BASE_URL}. ` +
        "Make sure it is running (docker compose up -d api).",
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = typeof data?.detail === "string" ? data.detail : "";
    } catch {
      // body wasn't JSON — fall back to a generic message per kind.
    }
    throw new SummonerSearchError(
      kindForStatus(res.status),
      detail || `The API returned an error (${res.status}).`,
      res.status,
    );
  }

  return (await res.json()) as MatchHistoryResponse;
}

// ──────────────────────────────────────────
// Riot per-game prediction (calls GET /riot/match/{matchId}/prediction).
//
// Same server-side contract: the Riot key stays on the backend and failures
// surface as a typed `RiotErrorKind`. This route adds one more real state —
// `unsupported` (HTTP 422) — for a game whose draft cannot be reconstructed
// (non-Summoner's-Rift / not a 5v5), so the per-game screen can explain why no
// prediction is shown instead of erroring out.
// ──────────────────────────────────────────

/** The model's prediction for one finished match (mirrors PredictionResponse). */
export interface MatchPredictionPredicted {
  winner: "Blue Team" | "Red Team";
  blue_win_probability: number;
  red_win_probability: number;
  confidence: number;
  model_used: string;
  model_accuracy: number | null;
}

/** What actually happened in the match (read from match-v5). */
export interface MatchPredictionActual {
  winner_side: "Blue Team" | "Red Team" | null;
  player_won: boolean | null;
}

/** Response body matching the API's `MatchPredictionResponse`. */
export interface MatchPrediction {
  match_id: string;
  puuid: string;
  platform: string;
  /** The 10 reconstructed picks: blue_top..red_support -> champion name. */
  draft: Record<string, string>;
  predicted: MatchPredictionPredicted;
  actual: MatchPredictionActual;
  /** True when one or more lanes were assigned approximately (Riot lane gaps). */
  fallback_used: boolean;
  warnings: string[];
}

/**
 * Fetch the draft model's prediction for one finished match plus the ACTUAL
 * result, via `GET /riot/match/{matchId}/prediction`.
 *
 * @param matchId The match-v5 id (e.g. "EUW1_123").
 * @param puuid   The player to scope `actual.player_won` to.
 * @param region  Optional platform routing value (e.g. "euw1"). Omitted -> the
 *                backend default (RIOT_PLATFORM).
 *
 * Throws a {@link SummonerSearchError} with a typed `kind` on network failure
 * or a non-2xx response. HTTP 422 maps to the `unsupported` kind so the UI can
 * explain that this game's draft cannot be analyzed (non-SR / not 5v5).
 */
export async function getMatchPrediction(
  matchId: string,
  puuid: string,
  region?: string,
): Promise<MatchPrediction> {
  const params = new URLSearchParams({ puuid });
  if (region && region.trim()) params.set("region", region.trim());

  let res: Response;
  try {
    res = await fetch(
      `${API_BASE_URL}/riot/match/${encodeURIComponent(matchId)}/prediction?${params.toString()}`,
    );
  } catch {
    throw new SummonerSearchError(
      "network",
      `Could not reach the API at ${API_BASE_URL}. ` +
        "Make sure it is running (docker compose up -d api).",
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = typeof data?.detail === "string" ? data.detail : "";
    } catch {
      // body wasn't JSON — fall back to a generic message per kind.
    }
    throw new SummonerSearchError(
      kindForStatus(res.status),
      detail || `The API returned an error (${res.status}).`,
      res.status,
    );
  }

  return (await res.json()) as MatchPrediction;
}

// ──────────────────────────────────────────
// Riot per-game TIMELINE prediction (GET /riot/match/{matchId}/timeline-prediction).
//
// Same server-side contract as the draft per-game route: the Riot key stays on
// the backend and failures surface as a typed `RiotErrorKind` (incl. 503
// no-key, 429 rate-limited, 422 unsupported — here "no usable timeline"). This
// charts how the at5/at10/at15/at20 win-prob models read the game minute by
// minute, alongside the ACTUAL result. Short games carry fewer checkpoints.
// ──────────────────────────────────────────

/** One minute checkpoint matching the API's `TimelineCheckpoint`. */
export interface TimelineCheckpoint {
  minute: number;
  /** Blue − red total gold at this minute (positive = blue ahead). */
  gold_diff: number;
  predicted: MatchPredictionPredicted;
}

/** Response body matching the API's `MatchTimelinePredictionResponse`. */
export interface MatchTimelinePrediction {
  match_id: string;
  puuid: string;
  platform: string;
  game_duration: number | null;
  actual: MatchPredictionActual;
  /** Per-minute win-probability checkpoints, earliest minute first. */
  checkpoints: TimelineCheckpoint[];
}

/**
 * Fetch the per-minute win-probability progression for one finished match via
 * `GET /riot/match/{matchId}/timeline-prediction`.
 *
 * @param matchId The match-v5 id (e.g. "EUW1_123").
 * @param puuid   The player to scope `actual.player_won` to.
 * @param region  Optional platform routing value (e.g. "euw1"). Omitted -> the
 *                backend default (RIOT_PLATFORM).
 *
 * Throws a {@link SummonerSearchError} with a typed `kind` on network failure
 * or a non-2xx response. HTTP 422 maps to `unsupported` (no usable timeline —
 * too short / non-SR), so the UI can explain why no progression is shown.
 */
export async function getMatchTimelinePrediction(
  matchId: string,
  puuid: string,
  region?: string,
): Promise<MatchTimelinePrediction> {
  const params = new URLSearchParams({ puuid });
  if (region && region.trim()) params.set("region", region.trim());

  let res: Response;
  try {
    res = await fetch(
      `${API_BASE_URL}/riot/match/${encodeURIComponent(matchId)}/timeline-prediction?${params.toString()}`,
    );
  } catch {
    throw new SummonerSearchError(
      "network",
      `Could not reach the API at ${API_BASE_URL}. ` +
        "Make sure it is running (docker compose up -d api).",
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = typeof data?.detail === "string" ? data.detail : "";
    } catch {
      // body wasn't JSON — fall back to a generic message per kind.
    }
    throw new SummonerSearchError(
      kindForStatus(res.status),
      detail || `The API returned an error (${res.status}).`,
      res.status,
    );
  }

  return (await res.json()) as MatchTimelinePrediction;
}

// ──────────────────────────────────────────
// Riot LIVE-game spectator prediction (calls GET /riot/live/{puuid}/prediction).
//
// Same server-side contract: the Riot key stays on the backend and failures
// surface as a typed `RiotErrorKind` (incl. 503 no-key, 429 rate-limited, 422
// unsupported). Spectator data carries NO lane info, so `fallback_used` is
// always true (lanes approximate) and there is NO actual result — the game is
// in progress. "Not in a game" is NOT an error: the backend returns
// `{ in_game: false }` with HTTP 200.
// ──────────────────────────────────────────

/** Response body matching the API's `LivePredictionResponse`. */
export interface LivePrediction {
  in_game: boolean;
  puuid: string;
  platform: string;
  game_id: string | null;
  queue_id: number | null;
  /** The 10 reconstructed picks (only when in game). */
  draft: Record<string, string> | null;
  /** The model's prediction for the live game (only when in game). */
  predicted: MatchPredictionPredicted | null;
  /** Always true for spectator data (no lane info) — lanes approximate. */
  fallback_used: boolean;
  warnings: string[];
}

/**
 * Fetch the draft model's prediction for the player's CURRENT live game via
 * `GET /riot/live/{puuid}/prediction`.
 *
 * @param puuid  The player's globally-unique id (from {@link searchSummoner}).
 * @param region Optional platform routing value (e.g. "euw1"). Omitted -> the
 *               backend default (RIOT_PLATFORM).
 *
 * Returns `{ in_game: false }` (HTTP 200) when the player is not in a game —
 * NOT an error. Throws a {@link SummonerSearchError} with a typed `kind` on
 * network failure or a non-2xx response (422 -> `unsupported` for a non-SR /
 * not-5v5 live game such as ARAM; 503 -> `no-key`; 429 -> `rate-limited`).
 */
export async function getLivePrediction(
  puuid: string,
  region?: string,
): Promise<LivePrediction> {
  const params = new URLSearchParams();
  if (region && region.trim()) params.set("region", region.trim());
  const qs = params.toString();

  let res: Response;
  try {
    res = await fetch(
      `${API_BASE_URL}/riot/live/${encodeURIComponent(puuid)}/prediction${qs ? `?${qs}` : ""}`,
    );
  } catch {
    throw new SummonerSearchError(
      "network",
      `Could not reach the API at ${API_BASE_URL}. ` +
        "Make sure it is running (docker compose up -d api).",
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = typeof data?.detail === "string" ? data.detail : "";
    } catch {
      // body wasn't JSON — fall back to a generic message per kind.
    }
    throw new SummonerSearchError(
      kindForStatus(res.status),
      detail || `The API returned an error (${res.status}).`,
      res.status,
    );
  }

  return (await res.json()) as LivePrediction;
}

// ──────────────────────────────────────────
// Display helpers for match rows (pure, UI-friendly).
// ──────────────────────────────────────────

const QUEUE_LABELS: Record<number, string> = {
  400: "Normal Draft",
  420: "Ranked Solo/Duo",
  430: "Normal Blind",
  440: "Ranked Flex",
  450: "ARAM",
};

/** Human label for a Riot queueId (falls back to a generic label). */
export function queueLabel(queueId: number | null): string {
  if (queueId == null) return "Summoner's Rift";
  return QUEUE_LABELS[queueId] ?? `Queue ${queueId}`;
}

/** Format a game duration (seconds) as mm:ss. */
export function formatDuration(seconds: number | null): string {
  if (seconds == null || seconds < 0) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/**
 * Format a match start (Unix epoch in ms) as a short relative time, e.g.
 * "2h ago", "3d ago", or an absolute date for older games.
 */
export function formatRelativeDate(epochMs: number | null): string {
  if (epochMs == null || epochMs <= 0) return "";
  const diffMs = Date.now() - epochMs;
  if (diffMs < 0) return "just now";
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(epochMs).toLocaleDateString();
}
