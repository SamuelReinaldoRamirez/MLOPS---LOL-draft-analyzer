"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import ErrorState from "@/components/ErrorState";
import ResultPanel from "@/components/ResultPanel";
import TeamDraftCard, { sidePicks } from "@/components/TeamDraftCard";
import TimelinePrediction from "@/components/TimelinePrediction";
import {
  getMatchPrediction,
  SummonerSearchError,
  type MatchPrediction,
  type RiotErrorKind,
} from "@/lib/api";

/** Friendly, non-technical copy for each typed failure state. */
function messageForKind(kind: RiotErrorKind, fallback: string): string {
  switch (kind) {
    case "not-found":
      return "We couldn't find this match. It may be too old, or the region is off.";
    case "rate-limited":
      return "The Riot API is rate-limited right now. Please wait a moment and try again.";
    case "no-key":
      return "Riot API key not configured on the server. Set RIOT_API_KEY in the API environment to enable per-game analysis.";
    case "unsupported":
      return "This game isn't a standard Summoner's Rift 5v5, so the draft model can't analyze it. Try a ranked or normal draft game.";
    case "upstream":
      return "Riot's servers returned a momentary error (502). This usually clears up in a few seconds — try again.";
    case "network":
      return fallback;
    default:
      return fallback || "Something went wrong analyzing this game. Please try again.";
  }
}

