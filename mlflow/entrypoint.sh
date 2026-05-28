#!/bin/bash
##############################################################################
# MLflow tracking server entrypoint.
#
# Backend store : PostgreSQL (reuses the existing `postgres` service, in a
#                 dedicated `mlflow` database created here on first boot).
# Artifact store: local volume mounted at /mlflow/artifacts.
#
# The `mlflow` database is created idempotently so we never need to touch the
# database/ image init scripts (which live outside this Phase-2 slice).
##############################################################################
set -euo pipefail

PGHOST="${POSTGRES_HOST:-postgres}"
PGPORT="${POSTGRES_PORT:-5432}"
PGUSER="${POSTGRES_USER:-lol_admin}"
PGPASSWORD="${POSTGRES_PASSWORD:-changeme}"
MLFLOW_DB="${MLFLOW_DB:-mlflow}"
ARTIFACT_ROOT="${MLFLOW_ARTIFACT_ROOT:-/mlflow/artifacts}"
export PGPASSWORD

echo "⏳ Waiting for PostgreSQL at ${PGHOST}:${PGPORT}..."
until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
    sleep 2
done
echo "✅ PostgreSQL is ready."

# Create the mlflow database if it does not already exist (idempotent).
if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${MLFLOW_DB}'" | grep -q 1; then
    echo "🆕 Creating database '${MLFLOW_DB}'..."
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
        -c "CREATE DATABASE ${MLFLOW_DB}"
else
    echo "ℹ️  Database '${MLFLOW_DB}' already exists."
fi

BACKEND_URI="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${MLFLOW_DB}"

mkdir -p "$ARTIFACT_ROOT"

echo "🚀 Starting MLflow tracking server on :5000"
exec mlflow server \
    --host 0.0.0.0 \
    --port 5000 \
    --backend-store-uri "$BACKEND_URI" \
    --artifacts-destination "$ARTIFACT_ROOT" \
    --serve-artifacts
