"use client";

import ResultPanel from "@/components/ResultPanel";
import TeamDraftCard, { sidePicks } from "@/components/TeamDraftCard";
import type { LivePrediction } from "@/lib/api";

/**
 * Presentation for an in-progress live game.
 *
 * Shows both teams' reconstructed draft and the draft model's predicted winner
 * + win-probability bar + confidence (via {@link ResultPanel}). There is NO
 * actual result (the game is live). Because spectator data carries no lane
 * info, lane assignment is approximate — surfaced as a clear note since
 * `fallback_used` is always true here.
 */
export default function LivePredictionView({ data }: { data: LivePrediction }) {
  // Only rendered for the in-game case; guard keeps the types honest.
  if (!data.in_game || !data.draft || !data.predicted) return null;

  const predictedSide = data.predicted.winner;

  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-2xl border border-teal/40 bg-teal/[0.08] px-5 py-4">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-teal/20 blur-3xl"
        />
        <p className="relative flex items-center gap-2.5 font-display text-lg font-bold text-teal">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-teal" />
          </span>
          Live game in progress
        </p>
        <p className="relative mt-1 text-sm text-ink-soft">
          The draft model favours{" "}
          <span className="font-semibold text-ink">{predictedSide}</span> based on
          the champion picks below. The game isn&apos;t over yet — this is a
          prediction, not a result.
        </p>
      </div>

      <p className="rounded-lg border-l-2 border-gold/60 bg-gold/[0.06] px-3.5 py-2.5 text-xs leading-relaxed text-ink-soft">
        Note: lanes are approximate — live spectator data has no role info, so
        each pick is placed by team order. The win prediction is side-based and
        unaffected, but the lane labels are a best-effort guess.
      </p>

      <div className="grid gap-5 md:grid-cols-2">
        <TeamDraftCard
          title="Blue Team"
          accent="blue"
          picks={sidePicks(data.draft, "blue")}
          predictedWinner={predictedSide === "Blue Team"}
        />
        <TeamDraftCard
          title="Red Team"
          accent="red"
          picks={sidePicks(data.draft, "red")}
          predictedWinner={predictedSide === "Red Team"}
        />
      </div>

      <ResultPanel result={data.predicted} />
    </div>
  );
}
