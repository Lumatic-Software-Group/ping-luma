from __future__ import annotations

import asyncio
import json
import logging

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from ping_luma.application.iran_reference import IranReferenceClient
from ping_luma.domain.messengers import MESSENGERS
from ping_luma.infrastructure import config, paas_health, usage_log
from ping_luma.infrastructure.asn import AsnMap
from ping_luma.infrastructure.crowdsource import CrowdSourceStore
from ping_luma.infrastructure.ooni import OoniClient
from ping_luma.presentation.formatters import (
    format_messenger_info,
    format_messenger_list,
    format_webapp_report,
    get_messenger,
)
from ping_luma.presentation.marketing import (
    compose_webapp_reply_html,
    contact_channel_kb,
    pick_marketing_block,
    should_show_iran_messenger_hook,
    smart_start_reply_markup,
    webapp_reply_markup,
    with_sales_footer,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx/httpcore log every request url at info
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("PingLuma")


def _schedule_stats(
        user_id: int | None,
        action: str,
        detail: str | None = None,
        telegram_username: str | None = None,
) -> None:
    if user_id is None or not usage_log.configured():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        asyncio.to_thread(
            usage_log.submit,
            user_id,
            action,
            detail,
            telegram_username,
        )
    )


MSG_WELCOME = (
    "<b>پینگ‌لوما</b>\n\n"
    "بررسی می‌کنیم پیام‌رسان‌های ایرانی از <b>شبکه شما</b> در دسترس هستند یا نه - "
    "چه برای چت، چه برای تماس.\n\n"
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

# see https://core.telegram.org/bots/webapps#initializing-mini-apps (sendData).
BTN_WEBAPP = "🌐 بررسی از شبکه شما"
BTN_LIST = "📋 فهرست پیام‌رسان‌ها"
BTN_SMART_START = "🏗️ شروع هوشمند بیزنس"

_PENDING_CONTACT: dict[int, str] = {}
_CONTACT_LABELS = {
    "urgent": "درخواست مشاوره فوری",
    "strategy": "درخواست استراتژی محتوا و برندینگ",
    "website": "درخواست مشاوره راه‌اندازی سایت و اپلیکیشن",
}


def _main_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text=BTN_WEBAPP, web_app=WebAppInfo(url=config.WEBAPP_URL))],
            [KeyboardButton(text=BTN_LIST)],
            [KeyboardButton(text=BTN_SMART_START)],
        ],
        resize_keyboard=True,
    )


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


def _webapp_inline_kb(show_connectivity_cta: bool) -> InlineKeyboardMarkup:
    return webapp_reply_markup(show_connectivity_cta)


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    _schedule_stats(
        u.id if u else None,
        "start",
        telegram_username=u.username if u else None,
    )
    await update.message.reply_text(
        with_sales_footer(MSG_WELCOME),
        parse_mode=ParseMode.HTML,
        reply_markup=_main_reply_kb(),
    )
    await update.message.reply_text(
        "<b>برای ارتباط با تیم لوماتیک، پلتفرم مورد نظر را انتخاب کنید</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=contact_channel_kb(),
    )


async def cmd_list(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    _schedule_stats(
        u.id if u else None,
        "list",
        telegram_username=u.username if u else None,
    )
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
    user_id = query.from_user.id
    _schedule_stats(
        user_id,
        f"callback:{data}"[:2000],
        telegram_username=query.from_user.username,
    )

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
            await query.message.reply_text(
                MSG_UNKNOWN,
                parse_mode=ParseMode.HTML,
            )
            return
        await query.message.reply_text(
            format_messenger_info(m),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    elif data == "back":
        await query.message.reply_text(
            MSG_BACK_MENU,
            parse_mode=ParseMode.HTML,
            reply_markup=_main_reply_kb(),
        )

    elif data.startswith("contact:"):
        intent = data.split(":", 1)[1]
        _PENDING_CONTACT[user_id] = intent
        await query.message.reply_text(
            "برای ارتباط با تیم لوماتیک، پلتفرم مورد نظر را انتخاب کنید",
            parse_mode=ParseMode.HTML,
            reply_markup=contact_channel_kb(),
        )

    elif data.startswith("channel:"):
        channel = data.split(":", 1)[1]
        intent = _PENDING_CONTACT.pop(user_id, None)
        label = _CONTACT_LABELS.get(intent, "مشاوره")
        if channel == "wa":
            url = f"{config.LUMATIC_WA_URL}"
        else:
            url = config.LUMATIC_TG_URL
        await query.message.reply_text(
            f"برای <b>{label}</b> روی لینک زیر بزنید:\n\n"
            f'<a href="{url}">شروع مکالمه</a>',
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )


async def on_webapp_data(
        update: Update, ctx: ContextTypes.DEFAULT_TYPE
) -> None:
    raw = update.message.web_app_data.data if update.message.web_app_data else ""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        await update.message.reply_text(
            with_sales_footer(MSG_BAD_PAYLOAD),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_reply_kb(),
        )
        return

    if not isinstance(payload, dict) or payload.get("kind") != "pingluma_result":
        await update.message.reply_text(
            with_sales_footer(MSG_BAD_PAYLOAD),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_reply_kb(),
        )
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

    report = format_webapp_report(payload, iran_ref=iran_ref)
    text = compose_webapp_reply_html(report, payload)
    show_c = should_show_iran_messenger_hook(payload)
    u = update.effective_user
    _schedule_stats(
        u.id if u else None,
        "webapp_result",
        usage_log.webapp_payload_detail(payload),
        telegram_username=u.username if u else None,
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_webapp_inline_kb(show_c),
        disable_web_page_preview=True,
    )


async def cmd_smart_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    _schedule_stats(
        u.id if u else None,
        "smart_start",
        telegram_username=u.username if u else None,
    )
    await update.message.reply_text(
        with_sales_footer(pick_marketing_block()),
        parse_mode=ParseMode.HTML,
        reply_markup=smart_start_reply_markup(),
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
    # polling cannot run while a webhook is set; HTTP 409 Conflict.
    await app.bot.delete_webhook(drop_pending_updates=config.DROP_PENDING)
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "شروع و منوی اصلی"),
            BotCommand("list", "فهرست پیام‌رسان‌ها"),
        ])
    except Exception as exc:
        log.warning("set_my_commands failed: %s", exc)

    if usage_log.configured():
        try:
            await asyncio.to_thread(usage_log.ensure_schema)
        except Exception as exc:
            log.warning("usage DB schema init failed: %s", exc)

    iran_client: IranReferenceClient = app.bot_data["iran_ref"]
    if not iran_client.configured:
        return
    try:
        await iran_client.refresh(force=True)
    except Exception as exc:
        log.warning("initial iran-ref refresh failed: %s", exc)
    app.bot_data["iran_ref_task"] = asyncio.create_task(_iran_refresh_loop(app))


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        log.error(
            "Telegram 409 Conflict: another client is already calling getUpdates for this "
            "bot token. Stop every other instance (second container, local run, old VPS), "
            "scale hosting to one replica, and revoke the token in BotFather if it leaked. "
            "Original error: %s",
            err,
        )
        return
    log.exception("Unhandled error while processing update", exc_info=err)


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
    # PaaS probes :PORT (e.g. 8080) over HTTP before the process is "healthy" — bind first.
    paas_health.start_background()
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
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_LIST}$"), cmd_list)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_SMART_START}$"), cmd_smart_start)
    )
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data)
    )
    app.add_error_handler(_on_error)

    app.run_polling(drop_pending_updates=config.DROP_PENDING)


if __name__ == "__main__":
    main()
