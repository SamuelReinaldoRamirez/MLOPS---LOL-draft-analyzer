#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Compute a drift report and PUSH its summary to the production Pushgateway, so
# the drift metric shows up in Prometheus -> Grafana (prod monitoring stack).
#
# The drift computation runs in the `training` Docker image (it has Evidently);
# the resulting monitoring/drift/reports/drift_summary.json is parsed and pushed
# as Prometheus gauges. Any args are forwarded to drift_report.py
# (e.g. `--drift` to force a drifted current set for a demo).
#
#   ./scripts/push_drift.sh              # normal (low/no drift)
#   ./scripts/push_drift.sh --drift      # simulate drift (share -> high)
#
# Override the target with PUSHGATEWAY_URL=... and the threshold with
# DRIFT_THRESHOLD=... (defaults mirror scripts/auto_retrain.py).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_DIR"

PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-https://lol-draft-pushgateway.fly.dev}"
THRESHOLD="${DRIFT_THRESHOLD:-0.5}"
SUMMARY="monitoring/drift/reports/drift_summary.json"

echo "🧮 Computing drift report (Evidently, in the training image)..."
# The training container doesn't mount the project, so write the report to a
# bind-mounted host dir (via --out-dir) — otherwise the JSON stays inside the
# container and we'd read a stale host copy.
mkdir -p "$PROJECT_DIR/monitoring/drift/reports"
docker compose run --rm \
    -v "$PROJECT_DIR/monitoring/drift/reports:/out" \
    training python scripts/drift_report.py "$@" --out-dir /out >/dev/null

test -f "$SUMMARY" || { echo "❌ $SUMMARY not produced"; exit 1; }

# Parse the summary + decide breach, emitting Prometheus exposition text.
METRICS="$(THRESHOLD="$THRESHOLD" python3 - "$SUMMARY" <<'PY'
import json, os, sys
s = json.load(open(sys.argv[1]))
thr = float(os.environ["THRESHOLD"])
share = float(s.get("drift_share", 0))
breach = 1 if share > thr else 0
print(f"""# HELP lol_drift_share Share of columns flagged as drifted by Evidently.
# TYPE lol_drift_share gauge
lol_drift_share {share}
# HELP lol_drift_n_drifted Number of drifted columns.
# TYPE lol_drift_n_drifted gauge
lol_drift_n_drifted {int(s.get('n_drifted', 0))}
# HELP lol_drift_n_columns Number of columns compared.
# TYPE lol_drift_n_columns gauge
lol_drift_n_columns {int(s.get('n_columns', 0))}
# HELP lol_drift_threshold Retrain threshold for the drift share.
# TYPE lol_drift_threshold gauge
lol_drift_threshold {thr}
# HELP lol_drift_breach 1 when drift_share exceeds the threshold (retrain due).
# TYPE lol_drift_breach gauge
lol_drift_breach {breach}""")
PY
)"

echo "📤 Pushing to ${PUSHGATEWAY_URL} ..."
printf '%s\n' "$METRICS" | curl -s --fail --data-binary @- \
    "${PUSHGATEWAY_URL}/metrics/job/lol_drift" \
    && echo "✅ Pushed drift metrics:" && printf '%s\n' "$METRICS" | grep -E '^lol_drift' || {
        echo "❌ Push failed"; exit 1; }
