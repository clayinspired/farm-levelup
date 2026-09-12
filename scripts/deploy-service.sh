#!/usr/bin/env bash
# Deploy the Telegram bot + plot store to Fly.
#   FLY_APP         Fly app name                 (required)
#   PLOTSTORE_URL   health-checked after deploy  (optional)
# Build context is the repo root so the image shares src/vm0047 with the pipeline.
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
[ -f .env ] && { set -a; . ./.env; set +a; }
: "${FLY_APP:?set FLY_APP (Fly app name)}"

flyctl deploy \
  --config service/fly.toml \
  --dockerfile service/Dockerfile \
  --app "$FLY_APP" \
  --ha=false "$@"

echo
[ -n "${PLOTSTORE_URL:-}" ] && { curl -s -m 25 "$PLOTSTORE_URL/health"; echo; } || true
