#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${1:-$ROOT/configs/abcflux_to_ilamb.yaml}"
"$ROOT/.venv/bin/dvmdostem-convert-obs" --config "$CONFIG"
