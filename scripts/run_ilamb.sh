#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ILAMB_ROOT="${ILAMB_ROOT:-$ROOT/outputs}"
CONFIG="${1:-$ROOT/configs/site_runs_ilamb.cfg}"

# Optional: enable ILAMB site plot pages (disabled by default upstream).
export ILAMB_ENABLE_SITE_PLOTS="${ILAMB_ENABLE_SITE_PLOTS:-0}"

echo "ILAMB_ROOT=$ILAMB_ROOT"
echo "Running ilamb-run with config $CONFIG"

if command -v mpirun >/dev/null 2>&1; then
  MPI_CMD=(mpirun -n 1)
else
  MPI_CMD=()
fi

if [[ -x "$ROOT/.venv/bin/ilamb-run" ]]; then
  ILAMB_RUN="$ROOT/.venv/bin/ilamb-run"
elif command -v ilamb-run >/dev/null 2>&1; then
  ILAMB_RUN="$(command -v ilamb-run)"
else
  echo "ilamb-run not found. Install ILAMB into the project venv first." >&2
  exit 1
fi

cd "$ILAMB_ROOT"
rm -f "$ILAMB_ROOT/_build/DVMDOSTEM-SiteRuns.pkl"

"${MPI_CMD[@]}" "$ILAMB_RUN" \
  --config "$CONFIG" \
  --model_root "$ILAMB_ROOT/MODELS/" \
  --models DVMDOSTEM-SiteRuns \
  --regions global \
  --clean

echo "Scoreboard: $ILAMB_ROOT/_build/index.html"
echo "View locally: python -m http.server --directory $ILAMB_ROOT/_build 8080"
