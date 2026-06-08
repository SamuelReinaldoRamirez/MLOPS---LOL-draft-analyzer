"""
Data loading utilities with Streamlit caching.

PRODUCTION/MLOPS variant: reads match data from the PostgreSQL database that the
MLOPS stack already provisions (same data as the original SQLite `lol_matches.db`
— identical tables/rows), so the multi-page app is reproducible via `make demo`
with no extra multi-GB SQLite file. Parquet-backed pages use bundled *sample*
parquets under streamlit_app/sample_data/.

Connection comes from the standard POSTGRES_* env vars (defaults match the
docker-compose service). DB helpers degrade gracefully (return empty/zero) if the
DB is unreachable, so the static pages still render anywhere.
"""
import os
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
import streamlit as st

# Bundled sample parquets (committed) so the parquet pages work reproducibly.
SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def _conn():
    """psycopg2 connection to the MLOPS Postgres (env-driven, compose defaults)."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "lol_draft"),
        user=os.getenv("POSTGRES_USER", "lol_admin"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def _query_df(sql: str, params=None) -> pd.DataFrame:
    """Run a query and return a DataFrame; empty DataFrame on any DB error."""
    try:
        with _conn() as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully for static pages
        st.warning(f"Base de données indisponible : {exc}")
        return pd.DataFrame()


def _scalar(sql: str, params=None, default=0):
    """Run a query returning a single scalar; `default` on any DB error."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else default
    except Exception:  # noqa: BLE001
        return default


@st.cache_data(ttl=3600)
def load_match_data(limit: int = None) -> pd.DataFrame:
    """Load match rows (optionally limited)."""
    sql = "SELECT * FROM matches ORDER BY collected_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return _query_df(sql)


@st.cache_data(ttl=3600)
def get_match_count() -> int:
    """Total number of matches."""
    return int(_scalar("SELECT COUNT(*) FROM matches"))


@st.cache_data(ttl=3600)
def get_timeline_match_count() -> int:
    """Number of distinct matches that have timeline data."""
    return int(_scalar("SELECT COUNT(DISTINCT match_id) FROM match_timeline"))


@st.cache_data(ttl=3600)
def load_timeline_data(match_id: str) -> pd.DataFrame:
    """Minute-by-minute timeline for a match."""
    return _query_df(
        "SELECT * FROM match_timeline WHERE match_id = %s ORDER BY minute",
        params=(match_id,),
    )


@st.cache_data(ttl=3600)
def get_sample_matches(n: int = 100) -> pd.DataFrame:
    """A sample of recent matches for display."""
    return _query_df(
        """
        SELECT m.match_id, m.game_duration, m.game_version,
               m.team_100_win, m.source_elo, m.collected_at
        FROM matches m
        ORDER BY m.collected_at DESC
        LIMIT %s
        """,
        params=(int(n),),
    )


@st.cache_data(ttl=3600)
def get_matches_with_timeline(limit: int = 1000) -> pd.DataFrame:
    """Matches that have timeline data, with their gold diff at minute 10."""
    return _query_df(
        """
        SELECT DISTINCT
            m.match_id, m.game_duration, m.game_version,
            m.team_100_win, m.source_elo, m.collected_at,
            (SELECT gold_diff FROM match_timeline
             WHERE match_id = m.match_id AND minute = 10 LIMIT 1) AS gold_diff_at_10
        FROM matches m
        INNER JOIN match_timeline mt ON m.match_id = mt.match_id
        WHERE m.game_duration >= 600
        ORDER BY m.collected_at DESC
        LIMIT %s
        """,
        params=(int(limit),),
    )


@st.cache_data(ttl=3600)
def get_match_details(match_id: str) -> dict:
    """Full details for a match: info + team_stats + players + timeline."""
    try:
        with _conn() as conn, conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute("SELECT * FROM matches WHERE match_id = %s", (match_id,))
            match_row = cur.fetchone()
            if not match_row:
                return None
            match_info = dict(match_row)

            cur.execute("SELECT * FROM team_stats WHERE match_id = %s", (match_id,))
            team_stats = [dict(r) for r in cur.fetchall()]
            match_info["team_stats"] = {ts["team_id"]: ts for ts in team_stats}

            cur.execute(
                "SELECT * FROM player_stats WHERE match_id = %s ORDER BY team_id, position",
                (match_id,),
            )
            match_info["players"] = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT * FROM match_timeline WHERE match_id = %s ORDER BY minute",
                (match_id,),
            )
            match_info["timeline"] = [dict(r) for r in cur.fetchall()]
            return match_info
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Base de données indisponible : {exc}")
        return None


@st.cache_data(ttl=3600)
def get_winrate_by_side() -> dict:
    """Win rate by side (blue = team 100, stored as smallint 0/1)."""
    df = _query_df(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN team_100_win::int = 1 THEN 1 ELSE 0 END) AS blue_wins
        FROM matches
        """
    )
    total = int(df["total"].iloc[0]) if not df.empty and df["total"].iloc[0] else 1
    blue_wins = int(df["blue_wins"].iloc[0]) if not df.empty and df["blue_wins"].iloc[0] else 0
    return {
        "total_matches": total,
        "blue_wins": blue_wins,
        "red_wins": total - blue_wins,
        "blue_winrate": blue_wins / total,
        "red_winrate": (total - blue_wins) / total,
    }


@st.cache_data(ttl=3600)
def get_average_game_duration() -> float:
    """Average game duration in minutes."""
    avg = _scalar("SELECT AVG(game_duration) FROM matches WHERE game_duration > 0", default=0)
    return (float(avg) or 0) / 60


# =============================================================================
# Parquet-backed loaders — use bundled *sample* parquets (reproducible).
# =============================================================================

def _read_sample(filename: str) -> pd.DataFrame:
    path = SAMPLE_DIR / filename
    if not path.exists():
        st.info(f"Échantillon parquet absent : {path.name} (données réduites).")
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data(ttl=3600)
def load_test_with_summoner() -> pd.DataFrame:
    return _read_sample("test_with_summoner_stats.parquet")


@st.cache_data(ttl=3600)
def load_train_with_summoner() -> pd.DataFrame:
    return _read_sample("train_with_summoner_stats.parquet")


@st.cache_data(ttl=3600)
def load_timeline_data_parquet() -> pd.DataFrame:
    return _read_sample("matches_with_multi_timeline.parquet")


@st.cache_data(ttl=3600)
def load_train_temporal_stats() -> pd.DataFrame:
    # No temporal sample bundled — fall back to the with-summoner sample.
    return load_train_with_summoner()


@st.cache_data(ttl=3600)
def load_test_temporal_stats() -> pd.DataFrame:
    return load_test_with_summoner()


@st.cache_data(ttl=3600)
def get_database_tables_info() -> dict:
    """Per-table row count + columns, via Postgres information_schema."""
    info: dict = {}
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
                """
            )
            tables = [r[0] for r in cur.fetchall()]
            for table in tables:
                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                count = cur.fetchone()[0]
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = %s ORDER BY ordinal_position
                    """,
                    (table,),
                )
                columns = [r[0] for r in cur.fetchall()]
                info[table] = {"row_count": count, "columns": columns}
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Base de données indisponible : {exc}")
    return info
