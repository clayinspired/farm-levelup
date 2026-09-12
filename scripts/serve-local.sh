#!/usr/bin/env bash
# Serve site/ locally for review. Also prints a private-network address if the
# host has one, so you can open it from a phone on the same network.
set -euo pipefail
cd "$(dirname "$0")/../site"
PORT="${1:-8811}"
# 100.64.0.0/10 is the shared CGNAT range used by tailnets
TS=$(/sbin/ifconfig 2>/dev/null | grep 'inet 100\.' | awk '{print $2}' | head -1)
echo "local    http://127.0.0.1:$PORT/"
[ -n "$TS" ] && echo "network  http://$TS:$PORT/"
exec python3 -m http.server "$PORT" --bind 0.0.0.0
