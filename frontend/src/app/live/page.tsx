"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ErrorState from "@/components/ErrorState";
import LivePredictionView from "@/components/LivePrediction";
import {
  getLivePrediction,
  SummonerSearchError,
  type LivePrediction,
  type RiotErrorKind,
} from "@/lib/api";

/** Friendly, non-technical copy for each typed failure state. */
function messageForKind(kind: RiotErrorKind, fallback: string): string {
  switch (kind) {
    case "not-found":
      return "We couldn't check this player's live game. The Riot ID/region may be off.";
    case "rate-limited":
      return "The Riot API is rate-limited right now. Please wait a moment and try again.";
    case "no-key":
      return "Riot API key not configured on the server. Set RIOT_API_KEY in the API environment to enable live-game analysis.";
    case "unsupported":
      return "This live game isn't a standard Summoner's Rift 5v5, so the draft model can't analyze it (e.g. ARAM).";
    case "upstream":
      return "Riot's servers returned a momentary error (502). This usually clears up in a few seconds — try again.";
    case "network":
      return fallback;
    default:
      return fallback || "Something went wrong checking this live game. Please try again.";
  }
}

function LivePredictionScreen() {
  const query = useSearchParams();
  const puuid = query.get("puuid") ?? "";
  const region = query.get("region") ?? "";
  const gameName = query.get("gameName") ?? "";
  const tag = query.get("tag") ?? "";

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<LivePrediction | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!puuid) {
      setData(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    getLivePrediction(puuid, region || undefined)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof SummonerSearchError) {
          setError(messageForKind(err.kind, err.message));
        } else {
          setError("Something went wrong checking this live game. Please try again.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [puuid, region, reloadKey]);

  // Link back to the player's game list (preserve who we were looking at).
  const backParams = new URLSearchParams();
  if (puuid) backParams.set("puuid", puuid);
  if (gameName) backParams.set("gameName", gameName);
  if (tag) backParams.set("tag", tag);
  if (region) backParams.set("region", region);
  const backHref = `/games?${backParams.toString()}`;

  const who = gameName && tag ? `${gameName}#${tag}` : gameName;

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
        <span className="eyebrow mt-4 flex items-center gap-2 text-teal">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-teal" />
          </span>
          Live Spectator
        </span>
        <h1 className="mt-1 font-display text-3xl font-bold text-ink sm:text-4xl">
          Live game
        </h1>
        <p className="mt-2 text-pretty text-ink-muted">
          If {who ? <span className="font-medium text-ink-soft">{who}</span> : "this player"} is
          in a game right now, the draft model predicts the winner from the live
          champion picks.
        </p>
      </header>

      {!puuid && (
        <div className="rounded-xl border border-gold/30 bg-gold/[0.06] px-4 py-3 text-sm text-ink-soft">
          No player selected.{" "}
          <Link href="/search" className="font-semibold text-gold underline-offset-2 hover:underline">
            Search for a player
          </Link>{" "}
          to check their live game.
        </div>
      )}

      {puuid && loading && (
        <div className="space-y-5" aria-hidden="true">
          <div className="skeleton h-20 rounded-2xl" />
          <div className="grid gap-5 md:grid-cols-2">
            <div className="skeleton h-80 rounded-2xl" />
            <div className="skeleton h-80 rounded-2xl" />
          </div>
          <div className="skeleton h-56 rounded-2xl" />
        </div>
      )}

      {puuid && !loading && error && (
        <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />
      )}

      {/* Not in a game right now: a graceful empty state, not an error. */}
      {puuid && !loading && !error && data && !data.in_game && (
        <div className="panel px-6 py-12 text-center">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-surface-2 text-ink-dim">
            <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
              <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <p className="mt-4 font-display text-lg font-bold text-ink">
            No live game right now
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink-soft">
            This player isn&apos;t in a game at the moment. Check back when
            they&apos;re in champion select or in-game, or browse their recent
            games instead.
          </p>
          <p className="mt-5">
            <Link href={backHref} className="btn-primary px-5 py-2.5">
              View recent games
            </Link>
          </p>
        </div>
      )}

      {/* In a game: show the reconstructed draft + the model's prediction. */}
      {puuid && !loading && !error && data && data.in_game && (
        <LivePredictionView data={data} />
      )}

      <footer className="mt-12 text-center text-xs text-ink-dim">
        Live data comes from the Riot Games API via this app&apos;s backend. For
        fun, not affiliated with Riot Games.
      </footer>
    </main>
  );
}

/**
 * Live-game prediction screen for a selected player.
 *
 * Reads the player from the URL query (`puuid` / `region`, plus optional
 * `gameName` / `tag` for the back-link) — the /games "Check live game" action
 * links here. Fetches `GET /riot/live/{puuid}/prediction`. In a game -> shows
 * both teams' reconstructed draft + the model's predicted winner +
 * win-probability bar + confidence (via {@link LivePredictionView}) and a clear
 * "lanes approximate" note (spectator data has no role info). Not in a game ->
 * a graceful "No live game right now" empty state. Handles loading /
 * rate-limited / no-key / unsupported (non-SR) / network states.
 *
 * `useSearchParams` requires a Suspense boundary in the Next 14 App Router, so
 * the screen is wrapped below (matching /games and /match).
 */
export default function LivePage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-4xl px-4 py-10 text-sm text-ink-muted">
          Loading…
        </main>
      }
    >
      <LivePredictionScreen />
    </Suspense>
  );
}
