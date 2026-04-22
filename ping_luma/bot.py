import asyncio
import logging
import time
from typing import Dict, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
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
    "<b>خوش آمدید به پینگ‌لوما</b>\n\n"
    "بررسی می‌کنیم که پیام‌رسان‌های ایرانی از شبکه شما قابل دسترس هستند یا نه —\n"
    "هم برای چت و هم برای تماس صوتی و تصویری.\n\n"
    "━━━━━━━━━━━━━━━━━\n"
    "🌐 <b>داشبورد وب</b> — بررسی دقیق از مرورگر شما\n"
    " <b>بررسی سریع</b> — وضعیت کلی پیام‌رسان‌ها\n"
    "━━━━━━━━━━━━━━━━━\n\n"
    "پیام‌رسان‌های پشتیبانی‌شده:\n"
    "<b>بله · ایتا · روبیکا · گپ · آی‌گپ · سروش‌پلاس</b>"
)

MSG_SCAN_RUNNING = "در حال بررسی پیام‌رسان‌ها… چند ثانیه صبر کنید."
MSG_QUICK_RUNNING = "در حال بررسی بله و روبیکا…"
MSG_COOLDOWN = "لطفاً {secs} ثانیه صبر کنید."
MSG_PROBING = "در حال بررسی <b>{name}</b>…"
MSG_UNKNOWN = "پیام‌رسان ناشناخته."
MSG_BACK_MENU = "یک گزینه را انتخاب کنید:"
MSG_STALE_SESSION = "این نشست منقضی شده.\nلطفاً /start را بزنید."

WEBAPP_URL: str = config.WEBAPP_URL  # e.g. "https://pingluma.app"


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🌐 بررسی از شبکه شما",
                web_app=WebAppInfo(url=WEBAPP_URL),
            ),
        ],
        [
            InlineKeyboardButton("بررسی سریع — بله و روبیکا", callback_data="quick"),
            InlineKeyboardButton("فهرست", callback_data="list"),
        ],
    ])


def _detail_kb() -> InlineKeyboardMarkup:
    rows, row = [], []
    for m in MESSENGERS:
        row.append(InlineKeyboardButton(m.name_fa, callback_data=f"detail:{m.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back")]
    ])


# Rate limiting
def _is_on_cooldown(chat_id: int) -> Tuple[bool, int]:
    elapsed = time.time() - _cooldown.get(chat_id, 0)
    remaining = int(config.SCAN_COOLDOWN - elapsed)
    return remaining > 0, max(remaining, 0)


def _mark_scan(chat_id: int) -> None:
    _cooldown[chat_id] = time.time()


async def _reject_stale(query) -> bool:
    if query.message.date.timestamp() >= BOT_START_TIME:
        return False
    await query.answer(MSG_STALE_SESSION, show_alert=True)
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    return True


async def _do_scan(chat_id: int, reply_fn) -> None:
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
    status_msg = await reply_fn(MSG_QUICK_RUNNING, parse_mode=ParseMode.HTML)

    (bale_ok, bale_lat), (rubika_ok, rubika_lat) = await asyncio.gather(
        asyncio.to_thread(run_quick_ping, "bale"),
        asyncio.to_thread(run_quick_ping, "rubika"),
    )

    def _row(ok: bool, lat: float, name: str, name_fa: str) -> str:
        if ok:
            return f"✅ <b>{name}</b> ({name_fa})  —  در دسترس  <code>{lat:.0f}ms</code>"
        return f"❌ <b>{name}</b> ({name_fa})  —  در دسترس نیست"

    text = (
            "<b>بررسی سریع</b>\n\n"
            + _row(bale_ok, bale_lat, "Bale", "بله") + "\n"
            + _row(rubika_ok, rubika_lat, "Rubika", "روبیکا") + "\n\n"
                                                                "<i>برای بررسی همه پیام‌رسان‌ها از داشبورد وب استفاده کنید.</i>"
    )
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
    lines = ["<b>پیام‌رسان‌های پشتیبانی‌شده</b>\n"]
    for m in MESSENGERS:
        lines.append(f"• <b>{m.name}</b> ({m.name_fa})")
    lines.append("\n<i>برای جزئیات یک پیام‌رسان را انتخاب کنید:</i>")
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
        lines = ["<b>پیام‌رسان‌های پشتیبانی‌شده</b>\n"]
        for m in MESSENGERS:
            lines.append(f"• <b>{m.name}</b> ({m.name_fa})")
        lines.append("\n<i>برای جزئیات یک پیام‌رسان را انتخاب کنید:</i>")
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


async def _broadcast(app: Application) -> None:
    global _last_broadcast_summary

    report: ScanReport = await asyncio.to_thread(run_full_scan)
    reachable_ids = ",".join(sorted(r.messenger.id for r in report.reachable))

    if reachable_ids == _last_broadcast_summary:
        return
    _last_broadcast_summary = reachable_ids

    text = format_scan_report(report)
    for chat_id in config.ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.warning("Broadcast to %s failed: %s", chat_id, exc)


def main() -> None:
    log.info("Starting PingLuma bot")

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
        log.info("Background broadcast every %d min", config.AUTO_CHECK_INTERVAL)

    app.run_polling(drop_pending_updates=config.DROP_PENDING)


if __name__ == "__main__":
    main()
