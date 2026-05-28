"""
Data loading utilities with Streamlit caching — PostgreSQL version.
"""

import pandas as pd
import streamlit as st

from db_utils import get_connection, fetchone, fetchall_dict


@st.cache_data(ttl=3600)
def get_match_count() -> int:
    """Get total number of matches in database."""
    row = fetchone("SELECT COUNT(*) FROM matches")
    return row[0] if row else 0


@st.cache_data(ttl=3600)
def get_timeline_match_count() -> int:
    """Get number of matches with timeline data."""
    row = fetchone("SELECT COUNT(DISTINCT match_id) FROM match_timeline")
    return row[0] if row else 0


@st.cache_data(ttl=3600)
def get_winrate_by_side() -> dict:
    """Get win rate statistics by side (blue vs red)."""
    row = fetchone("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN team_100_win = true THEN 1 ELSE 0 END) as blue_wins
        FROM matches
    """)
    total = row[0] if row and row[0] else 1
    blue_wins = row[1] if row and row[1] else 0

    return {
        "total_matches": total,
        "blue_wins": blue_wins,
        "red_wins": total - blue_wins,
        "blue_winrate": blue_wins / total,
        "red_winrate": (total - blue_wins) / total,
    }


@st.cache_data(ttl=3600)
def get_average_game_duration() -> float:
    """Get average game duration in minutes."""
    row = fetchone("SELECT AVG(game_duration) FROM matches WHERE game_duration > 0")
    return (row[0] or 0) / 60


@st.cache_data(ttl=3600)
def get_sample_matches(n: int = 100) -> pd.DataFrame:
    """Get a sample of recent matches."""
    with get_connection() as conn:
        query = f"""
            SELECT
                match_id, game_duration, game_version,
                team_100_win, source_elo, collected_at
            FROM matches
            ORDER BY collected_at DESC
            LIMIT {n}
        """
        return pd.read_sql_query(query, conn)


@st.cache_data(ttl=3600)
def get_match_details(match_id: str) -> dict:
    """Get full details for a specific match."""
    from db_utils import fetchall_dict as fad

    match_rows = fad("SELECT * FROM matches WHERE match_id = %s", (match_id,))
    if not match_rows:
        return None

    match_info = dict(match_rows[0])

    team_rows = fad("SELECT * FROM team_stats WHERE match_id = %s", (match_id,))
    match_info["team_stats"] = {r["team_id"]: dict(r) for r in team_rows}

    player_rows = fad(
        "SELECT * FROM player_stats WHERE match_id = %s ORDER BY team_id, position",
        (match_id,),
    )
    match_info["players"] = [dict(r) for r in player_rows]

    timeline_rows = fad(
        "SELECT * FROM match_timeline WHERE match_id = %s ORDER BY minute",
        (match_id,),
    )
    match_info["timeline"] = [dict(r) for r in timeline_rows]

    return match_info


@st.cache_data(ttl=3600)
def load_timeline_data(match_id: str) -> pd.DataFrame:
    """Load timeline data for a specific match."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM match_timeline WHERE match_id = %s ORDER BY minute",
            conn,
            params=(match_id,),
        )


@st.cache_data(ttl=3600)
def get_matches_with_timeline(limit: int = 1000) -> pd.DataFrame:
    """Get matches that have timeline data available."""
    with get_connection() as conn:
        query = f"""
            SELECT DISTINCT
                m.match_id, m.game_duration, m.game_version,
                m.team_100_win, m.source_elo, m.collected_at,
                (SELECT gold_diff FROM match_timeline
                 WHERE match_id = m.match_id AND minute = 10
                 LIMIT 1) as gold_diff_at_10
            FROM matches m
            INNER JOIN match_timeline mt ON m.match_id = mt.match_id
            WHERE m.game_duration >= 600
            ORDER BY m.collected_at DESC
            LIMIT {limit}
        """
        return pd.read_sql_query(query, conn)


@st.cache_data(ttl=3600)
def get_database_tables_info() -> dict:
    """Get info about all tables in the database."""
    rows = fetchall_dict("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    info = {}
    for row in rows:
        table = row["table_name"]
        count_row = fetchone(f'SELECT COUNT(*) FROM "{table}"')
        col_rows = fetchall_dict(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        info[table] = {
            "row_count": count_row[0] if count_row else 0,
            "columns": [c["column_name"] for c in col_rows],
        }
    return info
