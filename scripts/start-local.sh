#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "请先运行 uv sync --frozen"
  exit 1
fi
exec .venv/bin/python scripts/start.py
