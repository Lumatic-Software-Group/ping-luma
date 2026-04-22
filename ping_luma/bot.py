import asyncio
import logging
import time
from typing import Dict, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from ping_luma import config
from ping_luma.checker import (
    ScanReport,
    _check_one_messenger,
    format_messenger_detail,
    format_scan_report,
    run_full_scan,
    run_quick_ping,
)
from ping_luma.messengers import MESSENGER_BY_ID, MESSENGERS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("PingLuma")

BOT_START_TIME: int = int(time.time())

_cooldown: Dict[int, float] = {}

_last_broadcast_summary: str = ""

MSG_WELCOME = (
    "<b>خوش آمدید</b> — @ping_luma_bot\n\n"
    "این ربات بررسی می‌کند که آیا پیام‌رسان‌های ایرانی از شبکه شما قابل دسترس هستند یا خیر.\n\n"
    "━━━━━━━━━━━━━━━━━\n"
    "/scan   — بررسی کامل پیام‌رسان ها)\n"
    "/quick  — پینگ سریع\n"
    "/list   — فهرست پیام‌رسان‌های پشتیبانی‌شده\n"
    "━━━━━━━━━━━━━━━━━\n\n"
    "پیام‌رسان‌های بررسی‌شده: <b>بله، ایتا، روبیکا، گپ، آی‌گپ، سروش‌پلاس</b>\n\n"
    "برای شروع یک دکمه را بزنید:"
)

MSG_SCAN_RUNNING = (
    "در حال بررسی همه پیام‌رسان‌های ایرانی…\n"
    "بررسی ۷ پیام‌رسان به صورت همزمان — معمولاً حدود ۱۵ ثانیه طول می‌کشد."
)

MSG_COOLDOWN = "لطفاً {secs} ثانیه صبر کنید و سپس دوباره بررسی را اجرا کنید."
MSG_QUICK_RUNNING = "در حال پینگ سرور اصلی بله…"
MSG_PROBING = "در حال بررسی <b>{name}</b> — لطفاً صبر کنید…"
MSG_UNKNOWN = "پیام‌رسان ناشناخته."
MSG_BACK_MENU = "<b>خوش آمدید</b> — یک گزینه را انتخاب کنید:"
MSG_STALE_SESSION = (
    "این نشست منقضی شده.\n"
    "لطفاً /start بزنید تا منوی جدید باز شود."
)

MSG_QUICK_OK = (
    "✅ <b>سرور بله از شبکه شما در دسترس است</b>\n"
    "تأخیر: <code>{lat:.0f}ms</code>\n\n"
    "برای بررسی همه ۷ پیام‌رسان از /scan استفاده کنید."
)

MSG_QUICK_FAIL = (
    "❌ <b>سرور بله از شبکه شما در دسترس نیست</b>\n\n"
    "برای گزارش کامل از /scan استفاده کنید."
)

_AVAILABILITY_LABEL = {
    "global": "در دسترس جهانی",
    "mixed": "دسترسی ترکیبی",
    "iran": "مخصوص ایران",
}


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("بررسی کامل", callback_data="scan"),
            InlineKeyboardButton("پینگ سریع", callback_data="quick"),
        ],
        [
            InlineKeyboardButton("فهرست پیام‌رسان‌ها", callback_data="list"),
        ],
    ])


def _detail_kb() -> InlineKeyboardMarkup:
    rows, row = [], []
    for m in MESSENGERS:
        row.append(InlineKeyboardButton(
            f"{m.name_fa}", callback_data=f"detail:{m.id}"
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("بازگشت", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("بازگشت به منو", callback_data="back")]
    ])


# Rate limiting
def _is_on_cooldown(chat_id: int) -> Tuple[bool, int]:
    elapsed = time.time() - _cooldown.get(chat_id, 0)
    remaining = int(config.SCAN_COOLDOWN - elapsed)
    return remaining > 0, max(remaining, 0)


def _mark_scan(chat_id: int) -> None:
    _cooldown[chat_id] = time.time()


