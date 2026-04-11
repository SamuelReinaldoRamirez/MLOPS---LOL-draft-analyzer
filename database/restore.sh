#!/bin/bash
# Restore the pg_dump into PostgreSQL on first boot.
# Mounted as a docker-entrypoint-initdb.d script — runs only when the DB is empty.

set -euo pipefail

DUMP_FILE="/docker-entrypoint-initdb.d/lol_draft.dump"

if [ ! -f "$DUMP_FILE" ]; then
    echo "⚠️  No dump file found, starting with empty schema (init.sql)."
    exit 0
fi

DUMP_SIZE=$(stat -c%s "$DUMP_FILE")
echo "🔄 Restoring database from dump (${DUMP_SIZE} bytes)..."

pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --no-owner --no-privileges --if-exists --clean --verbose \
    "$DUMP_FILE"

echo "✅ Database restored successfully."
