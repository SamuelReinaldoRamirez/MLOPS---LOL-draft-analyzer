/**
 * Recent player searches (localStorage).
 *
 * Stores the user's own past RESOLVED searches so the search screen can offer
 * them as quick suggestions when the input is empty/short and merge matching
 * ones above the live fuzzy results. Purely client-side — every accessor guards
 * against SSR (no `window`) and against malformed/blocked storage, returning a
 * safe default so the search page can never crash because of history.
 */

/** One stored search: a resolved Riot ID + the region it was looked up on. */
export interface RecentSearch {
  gameName: string;
  tagLine: string;
  region: string;
}

const STORAGE_KEY = "lol-draft:recent-searches";
/** Cap so the dropdown stays short and storage stays tiny. */
const MAX_RECENT = 8;

/** True only in a browser with a usable localStorage (guards SSR + privacy modes). */
function hasStorage(): boolean {
  try {
    return typeof window !== "undefined" && !!window.localStorage;
  } catch {
    return false;
  }
}

function normalize(entry: Partial<RecentSearch> | null | undefined): RecentSearch | null {
  if (!entry) return null;
  const gameName = (entry.gameName ?? "").trim();
  const tagLine = (entry.tagLine ?? "").trim();
  const region = (entry.region ?? "").trim();
  if (!gameName) return null;
  return { gameName, tagLine, region };
}

/** Case-insensitive identity for dedupe: same name#tag on the same region. */
function sameSearch(a: RecentSearch, b: RecentSearch): boolean {
  return (
    a.gameName.toLowerCase() === b.gameName.toLowerCase() &&
    a.tagLine.toLowerCase() === b.tagLine.toLowerCase() &&
    a.region.toLowerCase() === b.region.toLowerCase()
  );
}

/**
 * Read the saved searches, most-recent first. Returns `[]` on SSR, when storage
 * is empty/blocked, or when the stored value is malformed.
 */
export function getRecentSearches(): RecentSearch[] {
  if (!hasStorage()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((e) => normalize(e))
      .filter((e): e is RecentSearch => e !== null)
      .slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

/**
 * Save a resolved search to the front of the list (dedup, most-recent first,
 * capped at {@link MAX_RECENT}). No-op on SSR / blocked storage / blank name.
 * Returns the resulting list so callers can update state without a re-read.
 */
export function addRecentSearch(entry: Partial<RecentSearch>): RecentSearch[] {
  const next = normalize(entry);
  if (!next || !hasStorage()) return getRecentSearches();

  const existing = getRecentSearches().filter((e) => !sameSearch(e, next));
  const updated = [next, ...existing].slice(0, MAX_RECENT);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // Storage full / blocked: keep working, just don't persist.
  }
  return updated;
}

/** Clear all saved searches (no-op on SSR / blocked storage). */
export function clearRecentSearches(): void {
  if (!hasStorage()) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
