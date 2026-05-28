"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import ChampionPicker from "@/components/ChampionPicker";
import ResultPanel from "@/components/ResultPanel";
import { isValidChampion } from "@/data/champions";
import {
  ROLES,
  predictDraft,
  type DraftPredictionRequest,
  type PredictionResponse,
  type Role,
} from "@/lib/api";

type TeamPicks = Record<Role, string>;

const EMPTY_TEAM: TeamPicks = {
  top: "",
  jungle: "",
  mid: "",
  adc: "",
  support: "",
};

function TeamBoard({
  title,
  accent,
  picks,
  onChange,
}: {
  title: string;
  accent: "blue" | "red";
  picks: TeamPicks;
  onChange: (role: Role, value: string) => void;
}) {
  const filled = ROLES.filter((r) => isValidChampion(picks[r.key])).length;
  const isBlue = accent === "blue";

  return (
    <div className="panel relative overflow-hidden p-5">
      {/* Team-colored top accent + corner wash */}
      <span
        className={`absolute inset-x-0 top-0 h-px ${
          isBlue ? "bg-blue-fill" : "bg-red-fill"
        }`}
      />
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute -top-16 ${
          isBlue ? "-left-16" : "-right-16"
        } h-40 w-40 rounded-full blur-3xl ${
          isBlue ? "bg-team_blue/20" : "bg-team_red/20"
        }`}
      />
      <div className="relative mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2.5 font-display text-lg font-semibold text-ink">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              isBlue
                ? "bg-team_blue shadow-glow-blue"
                : "bg-team_red shadow-glow-red"
            }`}
          />
          {title}
        </h2>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold tabular-nums ${
            filled === 5
              ? isBlue
                ? "border-team_blue/40 bg-team_blue/10 text-team_blue-glow"
                : "border-team_red/40 bg-team_red/10 text-team_red-glow"
              : "border-line text-ink-muted"
          }`}
        >
          {filled}/5
        </span>
      </div>
      <div className="relative space-y-3">
        {ROLES.map((role) => (
          <ChampionPicker
            key={role.key}
            label={role.label}
            role={role.key}
            accent={accent}
            value={picks[role.key]}
            onChange={(v) => onChange(role.key, v)}
          />
        ))}
      </div>
    </div>
  );
}

function VsBadge() {
  return (
    <span className="relative grid h-12 w-12 place-items-center">
      <span className="absolute inset-0 rotate-45 rounded-lg border border-gold/50 bg-canvas shadow-gold" />
      <span className="relative font-display text-sm font-bold tracking-widest text-gold-bright">
        VS
      </span>
    </span>
  );
}

export default function Home() {
  const [blue, setBlue] = useState<TeamPicks>({ ...EMPTY_TEAM });
  const [red, setRed] = useState<TeamPicks>({ ...EMPTY_TEAM });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);

  const allChosen = useMemo(() => {
    const everyValid = (team: TeamPicks) =>
      ROLES.every((r) => isValidChampion(team[r.key]));
    return everyValid(blue) && everyValid(red);
  }, [blue, red]);

  const chosenCount = useMemo(() => {
    const count = (team: TeamPicks) =>
      ROLES.filter((r) => isValidChampion(team[r.key])).length;
    return count(blue) + count(red);
  }, [blue, red]);

  async function handlePredict() {
    if (!allChosen || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const body: DraftPredictionRequest = {
      blue_top: blue.top,
      blue_jungle: blue.jungle,
      blue_mid: blue.mid,
      blue_adc: blue.adc,
      blue_support: blue.support,
      red_top: red.top,
      red_jungle: red.jungle,
      red_mid: red.mid,
      red_adc: red.adc,
      red_support: red.support,
    };

    try {
      const data = await predictDraft(body);
      setResult(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <header className="mx-auto mb-10 max-w-2xl text-center">
        <span className="eyebrow inline-flex items-center gap-2 text-gold">
          <span className="h-1 w-1 rounded-full bg-gold" />
          AI Draft Analysis
        </span>
        <h1 className="mt-3 text-balance font-display text-4xl font-bold leading-tight text-ink sm:text-5xl">
          Who wins the <span className="text-gold-gradient">draft</span>?
        </h1>
        <p className="mt-4 text-pretty text-base leading-relaxed text-ink-soft">
          Lock in a champion for every role on both teams and let the model call
          the side it favours — trained on real Summoner&apos;s Rift games.
        </p>
        <p className="mt-6">
          <Link
            href="/search"
            className="btn-secondary group"
          >
            Analyze your real games
            <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
              →
            </span>
          </Link>
        </p>
      </header>

      <div className="relative grid gap-5 md:grid-cols-2 md:gap-12">
        <TeamBoard
          title="Blue Team"
          accent="blue"
          picks={blue}
          onChange={(role, value) =>
            setBlue((prev) => ({ ...prev, [role]: value }))
          }
        />
        <TeamBoard
          title="Red Team"
          accent="red"
          picks={red}
          onChange={(role, value) =>
            setRed((prev) => ({ ...prev, [role]: value }))
          }
        />
        <div className="pointer-events-none absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 md:block">
          <VsBadge />
        </div>
      </div>

      <div className="mt-8 flex flex-col items-center gap-3">
        <button
          type="button"
          onClick={handlePredict}
          disabled={!allChosen || loading}
          className="btn-primary w-full max-w-sm text-base"
          aria-busy={loading}
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              Predicting…
            </>
          ) : (
            "Predict the winner"
          )}
        </button>
        {!allChosen && (
          <div className="flex w-full max-w-sm flex-col items-center gap-1.5">
            <div className="h-1 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-gold-sheen transition-all duration-500"
                style={{ width: `${(chosenCount / 10) * 100}%` }}
              />
            </div>
            <p className="text-xs text-ink-muted tabular-nums">
              {chosenCount}/10 champions chosen
            </p>
          </div>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="mx-auto mt-6 max-w-2xl rounded-xl border border-team_red/40 bg-team_red/10 px-4 py-3 text-sm text-team_red-glow"
        >
          {error}
        </div>
      )}

      {result && (
        <div className="mx-auto mt-8 max-w-3xl animate-fade-up">
          <ResultPanel result={result} />
        </div>
      )}

      <footer className="mt-14 text-center text-xs text-ink-dim">
        Predictions come from the LoL Draft Predictor API. Champion picks only —
        for fun, not betting.
      </footer>
    </main>
  );
}
