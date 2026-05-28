"use client";

import { useEffect, useState } from "react";
import ErrorState from "@/components/ErrorState";
import {
  getMatchTimelinePrediction,
  SummonerSearchError,
  type MatchTimelinePrediction,
  type RiotErrorKind,
  type TimelineCheckpoint,
} from "@/lib/api";

function pct(value: number): string {
  return `${(Math.max(0, Math.min(1, value)) * 100).toFixed(1)}%`;
}

/** Signed gold diff, e.g. "+975" (blue ahead) / "−420" (red ahead). */
function goldLabel(diff: number): string {
  const rounded = Math.round(diff);
  if (rounded === 0) return "even";
  const sign = rounded > 0 ? "+" : "−";
  return `${sign}${Math.abs(rounded).toLocaleString()}`;
}

/** Friendly copy for a timeline failure (mirrors the page's draft messages). */
function messageForKind(kind: RiotErrorKind, fallback: string): string {
  switch (kind) {
    case "not-found":
      return "We couldn't find this game's timeline. It may be too old, or the region is off.";
    case "rate-limited":
      return "The Riot API is rate-limited right now. Please wait a moment and try again.";
    case "no-key":
      return "Riot API key not configured on the server, so the timeline models can't run.";
    case "unsupported":
      return "This game has no usable timeline (too short, or not a standard game), so the minute-by-minute models can't chart it.";
    case "upstream":
      return "Riot's servers returned a momentary error (502) loading the timeline. Try again.";
    default:
      return fallback || "Couldn't load the win-probability timeline for this game.";
  }
}

/**
 * Compact "momentum strip": one stacked blue/red column per checkpoint, blue
 * filling from the top by its win probability. A glanceable read of how the
 * model's favour swung minute to minute, with a 50% reference line.
 */
