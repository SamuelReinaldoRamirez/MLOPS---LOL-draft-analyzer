#!/bin/bash
# Restore the pg_dump into PostgreSQL on first boot.
# Mounted as a docker-entrypoint-initdb.d script — runs only when the DB is empty.

set -e

DUMP_FILE="/docker-entrypoint-initdb.d/lol_draft.dump"

if [ -f "$DUMP_FILE" ]; then
    echo "🔄 Restoring database from dump..."
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --no-owner --no-privileges --if-exists --clean \
        "$DUMP_FILE" 2>/dev/null || true
    echo "✅ Database restored successfully."
else
    echo "⚠️  No dump file found, starting with empty schema (init.sql)."
fi
