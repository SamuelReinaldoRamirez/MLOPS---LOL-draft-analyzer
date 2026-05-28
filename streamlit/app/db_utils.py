"""
Database utilities — PostgreSQL connection layer.

Replaces SQLite calls from the original project with PostgreSQL
using psycopg2.  Reads connection parameters from environment variables
set in docker-compose.
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def get_dsn() -> str:
    """Build PostgreSQL DSN from environment."""
    return (
        f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'lol_draft')} "
        f"user={os.getenv('POSTGRES_USER', 'lol_admin')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'changeme')}"
    )


@contextmanager
def get_connection():
    """Context manager for a PostgreSQL connection."""
    conn = psycopg2.connect(get_dsn())
    try:
        yield conn
    finally:
        conn.close()


def fetchone(query: str, params=None):
    """Execute query and return one row."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetchall(query: str, params=None):
    """Execute query and return all rows."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetchall_dict(query: str, params=None):
    """Execute query and return list of dicts."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()
