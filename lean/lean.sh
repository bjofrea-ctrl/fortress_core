#!/usr/bin/env bash
# LEAN CLI helper — corre lean con TMPDIR bajo /Users (Docker Desktop en macOS
# NO comparte /var/folders ni /tmp; sin esto el backtest falla con
# 'invalid mount config for type bind').
set -euo pipefail

LEAN=/Users/boris/Desktop/fortress_core/backend/.venv/bin/lean
LEAN_DIR=/Users/boris/Desktop/fortress_core/lean
LEAN_TMP="${LEAN_TMP:-$HOME/lean-tmp}"
mkdir -p "$LEAN_TMP"

cd "$LEAN_DIR"
TMPDIR="$LEAN_TMP" "$LEAN" "$@"