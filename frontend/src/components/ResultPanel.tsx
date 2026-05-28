"use client";

import type { PredictionResponse } from "@/lib/api";

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * The prediction centerpiece: who's favoured, a dual blue/red win-probability
 * gauge, the confidence and model accuracy, and an honest note that the
 * draft-only model is roughly coin-flip accurate. Shared by the draft board,
 * the per-game analysis and the live-game views.
 */
export default function ResultPanel({ result }: { result: PredictionResponse }) {
  const blue = Math.max(0, Math.min(1, result.blue_win_probability));
  const red = Math.max(0, Math.min(1, result.red_win_probability));
  const blueFavoured = result.winner === "Blue Team";

  return (
    <section className="panel relative overflow-hidden p-6 sm:p-7">
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute -top-24 left-1/2 h-48 w-72 -translate-x-1/2 rounded-full blur-3xl ${
          blueFavoured ? "bg-team_blue/15" : "bg-team_red/15"
        }`}
      />
      <div className="relative">
        <span className="eyebrow">Prediction</span>
        <p className="mt-2 flex flex-wrap items-baseline gap-x-2 font-display text-2xl font-bold text-ink sm:text-3xl">
          Favoured to win
          <span
            className={blueFavoured ? "text-team_blue-glow" : "text-team_red-glow"}
          >
            {result.winner}
          </span>
        </p>

        {/* Dual win-probability gauge */}
        <div className="mt-6">
          <div className="mb-2 flex items-end justify-between font-display tabular-nums">
            <span
              className={`flex flex-col ${blueFavoured ? "" : "opacity-60"}`}
            >
              <span className="text-[11px] font-semibold uppercase tracking-wider text-team_blue-glow">
                Blue
              </span>
              <span
                className={`leading-none text-team_blue-glow ${
                  blueFavoured ? "text-2xl font-bold" : "text-lg font-semibold"
                }`}
              >
                {pct(blue)}
              </span>
            </span>
            <span
              className={`flex flex-col items-end ${blueFavoured ? "opacity-60" : ""}`}
            >
              <span className="text-[11px] font-semibold uppercase tracking-wider text-team_red-glow">
                Red
              </span>
              <span
                className={`leading-none text-team_red-glow ${
                  blueFavoured ? "text-lg font-semibold" : "text-2xl font-bold"
                }`}
              >
                {pct(red)}
              </span>
            </span>
          </div>
          <div className="relative flex h-9 w-full overflow-hidden rounded-lg bg-surface-2 ring-1 ring-inset ring-line">
            <div
              className="h-full bg-blue-fill shadow-glow-blue transition-[width] duration-700 ease-out"
              style={{ width: `${blue * 100}%` }}
              aria-label={`Blue team win probability ${pct(blue)}`}
            />
            <div
              className="h-full flex-1 bg-red-fill shadow-glow-red transition-[width] duration-700 ease-out"
              aria-label={`Red team win probability ${pct(red)}`}
            />
            {/* Coin-flip (50%) reference tick */}
            <span
              aria-hidden="true"
              className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-canvas/50"
            />
          </div>
        </div>

        {/* Stats */}
        <dl className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-line bg-surface-2/60 px-4 py-3">
            <dt className="text-xs text-ink-muted">Confidence</dt>
            <dd className="mt-0.5 font-display text-xl font-bold text-ink tabular-nums">
              {pct(result.confidence)}
            </dd>
          </div>
          <div className="rounded-xl border border-line bg-surface-2/60 px-4 py-3">
            <dt className="text-xs text-ink-muted">Model accuracy</dt>
            <dd className="mt-0.5 font-display text-xl font-bold text-ink tabular-nums">
              {result.model_accuracy != null
                ? pct(result.model_accuracy)
                : "—"}
            </dd>
          </div>
        </dl>

        <p className="mt-5 flex gap-2.5 rounded-lg border-l-2 border-gold/60 bg-gold/[0.06] px-3.5 py-2.5 text-xs leading-relaxed text-ink-soft">
          <svg
            viewBox="0 0 24 24"
            className="mt-0.5 h-4 w-4 shrink-0 text-gold"
            fill="none"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
            <path
              d="M12 11v5M12 8h.01"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
          <span>
            Heads up: this draft-only model sits around baseline accuracy
            (~50–55%). A real match turns on player skill and in-game decisions —
            treat this as a fun read on the champion picks, not a guarantee.
          </span>
        </p>
      </div>
    </section>
  );
}
