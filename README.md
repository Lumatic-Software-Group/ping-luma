# PingLuma

[![CI](https://github.com/YOUR_ORG/pingluma/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/pingluma/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**@ping_luma_bot** — Check whether Iranian messengers are reachable from
**your** network, in real time, and learn whether you need an Iranian-exit
VPN.

The bot is just a launcher and a results renderer. The actual probing
happens in your own browser/Telegram client via a WebApp, so the network
that's measured is the one your phone or laptop is sitting on.

---

## Supported Messengers

| Messenger | فارسی | Availability |
|---|---|---|
| Bale | بله | Global |
| Eitaa | ایتا | Mixed |
| Rubika | روبیکا | Mixed |
| Gap | گپ | Global |
| iGap | آی‌گپ | Global |
| Soroush Plus | سروش‌پلاس | Mixed |

**Availability:**

- Global — designed for worldwide use
- Mixed — globally reachable but some features are Iran-only
- Iran-only — domestic only; expected to be blocked outside Iran

---

## How "Your Network" is Honoured

A Telegram bot's Python code runs on the bot's host, not on the user's
device. So a server-side probe answers "can my server reach Bale?" — never
"can the user's WiFi reach Bale?".

PingLuma routes around this by doing all probing inside the WebApp:

1. The bot (`ping_luma/bot.py`) renders a **🌐 بررسی از شبکه شما** button.
2. Tapping it opens `web/dashboard.html` inside Telegram's WebView.
3. The dashboard runs `fetch()`, DNS-over-HTTPS lookups, and a WebRTC
   ICE-candidate gathering session — all from the user's network.
4. When done, the dashboard sends a small JSON summary back to the bot
   via `Telegram.WebApp.sendData(...)`.
5. The bot receives that summary and replies with a Persian message that
   combines the user's measurement with an optional **Iran-side reference**
   to decide whether an Iranian-exit VPN is needed.

```
User's phone (cellular / WiFi)
       │
       │  fetch / DoH / WebRTC  ──→  messenger origins, STUN/TURN
       │
       │  (results)
       ▼
Telegram WebApp (web/dashboard.html)
       │
       │  tg.sendData(JSON summary)
       ▼
@ping_luma_bot (your VPS)              optional GET → Iran-side reference
       │                                              │
       │   format_webapp_report(payload, iran_ref)   │
       └─────────────────────────────────────────────┘
                              │
                              ▼
                    Persian reply with
                    per-messenger advice
```

---

## VPN-Advice Decision Logic

Per-messenger, for both chat and call dimensions:

| Your network | Iran-side reference | Advice |
|---|---|---|
| reachable | any | No VPN needed |
| blocked | reachable | Iranian-exit VPN required |
| blocked | blocked | Globally down right now |
| blocked | unknown | Inconclusive (shown as a hint, not a verdict) |

Proprietary protocols (Rubika, Soroush+) cannot be probed from a browser,
so the call dimension falls back to the static prior shipped in
`ping_luma/messengers.py`. The bot tells the user explicitly when a line
is a static expectation vs. a measured result.

The full rule lives in `ping_luma/advice.py` and is unit-tested in
`tests/test_advice.py`.

---

## Project Structure

```
ping-luma/
├── .github/workflows/ci.yml
├── ping_luma/
│   ├── __init__.py
│   ├── advice.py            # decide_chat_advice / decide_call_advice
│   ├── asn.py               # ASN classifier (BGP-based structural verdict)
│   ├── asn_map.json         # baked host→ASN map (run scripts/refresh_asn_map.py)
│   ├── bot.py               # Telegram launcher + WebAppData receiver
│   ├── checker.py           # probing utilities (for an optional Iran-side service)
│   ├── config.py
│   ├── crowdsource.py       # in-memory store of real Iranian WebApp samples
│   ├── formatters.py        # Persian rendering of WebApp results
│   ├── iran_reference.py    # façade: ASN + OONI + Crowd + HTTP
│   ├── messengers.py
│   ├── ooni.py              # OONI Aggregation client (historical IR data)
│   └── publish_iran_reference.py  # CLI: probe → iran-ref.json
├── scripts/
│   └── refresh_asn_map.py   # offline refresh of asn_map.json from bgpview.io
├── tests/
│   ├── test_advice.py
│   ├── test_asn.py
│   ├── test_checker.py
│   ├── test_crowdsource.py
│   ├── test_formatters.py
│   ├── test_iran_reference.py
│   ├── test_messengers.py
│   ├── test_ooni.py
│   └── test_publish_iran_reference.py
├── volunteer-repo/          # template for the Iran-side reference repo
│   ├── .github/workflows/probe.yml
│   ├── .gitignore
│   ├── README.md
│   └── requirements.txt
├── web/
│   └── dashboard.html       # the only piece that probes from the user's network
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Quick Start

### 1 — Environment

```bash
cp .env.example .env
# edit .env: BOT_TOKEN and WEBAPP_URL are required
```

### 2 — Local (venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ping_luma.bot
```

### 3 — Docker

```bash
docker compose up -d
docker compose logs -f bot
```

You also need to host `web/dashboard.html` somewhere over HTTPS (Telegram
requires it) and put that URL into `WEBAPP_URL`. The included CI workflow
publishes the `web/` directory to GitHub Pages.

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message + WebApp launcher |
| `/list`  | List all messengers; tap one for a static info card |
| `/help`  | Same as `/start` |

There is intentionally no `/scan` or `/quick` — those would have run on
the bot host and would not reflect the user's network.

---

## Configuration

### Core

| Variable | Default | Required | Description |
|---|---|---|---|
| `BOT_TOKEN` | — | yes | From @BotFather |
| `WEBAPP_URL` | `https://pingluma.app` | yes | HTTPS URL serving `web/dashboard.html` |
| `BASE_URL` | `https://api.telegram.org/bot` | no | Telegram API base URL |
| `PROXY_URL` | *(empty)* | no | `socks5://…` or `http://…` proxy for the bot |
| `CONNECT_TIMEOUT` | `30` | no | Seconds |
| `READ_TIMEOUT` | `30` | no | Seconds |
| `WRITE_TIMEOUT` | `30` | no | Seconds |
| `DROP_PENDING` | `true` | no | Discard queued updates on startup |

### Iran-Side Reference

The bot answers *"would an Iranian VPN help this user?"* by merging up to
four independent Iran-side signal sources. None is mandatory; whatever is
configured is used.

**Authority chain (highest wins):**

```
HTTP override  >  Crowdsource  >  OONI  >  ASN classifier
```

Each source overrides the previous one only where it has a verdict;
where a source is silent, the lower-authority verdict survives.

> **Note:** a RIPE Atlas layer (live TCP/TLS probes from real Iranian
> probes) was scoped but **not shipped in this release** — it requires a
> credit budget that wasn't ready in time. It's planned for a future
> update.

| Variable | Default | Description |
|---|---|---|
| `IRAN_REFERENCE_URL` | *(empty)* | Optional HTTPS endpoint of an Iran-side reference service (operator escape hatch). |
| `IRAN_REFERENCE_TOKEN` | *(empty)* | Bearer token sent to that endpoint. |
| `IRAN_REFERENCE_TIMEOUT_S` | `6` | HTTP timeout for the reference fetch. |
| `IRAN_REFERENCE_TTL_S` | `21600` | Cache TTL for the merged snapshot, also drives the background refresh cadence. 6 h. |
| `ASN_MAP_PATH` | `ping_luma/asn_map.json` | Baked map of host→ASN classification. Refresh with the script below. |
| `OONI_ENABLED` | `true` | Toggle OONI cross-check. |
| `OONI_LOOKBACK_DAYS` | `7` | Aggregation window for OONI measurements. |
| `OONI_TTL_S` | `86400` | Per-host cache TTL (24 h, since OONI updates daily). |
| `OONI_TIMEOUT_S` | `15` | HTTP timeout for OONI calls. |
| `OONI_SUCCESS_THRESHOLD` | `0.7` | OK-rate threshold to mark a host reachable. |
| `OONI_BLOCKED_THRESHOLD` | `0.5` | Confirmed-block ratio to mark a host blocked. |
| `OONI_MIN_MEASUREMENTS` | `3` | Min Iranian probes that must have tested the host. |
| `CROWD_ENABLED` | `true` | Toggle the crowdsource layer. |
| `CROWD_COUNTRY` | `IR` | ISO-2 country triggering ingest from the WebApp's `country` field. |
| `CROWD_MAX_AGE_S` | `1200` | Rolling window length (20 min). |
| `CROWD_MAX_PER_MESSENGER` | `30` | Ring-buffer size per messenger. |
| `CROWD_DEDUP_WINDOW_S` | `1200` | Per-(user, messenger) dedup window. |
| `CROWD_MIN_SAMPLES` | `3` | Min DISTINCT-user samples before crowd emits a verdict. |
| `CROWD_SUCCESS_THRESHOLD` | `0.7` | Yes-rate threshold for `True`. |
| `CROWD_BLOCKED_THRESHOLD` | `0.3` | Yes-rate threshold for `False`. |

#### Source 4 (lowest) — ASN classifier (always on, free)

Some messenger TURN servers (notably Eitaa) sit on **Iran-only ASNs**.
By BGP rules, only Iranian-resident clients can route to those hosts at
all — so we already know the call works from Iran without sending any
packets. This is a deterministic, structural verdict.

The classifier reads `ping_luma/asn_map.json`. Bake it before deploy and
weekly thereafter:

```bash
python -m scripts.refresh_asn_map
```

The script resolves every messenger host, queries `api.bgpview.io` for
the announcing AS, and writes a fresh JSON. No API key required.

#### Source 3 — OONI (free, no key)

OONI's volunteer-run probes around the world report `web_connectivity`
results per country. The bot queries the per-domain aggregation for
Iran over the last `OONI_LOOKBACK_DAYS` and turns it into a chat-side
verdict:

* High `ok_count` → host is reachable from Iran today.
* High `confirmed_count` → host is confirmed blocked in Iran.
* Otherwise → silent.

OONI never measures WebRTC, so it deliberately produces no `call_ok`
verdict. Cached aggressively (24h) since underlying data refreshes daily.
Coverage is patchy for niche Iranian TURN domains, but mainstream
messenger origins are usually well-covered.

#### Source 2 — Crowdsource (free, live)

When a user opens the WebApp from an Iranian-routed connection (resident
*or* on an Iranian-exit VPN), their browser performs a real WebRTC ICE
gather, real DNS-over-HTTPS, and real `fetch()` against messenger
origins. That's the highest-fidelity *measured* signal we have in this
release.

The bot ingests these samples into a small in-memory store
(`ping_luma/crowdsource.py`) keyed by hashed user IDs, with a 20-min
rolling window and a per-user dedup window. Once `CROWD_MIN_SAMPLES`
distinct Iranian users have contributed for a given messenger, the
store emits a verdict and the façade overlays it on top of OONI.

**Privacy.** No PII is stored. Telegram user IDs are HMAC-SHA256 hashed
against a pepper generated freshly per process restart. Nothing is
written to disk; samples expire automatically.

**Cold start.** Below `CROWD_MIN_SAMPLES`, the layer emits no signal
and the lower-authority sources answer instead. So a freshly-deployed
bot still works — it just gets sharper as Iranian users start probing.

#### Source 1 (highest) — HTTP override (optional)

If you ever spin up your own Iranian probe service, expose a JSON
endpoint and point `IRAN_REFERENCE_URL` at it. Its results win over
every other source. Expected shape:

```
GET /reference  →  {
  "ts": "2026-04-26T20:00:00Z",
  "results": {
    "bale":   {"chat_ok": true, "call_ok": true},
    "eitaa":  {"chat_ok": true, "call_ok": true},
    ...
  }
}
```

**Easiest free path — volunteer + GitHub Pages-style hosting:** if you
have one trusted person inside Iran with any always-on device (PC, old
Android phone with Termux, Raspberry Pi), they can register as a
self-hosted GitHub Actions runner that probes every 30 min and commits
the JSON to a public repo. The bot fetches it via
`raw.githubusercontent.com` — entirely free, no Iranian VPS required.

Step-by-step setup walkthrough (operator + volunteer): see
[`volunteer-repo/README.md`](volunteer-repo/README.md). The
`volunteer-repo/` directory is a copy-pasteable template — clone an
empty public repo, drop the contents in, point GitHub Actions at it,
and you're done.

The publisher itself is shipped as a CLI in this package:

```bash
python -m ping_luma.publish_iran_reference --output iran-ref.json --pretty
```

Internally it just calls `ping_luma.checker.run_full_scan()` and
`ping_luma.checker.to_iran_reference_payload()`, which are also exposed
if you want to build something custom.

---

### Deploy checklist

1. `cp .env.example .env` and fill in `BOT_TOKEN`, `WEBAPP_URL`. Leave
   `OONI_ENABLED=true` and `CROWD_ENABLED=true`.
2. `python -m scripts.refresh_asn_map` — bakes `ping_luma/asn_map.json`.
3. Start the bot. On boot it will log:
   ```
   Iran reference enabled: ASN(N hosts) + OONI(7d lookback) + Crowd(IR, min=3, age=1200s)
   ```
4. OONI lookups are lazy and per-host; first user message warms its
   cache, then it stays warm for 24 h per host. The background refresh
   loop also pre-warms it every `IRAN_REFERENCE_TTL_S` seconds.
5. Crowdsource starts cold and warms up as Iranian users open the
   WebApp. After ~3 distinct Iranian users have probed a given
   messenger, it begins overriding OONI verdicts for that messenger.
   There is no manual seeding step.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --cov=ping_luma --cov-report=term-missing
```

---

## License

MIT
