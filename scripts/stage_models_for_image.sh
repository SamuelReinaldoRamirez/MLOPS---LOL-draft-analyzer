#!/bin/bash
# ──────────────────────────────────────────
# Stage models into the API build context so they get baked into the image.
# Run this BEFORE `docker build` / a PaaS build that has no docker volume.
# Copies model_*.pkl from the source project into api/models/, where the
# api/Dockerfile `COPY models/ /app/models/` step bakes them to /app/models.
# ──────────────────────────────────────────

set -euo pipefail

# Resolve paths relative to this script so it works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Destination: the API build context. api/Dockerfile COPYs this into /app/models.
DEST_DIR="${PROJECT_DIR}/api/models"

fail() {
    echo "❌ $*" >&2
    exit 1
}

# ── Locate the source models directory ──────────────────────────────────────
# Same detection order as scripts/seed_models.sh: an explicit SOURCE_MODELS_DIR,
# then the source project one level up (sibling layout), then two levels up
# (when this clean project is nested under e.g.
# MLOPS/MLOPS---LOL-draft-analyzer/). First match wins.
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
         SOURCE_MODELS_DIR=/path/to/models ./scripts/stage_models_for_image.sh"
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

# ── 3. Stage the models into the API build context ──────────────────────────
mkdir -p "$DEST_DIR"

echo "📦 Staging ${#model_files[@]} model(s) into ${DEST_DIR}/ for image bake ..."

for model_file in "${model_files[@]}"; do
    filename="$(basename "$model_file")"
    echo "  → Copying $filename"
    cp "$model_file" "${DEST_DIR}/${filename}"
done

echo ""
echo "✅ Staged ${#model_files[@]} model(s) into api/models/ (gitignored)."
echo "   They will be baked to /app/models by api/Dockerfile on the next build."
echo ""
echo "Next: build the API image (locally the docker-compose volume still wins):"
echo "   docker build -t lol-draft-api ./api"
echo "   # or on the PaaS, point the build at api/Dockerfile"
