#!/usr/bin/env python3
"""
Migrate SQLite (lol_matches.db) → PostgreSQL for LOL Draft Analyzer.

Usage:
    pip install psycopg2-binary
    python migrate_sqlite_to_postgres.py --sqlite-path /path/to/lol_matches.db

Environment variables (or .env file):
    POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT
"""

import sqlite3
import os
import sys
import argparse
import time


def load_env(env_path=".env"):
    """Load .env file into os.environ if it exists."""
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def get_pg_config():
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5434")),
        "database": os.environ.get("POSTGRES_DB", "lol_draft"),
        "user": os.environ.get("POSTGRES_USER", "lol_admin"),
        "password": os.environ.get("POSTGRES_PASSWORD", "lol_draft_2025"),
    }


# Tables in FK-safe order
MIGRATION_ORDER = [
    "matches",
    "team_stats",
    "summoners",
    "player_stats",
    "patches",
    "champion_patch_stats",
    "champion_mastery",
    "match_timeline",
    "match_events",
    "champion_synergies",
    "champion_matchups",
    "collection_progress",
    "collection_stats",
    "summoner_elo_history",
    "summoner_role_stats",
]

# Tables with SERIAL id (skip SQLite's rowid)
SERIAL_TABLES = {
    "team_stats", "player_stats", "collection_progress",
    "summoner_elo_history", "champion_mastery", "champion_patch_stats",
    "match_timeline", "match_events", "champion_synergies",
    "champion_matchups", "summoner_role_stats",
}


def get_columns(sqlite_cur, table):
    sqlite_cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in sqlite_cur.fetchall()]
    if table in SERIAL_TABLES and "id" in cols:
        cols.remove("id")
    return cols


def migrate_table(sqlite_cur, pg_conn, table, batch_size):
    import psycopg2

    sqlite_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    if not sqlite_cur.fetchone():
        print(f"  ⏭  {table}: not in SQLite, skip")
        return 0

    columns = get_columns(sqlite_cur, table)
    sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
    total = sqlite_cur.fetchone()[0]
    if total == 0:
        print(f"  ⏭  {table}: empty, skip")
        return 0

    print(f"  📦 {table}: {total:,} rows")

    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    sqlite_cur.execute(f"SELECT {col_list} FROM {table}")
    migrated = 0
    t0 = time.time()

    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break
        try:
            cur = pg_conn.cursor()
            cur.executemany(sql, rows)
            pg_conn.commit()
            cur.close()
            migrated += len(rows)
        except psycopg2.Error as e:
            pg_conn.rollback()
            print(f"\n  ⚠️  Error on {table}: {str(e).splitlines()[0]}")
            # row-by-row fallback
            for row in rows:
                try:
                    cur = pg_conn.cursor()
                    cur.execute(sql, row)
                    pg_conn.commit()
                    cur.close()
                    migrated += 1
                except psycopg2.Error:
                    pg_conn.rollback()

        elapsed = time.time() - t0
        rate = migrated / elapsed if elapsed > 0 else 0
        pct = migrated / total * 100
        print(f"     {migrated:,}/{total:,} ({pct:.1f}%) {rate:.0f} rows/s   ", end="\r")

    elapsed = time.time() - t0
    print(f"     ✅ {migrated:,} rows in {elapsed:.1f}s                      ")
    return migrated


def reset_sequences(pg_conn):
    cur = pg_conn.cursor()
    for table in SERIAL_TABLES:
        try:
            cur.execute(f"""
                SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                       COALESCE((SELECT MAX(id) FROM {table}), 1))
            """)
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()
    cur.close()


def main():
    load_env()

    parser = argparse.ArgumentParser(
        description="Migrate lol_matches.db (SQLite) → PostgreSQL"
    )
    parser.add_argument(
        "--sqlite-path", required=True,
        help="Path to lol_matches.db"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10000,
        help="Insert batch size (default: 10000)"
    )
    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    if not os.path.exists(args.sqlite_path):
        print(f"❌ SQLite file not found: {args.sqlite_path}")
        sys.exit(1)

    pg_cfg = get_pg_config()
    print(f"📂 Source:  {args.sqlite_path}")
    print(f"🐘 Target:  {pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['database']}")
    print()

    sqlite_conn = sqlite3.connect(args.sqlite_path)
    sqlite_cur = sqlite_conn.cursor()

    try:
        pg_conn = psycopg2.connect(**pg_cfg)
    except Exception as e:
        print(f"❌ Cannot connect to PostgreSQL: {e}")
        print("   Make sure the container is running: docker compose up -d")
        sys.exit(1)

    print("✅ Connected\n")

    total = 0
    t0 = time.time()

    for table in MIGRATION_ORDER:
        try:
            total += migrate_table(sqlite_cur, pg_conn, table, args.batch_size)
        except Exception as e:
            print(f"  ❌ {table} failed: {e}")
            try:
                pg_conn.close()
            except Exception:
                pass
            pg_conn = psycopg2.connect(**pg_cfg)

    print("\n🔄 Resetting sequences...")
    reset_sequences(pg_conn)

    elapsed = time.time() - t0
    print(f"\n{'=' * 50}")
    print(f"✅ Migration complete!")
    print(f"   {total:,} rows migrated in {elapsed / 60:.1f} min")
    print(f"{'=' * 50}")

    # Verify
    print("\n📊 Verification:")
    cur = pg_conn.cursor()
    for table in MIGRATION_ORDER:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg_n = cur.fetchone()[0]
            sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
            sq_n = sqlite_cur.fetchone()[0]
            ok = "✅" if pg_n == sq_n else f"⚠️  (SQLite: {sq_n:,})"
            print(f"   {table}: {pg_n:,} {ok}")
        except Exception:
            print(f"   {table}: skip")
    cur.close()
    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
