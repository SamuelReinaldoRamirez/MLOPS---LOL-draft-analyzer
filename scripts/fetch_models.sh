#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Fetch the trained models from DagsHub so `make demo` works on ANY machine.
#
# The 5 model_*.pkl (~14.5 MB) are DVC-tracked and hosted on the project's
# DagsHub DVC remote (NOT committed to git). This script pulls them via DVC into
# api/models/, from where scripts/seed_models.sh seeds them into the compose
# volume. model_draft.pkl in particular is NOT reproducible from this repo's
# training code, so it can only be shipped as a binary artefact.
#
# Idempotent: if the 5 .pkl are already present it does nothing. DVC verifies
# each file's md5 against its .dvc pointer, so a partial/corrupt pull never
# leaves a bad file in place. Auth comes from .dvc/config (the DagsHub remote).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_DIR"

MODELS=(model_draft model_at5 model_at10 model_at15 model_at20)
POINTERS=()
missing=0
for m in "${MODELS[@]}"; do
    POINTERS+=("api/models/${m}.pkl.dvc")
    [ -f "api/models/${m}.pkl" ] || missing=1
done

# Already present? Nothing to do.
if [ "$missing" -eq 0 ]; then
    echo "✅ Models already present in api/models/"
    exit 0
fi

# DVC is required to pull. Install it on demand so a fresh clone is turnkey.
if ! command -v dvc >/dev/null 2>&1; then
    echo "ℹ️  DVC not found — installing it (pip) ..."
    pip install --quiet 'dvc>=3.0,<4.0' || {
        echo "❌ Could not install DVC. Install it manually then re-run:"
        echo "     pip install 'dvc>=3.0,<4.0' && make fetch-models"
        exit 1
    }
fi

echo "⬇️  Pulling models from DagsHub (DVC) ..."
dvc pull "${POINTERS[@]}"

echo "✅ Models fetched into api/models/"
