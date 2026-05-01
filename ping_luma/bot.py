from __future__ import annotations

import asyncio
import json
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from ping_luma import config
from ping_luma.asn import AsnMap
from ping_luma.crowdsource import CrowdSourceStore
from ping_luma.formatters import (
    format_messenger_info,
    format_messenger_list,
    format_webapp_report,
    get_messenger,
)
from ping_luma.iran_reference import IranReferenceClient
from ping_luma.messengers import MESSENGERS
from ping_luma.ooni import OoniClient

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("PingLuma")

MSG_WELCOME = (
    "<b>پینگ‌لوما</b>\n\n"
    "بررسی می‌کنیم پیام‌رسان‌های ایرانی از <b>شبکه شما</b> در دسترس هستند یا نه — "
    "چه برای چت، چه برای تماس صوتی و تصویری.\n\n"
    "<b>چرا داشبورد؟</b>\n"
    "این بات روی سرور اجرا می‌شود، نه روی گوشی شما. تنها راه درست برای دیدن "
    "وضعیت <b>از شبکه خودِ شما</b>، باز کردن داشبورد است؛ تست‌ها از همان "
    "اینترنت وای‌فای یا داده‌ی موبایل شما انجام می‌شوند.\n\n"
    "پیام‌رسان‌های پشتیبانی‌شده:\n"
    "<b>بله · ایتا · روبیکا · گپ · آی‌گپ · سروش‌پلاس</b>"
)

