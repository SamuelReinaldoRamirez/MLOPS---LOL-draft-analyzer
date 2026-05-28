"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  searchSummoner,
  suggestPlayers,
  SummonerSearchError,
  type PlayerSuggestion,
  type RiotErrorKind,
  type SummonerResult,
} from "@/lib/api";
import {
  getRecentSearches,
  type RecentSearch,
} from "@/lib/recentSearches";

/** Platform routing values offered in the region select. */
const REGIONS: { value: string; label: string }[] = [
  { value: "euw1", label: "EU West" },
  { value: "eun1", label: "EU Nordic & East" },
  { value: "na1", label: "North America" },
  { value: "kr", label: "Korea" },
  { value: "br1", label: "Brazil" },
  { value: "jp1", label: "Japan" },
  { value: "oc1", label: "Oceania" },
  { value: "tr1", label: "Türkiye" },
  { value: "la1", label: "LAN" },
  { value: "la2", label: "LAS" },
];

/** Friendly, non-technical copy for each typed failure state. */
function messageForKind(kind: RiotErrorKind, fallback: string): string {
  switch (kind) {
    case "not-found":
      return "No player found with that Riot ID. Check the name and tag (e.g. Faker#KR1).";
    case "rate-limited":
      return "The Riot API is rate-limited right now. Please wait a moment and try again.";
    case "no-key":
      return "Riot API key not configured on the server. Set RIOT_API_KEY in the API environment to enable player search.";
    case "upstream":
      return "Riot's servers returned a momentary error (502). This usually clears up in a few seconds — try the search again.";
    case "network":
      return fallback;
    default:
      return fallback || "Something went wrong contacting Riot. Please try again.";
  }
}

/** Split a "Name#TAG" Riot ID into its parts (tag may be omitted). */
function splitRiotId(raw: string): { gameName: string; tagLine: string } {
  const hash = raw.lastIndexOf("#");
  if (hash === -1) return { gameName: raw.trim(), tagLine: "" };
  return {
    gameName: raw.slice(0, hash).trim(),
    tagLine: raw.slice(hash + 1).trim(),
  };
}

/** Debounce (ms) before firing a suggestion fetch as the user types. */
const SUGGEST_DEBOUNCE_MS = 200;

/** A row rendered in the autocomplete dropdown. */
type SuggestionItem =
  | { kind: "recent"; gameName: string; tagLine: string; region: string }
  | { kind: "db"; gameName: string; tagLine: string; games: number };

/** Build the "Name#TAG" string a row fills the input with. */
function itemRiotId(item: SuggestionItem): string {
  return item.tagLine ? `${item.gameName}#${item.tagLine}` : item.gameName;
}

/** Stable identity for dedupe across recent + DB rows (case-insensitive). */
function itemKey(item: SuggestionItem): string {
  return `${item.gameName.toLowerCase()}#${item.tagLine.toLowerCase()}`;
}

export interface SummonerSearchProps {
  /** Called when the user selects a resolved player (card "Select" action). */
  onSelect?: (summoner: SummonerResult) => void;
  /**
   * Called whenever a search RESOLVES successfully (typed + region used). The
   * search screen uses this to record the search in localStorage history.
   */
  onResolved?: (info: { gameName: string; tagLine: string; region: string }) => void;
}

/**
 * Riot ID search box with a fuzzy autocomplete dropdown + resolved-player card.
 *
 * As the user types, a debounced call to `GET /riot/suggest` returns typo-
 * tolerant suggestions drawn from the LOCAL DB (real player names, pg_trgm).
 * When the input is empty/short the dropdown shows the user's own recent
 * searches; while typing, matching recents are merged ABOVE the DB matches.
 * Selecting a row (click / Enter) fills the Riot ID and runs the real
 * `GET /riot/summoner` search. Suggestions are best-effort and never block the
 * page. Keyboard: ↑/↓ move, Enter picks, Esc closes; ARIA combobox/listbox.
 */
