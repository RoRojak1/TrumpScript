#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python -m nutrition_bot.x5_cli \
  --menu nutrition_bot/data/sample_menu.json \
  --json \
  "$@"
