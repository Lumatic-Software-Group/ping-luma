# PingLuma

[![CI](https://github.com/YOUR_ORG/pingluma/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/pingluma/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**@ping_luma_bot** — Check whether Iranian messengers are reachable from
*your* network, in real time.

PingLuma probes 7 Iranian messenger platforms concurrently from the caller's
network and reports which ones are accessible.
It ships as a Telegram bot and a standalone browser dashboard.

---

## Supported Messengers

| Messenger | فارسی | Availability | Description |
|---|---|---|---|
| Bale | بله | Global | Messaging + payment by Bank Melli Iran |
| Eitaa | ایتا | Mixed | Islamic-values messaging app |
| Rubika | روبیکا | Mixed | Social messenger by MCI (Hamrah-e-Aval) |
| Gap | گپ | Global | Cross-platform messenger |
| iGap | آی‌گپ | Global | Feature-rich messenger with VoIP |
| Soroush Plus | سروش‌پلاس | Mixed | IRIB state-affiliated messenger |
| Shad | شاد | Iran-only | Ministry of Education messenger |

**Availability:**
- Global — designed for worldwide use
- Mixed — globally reachable but some features are Iran-only
- Iran-only — domestic only; expected to be blocked outside Iran

---

## Project Structure

```
ping-luma/
├── .github/
│   └── workflows/
│       └── ci.yml
├── ping_luma/
│   ├── __init__.py
│   ├── config.py
│   ├── messengers.py
│   ├── checker.py
│   └── bot.py
├── web/
│   └── dashboard.html
├── tests/
│   ├── __init__.py
│   └── test_pingluma.py
├── .env.example
├── .gitignore
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

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message + inline menu |
| `/scan`  | Full scan — all 7 messengers concurrently (~15 s) |
| `/quick` | Fast single ping — Bale API only (~2 s) |
| `/list`  | Browse all messengers with one-tap detail probes |
| `/help`  | Command list |

---

## Architecture

```
User (any country)
       │
       ├── Telegram → @ping_luma_bot
       │       └── bot.py
       │               ├── /scan  → run_full_scan()
       │               │       └── ThreadPoolExecutor (7 workers)
       │               │               └── _check_one_messenger() per messenger
       │               │                       ├── _probe_url()  (HTTPS + SSL)
       │               │                       └── _probe_dns()  (socket resolve)
       │               ├── /quick → run_quick_ping()
       │               └── /list  → _check_one_messenger() on demand
       │
       └── Browser → web/dashboard.html
               └── fetch() + Image DNS trick (client-side, no server required)
```

### Scoring

Each messenger is scored 0–100:

| Component | Weight |
|---|---|
| URL reachability | 60 pts (proportional) |
| DNS resolution | 30 pts (proportional) |
| Latency bonus (< 500 ms) | +10 pts |
| Latency bonus (< 1200 ms) | +5 pts |

| Score | Verdict |
|---|---|
| ≥ 70 | REACHABLE |
| 30–69 | PARTIAL |
| < 30 | BLOCKED |

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | **Required.** From @BotFather |
| `BASE_URL` | `https://api.telegram.org/bot` | Telegram API base URL |
| `PROXY_URL` | *(empty)* | `socks5://…` or `http://…` proxy |
| `CONNECT_TIMEOUT` | `30` | Seconds |
| `READ_TIMEOUT` | `30` | Seconds |
| `WRITE_TIMEOUT` | `30` | Seconds |
| `DROP_PENDING` | `true` | Discard queued updates on startup |
| `SCAN_COOLDOWN` | `30` | Minimum seconds between scans per user |
| `AUTO_CHECK_INTERVAL` | `30` | Minutes between background broadcasts (0 = off) |
| `ALERT_CHAT_IDS` | *(empty)* | Comma-separated chat IDs for status-change alerts |

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --cov=pingluma --cov-report=term-missing
```