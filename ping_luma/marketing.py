from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_IRAN_HOOK_IDS = frozenset({"bale", "rubika", "soroush"})


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


def _wa_url(base: str, prefill: str) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode({'text': prefill})}"


def hook_connectivity_block() -> str:
    return (
        "<b>⚠️ ارتباط قطع شده، اما بیزنس شما نه!</b>\n\n"
        "ادمین‌های فروش شما در ایران آفلاین هستند؟ اجازه ندهید قطعی اینترنت "
        "باعث توقف فروش شما شود. برای دریافت راهکار «دستیار مجازی ۲۴ ساعته» "
        "لوماتیک، همین حالا مشاوره بگیرید [۱]."
    )


def hook_crisis_strategy_block() -> str:
    return (
        "<b>✨ در زمان بحران، معتبر دیده شوید</b>\n\n"
        "شایعات و نویز در گروه‌ها، اعتماد مشتریان شما را هدف قرار می‌دهند. "
        "برای دریافت استراتژی محتوای حرفه‌ای و ضد‌شایعه مجهز به هوش مصنوعی، "
        "با ما در تماس باشید [۱]."
    )


def hook_smart_start_block() -> str:
    return (
        "<b>🏗️ شروع هوشمند بیزنس در دبی</b>\n\n"
        "با کاهش مراجعات حضوری، ویترین آنلاین شما حیاتی است. طراحی سایت و "
        "اپلیکیشن اقتصادی مجهز به AI با هدف کاهش هزینه‌های استخدام [۱]. "
        "برای مشاهده نمونه‌کارها پیام دهید."
    )


def sales_footer_html(wa_url: str, tg_url: str) -> str:
    return (
        "«آینده بیزنس خود را امروز بسازید. برای مشاوره رایگان و دریافت جزئیات "
        "خدمات، در تلگرام یا واتس‌اپ با ما در ارتباط باشید.»\n\n"
        f"<a href=\"{wa_url}\">ارتباط در واتس‌اپ (+971&nbsp;50&nbsp;265&nbsp;9885)</a>\n"
        f"<a href=\"{tg_url}\">ارتباط در تلگرام (lumaticgroup@)</a>\n\n"
        "✅ شامل ۹۰ روز پشتیبانی رایگان."
    )


def with_footer(body: str, wa_url: str, tg_url: str) -> str:
    return f"{body.rstrip()}\n\n━━━━━━━━━━━━━━━━━━━\n{sales_footer_html(wa_url, tg_url)}"


def webapp_reply_markup(
        show_connectivity_cta: bool,
        wa_base_url: str,
) -> InlineKeyboardMarkup:
    """Inline CTAs after a WebApp report; URLs use WhatsApp with distinct prefills."""
    rows: list[list[InlineKeyboardButton]] = []
    if show_connectivity_cta:
        rows.append([
            InlineKeyboardButton(
                "📞 درخواست مشاوره فوری",
                url=_wa_url(
                    wa_base_url,
                    "سلام، درخواست مشاوره فوری پس از قطع/ناپایداری بله، روبیکا یا سروش‌پلاس.",
                ),
            ),
        ])
    rows.append([
        InlineKeyboardButton(
            "✍️ استراتژی محتوا و برندینگ",
            url=_wa_url(wa_base_url, "سلام، درخواست استراتژی محتوا و برندینگ."),
        ),
    ])
    return InlineKeyboardMarkup(rows)


def smart_start_reply_markup(wa_base_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🌐 مشاوره راه‌اندازی سایت",
            url=_wa_url(
                wa_base_url,
                "سلام، درخواست مشاوره راه‌اندازی سایت و اپلیکیشن.",
            ),
        ),
    ]])


def compose_webapp_reply_html(
        report_html: str,
        payload: dict[str, Any],
        wa_url: str,
        tg_url: str,
) -> str:
    blocks = [report_html.rstrip()]
    if should_show_iran_messenger_hook(payload):
        blocks.append(hook_connectivity_block())
    blocks.append(hook_crisis_strategy_block())
    core = "\n\n".join(blocks)
    return with_footer(core, wa_url, tg_url)
