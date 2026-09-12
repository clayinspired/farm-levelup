"""Telegram handlers for farmlevelup. Deployed copy — runs inside the Fly app
alongside the plot store, so a drawn field is answered by the same process that
stores it (no NAT relay, no polling).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, WebAppInfo)
from telegram.constants import ParseMode
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from . import eligibility as elig
from . import revenue as rev

log = logging.getLogger("farmbot")

BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
CHECK_TIMEOUT_S = 150

WELCOME = (
    "<b>farmlevelup</b>\n\n"
    "Some buyers pay farmers to plant trees and keep them standing. "
    "I check if your land can join, and tell you what it really pays.\n\n"
    "Send me where your land is 👇\n"
    "<i>Tap the button, or type something like</i> <code>13.80, 9.00</code>"
)

LOC_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("📍 Share my location", request_location=True)]],
    resize_keyboard=True, one_time_keyboard=True)

COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)\s*$")


def pct(v: float, d: int = 1) -> str:
    return f"{v * 100:.{d}f}%"


def verdict_line(r: dict) -> str:
    if r["verdict"] == "PASS":
        return "🟢 <b>Looks good.</b> No forest here for 10 years."
    if r["verdict"] == "FAIL":
        return "🔴 <b>Not suitable.</b> This was forest, cut down recently."
    if not r["non_forest_ok"]:
        return f"🟡 <b>Already has trees</b> ({pct(r['max_forest'], 0)}). Harder to qualify."
    return "🟡 <b>Trees were cut here recently.</b> You would need to show why."


def report(r: dict, lat: float, lon: float) -> str:
    """Kept short enough to read on one phone screen without scrolling."""
    h = rev.per_hectare()
    f = rev.fmt_usd
    lines = [f"📍 <code>{lat:.5f}, {lon:.5f}</code>", "", verdict_line(r)]
    if r["verdict"] != "FAIL":
        lines += [
            "",
            f"💰 <b>~{f(h['usd_ha'][1])} per hectare a year</b> "
            f"({f(h['usd_acre'][1])} per acre)",
            "<i>if the trees stay standing</i>",
            "",
            "<b>Good to know</b>",
            f"• Cut them back for leaves → only ~{f(h['leaf_usd_ha'][1])}/ha",
            "• Paid years later, after someone checks the trees",
            f"• Worth the paperwork above ~{h['breakeven_ha']:,.0f} ha — most farmers join a group",
            f"• Moringa leaves pay far more: ~{f(h['crop_usd_ha'][1])}/ha",
        ]
    return "\n".join(lines)


async def draw_markup(store, chat_id: int, lat: float, lon: float):
    """Inline, not a reply keyboard. A reply keyboard replaces the text input and
    Telegram frequently collapses it behind a small icon, so the button looked
    missing. An inline button is attached to the message and cannot be hidden.

    sendData() does not work from inline buttons, but it is no longer needed: the
    page POSTs to the store, and the store runs in this same process, so the chat
    is answered directly."""
    tok = secrets.token_urlsafe(12)
    store.new_session(tok, chat_id, lat, lon)
    url = f"{BASE_URL}/draw/?t={tok}&lat={lat:.6f}&lon={lon:.6f}"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✏️ Draw my field", web_app=WebAppInfo(url=url))]])


async def deliver(msg, ctx, lat: float, lon: float):
    bbox = elig.bbox_from_point(lat, lon, 1.0)
    status = None
    if elig.cache_get(elig.point_key(lat, lon, 1.0)) is None:
        status = await msg.reply_text("🔍 Checking the last 10 years of satellite pictures…")
    try:
        r = await asyncio.wait_for(asyncio.to_thread(elig.check, bbox), timeout=CHECK_TIMEOUT_S)
    except asyncio.TimeoutError:
        await (status.edit_text if status else msg.reply_text)(
            "⏳ Too slow right now. Send the location again.")
        return
    except Exception as exc:
        log.exception("check failed")
        await (status.edit_text if status else msg.reply_text)(
            f"😞 Could not read the satellite data ({type(exc).__name__}). Send it again.")
        return

    if status:
        await status.delete()
    markup = None
    if r["verdict"] != "FAIL":
        store = ctx.application.bot_data["store"]
        markup = await draw_markup(store, msg.chat_id, lat, lon)
    await msg.reply_text(report(r, lat, lon), parse_mode=ParseMode.HTML,
                         reply_markup=markup)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.effective_message.reply_text(WELCOME, parse_mode=ParseMode.HTML,
                                              reply_markup=LOC_KB)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Send me where your land is and I will tell you if it can join, and what it pays.\n\n"
        "This is a first check only. Your country's forest rules, your land papers and a "
        "visit to the field still decide it.", parse_mode=ParseMode.HTML)


async def got_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    loc = update.effective_message.location
    await update.effective_message.reply_text("📍 Got it.", reply_markup=ReplyKeyboardRemove())
    await deliver(update.effective_message, ctx, loc.latitude, loc.longitude)


async def got_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    m = COORD_RE.match((msg.text or "").strip())
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            await msg.reply_text("That is not a real place. Try like 13.80, 9.00")
            return
        await deliver(msg, ctx, lat, lon)
        return
    await msg.reply_text(
        "Send me where your land is — tap the button, or type something like "
        "<code>13.80, 9.00</code>.", parse_mode=ParseMode.HTML, reply_markup=LOC_KB)


async def on_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    store = ctx.application.bot_data["store"]
    share = None
    try:
        body = json.loads(msg.web_app_data.data)
        if "plot_id" in body:
            rec = store.get_plot(int(body["plot_id"]))
            if not rec:
                raise ValueError("plot missing")
            body = rec
            share = rec.get("share")
        coords = [(float(c[0]), float(c[1])) for c in body["coordinates"]]
    except Exception:
        await msg.reply_text("I could not read that field. Please draw it again.",
                             reply_markup=ReplyKeyboardRemove())
        return
    if len(coords) < 3:
        await msg.reply_text("A field needs at least 3 points.",
                             reply_markup=ReplyKeyboardRemove())
        return
    area = float(body.get("area_ha") or 0) or elig.polygon_area_ha(coords)
    await msg.reply_text("Got your field ✏️", reply_markup=ReplyKeyboardRemove())
    await answer_polygon(ctx.application, msg.chat_id, coords, area, share=share)


async def answer_polygon(tg_app, chat_id: int, coords, area_ha: float, share: str | None = None):
    bot = tg_app.bot
    if area_ha <= 0.0001:
        await bot.send_message(chat_id, "That shape has no area — please draw it again.")
        return
    status = await bot.send_message(
        chat_id, f"✏️ <b>{area_ha:.2f} hectares</b> ({area_ha / rev.ACRE_HA:.2f} acres). "
                 "Checking…", parse_mode=ParseMode.HTML)
    try:
        r = await asyncio.wait_for(asyncio.to_thread(elig.check_polygon, coords),
                                   timeout=CHECK_TIMEOUT_S)
    except Exception as exc:
        log.exception("polygon check failed")
        await status.edit_text(f"😞 Could not check that field ({type(exc).__name__}).")
        return
    await status.delete()

    note = ("\n<i>Your field is smaller than one satellite pixel, so this reads the land "
            "just around it.</i>") if r.get("subpixel") else ""
    e = rev.estimate(area_ha, "agroforestry")
    f = rev.fmt_usd
    body = [f"<b>Your field: {area_ha:.2f} ha</b> ({area_ha / rev.ACRE_HA:.2f} acres)",
            "", verdict_line(r) + note]
    if r["verdict"] != "FAIL":
        body += ["",
                 f"💰 <b>~{f(e.annual_net_to_farmer_usd[1])} a year</b> for this field",
                 f"<i>Moringa leaves from it: ~{f(rev.moringa_crop_income(area_ha)[1])} a year</i>"]
    body += ["", "<i>A first check only — your country's forest rules, land papers and a "
                 "visit still decide it.</i>"]

    markup = None
    if share:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(
            "🗺 See your field on the map",
            url=f"{BASE_URL}/map/?plot={share}")]])
    await bot.send_message(chat_id, "\n".join(body), parse_mode=ParseMode.HTML,
                           reply_markup=markup)


def build_application(token: str, store):
    app = (ApplicationBuilder().token(token).build())
    app.bot_data["store"] = store
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.LOCATION, got_location))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, got_text))
    return app
