"use client";

import ChampionAvatar from "@/components/ChampionAvatar";
import {
  formatDuration,
  formatRelativeDate,
  queueLabel,
  type MatchSummary,
} from "@/lib/api";

/** Champion square icon URL (Data-Dragon). Champion names from the API are
 *  Data-Dragon keys (e.g. "LeeSin"), so the name maps straight to the file. */
function championIconUrl(championName: string): string {
  return `https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/${championName}.png`;
}

function WinLossBadge({ win }: { win: boolean | null }) {
  if (win == null) {
    return (
      <span className="rounded-md bg-surface-3 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-ink-muted">
        —
      </span>
    );
  }
  return win ? (
    <span className="rounded-md bg-win/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-win">
      Win
    </span>
  ) : (
    <span className="rounded-md bg-loss/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-loss">
      Loss
    </span>
  );
}

function MatchRow({
  match,
  onSelect,
}: {
  match: MatchSummary;
  onSelect?: (match: MatchSummary) => void;
}) {
  const champ = match.champion_name;
  const win = match.win;
  const accent =
    win === true
      ? "bg-win shadow-[0_0_12px_rgba(52,211,153,0.6)]"
      : win === false
        ? "bg-loss shadow-[0_0_12px_rgba(251,110,110,0.6)]"
        : "bg-line-strong";

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect?.(match)}
        className="group relative flex w-full items-center gap-3.5 overflow-hidden rounded-xl border border-line bg-surface/70 py-3 pl-5 pr-3 text-left transition duration-200 hover:border-gold/40 hover:bg-surface-2"
      >
        {/* Win/loss accent rail */}
        <span
          aria-hidden="true"
          className={`absolute inset-y-0 left-0 w-1 ${accent}`}
        />

        <ChampionAvatar
          src={champ ? championIconUrl(champ) : null}
          alt={champ ?? "Unknown champion"}
          size={48}
          className={`rounded-lg ring-1 ${
            win === true
              ? "ring-win/40"
              : win === false
                ? "ring-loss/40"
                : "ring-line"
          }`}
        />

        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-semibold text-ink">
            <span className="truncate">{champ ?? "Unknown champion"}</span>
            <WinLossBadge win={win} />
          </p>
          <p className="mt-0.5 truncate text-sm text-ink-muted">
            {queueLabel(match.queue_id)}
            <span className="text-ink-dim"> · </span>
            <span className="tabular-nums">{formatDuration(match.game_duration)}</span>
            {match.game_creation ? (
              <>
                <span className="text-ink-dim"> · </span>
                {formatRelativeDate(match.game_creation)}
              </>
            ) : null}
          </p>
        </div>

        <span className="flex shrink-0 items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-ink-muted transition-colors group-hover:border-gold/50 group-hover:text-gold">
          Analyze
          <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
            →
          </span>
        </span>
      </button>
    </li>
  );
}

export interface MatchHistoryProps {
  matches: MatchSummary[];
  /** Optional: forwards a clicked match to the per-game prediction screen. */
  onSelectMatch?: (match: MatchSummary) => void;
}

/**
 * Presentational list of recent matches.
 *
 * Each row shows the player's champion, a Win/Loss badge, the queue label, the
 * duration (mm:ss) and a relative date. Clicking a row forwards the match to
 * the per-game prediction screen.
 */
export default function MatchHistory({
  matches,
  onSelectMatch,
}: MatchHistoryProps) {
  if (matches.length === 0) {
    return (
      <div className="panel px-6 py-12 text-center">
        <p className="text-ink-soft">
          No recent Summoner&apos;s Rift games found for this player.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-2.5">
      {matches.map((m) => (
        <MatchRow key={m.match_id} match={m} onSelect={onSelectMatch} />
      ))}
    </ul>
  );
}
