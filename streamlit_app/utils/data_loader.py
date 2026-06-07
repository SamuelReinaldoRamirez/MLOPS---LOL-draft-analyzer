"""
Data loading utilities with Streamlit caching.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "collect_data"))

from config import DATABASE_PATH, PROJECT_ROOT

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@st.cache_data(ttl=3600)
def load_match_data(limit: int = None) -> pd.DataFrame:
    """
    Load match data from SQLite database.

    Args:
        limit: Optional limit on number of matches to load

    Returns:
        DataFrame with match data
    """
    from database import MatchDatabase

    db = MatchDatabase(str(DATABASE_PATH))
    df = db.export_to_dataframe()

    if limit:
        df = df.head(limit)

    return df


@st.cache_data(ttl=3600)
def get_match_count() -> int:
    """Get total number of matches in database."""
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM matches")
    count = cursor.fetchone()[0]
    conn.close()
    return count


@st.cache_data(ttl=3600)
def get_timeline_match_count() -> int:
    """Get number of matches with timeline data."""
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT match_id) FROM match_timeline")
    count = cursor.fetchone()[0]
    conn.close()
    return count


@st.cache_data(ttl=3600)
def load_timeline_data(match_id: str) -> pd.DataFrame:
    """
    Load timeline data for a specific match.

    Args:
        match_id: Match ID to load timeline for

    Returns:
        DataFrame with minute-by-minute timeline data
    """
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    query = """
        SELECT * FROM match_timeline
        WHERE match_id = ?
        ORDER BY minute
    """
    df = pd.read_sql_query(query, conn, params=(match_id,))
    conn.close()
    return df


@st.cache_data(ttl=3600)
def get_sample_matches(n: int = 100) -> pd.DataFrame:
    """
    Get a sample of matches for display.

    Args:
        n: Number of matches to sample

    Returns:
        DataFrame with sample matches
    """
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    query = f"""
        SELECT
            m.match_id,
            m.game_duration,
            m.game_version,
            m.team_100_win,
            m.source_elo,
            m.collected_at
        FROM matches m
        ORDER BY m.collected_at DESC
        LIMIT {n}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


@st.cache_data(ttl=3600)
def get_matches_with_timeline(limit: int = 1000) -> pd.DataFrame:
    """
    Get matches that have timeline data available.

    Args:
        limit: Maximum number of matches to return

    Returns:
        DataFrame with matches that have timeline data
    """
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    query = f"""
        SELECT DISTINCT
            m.match_id,
            m.game_duration,
            m.game_version,
            m.team_100_win,
            m.source_elo,
            m.collected_at,
            (SELECT gold_diff FROM match_timeline
             WHERE match_id = m.match_id AND minute = 10
             LIMIT 1) as gold_diff_at_10
        FROM matches m
        INNER JOIN match_timeline mt ON m.match_id = mt.match_id
        WHERE m.game_duration >= 600
        ORDER BY m.collected_at DESC
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


@st.cache_data(ttl=3600)
def get_match_details(match_id: str) -> dict:
    """
    Get full details for a specific match.

    Args:
        match_id: Match ID

    Returns:
        Dict with match details including player stats
    """
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get match info
    cursor.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,))
    match_row = cursor.fetchone()
    if not match_row:
        conn.close()
        return None

    match_info = dict(match_row)

    # Get team stats
    cursor.execute("SELECT * FROM team_stats WHERE match_id = ?", (match_id,))
    team_stats = [dict(row) for row in cursor.fetchall()]
    match_info["team_stats"] = {ts["team_id"]: ts for ts in team_stats}

    # Get player stats
    cursor.execute("SELECT * FROM player_stats WHERE match_id = ? ORDER BY team_id, position", (match_id,))
    player_stats = [dict(row) for row in cursor.fetchall()]
    match_info["players"] = player_stats

    # Get timeline if available
    cursor.execute("SELECT * FROM match_timeline WHERE match_id = ? ORDER BY minute", (match_id,))
    timeline = [dict(row) for row in cursor.fetchall()]
    match_info["timeline"] = timeline

    conn.close()
    return match_info


@st.cache_data(ttl=3600)
def get_winrate_by_side() -> dict:
    """Get win rate statistics by side (blue vs red)."""
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN team_100_win = 1 THEN 1 ELSE 0 END) as blue_wins
        FROM matches
    """)
    row = cursor.fetchone()
    conn.close()

    total = row[0] if row[0] else 1
    blue_wins = row[1] if row[1] else 0

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
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT AVG(game_duration) FROM matches WHERE game_duration > 0")
    avg_duration = cursor.fetchone()[0]
    conn.close()
    return (avg_duration or 0) / 60  # Convert to minutes


# =============================================================================
# NEW DATA LOADERS (parquet-based)
# =============================================================================

@st.cache_data(ttl=3600)
def load_test_with_summoner() -> pd.DataFrame:
    """Load the test set with summoner stats from parquet."""
    path = PROCESSED_DIR / "test_with_summoner_stats.parquet"
    if not path.exists():
        st.error(f"Fichier introuvable : {path}")
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data(ttl=3600)
def load_train_with_summoner() -> pd.DataFrame:
    """Load the train set with summoner stats from parquet."""
    path = PROCESSED_DIR / "train_with_summoner_stats.parquet"
    if not path.exists():
        st.error(f"Fichier introuvable : {path}")
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data(ttl=3600)
def load_timeline_data_parquet() -> pd.DataFrame:
    """Load multi-timestamp timeline data from parquet."""
    path = PROCESSED_DIR / "matches_with_multi_timeline.parquet"
    if not path.exists():
        st.error(f"Fichier introuvable : {path}")
        return pd.DataFrame()
    return pd.read_parquet(path)


# =============================================================================
# V3 DATA LOADERS (temporal summoner stats)
# =============================================================================

@st.cache_data(ttl=3600)
def load_train_temporal_stats() -> pd.DataFrame:
    """Load the train set with temporal summoner stats from parquet."""
    path = PROCESSED_DIR / "train_temporal_stats.parquet"
    if not path.exists():
        st.warning(f"V3 train parquet introuvable : {path}, fallback to V2")
        return load_train_with_summoner()
    return pd.read_parquet(path)


@st.cache_data(ttl=3600)
def load_test_temporal_stats() -> pd.DataFrame:
    """Load the test set with temporal summoner stats from parquet."""
    path = PROCESSED_DIR / "test_temporal_stats.parquet"
    if not path.exists():
        st.warning(f"V3 test parquet introuvable : {path}, fallback to V2")
        return load_test_with_summoner()
    return pd.read_parquet(path)


@st.cache_data(ttl=3600)
def get_database_tables_info() -> dict:
    """Get info about all tables in the database (name, row count, columns)."""
    import sqlite3

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    info = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
        count = cursor.fetchone()[0]
        cursor.execute(f"PRAGMA table_info([{table}])")
        columns = [row[1] for row in cursor.fetchall()]
        info[table] = {"row_count": count, "columns": columns}

    conn.close()
    return info