function MomentumStrip({ checkpoints }: { checkpoints: TimelineCheckpoint[] }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2/50 p-4">
      <div className="relative flex items-end gap-2 overflow-x-auto pb-1">
        {/* 50% reference line */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-4 top-[40px] z-10 border-t border-dashed border-line-strong/70"
        />
        {checkpoints.map((cp) => {
          const blue = Math.max(0, Math.min(1, cp.predicted.blue_win_probability));
          const blueFav = cp.predicted.winner === "Blue Team";
          return (
            <div key={cp.minute} className="flex min-w-[2.25rem] flex-1 flex-col items-center gap-1.5">
              <div className="relative flex h-20 w-7 flex-col overflow-hidden rounded-md ring-1 ring-line">
                <div
                  className="w-full bg-blue-fill"
                  style={{ height: `${blue * 100}%` }}
                  title={`Blue ${pct(blue)}`}
                />
                <div className="w-full flex-1 bg-red-fill" />
              </div>
              <span
                className={`text-[11px] font-semibold tabular-nums ${
                  blueFav ? "text-team_blue-glow" : "text-team_red-glow"
                }`}
              >
                {cp.minute}&apos;
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * One checkpoint row: the minute, the gold lead, a Blue/Red win-probability bar,
 * and a tag for whether this minute's model favoured the side that ACTUALLY won.
 */
function CheckpointRow({
  cp,
  actualWinner,
}: {
  cp: TimelineCheckpoint;
  actualWinner: "Blue Team" | "Red Team" | null;
}) {
  const blue = Math.max(0, Math.min(1, cp.predicted.blue_win_probability));
  const red = Math.max(0, Math.min(1, cp.predicted.red_win_probability));
  const favoured = cp.predicted.winner;
  const goldBlueAhead = cp.gold_diff > 0;

  // Did this checkpoint call the eventual winner correctly? Only meaningful
  // when the match has a recorded winner.
  const correct = actualWinner != null ? favoured === actualWinner : null;

  return (
    <li className="rounded-xl border border-line bg-surface/70 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex h-7 min-w-[3.25rem] items-center justify-center rounded-md bg-surface-3 px-2 font-display text-sm font-semibold text-ink tabular-nums">
            {cp.minute}:00
          </span>
          <span
            className={`text-xs font-medium tabular-nums ${
              cp.gold_diff === 0
                ? "text-ink-muted"
                : goldBlueAhead
                  ? "text-team_blue-glow"
                  : "text-team_red-glow"
            }`}
            title="Total team gold difference (blue − red) at this minute"
          >
            Gold {goldLabel(cp.gold_diff)}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`text-sm font-semibold ${
              favoured === "Blue Team" ? "text-team_blue-glow" : "text-team_red-glow"
            }`}
          >
            {favoured} favoured
          </span>
          {correct != null &&
            (correct ? (
              <span className="rounded-md bg-win/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-win">
                Matched
              </span>
            ) : (
              <span className="rounded-md bg-gold/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-gold">
                Missed
              </span>
            ))}
        </div>
      </div>

      {/* Win-probability bar (same look as the draft ResultPanel). */}
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-xs font-medium tabular-nums">
          <span className="text-team_blue-glow">Blue {pct(blue)}</span>
          <span className="text-team_red-glow">Red {pct(red)}</span>
        </div>
        <div className="flex h-3.5 w-full overflow-hidden rounded-full bg-surface-2 ring-1 ring-inset ring-line">
          <div
            className="h-full bg-blue-fill transition-[width] duration-500"
            style={{ width: `${blue * 100}%` }}
            aria-label={`Minute ${cp.minute}: blue win probability ${pct(blue)}`}
          />
          <div
            className="h-full flex-1 bg-red-fill"
            aria-label={`Minute ${cp.minute}: red win probability ${pct(red)}`}
          />
        </div>
      </div>
    </li>
  );
}

/** Compact summary of how the favoured side shifts across the checkpoints. */
function ShiftSummary({ data }: { data: MatchTimelinePrediction }) {
  const correctCount = data.actual.winner_side
    ? data.checkpoints.filter(
        (cp) => cp.predicted.winner === data.actual.winner_side,
      ).length
    : 0;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-ink-muted">Favoured over time:</span>
      <span className="flex items-center gap-1">
        {data.checkpoints.map((cp, i) => (
          <span
            key={cp.minute}
            title={`${cp.minute}': ${cp.predicted.winner}`}
            className={`h-2.5 w-2.5 rounded-full ${
              cp.predicted.winner === "Blue Team" ? "bg-team_blue" : "bg-team_red"
            } ${i > 0 ? "" : ""}`}
          />
        ))}
      </span>
      {data.actual.winner_side && (
        <span className="text-ink-muted">
          ·{" "}
          <span className="font-semibold text-ink tabular-nums">
            {correctCount}/{data.checkpoints.length}
          </span>{" "}
          matched the winner ({data.actual.winner_side}).
        </span>
      )}
    </div>
  );
}

/**
 * Win-probability TIMELINE for one finished game.
 *
 * Fetches `GET /riot/match/{matchId}/timeline-prediction` (the at5/at10/at15/
 * at20 models run on the game state reconstructed from the match-v5 timeline)
 * and renders a momentum strip plus one row per checkpoint: the minute, the
 * gold lead, a Blue/Red win-probability bar, and whether that minute's favoured
 * side matched the eventual ACTUAL winner. Self-contained loading / error /
 * "timeline unavailable" states so a timeline failure never blocks the draft
 * section above it.
 */
export default function TimelinePrediction({
  matchId,
  puuid,
  region,
}: {
  matchId: string;
  puuid: string;
  region?: string;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<MatchTimelinePrediction | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!matchId || !puuid) {
      setData(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    getMatchTimelinePrediction(matchId, puuid, region || undefined)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof SummonerSearchError) {
          setError(messageForKind(err.kind, err.message));
        } else {
          setError("Couldn't load the win-probability timeline for this game.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [matchId, puuid, region, reloadKey]);

  if (!matchId || !puuid) return null;

  return (
    <section className="panel p-6 sm:p-7">
      <span className="eyebrow text-gold">Live Model</span>
      <h2 className="mt-1 font-display text-xl font-bold text-ink">
        Win probability over time
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        How the in-game models (at 5/10/15/20 min) read this game as it unfolded,
        from gold and early objectives — checked against who actually won.
      </p>

      {loading && (
        <div className="mt-5 space-y-3" aria-hidden="true">
          <div className="skeleton h-28 rounded-xl" />
          <div className="skeleton h-16 rounded-xl" />
          <div className="skeleton h-16 rounded-xl" />
        </div>
      )}

      {!loading && error && (
        <div className="mt-5">
          <ErrorState
            message={error}
            tone="muted"
            role="status"
            onRetry={() => setReloadKey((k) => k + 1)}
          />
        </div>
      )}

      {!loading && !error && data && data.checkpoints.length === 0 && (
        <div className="mt-5 rounded-xl border border-line bg-surface-2/60 px-4 py-3 text-sm text-ink-soft">
          No timeline checkpoints are available for this game.
        </div>
      )}

      {!loading && !error && data && data.checkpoints.length > 0 && (
        <div className="mt-5 space-y-4">
          <MomentumStrip checkpoints={data.checkpoints} />
          <ShiftSummary data={data} />
          <ul className="space-y-2.5">
            {data.checkpoints.map((cp) => (
              <CheckpointRow
                key={cp.minute}
                cp={cp}
                actualWinner={data.actual.winner_side}
              />
            ))}
          </ul>
          <p className="rounded-lg border-l-2 border-gold/60 bg-gold/[0.06] px-3.5 py-2.5 text-xs leading-relaxed text-ink-soft">
            These minute-by-minute models use gold and early objectives only — a
            real game still turns on teamfights and decisions, so read the
            progression as a guide, not a certainty.
          </p>
        </div>
      )}
    </section>
  );
}
