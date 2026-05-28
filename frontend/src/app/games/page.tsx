"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import MatchHistory from "@/components/MatchHistory";
import ErrorState from "@/components/ErrorState";
import {
  getMatchHistory,
  SummonerSearchError,
  type MatchSummary,
  type RiotErrorKind,
} from "@/lib/api";

/** Friendly, non-technical copy for each typed failure state. */
function messageForKind(kind: RiotErrorKind, fallback: string): string {
  switch (kind) {
    case "not-found":
      return "We couldn't find recent games for this player. They may have no ranked/draft history, or the Riot ID/region is off.";
    case "rate-limited":
      return "The Riot API is rate-limited right now. Please wait a moment and try again.";
    case "no-key":
      return "Riot API key not configured on the server. Set RIOT_API_KEY in the API environment to enable match history.";
    case "upstream":
      return "Riot's servers returned a momentary error (502). This usually clears up in a few seconds — try again.";
    case "network":
      return fallback;
    default:
      return fallback || "Something went wrong loading match history. Please try again.";
  }
}

function MatchHistoryScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const puuid = params.get("puuid") ?? "";
  const gameName = params.get("gameName") ?? "";
  const tag = params.get("tag") ?? "";
  const region = params.get("region") ?? "";

  // "Analyze →" on a row routes to the per-game prediction screen, forwarding
  // the player (puuid + region, plus gameName/tag for the back-link there).
  function handleSelectMatch(match: MatchSummary) {
    const q = new URLSearchParams({ puuid });
    if (region) q.set("region", region);
    if (gameName) q.set("gameName", gameName);
    if (tag) q.set("tag", tag);
    router.push(`/match/${encodeURIComponent(match.match_id)}?${q.toString()}`);
  }

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [matches, setMatches] = useState<MatchSummary[] | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!puuid) {
      setMatches(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setMatches(null);

    getMatchHistory(puuid, region || undefined)
      .then((data) => {
        if (!cancelled) setMatches(data.matches);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof SummonerSearchError) {
          setError(messageForKind(err.kind, err.message));
        } else {
          setError("Something went wrong loading match history. Please try again.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [puuid, region, reloadKey]);

  const title =
    gameName && tag ? `${gameName}#${tag}` : gameName || "Recent games";

  // "Check live game" forwards the same player context (puuid + region, plus
  // gameName/tag for the back-link there) to the live-game screen.
  const liveParams = new URLSearchParams();
  if (puuid) liveParams.set("puuid", puuid);
  if (region) liveParams.set("region", region);
  if (gameName) liveParams.set("gameName", gameName);
  if (tag) liveParams.set("tag", tag);
  const liveHref = `/live?${liveParams.toString()}`;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:py-12">
      <header className="mb-7">
        <p className="text-sm">
          <Link
            href="/search"
            className="inline-flex items-center gap-1.5 text-ink-muted transition-colors hover:text-gold"
          >
            <span aria-hidden="true">←</span> Back to player search
          </Link>
        </p>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <span className="eyebrow text-gold">Match History</span>
            <h1 className="mt-1 font-display text-3xl font-bold text-ink sm:text-4xl">
              {gameName && tag ? (
                <>
                  {gameName}
                  <span className="text-ink-dim">#{tag}</span>
                </>
              ) : (
                title
              )}
            </h1>
          </div>
          {puuid && (
            <Link
              href={liveHref}
              className="inline-flex items-center gap-2 rounded-xl border border-teal/40 bg-teal/10 px-4 py-2.5 text-sm font-semibold text-teal transition hover:border-teal/70 hover:bg-teal/15"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-teal" />
              </span>
              Check live game
            </Link>
          )}
        </div>
        <p className="mt-2 text-pretty text-ink-muted">
          Recent Summoner&apos;s Rift games
          {region ? ` on ${region.toUpperCase()}` : ""}. Pick a game to see the
          model&apos;s draft prediction vs the real result.
        </p>
      </header>

      {!puuid && (
        <div className="rounded-xl border border-gold/30 bg-gold/[0.06] px-4 py-3 text-sm text-ink-soft">
          No player selected.{" "}
          <Link href="/search" className="font-semibold text-gold underline-offset-2 hover:underline">
            Search for a player
          </Link>{" "}
          to see their recent games.
        </div>
      )}

      {puuid && loading && (
        <ul className="space-y-2.5" aria-hidden="true">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <li
              key={i}
              className="flex items-center gap-3.5 rounded-xl border border-line bg-surface/70 py-3 pl-5 pr-3"
            >
              <div className="skeleton h-12 w-12 shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="skeleton h-4 w-1/3" />
                <div className="skeleton h-3 w-1/2" />
              </div>
              <div className="skeleton h-8 w-20 rounded-lg" />
            </li>
          ))}
        </ul>
      )}

      {puuid && !loading && error && (
        <ErrorState message={error} onRetry={() => setReloadKey((k) => k + 1)} />
      )}

      {puuid && !loading && !error && matches && (
        <MatchHistory matches={matches} onSelectMatch={handleSelectMatch} />
      )}

      <footer className="mt-12 text-center text-xs text-ink-dim">
        Match data comes from the Riot Games API via this app&apos;s backend.
        For fun, not affiliated with Riot Games.
      </footer>
    </main>
  );
}

/**
 * Match-history screen for a selected player.
 *
 * Reads the player from the URL query (`puuid`, `gameName`, `tag`, `region`) —
 * the /search "Select" action navigates here. Lists the player's recent real
 * Summoner's Rift games with graceful loading / empty / error states. Each row
 * routes to the per-game prediction screen.
 *
 * `useSearchParams` requires a Suspense boundary in the Next 14 App Router, so
 * the screen is wrapped below.
 */
export default function GamesPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-3xl px-4 py-10 text-sm text-ink-muted">
          Loading…
        </main>
      }
    >
      <MatchHistoryScreen />
    </Suspense>
  );
}
