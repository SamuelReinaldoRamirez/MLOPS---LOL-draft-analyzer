"use client";

import { useId } from "react";
import {
  CHAMPION_NAMES,
  championPortraitByName,
  isValidChampion,
} from "@/data/champions";
import ChampionAvatar from "@/components/ChampionAvatar";
import RoleIcon from "@/components/RoleIcon";
import type { Role } from "@/lib/api";

interface ChampionPickerProps {
  label: string;
  role: Role;
  value: string;
  onChange: (value: string) => void;
  accent: "blue" | "red";
}

/**
 * A searchable champion selector backed by a native `<datalist>`.
 *
 * Users type to filter the 172 valid champions; only an exact match counts as a
 * real pick (the parent gates Predict on validity). A valid pick shows the
 * champion's portrait inline; free text that isn't recognised gets a red ring.
 */
export default function ChampionPicker({
  label,
  role,
  value,
  onChange,
  accent,
}: ChampionPickerProps) {
  const listId = useId();
  const valid = isValidChampion(value);
  const showInvalid = value !== "" && !valid;

  const focusRing =
    accent === "blue"
      ? "focus:border-team_blue/70 focus:ring-team_blue/30"
      : "focus:border-team_red/70 focus:ring-team_red/30";
  const ring = valid
    ? accent === "blue"
      ? "ring-2 ring-team_blue/60"
      : "ring-2 ring-team_red/60"
    : "ring-1 ring-line";

  return (
    <label className="block">
      <span className="mb-1.5 flex items-center gap-1.5 eyebrow">
        <RoleIcon role={role} className="h-3.5 w-3.5 text-ink-muted" />
        {label}
      </span>
      <div className="relative">
        <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2">
          <ChampionAvatar
            src={valid ? championPortraitByName(value) : null}
            alt={valid ? value : ""}
            size={32}
            className={`rounded-md ${ring}`}
          />
        </span>
        <input
          type="text"
          list={listId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search champion…"
          autoComplete="off"
          aria-invalid={showInvalid}
          className={[
            "field h-12 pl-12 pr-3 font-medium",
            focusRing,
            showInvalid
              ? "border-team_red/70 ring-2 ring-team_red/30"
              : "",
          ].join(" ")}
        />
        <datalist id={listId}>
          {CHAMPION_NAMES.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>
      {showInvalid && (
        <span className="mt-1 block text-xs text-team_red">
          Pick a champion from the list.
        </span>
      )}
    </label>
  );
}
