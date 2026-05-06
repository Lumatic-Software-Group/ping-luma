from __future__ import annotations

import random
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_IRAN_HOOK_IDS = frozenset({"bale", "rubika", "soroush"})
_DIVIDER = "• • • • • • • • • • •"


def should_show_iran_messenger_hook(payload: dict[str, Any]) -> bool:
    """True when Bale, Rubika, or Soroush+ is down or unstable (chat_ok is false)."""
    results = payload.get("results") or []
    if not isinstance(results, list):
        return False
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("id") not in _IRAN_HOOK_IDS:
            continue
        if r.get("chat_ok") is False:
            return True
    return False


def hook_connectivity_block() -> str:
    return (
        "<b>⚠️ ارتباط قطع شده، اما بیزنس شما نه!</b>\n\n"
        "ادمین‌های فروش شما در ایران آفلاین هستند؟ اجازه ندهید قطعی اینترنت "
        "باعث توقف فروش شما شود. برای دریافت راهکار «دستیار مجازی ۲۴ ساعته» "
        "لوماتیک، همین حالا مشاوره بگیرید."
    )


def hook_crisis_strategy_block() -> str:
    return (
        "<b>✨ در زمان بحران، معتبر دیده شوید</b>\n\n"
        "شایعات در گروه‌ها، اعتماد مشتریان شما را هدف قرار می‌دهند. "
        "برای دریافت استراتژی محتوای حرفه‌ای و ضد‌شایعه مجهز به هوش مصنوعی، "
        "با ما در تماس باشید."
    )


def hook_smart_start_block() -> str:
    return (
        "<b>🏗️ شروع هوشمند بیزنس در دبی</b>\n\n"
        "با کاهش مراجعات حضوری، ویترین آنلاین شما حیاتی است. طراحی سایت و "
        "اپلیکیشن اقتصادی مجهز به AI با هدف کاهش هزینه‌های بیزینس شما. "
        "برای مشاوره با ما در تماس باشید."
    )


def contact_channel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 واتساپ", callback_data="channel:wa"),
        InlineKeyboardButton("📩 تلگرام", callback_data="channel:tg"),
    ]])


def sales_footer_html() -> str:
    return (
        "🔴 <b>بقاء یا توقف؟</b>\n"
        "<b>شروع بیزنس در دبی: پرهزینه یا هوشمند؟</b>\n\n"
        "در شرایطی که خاموشی اینترنت و بحران منطقه، پایداری کسب‌وکارها را "
        "تهدید می‌کند، راهی هوشمندانه‌تر برای بقا وجود دارد.\n\n"
        "⚡️ با اتوماسیون هوشمند <b>لوماتیک</b>، وابستگی بیزنس خود را به "
        "زیرساخت‌های ناپایدار قطع کنید و هزینه‌های خود را در این وضعیت "
        "سخت مدیریت کنید.\n\n"
        "🎯 <i>آینده بیزنس خود را، حتی در قلب بحران، امروز بسازید.</i>\n\n"
        "✅ <b>۹۰ روز پشتیبانی رایگان</b> برای تمام خدمات."
    )


def with_sales_footer(body: str) -> str:
    return f"{body.rstrip()}\n\n{_DIVIDER}\n\n{sales_footer_html()}"


def webapp_reply_markup(
        show_connectivity_cta: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if show_connectivity_cta:
        rows.append([
            InlineKeyboardButton(
                "📞 درخواست مشاوره فوری",
                callback_data="contact:urgent",
            ),
        ])
    rows.append([
        InlineKeyboardButton(
            "✍️ استراتژی محتوا و برندینگ",
            callback_data="contact:strategy",
        ),
    ])
    return InlineKeyboardMarkup(rows)


def smart_start_reply_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🌐 مشاوره راه‌اندازی سایت",
            callback_data="contact:website",
        ),
    ]])


def pick_marketing_block() -> str:
    options: list[str] = [
        hook_connectivity_block(),
        hook_crisis_strategy_block(),
        hook_smart_start_block(),
    ]
    return random.choice(options)


def compose_webapp_reply_html(
        report_html: str,
        payload: dict[str, Any] | None = None,
) -> str:
    blocks: list[str] = [
        report_html.rstrip(),
        _DIVIDER,
        pick_marketing_block(),
    ]
    return "\n\n".join(blocks)
