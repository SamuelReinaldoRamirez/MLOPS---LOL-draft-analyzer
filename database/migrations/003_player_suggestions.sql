-- ============================================================
-- 003_player_suggestions.sql
-- Fuzzy player-name autocomplete support for the /search screen.
--
-- Adds a trigram-indexed materialized view of the DISTINCT real player names
-- found in `player_stats` (~111k distinct riot_id_name values across ~3M rows),
-- so the API's GET /riot/suggest endpoint can return typo-tolerant suggestions
-- ranked by similarity + popularity WITHOUT scanning the 3M-row base table on
-- every keystroke.
--
-- IDEMPOTENT: safe to run more than once (IF NOT EXISTS everywhere).
--
-- Apply (running stack):
--   docker exec -i lol_draft_db psql -U lol_admin -d lol_draft \
--     < database/migrations/003_player_suggestions.sql
--
-- REFRESH (after re-importing / growing player_stats — rebuilds the view rows):
--   REFRESH MATERIALIZED VIEW player_name_suggestions;
--   -- or, once a unique index exists, CONCURRENTLY (non-blocking):
--   --   REFRESH MATERIALIZED VIEW CONCURRENTLY player_name_suggestions;
--
-- NOTE: building the view + GIN index over ~3M rows takes ~30-90s; that is a
-- one-off cost. The endpoint itself only ever touches the small materialized
-- view (~111k rows), so suggestions are fast.
-- ============================================================

-- Trigram similarity operators / functions (similarity(), %, gin_trgm_ops).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Distinct (name, tag) pairs with a per-pair game count used as a popularity
-- tie-breaker. Empty / null names are excluded at build time so the endpoint
-- never has to filter them out.
CREATE MATERIALIZED VIEW IF NOT EXISTS player_name_suggestions AS
SELECT
    riot_id_name,
    riot_id_tagline,
    count(*) AS games
FROM player_stats
WHERE riot_id_name IS NOT NULL
  AND riot_id_name <> ''
GROUP BY riot_id_name, riot_id_tagline;

-- GIN trigram index on lower(name) powers the fuzzy `%` / similarity() match.
-- Built on the lowercase expression so the endpoint can match case-insensitively
-- using the SAME expression (index is then actually used).
CREATE INDEX IF NOT EXISTS idx_pns_name_trgm
    ON player_name_suggestions
    USING gin (lower(riot_id_name) gin_trgm_ops);

-- B-tree on lower(name) accelerates the exact / prefix (LIKE 'q%') path and the
-- `lower(name) = lower(q)` exact-match ranking term.
CREATE INDEX IF NOT EXISTS idx_pns_name_lower
    ON player_name_suggestions (lower(riot_id_name));

-- Unique index over the grouped key — required for REFRESH ... CONCURRENTLY and
-- harmless otherwise (the GROUP BY guarantees uniqueness of (name, tag)).
CREATE UNIQUE INDEX IF NOT EXISTS idx_pns_name_tag_unique
    ON player_name_suggestions (riot_id_name, riot_id_tagline);
