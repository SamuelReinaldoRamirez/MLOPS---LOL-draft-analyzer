#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DVC pipeline shim — runs `train_all_models.py` for a single timeline model
# (e.g. at5, at10, at15, at20) and ensures the resulting `.pkl` lands on the
# host so DVC can hash + version it.
#
# We bind-mount `./models` into the training container at /app/models — this
# overrides the compose-named volume `lol_draft_models` for THIS run only, so
# the existing `make demo` flow stays untouched.
#
# Usage (from dvc.yaml):    ./scripts/dvc_train.sh at10
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL="${1:-}"
if [[ -z "$MODEL" ]]; then
  echo "Usage: $0 <model>   # e.g. at5, at10, at15, at20" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${REPO_ROOT}/models"

# We delegate to docker compose so the training environment (Python + libs +
# DB connectivity) matches the compose stack exactly. `--build` is omitted: if
# the image is stale, run `make build` once.
docker compose -f "${REPO_ROOT}/docker-compose.yml" run --rm \
  -v "${REPO_ROOT}/models:/app/models" \
  -v "${REPO_ROOT}/params.yaml:/app/params.yaml:ro" \
  -e DVC_RUN=1 \
  training python scripts/train_all_models.py --model "$MODEL"

# Side-effect: train_all_models.py also writes models/metrics_at<minute>.json
# (a tiny JSON), tracked as a `metrics` output by dvc.yaml. If the file is
# missing (e.g. older training image), we synthesize a placeholder so DVC
# does not fail the stage.
METRICS_FILE="${REPO_ROOT}/models/metrics_${MODEL}.json"
if [[ ! -f "$METRICS_FILE" ]]; then
  echo '{"note":"metrics file not emitted by training (older image?)"}' > "$METRICS_FILE"
fi

echo "DVC stage done: model_${MODEL}.pkl + metrics_${MODEL}.json"
