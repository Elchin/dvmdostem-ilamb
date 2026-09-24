#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${1:-$ROOT/configs/check_conversions.yaml}"
"$ROOT/.venv/bin/dvmdostem-check-conversions" --config "$CONFIG"
