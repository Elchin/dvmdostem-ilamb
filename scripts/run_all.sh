#!/usr/bin/env bash
# Run the full DVMDOSTEM → ILAMB pipeline and produce outputs/_build/index.html.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ILAMB_ROOT="${ILAMB_ROOT:-$ROOT/outputs}"
ILAMB_DIR="${ILAMB_DIR:-$ROOT/vendor/ILAMB}"
ILAMB_REPO="${ILAMB_REPO:-https://github.com/rubisco-sfa/ILAMB.git}"
SKIP_SETUP=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-setup]

Run all pipeline stages (obs conversion, model conversion, validation, ILAMB)
and write the HTML scoreboard to:
  \$ILAMB_ROOT/_build/index.html  (default: $ROOT/outputs/_build/index.html)

Environment:
  ILAMB_ROOT   ILAMB data/build directory (default: $ROOT/outputs)
  ILAMB_DIR    Local ILAMB clone used for installation (default: $ROOT/vendor/ILAMB)

Options:
  --skip-setup  Skip venv/package/ILAMB installation and run stages only
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-setup) SKIP_SETUP=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

apply_ilamb_site_patch() {
  local model_result="$1/src/ILAMB/ModelResult.py"
  if [[ ! -f "$model_result" ]]; then
    echo "ILAMB ModelResult.py not found at $model_result" >&2
    exit 1
  fi
  python3 - "$model_result" <<'PY'
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = "if var.area is not None and not np.allclose("
if needle in text:
    print("ILAMB ModelResult.py already patched for site-format model files")
    sys.exit(0)

old = "if not np.allclose(\n                    var.area.shape"
new = needle + "\n                    var.area.shape"
if old not in text:
    print(
        "WARNING: could not locate ModelResult.py patch target; "
        "ILAMB site-format model files may fail.",
        file=sys.stderr,
    )
    sys.exit(0)

open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
print("Applied ILAMB ModelResult.py site-format patch")
PY
}

setup_environment() {
  echo "==> Setting up Python environment in $ROOT/.venv"
  if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    python3 -m venv "$ROOT/.venv"
  fi

  "$ROOT/.venv/bin/pip" install -q -U pip
  "$ROOT/.venv/bin/pip" install -q -e "$ROOT"

  if [[ ! -d "$ILAMB_DIR/.git" ]]; then
    echo "==> Cloning ILAMB into $ILAMB_DIR"
    git clone --depth 1 "$ILAMB_REPO" "$ILAMB_DIR"
  fi

  apply_ilamb_site_patch "$ILAMB_DIR"

  echo "==> Installing ILAMB from $ILAMB_DIR"
  if ! "$ROOT/.venv/bin/pip" install -q -e "$ILAMB_DIR"; then
    cat >&2 <<EOF
Failed to install ILAMB. Common fixes:
  - Install OpenMPI: sudo apt-get install openmpi-bin libopenmpi-dev
  - Install cartopy/GEOS build deps, or use conda/mamba for ILAMB dependencies
  - Set ILAMB_DIR to an existing ILAMB checkout and retry
EOF
    exit 1
  fi

  if ! command -v mpirun >/dev/null 2>&1; then
    echo "WARNING: mpirun not found. Install OpenMPI before running ILAMB." >&2
  fi
}

if [[ "$SKIP_SETUP" == false ]]; then
  setup_environment
fi

mkdir -p "$ILAMB_ROOT"

echo "==> Stage 1: observations -> ILAMB NetCDF"
"$ROOT/scripts/run_stage1.sh"

echo "==> Stage 2: model -> ILAMB NetCDF"
"$ROOT/scripts/run_stage2.sh"

echo "==> Stage 3: validate conversions"
"$ROOT/scripts/run_stage3.sh"

echo "==> Stage 4/5: ILAMB benchmark + scoreboard"
"$ROOT/scripts/run_ilamb.sh"

SCOREBOARD="$ILAMB_ROOT/_build/index.html"
if [[ ! -f "$SCOREBOARD" ]]; then
  echo "Expected scoreboard not found: $SCOREBOARD" >&2
  exit 1
fi

echo
echo "Pipeline complete."
echo "Scoreboard: $SCOREBOARD"
echo "View locally: python -m http.server --directory $ILAMB_ROOT/_build 8080"
