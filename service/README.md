# service — Telegram bot + plot store

Part of **farm-levelup**.

One Fly app (a ~1 GB volume mounted at `/data`) running both the
bot and the store in a single process. That is the point: the drawing page POSTs a polygon
to the store, and because the bot is in the same process it answers the chat directly —
no relay, no polling, no inbound hole through NAT.

Telegram delivers updates by **webhook** (`/tg/webhook`, validated against a secret token).

```
main.py              aiohttp app: store routes + webhook, SQLite on the volume
app/bot.py           handlers, copy, money figures
app/eligibility.py   fast Hansen-only VM0047 check (point or polygon), cached
app/revenue.py       moringa + carbon economics
```

`vm0047/hansen.py` is **not** vendored here — `service/Dockerfile` copies `src/vm0047/`
from the repo root, so the bot and the research pipeline share one implementation.

## Deploy

```bash
./scripts/deploy-service.sh
```

Build context is the repo root (`--dockerfile service/Dockerfile`), which is what lets the
image pull in `src/vm0047`.

## Config

Fly secrets — never in the image, never in git:

| name | purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `FARM_API_KEY` | guards the bot-facing store routes |
| `WEBHOOK_SECRET` | validates Telegram's webhook calls |
| `SELF_URL` | where to register the webhook |
| `ALLOWED_ORIGINS` | site origins allowed to POST plots (CORS) |
| `PUBLIC_BASE_URL` | site origin used to build draw links |

## Routes

```
GET  /health          open     liveness + plot count + cache stats
POST /sessions        key      bot registers {token, chat_id, lat, lon}
POST /plots/{token}   open*    page submits a polygon -> {id, relayed, share}
GET  /share/{token}   open     geometry only, never the chat it came from
GET  /pending         key      unclaimed plots (fallback path), marks claimed
GET  /plots/id/{id}   key      one plot
GET  /plots           key      the whole archive
POST /tg/webhook      secret   Telegram updates
```

\* bounded rather than unauthenticated: 256 KB body cap, 3–500 points, coordinate range
validation, and 20 submissions per IP per minute. CORS is limited to the site's origins.

## Data

Every drawn field is kept, including ones whose token no longer maps to a chat
(`relayed: false`) — a farmer's boundary is never discarded because a link expired.
Each plot gets an unguessable `share` token so it can be opened on the map without
exposing the archive to enumeration.

The eligibility cache lives on the same volume and is keyed by Hansen dataset version,
so a future GFC release invalidates it automatically.

## Things that cost time, so they are written down

- **A new Fly app has no public IP.** `flyctl deploy` succeeds, the machine passes its
  internal health check, and the hostname still resolves to nothing. Run
  `flyctl ips allocate-v4 --shared` and `allocate-v6` once. A negative DNS answer can
  then stay cached locally for several minutes after the IP exists.
- **rasterio on `python:*-slim` needs `libexpat1`.** The manylinux wheel bundles GDAL but
  still links libexpat at runtime, so the container crash-loops on import until the
  apt package is added.
- **Telegram reply keyboards can look like nothing rendered.** A `ReplyKeyboardMarkup`
  replaces the text input and is frequently collapsed behind a small icon, so the button
  appears missing. Inline buttons attach to the message and cannot be hidden — use those
  unless `WebApp.sendData` is genuinely required, which it is not here because the store
  shares a process with the bot.
- **`WebApp.sendData` caps at 4096 bytes.** A finger-traced polygon exceeds it easily.
  The page sends a plot id instead, and only falls back to inline geometry (decimated to
  110 points) when the store is unreachable.
- **Give any browser fetch a timeout.** A sleeping Fly machine cold-starts, and without
  `AbortController` the drawing page hung on "Sending…" forever instead of falling back.
- **CORS origins are configuration now.** `ALLOWED_ORIGINS` is a Fly secret; deploying to
  a fresh app without setting it makes the drawing page fail CORS with no hardcoded
  fallback.