export default function SummonerSearch({ onSelect, onResolved }: SummonerSearchProps) {
  const [riotId, setRiotId] = useState("");
  const [region, setRegion] = useState("euw1");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SummonerResult | null>(null);
  const [selected, setSelected] = useState(false);

  // Autocomplete state.
  const [suggestions, setSuggestions] = useState<PlayerSuggestion[]>([]);
  const [recent, setRecent] = useState<RecentSearch[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Bumped on every keystroke so a slow in-flight fetch can't overwrite newer
  // results (last-write-wins by request id).
  const fetchSeq = useRef(0);
  const listboxId = "summoner-suggestions";

  const { gameName, tagLine } = splitRiotId(riotId);
  const canSubmit = gameName.length > 0 && tagLine.length > 0 && !loading;
  const trimmedQuery = riotId.trim();

  // Load recent searches once on mount (client-only; safe on SSR).
  useEffect(() => {
    setRecent(getRecentSearches());
  }, []);

  // Debounced fuzzy fetch as the user types (>= 2 chars). The query is the part
  // before any '#', so "Fak#" still suggests on "Fak".
  useEffect(() => {
    const namePart = splitRiotId(riotId).gameName;
    if (namePart.length < 2) {
      setSuggestions([]);
      return;
    }
    const seq = ++fetchSeq.current;
    const handle = window.setTimeout(async () => {
      const results = await suggestPlayers(namePart, 8);
      // Ignore if a newer keystroke already superseded this request.
      if (seq === fetchSeq.current) setSuggestions(results);
    }, SUGGEST_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [riotId]);

  // Close the dropdown on an outside click.
  useEffect(() => {
    function onDocPointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", onDocPointerDown);
    return () => document.removeEventListener("pointerdown", onDocPointerDown);
  }, []);

  // Build the merged dropdown rows: matching recents first, then DB matches
  // (de-duplicated). With a short query, show recent searches only.
  function buildItems(): SuggestionItem[] {
    const q = splitRiotId(riotId).gameName.toLowerCase();
    const items: SuggestionItem[] = [];
    const seen = new Set<string>();

    const recentItems: SuggestionItem[] = recent.map((r) => ({
      kind: "recent" as const,
      gameName: r.gameName,
      tagLine: r.tagLine,
      region: r.region,
    }));

    if (q.length < 2) {
      // Empty/short: recent searches only (labelled in the UI).
      for (const it of recentItems) {
        const key = itemKey(it);
        if (!seen.has(key)) {
          seen.add(key);
          items.push(it);
        }
      }
      return items;
    }

    // Typing: matching recents on top, then DB suggestions (deduped).
    for (const it of recentItems) {
      if (it.gameName.toLowerCase().includes(q)) {
        const key = itemKey(it);
        if (!seen.has(key)) {
          seen.add(key);
          items.push(it);
        }
      }
    }
    for (const s of suggestions) {
      const it: SuggestionItem = {
        kind: "db",
        gameName: s.game_name,
        tagLine: s.tag_line ?? "",
        games: s.games,
      };
      const key = itemKey(it);
      if (!seen.has(key)) {
        seen.add(key);
        items.push(it);
      }
    }
    return items;
  }

  const items = open ? buildItems() : [];
  const hasItems = items.length > 0;
  const showRecentLabel = trimmedQuery.length < 2 && hasItems;

  // Run the real summoner search for an explicit name/tag/region (shared by the
  // form submit and selecting a suggestion).
  const runSearch = useCallback(
    async (name: string, tag: string, reg: string) => {
      if (!name || !tag) return;
      setOpen(false);
      setActiveIndex(-1);
      setLoading(true);
      setError(null);
      setResult(null);
      setSelected(false);

      try {
        const data = await searchSummoner(name, tag, reg);
        setResult(data);
        onResolved?.({ gameName: data.game_name, tagLine: data.tag_line, region: reg });
        setRecent(getRecentSearches());
      } catch (err) {
        if (err instanceof SummonerSearchError) {
          setError(messageForKind(err.kind, err.message));
        } else {
          setError("Something went wrong. Please try again.");
        }
      } finally {
        setLoading(false);
      }
    },
    [onResolved],
  );

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    void runSearch(gameName, tagLine, region);
  }

  // Pick a dropdown row: fill the input and run the search immediately. A recent
  // search also restores the region it was made on.
  function pickItem(item: SuggestionItem) {
    const riot = itemRiotId(item);
    setRiotId(riot);
    const reg = item.kind === "recent" && item.region ? item.region : region;
    if (item.kind === "recent" && item.region) setRegion(item.region);
    const parts = splitRiotId(riot);
    if (parts.gameName && parts.tagLine) {
      void runSearch(parts.gameName, parts.tagLine, reg);
    } else {
      // No tag yet (e.g. picked a DB name without a tag): keep the dropdown
      // closed and let the user add the tag, then Search.
      setOpen(false);
      setActiveIndex(-1);
      inputRef.current?.focus();
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setRiotId(e.target.value);
    setOpen(true);
    setActiveIndex(-1);
  }

  function handleInputFocus() {
    // Show recent searches (or current matches) on focus.
    setOpen(true);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      if (!open) {
        setOpen(true);
        return;
      }
      if (!hasItems) return;
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      if (!open || !hasItems) return;
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      // Only intercept Enter when a row is highlighted; otherwise let the form
      // submit normally.
      if (open && activeIndex >= 0 && activeIndex < items.length) {
        e.preventDefault();
        pickItem(items[activeIndex]);
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
        setActiveIndex(-1);
      }
    }
  }

  function handleSelect() {
    if (!result) return;
    setSelected(true);
    onSelect?.(result);
  }

  const activeOptionId =
    open && activeIndex >= 0 ? `${listboxId}-opt-${activeIndex}` : undefined;

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div ref={rootRef} className="relative">
          <label className="block">
            <span className="mb-1.5 block eyebrow">Riot ID</span>
            <span className="relative block">
              <svg
                viewBox="0 0 24 24"
                className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-dim"
                fill="none"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
                <path d="m20 20-3.2-3.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
              <input
                ref={inputRef}
                type="text"
                value={riotId}
                onChange={handleInputChange}
                onFocus={handleInputFocus}
                onKeyDown={handleKeyDown}
                placeholder="Name#TAG  (e.g. Faker#KR1)"
                autoComplete="off"
                role="combobox"
                aria-expanded={open && hasItems}
                aria-controls={listboxId}
                aria-autocomplete="list"
                aria-activedescendant={activeOptionId}
                className="field h-12 pl-10 font-medium"
              />
            </span>
            <span className="mt-1.5 block text-xs text-ink-muted">
              Start typing a name for suggestions, or enter the full Riot ID with
              the tag after the #.
            </span>
          </label>

          {open && hasItems && (
            <ul
              id={listboxId}
              role="listbox"
              aria-label="Player suggestions"
              className="absolute z-30 mt-1.5 max-h-72 w-full overflow-auto rounded-xl border border-line bg-surface shadow-card-hover backdrop-blur-sm"
            >
              {showRecentLabel && (
                <li
                  aria-hidden="true"
                  className="px-3.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-ink-dim"
                >
                  Recent searches
                </li>
              )}
              {items.map((item, idx) => {
                const isActive = idx === activeIndex;
                return (
                  <li
                    key={`${item.kind}-${itemKey(item)}`}
                    id={`${listboxId}-opt-${idx}`}
                    role="option"
                    aria-selected={isActive}
                    // onMouseDown (not onClick) so it fires before the input's
                    // blur closes the dropdown.
                    onMouseDown={(e) => {
                      e.preventDefault();
                      pickItem(item);
                    }}
                    onMouseEnter={() => setActiveIndex(idx)}
                    className={`flex cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5 text-sm transition-colors ${
                      isActive ? "bg-gold/10 text-ink" : "text-ink-soft"
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2.5">
                      {item.kind === "recent" ? (
                        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-ink-dim" fill="none" aria-hidden="true">
                          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
                          <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-ink-dim" fill="none" aria-hidden="true">
                          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.6" />
                          <path d="m20 20-3.2-3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                        </svg>
                      )}
                      <span className="min-w-0 truncate">
                        <span className="font-medium text-ink">{item.gameName}</span>
                        {item.tagLine && (
                          <span className="text-ink-dim">#{item.tagLine}</span>
                        )}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-ink-dim tabular-nums">
                      {item.kind === "recent"
                        ? "recent"
                        : item.games > 0
                          ? `${item.games.toLocaleString()} game${item.games === 1 ? "" : "s"}`
                          : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <label className="block">
          <span className="mb-1.5 block eyebrow">Region</span>
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="field h-12 cursor-pointer appearance-none bg-[length:1.1rem] bg-[right_0.9rem_center] bg-no-repeat pr-10"
            style={{
              backgroundImage:
                "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238A97AE' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E\")",
            }}
          >
            {REGIONS.map((r) => (
              <option key={r.value} value={r.value} className="bg-surface text-ink">
                {r.label}
              </option>
            ))}
          </select>
        </label>

        <button type="submit" disabled={!canSubmit} className="btn-primary w-full">
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              Searching…
            </>
          ) : (
            "Search player"
          )}
        </button>
      </form>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-team_red/40 bg-team_red/10 px-4 py-3 text-sm text-team_red-glow"
        >
          {error}
        </div>
      )}

      {result && (
        <div className="panel animate-fade-up flex items-center gap-4 p-4 sm:p-5">
          {result.profile_icon_id != null ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`https://ddragon.leagueoflegends.com/cdn/14.10.1/img/profileicon/${result.profile_icon_id}.png`}
              alt=""
              width={56}
              height={56}
              className="h-14 w-14 shrink-0 rounded-full bg-surface-2 ring-2 ring-gold/50"
            />
          ) : (
            <div className="h-14 w-14 shrink-0 rounded-full bg-surface-2 ring-2 ring-line" />
          )}
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-bold text-ink">
              {result.game_name}
              <span className="text-ink-dim">#{result.tag_line}</span>
            </p>
            <p className="text-sm text-ink-muted">
              {result.summoner_level != null
                ? `Level ${result.summoner_level}`
                : "Level unknown"}
              {" · "}
              {result.platform.toUpperCase()}
            </p>
          </div>
          <button
            type="button"
            onClick={handleSelect}
            className="btn-primary ml-auto shrink-0 px-5 py-2.5"
          >
            {selected ? "Selected ✓" : "View games"}
          </button>
        </div>
      )}
    </div>
  );
}