async def _reject_stale(query) -> bool:
    """
    Reject an inline button press if it came from a message sent before this
    process started. Removes the keyboard so the user cannot press it again.
    """
    if query.message.date.timestamp() >= BOT_START_TIME:
        return False
    await query.answer(MSG_STALE_SESSION, show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    return True


async def _do_scan(chat_id: int, reply_fn) -> None:
    """Run a full scan and send/edit the result message."""
    on_cd, secs = _is_on_cooldown(chat_id)
    if on_cd:
        await reply_fn(
            MSG_COOLDOWN.format(secs=secs),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_kb(),
        )
        return

    _mark_scan(chat_id)
    status_msg = await reply_fn(MSG_SCAN_RUNNING, parse_mode=ParseMode.HTML)
    report: ScanReport = await asyncio.to_thread(run_full_scan)
    await status_msg.edit_text(
        format_scan_report(report),
        parse_mode=ParseMode.HTML,
        reply_markup=_main_kb(),
    )


async def _do_quick(reply_fn) -> None:
    """Run a quick ping against Bale and send/edit the result message."""
    status_msg = await reply_fn(MSG_QUICK_RUNNING, parse_mode=ParseMode.HTML)
    reachable, latency = await asyncio.to_thread(run_quick_ping, "bale")
    text = MSG_QUICK_OK.format(lat=latency) if reachable else MSG_QUICK_FAIL
    await status_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_main_kb(),
    )


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        MSG_WELCOME,
        parse_mode=ParseMode.HTML,
        reply_markup=_main_kb(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_scan(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_scan(update.effective_chat.id, update.message.reply_text)


async def cmd_quick(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_quick(update.message.reply_text)


async def cmd_list(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["<b>پیام‌رسان‌های ایرانی پشتیبانی‌شده</b>\n"]
    for m in MESSENGERS:
        avail = _AVAILABILITY_LABEL.get(m.availability, "")
        lines.append(f"<b>{m.name}</b> ({m.name_fa})  —  {avail}")
    lines.append("\n<i>برای بررسی جزئیات یک پیام‌رسان روی دکمه‌های زیر بزنید:</i>")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=_detail_kb(),
    )


async def on_button(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id

    if await _reject_stale(query):
        return

    await query.answer()
    data = query.data or ""

    if data == "scan":
        await _do_scan(chat_id, query.message.reply_text)

    elif data == "quick":
        await _do_quick(query.message.reply_text)

    elif data == "list":
        lines = ["<b>پیام‌رسان‌های ایرانی پشتیبانی‌شده</b>\n"]
        for m in MESSENGERS:
            avail = _AVAILABILITY_LABEL.get(m.availability, "")
            lines.append(f"<b>{m.name}</b> ({m.name_fa})  —  {avail}")
        lines.append("\n<i>برای بررسی جزئیات یک پیام‌رسان روی دکمه‌های زیر بزنید:</i>")
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=_detail_kb(),
        )

    elif data.startswith("detail:"):
        messenger_id = data.split(":", 1)[1]
        m = MESSENGER_BY_ID.get(messenger_id)
        if not m:
            await query.message.reply_text(MSG_UNKNOWN, parse_mode=ParseMode.HTML)
            return
        status_msg = await query.message.reply_text(
            MSG_PROBING.format(name=m.name_fa),
            parse_mode=ParseMode.HTML,
        )
        result = await asyncio.to_thread(_check_one_messenger, m)
        await status_msg.edit_text(
            format_messenger_detail(result),
            parse_mode=ParseMode.HTML,
            reply_markup=_back_kb(),
        )

    elif data == "back":
        await query.message.reply_text(
            MSG_BACK_MENU,
            parse_mode=ParseMode.HTML,
            reply_markup=_main_kb(),
        )


async def _broadcast(app: Application) -> None:  # type: ignore[type-arg]
    """
    Run a full scan and notify ALERT_CHAT_IDS if the status summary changed
    since the last broadcast. Avoids flooding chats with identical reports.
    """
    global _last_broadcast_summary

    report: ScanReport = await asyncio.to_thread(run_full_scan)
    summary = f"{len(report.reachable)}/{len(report.results)}"

    if summary == _last_broadcast_summary:
        return
    _last_broadcast_summary = summary

    text = (
            f"<b>گزارش پینگ‌لوما</b>\n"
            f"{summary} از پیام‌رسان‌های ایرانی در حال حاضر قابل دسترس هستند.\n\n"
            + format_scan_report(report)
    )
    for chat_id in config.ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.warning("Broadcast to %s failed: %s", chat_id, exc)


def main() -> None:
    log.info("Starting PingLuma bot — drop_pending_updates=%s", config.DROP_PENDING)

    request_kwargs: Dict = dict(
        connect_timeout=config.CONNECT_TIMEOUT,
        read_timeout=config.READ_TIMEOUT,
        write_timeout=config.WRITE_TIMEOUT,
    )
    if config.PROXY_URL:
        request_kwargs["proxy"] = config.PROXY_URL
        log.info("Using proxy: %s", config.PROXY_URL)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .base_url(config.BASE_URL)
        .request(HTTPXRequest(**request_kwargs))
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("quick", cmd_quick))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CallbackQueryHandler(on_button))

    if config.AUTO_CHECK_INTERVAL > 0:
        app.job_queue.run_repeating(
            lambda _ctx: asyncio.ensure_future(_broadcast(app)),
            interval=config.AUTO_CHECK_INTERVAL * 60,
            first=120,
        )
        log.info("Background broadcast every %d minutes", config.AUTO_CHECK_INTERVAL)

    log.info(
        "PingLuma running | base=%s | cooldown=%ds | boot_ts=%d",
        config.BASE_URL,
        config.SCAN_COOLDOWN,
        BOT_START_TIME,
    )
    app.run_polling(drop_pending_updates=config.DROP_PENDING)


if __name__ == "__main__":
    main()