# بله‌چک — Bale Connectivity Monitor

[![CI](https://github.com/YOUR_ORG/ping-luma/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/ping-luma/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

A Persian-language tool for monitoring Bale Messenger connectivity.
Ships as a Bale/Telegram bot **and** a standalone browser dashboard.

---

## Project Structure

```
ping-luma/
├── .github/
│   └── workflow/
│       └── ci.yml              # Lint → Test → Docker build → Deploy
├── ping_luma/               # Python package
│   ├── __init__.py
│   ├── config.py               # All settings via env vars
│   ├── checker.py              # Connectivity engine (probes, scoring)
│   └── bot.py                  # Bale / Telegram bot with TTL cache
├── web/
│   └── dashboard.html          # Persian browser dashboard (no server needed)
├── test/
│   ├── __init__.py
│   └── test_checker.py         # Unit tests (offline, all network mocked)
├── .env.example                # Environment variable template
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml              # Ruff + Mypy + Pytest config
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Cache Fix — What Was Wrong

The previous version stored `CheckReport` objects with **no expiry**:
```python
# BUG: never expires
_cache: Dict[int, CheckReport] = {}
```

Now every entry is stored with a timestamp and expired after `CACHE_TTL` seconds:
```python
# FIX: (report, cached_at_epoch) with TTL
_cache: Dict[int, Tuple[CheckReport, float]] = {}
```

`/status` now **auto-reruns a fresh check** when the cache is expired instead
of silently returning stale data.

Also changed `drop_pending_updates=False` (was `True`) so messages sent
while the bot restarts during development are never silently dropped.

---

## Quick Start

### 1 — Environment

```bash
cp .env.example .env
# Edit .env — set BOT_TOKEN at minimum
```

### 2 — Local (venv)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m ping_luma.bot
```

### 3 — Docker

```bash
docker compose up -d
docker compose logs -f bot
```

---

## Web Dashboard

Open `web/dashboard.html` directly in any browser — no server required.
All checks run client-side via `fetch()`.

| Mode | What it checks | Time |
|---|---|---|
| ⚡ پینگ سریع | API gateway only | ~2 sec |
| 🔍 بررسی کامل | 4 servers + 3 DNS records + score | ~10 sec |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome + inline buttons |
| `/check` | Full connectivity report |
| `/quick` | Fast single ping to `tapi.bale.ai` |
| `/status` | Last cached result (auto-refreshes if expired) |
| `/help` | Command list |

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | **Required.** From `@BotFather_bot` on Bale |
| `BASE_URL` | https://api.telegram.org/bot` | Bale or Telegram API base |
| `PROXY_URL` | *(empty)* | `socks5://...` or `http://...` if no system VPN |
| `CONNECT_TIMEOUT` | `30` | Seconds for initial connection |
| `READ_TIMEOUT` | `30` | Seconds to wait for response |
| `WRITE_TIMEOUT` | `30` | Seconds to wait on send |
| `CACHE_TTL` | `300` | Seconds before `/status` runs a fresh check |
| `AUTO_CHECK_INTERVAL` | `15` | Minutes between background probes (0 = off) |
| `ALERT_CHAT_IDS` | *(empty)* | Comma-separated chat IDs for status-change alerts |

---

## CI/CD Pipeline

```
Push / PR
    │
    ├─► lint        ruff check + ruff format + mypy
    │
    ├─► test        pytest on Python 3.9 / 3.10 / 3.11
    │               + coverage report uploaded to Codecov
    │
    ├─► docker      docker buildx (no push on PR)
    │
    └─► deploy      (main branch only)
                    docker build + push to Docker Hub
                    SSH → docker compose pull + up -d
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token |
| `DEPLOY_HOST` | Production server IP |
| `DEPLOY_USER` | SSH user on server |
| `DEPLOY_SSH_KEY` | Private SSH key (paste full contents) |

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --cov=ping_luma --cov-report=term-missing
```

All tests are **offline** — network calls are mocked.

---

## Getting a Bot Token (Bale)

1. Open Bale → search `@BotFather_bot`
2. Send `/newbot`
3. Follow prompts and copy the token
4. Set `BOT_TOKEN=<token>` in your `.env`