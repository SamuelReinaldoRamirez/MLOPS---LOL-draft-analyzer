"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import SummonerSearch from "@/components/SummonerSearch";
import type { SummonerResult } from "@/lib/api";
import { addRecentSearch } from "@/lib/recentSearches";

/**
 * Player search / select screen.
 *
 * Resolves a Riot ID via the REAL backend (`GET /riot/summoner`) and shows the
 * matched player with a "Select" action. Selecting navigates to the match
 * history screen (`/games`), passing the player via URL query params (puuid,
 * gameName, tag, region) so the history page can fetch their recent games. All
 * failure states (loading, not-found, rate-limited, no-key, network) are
 * handled inside {@link SummonerSearch}.
 */
export default function SearchPage() {
  const router = useRouter();

  function handleSelect(summoner: SummonerResult) {
    const params = new URLSearchParams({
      puuid: summoner.puuid,
      gameName: summoner.game_name,
      tag: summoner.tag_line,
      region: summoner.platform,
    });
    router.push(`/games?${params.toString()}`);
  }

  /**
   * A search RESOLVED successfully — remember it (localStorage) so it appears in
   * the autocomplete dropdown's "Recent searches" next time. Best-effort: the
   * helper guards SSR / blocked storage and never throws.
   */
  function handleResolved(info: {
    gameName: string;
    tagLine: string;
    region: string;
  }) {
    addRecentSearch(info);
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-10 sm:py-14">
      <p className="mb-6 text-sm">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-ink-muted transition-colors hover:text-gold"
        >
          <span aria-hidden="true">←</span> Back to the draft predictor
        </Link>
      </p>

      <header className="mb-8 text-center">
        <span className="eyebrow text-gold">Player Lookup</span>
        <h1 className="mt-3 font-display text-3xl font-bold text-ink sm:text-4xl">
          Find your games
        </h1>
        <p className="mx-auto mt-3 max-w-md text-pretty text-ink-soft">
          Search any League of Legends account by Riot ID to analyze their real
          matches, live games and minute-by-minute odds.
        </p>
      </header>

      <div className="panel p-5 sm:p-6">
        <SummonerSearch onSelect={handleSelect} onResolved={handleResolved} />
      </div>

      <footer className="mt-10 text-center text-xs text-ink-dim">
        Player data comes from the Riot Games API via this app&apos;s backend.
        Riot ID search only — for fun, not affiliated with Riot Games.
      </footer>
    </main>
  );
}
