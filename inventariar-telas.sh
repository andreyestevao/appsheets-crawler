#!/usr/bin/env bash
# Inventário de telas AppSheet autenticadas — atalho de execução.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt
python -m playwright install chromium 2>/dev/null || true

export PYTHONUNBUFFERED=1
python scripts/inventariar_telas.py "$@"
