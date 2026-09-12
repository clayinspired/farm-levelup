"""farmlevelup — Telegram bot + plot store in one process.

Running both together is the point: the drawing page POSTs a polygon to the same
process that runs the bot, so it can answer the chat immediately. No NAT relay,
no /pending polling, no claim races. Telegram reaches us by webhook.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sqlite3
import time
from pathlib import Path

from aiohttp import web
from telegram import Update

from app import bot as botmod
from app import eligibility as elig

DB_PATH = Path(os.environ.get("DB_PATH", "/data/plots.db"))
API_KEY = os.environ.get("FARM_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
SELF_URL = os.environ.get("SELF_URL", "").rstrip("/")

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("farmlevelup")

# Comma-separated list of site origins allowed to POST plots, e.g.
#   ALLOWED_ORIGINS="https://example.com,https://preview.example.pages.dev"
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()}
ORIGIN_SUFFIX = os.environ.get("ALLOWED_ORIGIN_SUFFIX", "").strip()

# Public-facing limits. POST /plots/{token} is reachable by anyone who has a token,
# so bound what a single caller can cost us.
MAX_BODY_BYTES = 256 * 1024
MAX_POINTS = 500
RATE_WINDOW_S = 60
RATE_MAX_POSTS = 20
_rate: dict[str, list[float]] = {}


def rate_ok(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < RATE_WINDOW_S]
    if len(hits) >= RATE_MAX_POSTS:
        _rate[ip] = hits
        return False
    hits.append(now)
    _rate[ip] = hits
    if len(_rate) > 5000:                       # bound the table itself
        for k in [k for k, v in _rate.items() if not v or now - v[-1] > RATE_WINDOW_S * 5]:
            _rate.pop(k, None)
    return True


def valid_ring(coords) -> bool:
    if not (3 <= len(coords) <= MAX_POINTS):
        return False
    for lon, lat in coords:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return False
    return True


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS sessions(
                token TEXT PRIMARY KEY, chat_id INTEGER, lat REAL, lon REAL, created REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS plots(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT, chat_id INTEGER, lat REAL, lon REAL,
                coordinates TEXT, area_ha REAL, created REAL,
                claimed INTEGER DEFAULT 0, note TEXT)""")
            # added later; existing databases need the column backfilled
            cols = {r["name"] for r in c.execute("PRAGMA table_info(plots)")}
            if "share" not in cols:
                c.execute("ALTER TABLE plots ADD COLUMN share TEXT")
                for row in c.execute("SELECT id FROM plots WHERE share IS NULL").fetchall():
                    c.execute("UPDATE plots SET share=? WHERE id=?",
                              (secrets.token_urlsafe(9), row["id"]))
            c.execute("CREATE INDEX IF NOT EXISTS plots_share ON plots(share)")
            c.commit()

    def _c(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def new_session(self, token, chat_id, lat, lon):
        with self._c() as c:
            c.execute("INSERT OR REPLACE INTO sessions VALUES(?,?,?,?,?)",
                      (token, chat_id, lat, lon, time.time()))
            c.commit()

    def add_plot(self, token, coords, area_ha, note=None):
        share = secrets.token_urlsafe(9)
        with self._c() as c:
            s = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
            cur = c.execute(
                "INSERT INTO plots(token,chat_id,lat,lon,coordinates,area_ha,created,"
                "claimed,note,share) VALUES(?,?,?,?,?,?,?,0,?,?)",
                (token, s["chat_id"] if s else None, s["lat"] if s else None,
                 s["lon"] if s else None, json.dumps(coords), area_ha, time.time(),
                 note, share))
            c.commit()
            return cur.lastrowid, (s["chat_id"] if s else None), share

    def get_share(self, tok):
        """Public view of a plot: geometry only, never the chat it came from."""
        with self._c() as c:
            r = c.execute("SELECT coordinates, area_ha, lat, lon FROM plots WHERE share=?",
                          (tok,)).fetchone()
        if not r:
            return None
        return {"coordinates": json.loads(r["coordinates"]), "area_ha": r["area_ha"],
                "lat": r["lat"], "lon": r["lon"]}

    def get_plot(self, pid):
        with self._c() as c:
            r = c.execute("SELECT * FROM plots WHERE id=?", (pid,)).fetchone()
        if not r:
            return None
        d = dict(r); d["coordinates"] = json.loads(d["coordinates"])
        return d

    def take_pending(self, limit=20):
        with self._c() as c:
            rows = c.execute("SELECT * FROM plots WHERE claimed=0 AND chat_id IS NOT NULL"
                             " ORDER BY id LIMIT ?", (limit,)).fetchall()
            out = [dict(r) for r in rows]
            if out:
                c.executemany("UPDATE plots SET claimed=1 WHERE id=?", [(r["id"],) for r in out])
                c.commit()
        for r in out:
            r["coordinates"] = json.loads(r["coordinates"])
        return out

    def mark_claimed(self, pid):
        with self._c() as c:
            c.execute("UPDATE plots SET claimed=1 WHERE id=?", (pid,))
            c.commit()

    def all_plots(self, limit=1000):
        with self._c() as c:
            rows = c.execute("SELECT * FROM plots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["coordinates"] = json.loads(d["coordinates"]); out.append(d)
        return out

    def count(self):
        with self._c() as c:
            return c.execute("SELECT COUNT(*) n FROM plots").fetchone()["n"]


def authed(req) -> bool:
    return bool(API_KEY) and req.headers.get("X-Api-Key") == API_KEY


@web.middleware
async def cors(request, handler):
    origin = request.headers.get("Origin", "")
    allow = origin if (origin in ALLOWED_ORIGINS
                       or (ORIGIN_SUFFIX and origin.endswith(ORIGIN_SUFFIX))) else ""
    resp = web.Response(status=204) if request.method == "OPTIONS" else await handler(request)
    if allow:
        resp.headers["Access-Control-Allow-Origin"] = allow
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Vary"] = "Origin"
    return resp


async def health(req):
    return web.json_response({"ok": True, "plots": req.app["store"].count(),
                              "cache": elig.cache_stats(),
                              "bot": bool(req.app.get("tg"))})


async def new_session(req):
    if not authed(req):
        return web.json_response({"error": "unauthorised"}, status=401)
    b = await req.json()
    req.app["store"].new_session(b["token"], b.get("chat_id"), b.get("lat"), b.get("lon"))
    return web.json_response({"ok": True})


async def post_plot(req):
    """The drawing page submits here. Because the bot lives in this process, a plot
    tied to a chat is answered straight away rather than queued for a poller."""
    ip = (req.headers.get("Fly-Client-IP")
          or req.headers.get("X-Forwarded-For", "").split(",")[0].strip()
          or (req.remote or "?"))
    if not rate_ok(ip):
        return web.json_response({"error": "too many submissions, try again shortly"},
                                 status=429)

    token = req.match_info["token"]
    if len(token) > 64:
        return web.json_response({"error": "bad token"}, status=400)
    try:
        b = await req.json()
        coords = [[float(x), float(y)] for x, y in b["coordinates"]]
    except Exception:
        return web.json_response({"error": "bad payload"}, status=400)
    if not valid_ring(coords):
        return web.json_response(
            {"error": f"need 3-{MAX_POINTS} points with valid coordinates"}, status=400)

    store = req.app["store"]
    area = float(b.get("area_ha") or 0) or elig.polygon_area_ha([(c[0], c[1]) for c in coords])
    pid, chat_id, share = store.add_plot(token, coords, area, b.get("note"))

    tg = req.app.get("tg")
    if chat_id and tg:
        store.mark_claimed(pid)
        asyncio.create_task(botmod.answer_polygon(
            tg, int(chat_id), [(c[0], c[1]) for c in coords], area, share=share))
    return web.json_response({"ok": True, "id": pid, "relayed": bool(chat_id),
                              "share": share})


async def share_plot(req):
    """Unauthenticated, but keyed by an unguessable token and geometry-only."""
    rec = req.app["store"].get_share(req.match_info["tok"])
    if not rec:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(rec)


async def pending(req):
    if not authed(req):
        return web.json_response({"error": "unauthorised"}, status=401)
    return web.json_response({"plots": req.app["store"].take_pending()})


async def get_plot(req):
    if not authed(req):
        return web.json_response({"error": "unauthorised"}, status=401)
    rec = req.app["store"].get_plot(int(req.match_info["pid"]))
    if not rec:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(rec)


async def list_plots(req):
    if not authed(req):
        return web.json_response({"error": "unauthorised"}, status=401)
    rows = req.app["store"].all_plots()
    return web.json_response({"count": len(rows), "plots": rows})


async def telegram_webhook(req):
    if WEBHOOK_SECRET and req.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return web.Response(status=403)
    tg = req.app.get("tg")
    if not tg:
        return web.Response(status=503)
    data = await req.json()
    await tg.update_queue.put(Update.de_json(data, tg.bot))
    return web.Response(text="ok")


async def on_start(app):
    if not TG_TOKEN:
        log.warning("no TELEGRAM_BOT_TOKEN — running as store only")
        return
    tg = botmod.build_application(TG_TOKEN, app["store"])
    await tg.initialize()
    await tg.start()
    app["tg"] = tg
    if SELF_URL:
        await tg.bot.set_webhook(f"{SELF_URL}/tg/webhook",
                                 secret_token=WEBHOOK_SECRET or None,
                                 drop_pending_updates=False,
                                 allowed_updates=["message", "callback_query"])
        log.info("webhook set to %s/tg/webhook", SELF_URL)
    me = await tg.bot.get_me()
    log.info("bot ready: @%s", me.username)


async def on_stop(app):
    tg = app.get("tg")
    if tg:
        await tg.stop()
        await tg.shutdown()


def make_app():
    app = web.Application(middlewares=[cors], client_max_size=MAX_BODY_BYTES)
    app["store"] = Store(DB_PATH)
    app.router.add_get("/health", health)
    app.router.add_post("/sessions", new_session)
    app.router.add_route("OPTIONS", "/plots/{token}", lambda r: web.Response(status=204))
    app.router.add_post("/plots/{token}", post_plot)
    app.router.add_get("/share/{tok}", share_plot)
    app.router.add_get("/pending", pending)
    app.router.add_get("/plots/id/{pid}", get_plot)
    app.router.add_get("/plots", list_plots)
    app.router.add_post("/tg/webhook", telegram_webhook)
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), port=int(os.environ.get("PORT", "8080")))
