#!/usr/bin/env python3
"""Watch fields as they are drawn.

    ./scripts/watch-plots.py           follow new submissions (Ctrl-C to stop)
    ./scripts/watch-plots.py --all     print everything stored, then exit
    ./scripts/watch-plots.py --geojson > plots.geojson
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env():
    cfg = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


CFG = env()
KEY = CFG.get("FARM_API_KEY") or sys.exit("FARM_API_KEY missing from .env")
STORE = (CFG.get("PLOTSTORE_URL") or sys.exit("PLOTSTORE_URL missing from .env")).rstrip("/")
SITE = (CFG.get("SITE_URL") or "").rstrip("/")


def fetch():
    req = urllib.request.Request(f"{STORE}/plots", headers={"X-Api-Key": KEY})
    with urllib.request.urlopen(req, timeout=25) as r:
        return sorted(json.load(r)["plots"], key=lambda p: p["id"])


def line(p):
    t = datetime.fromtimestamp(p["created"]).strftime("%H:%M:%S")
    return (f"  {t}  #{p['id']:<4} chat={str(p['chat_id'] or '-'):<11}"
            f"{(p['area_ha'] or 0):>9.2f} ha {len(p['coordinates']):>4} pts  "
            + (f"{SITE}/map/?plot={p['share']}" if SITE else f"share={p['share']}"))


def geojson(plots):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: p[k] for k in ("id", "chat_id", "area_ha", "created", "share")},
         "geometry": {"type": "Polygon",
                      "coordinates": [p["coordinates"] + [p["coordinates"][0]]]}}
        for p in plots]}


def main():
    args = set(sys.argv[1:])
    if "--geojson" in args:
        json.dump(geojson(fetch()), sys.stdout, indent=1)
        return
    if "--all" in args:
        plots = fetch()
        print(f"{len(plots)} field(s) stored:")
        for p in plots:
            print(line(p))
        return

    print(f"Watching {STORE} — Ctrl-C to stop")
    try:
        seen = {p["id"] for p in fetch()}
        print(f"  ({len(seen)} already stored; showing new ones as they arrive)")
    except Exception as exc:
        print(f"  could not reach the store: {exc}")
        seen = set()
    while True:
        try:
            for p in fetch():
                if p["id"] not in seen:
                    seen.add(p["id"])
                    print(line(p), flush=True)
        except Exception as exc:
            print(f"  ! {type(exc).__name__}: {exc}", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
