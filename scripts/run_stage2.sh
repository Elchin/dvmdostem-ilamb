#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${1:-$ROOT/configs/model_to_ilamb.yaml}"
"$ROOT/.venv/bin/dvmdostem-convert-model" --config "$CONFIG"
