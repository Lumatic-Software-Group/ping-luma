"""
ping_luma/bot.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bale Messenger Bot — پایش اتصال

دستورات
  /start   — خوش‌آمد + راهنما
  /check   — بررسی کامل (سرورها + DNS + امتیاز)
  /quick   — پینگ سریع سرور اصلی
  /status  — آخرین نتیجه ذخیره‌شده (حداکثر ۵ دقیقه)
  /help    — راهنما

Cache fix
  هر نتیجه با یک timestamp ذخیره می‌شود.
  اگر نتیجه از CACHE_TTL ثانیه قدیمی‌تر باشد،
  /status به‌جای نمایش داده کهنه، یک بررسی تازه اجرا می‌کند.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from ping_luma import config
from ping_luma.checker import (
    CheckReport,
    report_to_text,
    run_full_check,
    run_quick_ping,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("BaleBot")

# ── TTL Cache ─────────────────────────────────────────────────────────────────
# Stores (report, cached_at_epoch) per chat_id.
# Entries older than config.CACHE_TTL seconds are treated as stale;
# /status will automatically trigger a fresh check in that case.

_cache: Dict[int, Tuple[CheckReport, float]] = {}
_cache_lock = threading.Lock()


def _get_cached(chat_id: int) -> Optional[CheckReport]:
    """Return cached report if still fresh, else None."""
    with _cache_lock:
        entry = _cache.get(chat_id)
    if entry is None:
        return None
    report, cached_at = entry
    age = time.time() - cached_at
    if age > config.CACHE_TTL:
        log.info("Cache expired for chat %s (age=%ds)", chat_id, int(age))
        return None
    return report


def _set_cached(chat_id: int, report: CheckReport) -> None:
    with _cache_lock:
        _cache[chat_id] = (report, time.time())

# ── Keyboard ──────────────────────────────────────────────────────────────────

def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 بررسی کامل", callback_data="check"),
            InlineKeyboardButton("⚡ پینگ سریع",  callback_data="quick"),
        ],
        [
            InlineKeyboardButton("📊 آخرین نتیجه", callback_data="status"),
        ],
    ])

# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
            r"👋 *به ربات بله‌چک خوش آمدید*" + "\n\n"
                                              r"این ربات وضعیت اتصال به بله را بررسی می‌کند\." + "\n\n"
                                                                                                 "━━━━━━━━━━━━━━━━━\n"
                                                                                                 r"🔍 /check  — بررسی کامل \(۴ سرور \+ DNS\)" + "\n"
                                                                                                                                               "⚡ /quick  — پینگ سریع سرور اصلی\n"
                                                                                                                                               "📊 /status — آخرین نتیجه ذخیره‌شده\n"
                                                                                                                                               "━━━━━━━━━━━━━━━━━\n\n"
                                                                                                                                               "یکی از دکمه‌های زیر را انتخاب کنید:"
    )
    await update.message.reply_text(
        text, parse_mode="MarkdownV2", reply_markup=_kb()
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def _run_and_reply_full(chat_id: int, reply_fn) -> None:
    """Run full check, update cache, send formatted result."""
    msg = await reply_fn(r"⏳ در حال بررسی… لطفاً صبر کنید \(~۱۰ ثانیه\)",
                         parse_mode="MarkdownV2")
    report = run_full_check()
    _set_cached(chat_id, report)
    await msg.edit_text(
        report_to_text(report), parse_mode="Markdown", reply_markup=_kb()
    )


async def cmd_check(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_and_reply_full(
        update.effective_chat.id, update.message.reply_text
    )


async def cmd_quick(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text("⚡ در حال پینگ سرور اصلی…")
    reachable, latency = run_quick_ping()
    if reachable:
        text = (
            f"✅ *سرور اصلی بله در دسترس است*\n"
            f"📶 تأخیر: `{latency:.1f}ms`\n\n"
            f"برای گزارش کامل از /check استفاده کنید"
        )
    else:
        text = (
            "❌ *سرور اصلی بله پاسخ نمی‌دهد*\n\n"
            "برای اطلاعات بیشتر از /check استفاده کنید"
        )
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=_kb())


async def cmd_status(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    report  = _get_cached(chat_id)

    if report is None:
        # Cache empty or expired → run a fresh check automatically
        await update.message.reply_text(
            "🔄 نتیجه‌ای در حافظه نیست یا منقضی شده — بررسی جدید شروع می‌شود…"
        )
        await _run_and_reply_full(chat_id, update.message.reply_text)
        return

    age_s  = int(time.time() - _cache[chat_id][1])
    header = f"📊 *آخرین نتیجه* — `{age_s}` ثانیه پیش\n\n"
    await update.message.reply_text(
        header + report_to_text(report),
        parse_mode="Markdown",
        reply_markup=_kb(),
        )

# ── Callback handler ──────────────────────────────────────────────────────────

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query   = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if query.data == "check":
        await _run_and_reply_full(chat_id, query.message.reply_text)

    elif query.data == "quick":
        # Reuse cmd_quick logic via a lightweight shim
        msg      = await query.message.reply_text("⚡ در حال پینگ سرور اصلی…")
        reachable, latency = run_quick_ping()
        if reachable:
            text = (
                f"✅ *سرور اصلی بله در دسترس است*\n"
                f"📶 تأخیر: `{latency:.1f}ms`\n\n"
                f"برای گزارش کامل از /check استفاده کنید"
            )
        else:
            text = (
                "❌ *سرور اصلی بله پاسخ نمی‌دهد*\n\n"
                "برای اطلاعات بیشتر از /check استفاده کنید"
            )
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=_kb())

    elif query.data == "status":
        report = _get_cached(chat_id)
        if report is None:
            await query.message.reply_text(
                "🔄 نتیجه‌ای در حافظه نیست یا منقضی شده — بررسی جدید شروع می‌شود…"
            )
            await _run_and_reply_full(chat_id, query.message.reply_text)
        else:
            age_s  = int(time.time() - _cache[chat_id][1])
            header = f"📊 *آخرین نتیجه* — `{age_s}` ثانیه پیش\n\n"
            await query.message.reply_text(
                header + report_to_text(report),
                parse_mode="Markdown",
                reply_markup=_kb(),
                )

# ── Auto-broadcast ────────────────────────────────────────────────────────────

_last_status: Optional[str] = None


async def _broadcast(app: Application) -> None:  # type: ignore[type-arg]
    global _last_status
    report = run_full_check()
    if report.overall_status == _last_status:
        return
    _last_status = report.overall_status
    badge = {"ONLINE": "🟢", "DEGRADED": "🟡", "OFFLINE": "🔴"}.get(
        report.overall_status, "⚪"
    )
    text = (
        f"{badge} *وضعیت بله تغییر کرد ← {report.overall_status}*\n"
        f"{report.summary}\n💡 {report.advice}"
    )
    for cid in config.ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(cid, text, parse_mode="Markdown")
        except Exception as exc:
            log.warning("Alert to %s failed: %s", cid, exc)

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    request_kwargs: Dict = dict(
        connect_timeout=config.CONNECT_TIMEOUT,
        read_timeout=config.READ_TIMEOUT,
        write_timeout=config.WRITE_TIMEOUT,
    )
    if config.PROXY_URL:
        request_kwargs["proxy"] = config.PROXY_URL
        log.info("Proxy: %s", config.PROXY_URL)
    else:
        log.info("No explicit proxy — using system routing")

    request = HTTPXRequest(**request_kwargs)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .base_url(config.BASE_URL)
        .request(request)
        .build()
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("check",  cmd_check))
    app.add_handler(CommandHandler("quick",  cmd_quick))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(on_button))

    if config.AUTO_CHECK_INTERVAL > 0:
        app.job_queue.run_repeating(
            lambda _ctx: asyncio.ensure_future(_broadcast(app)),
            interval=config.AUTO_CHECK_INTERVAL * 60,
            first=60,
        )
        log.info(
            "Auto-check every %d min — alerts → %s",
            config.AUTO_CHECK_INTERVAL, config.ALERT_CHAT_IDS,
        )

    log.info("Starting — base: %s  cache_ttl: %ds", config.BASE_URL, config.CACHE_TTL)
    # drop_pending_updates=False so we never miss messages sent while the bot
    # was restarting (e.g. during a hot-reload in development).
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()