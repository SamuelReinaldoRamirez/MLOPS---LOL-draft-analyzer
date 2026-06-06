/**
 * Champion list bundled from the API's `champion_id_map.json`.
 *
 * This is a static, build-time copy of `api/app/champion_id_map.json` so the
 * draft pickers do not depend on the API being reachable just to populate the
 * dropdowns. We derive a sorted list of unique Data-Dragon display names —
 * exactly the names the API's draft endpoint resolves against.
 */
import championIdMap from "./champion_id_map.json";

type ChampionEntry = { id: number; name: string };

const map = championIdMap as Record<string, ChampionEntry>;

/** Sorted, de-duplicated list of champion display names (e.g. "Lee Sin"). */
export const CHAMPION_NAMES: string[] = Array.from(
  new Set(Object.values(map).map((c) => c.name)),
).sort((a, b) => a.localeCompare(b));

/**
 * Normalise a champion name the SAME way the API does
 * (`api/app/main.py::_normalize_champion_name`): lower-case then strip every
 * non-alphanumeric char. So "fiora", "Fiora ", "Miss Fortune" and "missfortune"
 * all collapse to the same key. Keeping this in lock-step with the API means the
 * front never rejects a value the API would happily resolve.
 */
function normalizeName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Normalised key -> canonical Data-Dragon name (e.g. "fiora" -> "Fiora"). */
const NORMALIZED_TO_CANONICAL = new Map<string, string>(
  CHAMPION_NAMES.map((n) => [normalizeName(n), n]),
);

/**
 * Resolve a possibly-messy input (any case / spacing) to the canonical champion
 * name, or null if it isn't a real champion.
 */
export function canonicalChampion(name: string): string | null {
  return NORMALIZED_TO_CANONICAL.get(normalizeName(name)) ?? null;
}

/** Case/spacing-insensitive membership check — mirrors the API's tolerance. */
export function isValidChampion(name: string): boolean {
  return NORMALIZED_TO_CANONICAL.has(normalizeName(name));
}

/** Display name (e.g. "Lee Sin") -> Riot champion numeric id, for icons. */
const NAME_TO_ID = new Map<string, number>(
  Object.values(map).map((c) => [c.name, c.id]),
);

/** Resolve a champion name (any case/spacing) to its numeric Riot id (or null). */
export function championIdByName(name: string): number | null {
  const canonical = canonicalChampion(name);
  return canonical ? NAME_TO_ID.get(canonical) ?? null : null;
}

/**
 * Square champion portrait URL for a display name, resolved via the numeric
 * id (Community Dragon). Returns null for an unknown name so callers can render
 * a placeholder. Name-casing-proof, unlike Data-Dragon's filename-by-key.
 */
export function championPortraitByName(name: string): string | null {
  const id = championIdByName(name);
  if (id == null) return null;
  return `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/${id}.png`;
}

/**
 * Square champion icon by Data-Dragon key — the champion-name form the API
 * returns in match/live drafts (e.g. "LeeSin", "MissFortune").
 */
export function championIconByKey(key: string): string {
  return `https://ddragon.leagueoflegends.com/cdn/14.10.1/img/champion/${key}.png`;
}