MSG_BACK_MENU = "یک گزینه را انتخاب کنید:"
MSG_UNKNOWN = "پیام‌رسان ناشناخته."
MSG_BAD_PAYLOAD = (
    "داده‌ی دریافت‌شده از داشبورد قابل خواندن نبود. لطفاً دوباره تلاش کنید."
)


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🌐 بررسی از شبکه شما",
                web_app=WebAppInfo(url=config.WEBAPP_URL),
            ),
        ],
        [InlineKeyboardButton("📋 فهرست پیام‌رسان‌ها", callback_data="list")],
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


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        MSG_WELCOME,
        parse_mode=ParseMode.HTML,
        reply_markup=_main_kb(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_list(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        format_messenger_list(),
        parse_mode=ParseMode.HTML,
        reply_markup=_detail_kb(),
        disable_web_page_preview=True,
    )


async def on_button(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "list":
        await query.message.reply_text(
            format_messenger_list(),
            parse_mode=ParseMode.HTML,
            reply_markup=_detail_kb(),
            disable_web_page_preview=True,
        )

    elif data.startswith("detail:"):
        messenger_id = data.split(":", 1)[1]
        m = get_messenger(messenger_id)
        if not m:
            await query.message.reply_text(MSG_UNKNOWN, parse_mode=ParseMode.HTML)
            return
        await query.message.reply_text(
            format_messenger_info(m),
            parse_mode=ParseMode.HTML,
            reply_markup=_back_kb(),
            disable_web_page_preview=True,
        )

    elif data == "back":
        await query.message.reply_text(
            MSG_BACK_MENU,
            parse_mode=ParseMode.HTML,
            reply_markup=_main_kb(),
        )


async def on_webapp_data(
        update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> None:
    raw = update.message.web_app_data.data if update.message.web_app_data else ""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        await update.message.reply_text(MSG_BAD_PAYLOAD, parse_mode=ParseMode.HTML)
        return

    if not isinstance(payload, dict) or payload.get("kind") != "pingluma_result":
        await update.message.reply_text(MSG_BAD_PAYLOAD, parse_mode=ParseMode.HTML)
        return

    iran_client: IranReferenceClient = ctx.application.bot_data["iran_ref"]

    # Crowdsource ingest: if this user's WebApp reports an Iranian-routed
    # connection (resident or on an Iranian-exit VPN), their measurement
    # is the highest-fidelity Iran-side signal we can collect. The store
    # itself filters by country and dedups by hashed user id.
    crowd = iran_client.crowdsource
    user = update.effective_user
    if crowd is not None and user is not None:
        try:
            await crowd.ingest_payload(user_id=user.id, payload=payload)
        except Exception as exc:
            log.debug("crowdsource ingest failed: %s", exc)

    iran_ref = await iran_client.refresh()

    text = format_webapp_report(payload, iran_ref=iran_ref)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_main_kb(),
        disable_web_page_preview=True,
    )


def _build_iran_reference() -> IranReferenceClient:
    asn_map = AsnMap(config.ASN_MAP_PATH)
    ooni = OoniClient(
        enabled=config.OONI_ENABLED,
        lookback_days=config.OONI_LOOKBACK_DAYS,
        ttl_s=config.OONI_TTL_S,
        http_timeout_s=config.OONI_TIMEOUT_S,
        success_threshold=config.OONI_SUCCESS_THRESHOLD,
        confirmed_blocked_threshold=config.OONI_BLOCKED_THRESHOLD,
        min_measurements=config.OONI_MIN_MEASUREMENTS,
    )
    crowd = CrowdSourceStore(
        enabled=config.CROWD_ENABLED,
        country_filter=config.CROWD_COUNTRY,
        max_age_s=config.CROWD_MAX_AGE_S,
        max_per_messenger=config.CROWD_MAX_PER_MESSENGER,
        dedup_window_s=config.CROWD_DEDUP_WINDOW_S,
        min_samples=config.CROWD_MIN_SAMPLES,
        success_threshold=config.CROWD_SUCCESS_THRESHOLD,
        blocked_threshold=config.CROWD_BLOCKED_THRESHOLD,
    )
    client = IranReferenceClient(
        http_url=config.IRAN_REFERENCE_URL,
        http_token=config.IRAN_REFERENCE_TOKEN,
        http_timeout_s=config.IRAN_REFERENCE_TIMEOUT_S,
        asn_map=asn_map,
        ooni=ooni,
        crowdsource=crowd,
        ttl_s=config.IRAN_REFERENCE_TTL_S,
    )

    sources = []
    if asn_map and len(asn_map) > 0:
        sources.append(f"ASN({len(asn_map)} hosts)")
    if ooni.configured:
        sources.append(f"OONI({config.OONI_LOOKBACK_DAYS}d lookback)")
    if crowd.configured:
        sources.append(
            f"Crowd({config.CROWD_COUNTRY},"
            f" min={config.CROWD_MIN_SAMPLES},"
            f" age={config.CROWD_MAX_AGE_S}s)"
        )
    if config.IRAN_REFERENCE_URL:
        sources.append(f"HTTP({config.IRAN_REFERENCE_URL})")
    if sources:
        log.info("Iran reference enabled: %s", " + ".join(sources))
    else:
        log.info("Iran reference: no sources configured — falling back to static priors")
    return client


async def _iran_refresh_loop(app: Application) -> None:
    """Background task: keep the Iran-reference cache warm.

    Runs forever at ``IRAN_REFERENCE_TTL_S`` cadence. Survives transient
    failures (the underlying refresh swallows per-source errors). Mostly
    keeps the HTTP override fresh and pre-warms OONI's per-host cache.
    """
    iran_client: IranReferenceClient = app.bot_data["iran_ref"]
    interval = max(60, config.IRAN_REFERENCE_TTL_S)
    while True:
        try:
            await iran_client.refresh(force=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("iran-ref refresh loop error: %s", exc)
        await asyncio.sleep(interval)


async def _post_init(app: Application) -> None:
    iran_client: IranReferenceClient = app.bot_data["iran_ref"]
    if not iran_client.configured:
        return
    try:
        await iran_client.refresh(force=True)
    except Exception as exc:
        log.warning("initial iran-ref refresh failed: %s", exc)
    app.bot_data["iran_ref_task"] = asyncio.create_task(_iran_refresh_loop(app))


async def _post_shutdown(app: Application) -> None:
    task: asyncio.Task | None = app.bot_data.get("iran_ref_task")
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def main() -> None:
    log.info("Starting PingLuma bot")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set")

    request_kwargs: dict = dict(
        connect_timeout=config.CONNECT_TIMEOUT,
        read_timeout=config.READ_TIMEOUT,
        write_timeout=config.WRITE_TIMEOUT,
    )
    if config.PROXY_URL:
        request_kwargs["proxy"] = config.PROXY_URL
        log.info("Using proxy: %s", config.PROXY_URL)

    iran_client = _build_iran_reference()

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .base_url(config.BASE_URL)
        .request(HTTPXRequest(**request_kwargs))
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["iran_ref"] = iran_client

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data)
    )

    app.run_polling(drop_pending_updates=config.DROP_PENDING)


if __name__ == "__main__":
    main()
