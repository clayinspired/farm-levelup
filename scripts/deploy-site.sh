#!/usr/bin/env bash
# Publish site/ to Cloudflare Pages.
#   CF_PAGES_PROJECT   Pages project name          (required)
#   CLOUDFLARE_API_TOKEN or CF_ENV_FILE            (required)
#   SITE_URL           printed on success          (optional)
set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck disable=SC1091
[ -f .env ] && { set -a; . ./.env; set +a; }
: "${CF_PAGES_PROJECT:?set CF_PAGES_PROJECT (Cloudflare Pages project name)}"

if [ ! -f site/config.js ]; then
  echo "site/config.js missing — copy site/config.example.js and fill it in" >&2
  exit 1
fi
if [ ! -f site/map/data/index.json ]; then
  echo "site/map/data missing — run:  uv run python src/vm0047/export_web.py" >&2
  exit 1
fi

# wrangler needs node >= 20; point NODE_BIN at it if your default is older
[ -n "${NODE_BIN:-}" ] && export PATH="$NODE_BIN:$PATH"

# CLOUDFLARE_API_TOKEN may come from the environment, or from a file named by
# CF_ENV_FILE (keep that file outside the repo).
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] && [ -n "${CF_ENV_FILE:-}" ]; then
  # shellcheck disable=SC1090
  . "$CF_ENV_FILE"
fi
: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN or CF_ENV_FILE}"

# the proxy vars in this shell break wrangler's uploads
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  npx --yes wrangler pages deploy site \
    --project-name="$CF_PAGES_PROJECT" --branch=master

echo "live: ${SITE_URL:-(see your Pages dashboard)}"
