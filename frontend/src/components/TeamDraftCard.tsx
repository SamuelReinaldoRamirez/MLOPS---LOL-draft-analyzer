"use client";

import ChampionAvatar from "@/components/ChampionAvatar";
import RoleIcon from "@/components/RoleIcon";
import { championIconByKey } from "@/data/champions";
import { ROLES, type Role } from "@/lib/api";

/** Pull the 5 role picks for one side out of the flat `side_role` draft map. */
export function sidePicks(
  draft: Record<string, string>,
  side: "blue" | "red",
): Record<Role, string> {
  const out = {} as Record<Role, string>;
  for (const r of ROLES) {
    out[r.key] = draft[`${side}_${r.key}`] ?? "";
  }
  return out;
}

/**
 * One side's reconstructed draft (5 champions by role), styled to its team
 * color. Optional badges flag the side that actually won and/or the side the
 * model favoured. Shared by the per-game analysis and live-game views.
 */
export default function TeamDraftCard({
  title,
  accent,
  picks,
  actualWinner = false,
  predictedWinner = false,
}: {
  title: string;
  accent: "blue" | "red";
  picks: Record<Role, string>;
  actualWinner?: boolean;
  predictedWinner?: boolean;
}) {
  const isBlue = accent === "blue";

  return (
    <div className="panel relative overflow-hidden p-5">
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
          isBlue ? "bg-team_blue/15" : "bg-team_red/15"
        }`}
      />
      <div className="relative mb-4 flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-2.5 font-display text-lg font-semibold text-ink">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              isBlue ? "bg-team_blue shadow-glow-blue" : "bg-team_red shadow-glow-red"
            }`}
          />
          {title}
        </h2>
        {actualWinner && (
          <span className="rounded-md bg-win/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-win">
            Won
          </span>
        )}
        {predictedWinner && (
          <span className="rounded-md border border-gold/40 bg-gold/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-gold">
            Model favoured
          </span>
        )}
      </div>
      <ul className="relative space-y-2">
        {ROLES.map((role) => {
          const champ = picks[role.key];
          return (
            <li
              key={role.key}
              className="flex items-center gap-3 rounded-lg border border-line bg-surface-2/60 px-3 py-2"
            >
              <ChampionAvatar
                src={champ ? championIconByKey(champ) : null}
                alt={champ || role.label}
                size={36}
                className={`rounded-md ring-1 ${
                  isBlue ? "ring-team_blue/30" : "ring-team_red/30"
                }`}
              />
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-dim">
                  <RoleIcon role={role.key} className="h-3 w-3" />
                  {role.label}
                </p>
                <p className="truncate font-medium text-ink">{champ || "Unknown"}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