/** Big, clear right/wrong banner comparing predicted vs actual winner side. */
function VerdictBanner({ data }: { data: MatchPrediction }) {
  const predictedSide = data.predicted.winner;
  const actualSide = data.actual.winner_side;

  // No recorded winner -> we can only show the prediction, not a verdict.
  if (!actualSide) {
    return (
      <div className="rounded-xl border border-line bg-surface-2/60 px-4 py-3 text-sm text-ink-soft">
        This match has no recorded result, so we can&apos;t check the prediction.
      </div>
    );
  }

  const correct = predictedSide === actualSide;
  return (
    <div
      className={`flex items-start gap-3 rounded-2xl border px-5 py-4 ${
        correct
          ? "border-win/40 bg-win/[0.08]"
          : "border-gold/40 bg-gold/[0.07]"
      }`}
    >
      <span
        className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full ${
          correct ? "bg-win/20 text-win" : "bg-gold/20 text-gold"
        }`}
      >
        {correct ? (
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
            <path d="m5 12.5 4.5 4.5L19 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
            <path d="M7 7l10 10M17 7 7 17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
        )}
      </span>
      <div>
        <p className={`font-display text-lg font-bold ${correct ? "text-win" : "text-gold-bright"}`}>
          {correct
            ? "The model called this game correctly"
            : "The model got this one wrong"}
        </p>
        <p className="mt-0.5 text-sm text-ink-soft">
          Model favoured <span className="font-semibold text-ink">{predictedSide}</span>; the
          actual winner was <span className="font-semibold text-ink">{actualSide}</span>.
          {data.actual.player_won != null && (
            <>
              {" "}This player{" "}
              <span className={`font-semibold ${data.actual.player_won ? "text-win" : "text-loss"}`}>
                {data.actual.player_won ? "won" : "lost"}
              </span>{" "}
              the game.
            </>
          )}
        </p>
      </div>
    </div>
  );
}

function MatchPredictionScreen() {
  const routeParams = useParams<{ matchId: string }>();
  const matchId = decodeURIComponent(
    Array.isArray(routeParams.matchId)
      ? routeParams.matchId[0]
      : routeParams.matchId ?? "",
  );

  const query = useSearchParams();
  const puuid = query.get("puuid") ?? "";
  const region = query.get("region") ?? "";
  const gameName = query.get("gameName") ?? "";
  const tag = query.get("tag") ?? "";

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<MatchPrediction | null>(null);
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

    getMatchPrediction(matchId, puuid, region || undefined)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof SummonerSearchError) {
          setError(messageForKind(err.kind, err.message));
        } else {
          setError("Something went wrong analyzing this game. Please try again.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [matchId, puuid, region, reloadKey]);

  // Link back to the player's game list (preserve who we were looking at).
  const backParams = new URLSearchParams();
  if (puuid) backParams.set("puuid", puuid);
  if (gameName) backParams.set("gameName", gameName);
  if (tag) backParams.set("tag", tag);
  if (region) backParams.set("region", region);
  const backHref = `/games?${backParams.toString()}`;

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:py-12">
      <header className="mb-7">
        <p className="text-sm">
          <Link
            href={backHref}
            className="inline-flex items-center gap-1.5 text-ink-muted transition-colors hover:text-gold"
          >
            <span aria-hidden="true">←</span> Back to recent games
          </Link>
        </p>
        <span className="eyebrow mt-4 block text-gold">Game Analysis</span>
        <h1 className="mt-1 font-display text-3xl font-bold text-ink sm:text-4xl">
          Predicted vs reality
        </h1>
        <p className="mt-2 text-pretty text-ink-muted">
          The draft model&apos;s call from this game&apos;s champion picks,
          checked against what actually happened.
        </p>
      </header>

      {(!matchId || !puuid) && (
        <div className="rounded-xl border border-gold/30 bg-gold/[0.06] px-4 py-3 text-sm text-ink-soft">
          Missing match or player.{" "}
          <Link href="/search" className="font-semibold text-gold underline-offset-2 hover:underline">
            Search for a player
          </Link>{" "}
          and pick a game to analyze.
        </div>
      )}

      {matchId && puuid && loading && (
        <div className="space-y-5" aria-hidden="true">
          <div className="skeleton h-20 rounded-2xl" />
          <div className="grid gap-5 md:grid-cols-2">
            <div className="skeleton h-80 rounded-2xl" />
            <div className="skeleton h-80 rounded-2xl" />
          </div>
          <div className="skeleton h-56 rounded-2xl" />
        </div>
      )}

      {matchId && puuid && !loading && error && (
        <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />
      )}

      {matchId && puuid && !loading && !error && data && (
        <div className="space-y-6">
          <VerdictBanner data={data} />

          {data.fallback_used && (
            <p className="rounded-lg border-l-2 border-line-strong bg-surface-2/60 px-3.5 py-2.5 text-xs text-ink-muted">
              Note: Riot didn&apos;t report full lane data for this game, so lane
              assignments are approximate.
            </p>
          )}

          <div className="grid gap-5 md:grid-cols-2">
            <TeamDraftCard
              title="Blue Team"
              accent="blue"
              picks={sidePicks(data.draft, "blue")}
              predictedWinner={data.predicted.winner === "Blue Team"}
              actualWinner={data.actual.winner_side === "Blue Team"}
            />
            <TeamDraftCard
              title="Red Team"
              accent="red"
              picks={sidePicks(data.draft, "red")}
              predictedWinner={data.predicted.winner === "Red Team"}
              actualWinner={data.actual.winner_side === "Red Team"}
            />
          </div>

          <ResultPanel result={data.predicted} />
        </div>
      )}

      {/* Win-probability timeline. Fetches independently of the draft section
          (it owns its own loading / error / "unavailable" states), so a
          timeline failure never blocks the draft view above it. */}
      {matchId && puuid && (
        <div className="mt-6">
          <TimelinePrediction
            matchId={matchId}
            puuid={puuid}
            region={region || undefined}
          />
        </div>
      )}

      <footer className="mt-12 text-center text-xs text-ink-dim">
        Match data comes from the Riot Games API via this app&apos;s backend.
        For fun, not affiliated with Riot Games.
      </footer>
    </main>
  );
}

/**
 * Per-game analysis screen.
 *
 * Reads `matchId` from the route param and `puuid` / `region` (plus optional
 * `gameName` / `tag` for the back-link) from the query — the /games list links
 * here. Fetches `GET /riot/match/{matchId}/prediction`, then shows both teams'
 * reconstructed draft, the model's predicted winner + win-probability bar +
 * confidence (via {@link ResultPanel}), the actual result, and a clear
 * "predicted correctly / incorrectly" verdict. Handles loading / not-found /
 * rate-limited / no-key / unsupported (non-SR) / network states.
 *
 * `useSearchParams` requires a Suspense boundary in the Next 14 App Router, so
 * the screen is wrapped below (matching /games).
 */
export default function MatchPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-4xl px-4 py-10 text-sm text-ink-muted">
          Loading…
        </main>
      }
    >
      <MatchPredictionScreen />
    </Suspense>
  );
}
