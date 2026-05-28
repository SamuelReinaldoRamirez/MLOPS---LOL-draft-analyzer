"""
Database utilities for training scripts — PostgreSQL connection layer.
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import pandas as pd


def get_dsn(connect_timeout: int = 5) -> str:
    """Build PostgreSQL DSN from environment.

    ``connect_timeout`` (libpq standard, in seconds, default 5) bounds how long
    a connection attempt waits before failing — so callers degrade quickly when
    the DB is down/unreachable instead of blocking. It only affects the connect
    phase and is backward-compatible (every existing caller relied on the
    default DSN string). Pass ``0`` to restore the old unbounded behaviour.
    """
    dsn = (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'lol_draft')} "
        f"user={os.getenv('POSTGRES_USER', 'lol_admin')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'changeme')}"
    )
    if connect_timeout:
        dsn += f" connect_timeout={int(connect_timeout)}"
    return dsn


@contextmanager
def get_connection():
    """Context manager for a PostgreSQL connection."""
    conn = psycopg2.connect(get_dsn())
    try:
        yield conn
    finally:
        conn.close()


def read_sql(query: str, params=None) -> pd.DataFrame:
    """Execute query and return a DataFrame."""
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def fetchone(query: str, params=None):
    """Execute query and return one row."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()
