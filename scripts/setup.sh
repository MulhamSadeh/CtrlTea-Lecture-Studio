#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
cd frontend
npm ci --no-audit --no-fund
npm run build
cd ..
font_target="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/ctrltea"
mkdir -p "$font_target"
cp assets/fonts/*.ttf frontend/public/fonts/*.ttf "$font_target/"
fc-cache -f "$font_target"
printf '\nStart: .venv/bin/python scripts/start.py\n'
