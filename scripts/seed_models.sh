#!/bin/bash
# ──────────────────────────────────────────
# Seed models from the original project into the Docker volume
# Run this ONCE after first `docker compose up -d`
# ──────────────────────────────────────────

set -euo pipefail

# Resolve paths relative to this script so it works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONTAINER="${API_CONTAINER:-lol_draft_api}"

fail() {
    echo "❌ $*" >&2
    exit 1
}

# ── Locate the source models directory ──────────────────────────────────────
# The original (source) project lives near this repo. We auto-detect it in
# order: an explicit SOURCE_MODELS_DIR, then the source project one level up
# (sibling layout), then two levels up (when this clean project is nested under
# e.g. MLOPS/MLOPS---LOL-draft-analyzer/). First match wins.
CANDIDATES=(
    ${SOURCE_MODELS_DIR:+"$SOURCE_MODELS_DIR"}
    "${PROJECT_DIR}/../datascientest-lol-draft_analyzer/models"
    "${PROJECT_DIR}/../../datascientest-lol-draft_analyzer/models"
)

SOURCE_DIR=""
for candidate in "${CANDIDATES[@]}"; do
    if [ -d "$candidate" ]; then
        SOURCE_DIR="$candidate"
        break
    fi
done

# ── 1. Source models directory must exist ───────────────────────────────────
if [ -z "$SOURCE_DIR" ]; then
    fail "Source models directory not found. Tried:
$(printf '       %s\n' "${CANDIDATES[@]}")
   Expected the original project at one of those locations, e.g.:
       <parent>/datascientest-lol-draft_analyzer/models/
   Fixes:
     - Clone/place the source project next to this repo, OR
     - Point SOURCE_MODELS_DIR at the models folder, e.g.:
         SOURCE_MODELS_DIR=/path/to/models ./scripts/seed_models.sh"
fi

# ── 2. There must be at least one model_*.pkl to copy ───────────────────────
shopt -s nullglob
model_files=("$SOURCE_DIR"/model_*.pkl)
shopt -u nullglob

if [ "${#model_files[@]}" -eq 0 ]; then
    fail "No model files found in: $SOURCE_DIR
   Expected files like: model_draft.pkl, model_at5.pkl, model_at10.pkl, ...
   The directory exists but contains no 'model_*.pkl' files."
fi

# ── 3. Docker + target container must be available ──────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    fail "'docker' command not found. Install Docker and start the stack first:
       docker compose up -d"
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    fail "Target container '$CONTAINER' is not running.
   Start the stack first:
       docker compose up -d
   Or override the container name:
       API_CONTAINER=<name> ./scripts/seed_models.sh"
fi

# ── 4. Copy the models ──────────────────────────────────────────────────────
echo "📦 Seeding ${#model_files[@]} model(s) into ${CONTAINER}:/app/models ..."

for model_file in "${model_files[@]}"; do
    filename="$(basename "$model_file")"
    echo "  → Copying $filename"
    docker cp "$model_file" "${CONTAINER}:/app/models/${filename}"
done

echo ""
echo "✅ Models seeded. Verify with:"
echo "   docker exec $CONTAINER ls -la /app/models/"
echo ""
echo "Restart services to pick up models:"
echo "   docker compose restart streamlit api"
