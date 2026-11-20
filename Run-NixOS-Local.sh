#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CTRLTEA_AUTH_MODE=local
export CTRLTEA_DB_BACKEND=sqlite
export CTRLTEA_PUBLIC_ORIGIN=http://127.0.0.1:8766
export CTRLTEA_DATA_DIR="${CTRLTEA_DATA_DIR:-$PWD/data}"
if ! command -v nix >/dev/null 2>&1; then
    echo 'nix executable not found. Enable Nix first.' >&2
    exit 1
fi
exec nix --extra-experimental-features 'nix-command flakes' develop --command bash -c 'python scripts/start.py --port 8766'
