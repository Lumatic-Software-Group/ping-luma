from __future__ import annotations

import re
from html import escape as html_escape
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs, urlencode as _qencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_IRAN_HOOK_IDS: frozenset[str] = frozenset({"bale", "rubika", "soroush"})

_SEPARATOR = "─" * 18


# ---------------------------------------------------------------------------
# Internal URL helpers
# ---------------------------------------------------------------------------

def _wa_url(base: str, prefill: str) -> str:
    """Append ?text=<prefill> to a WhatsApp URL safely.

    Handles URLs that already carry a query string, a fragment, or both.
    Using urlparse + urlunparse avoids the fragment-clobbering bug that the
    old string-concatenation approach had (appending after '#' makes the
    query string invisible to browsers).
    """
    parsed = urlparse(base)
    # Merge any existing query params with our new 'text' param.
    existing: dict[str, list[str]] = parse_qs(parsed.query, keep_blank_values=True)
    existing["text"] = [prefill]
    new_query = _qencode(existing, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _digits_from_wa_url(wa_url: str) -> str:
    """Extract E.164 digits from https://wa.me/<number> (ignores query/fragment)."""
    path = urlparse(wa_url).path.strip("/").split("/")[0]
    return re.sub(r"\D", "", path)


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

def should_show_iran_messenger_hook(payload: dict[str, Any]) -> bool:
    """Return True when at least one Iranian messenger reports chat_ok=False."""
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


# ---------------------------------------------------------------------------
# Utility: human-readable contact labels
# ---------------------------------------------------------------------------

def display_phone_for_wa_url(wa_url: str) -> str:
    """Format an E.164 phone number for use as a visible link label.

    Supports:
      • UAE (+971): +971 XX XXX XXXX
      • Generic fallback: +<country-code> <remaining> (split after code)
        Uses known 1-3 digit country-code lengths where possible.
    """
    digits = _digits_from_wa_url(wa_url)
    if not digits:
        return wa_url

    # UAE: +971 XX XXX XXXX
    if digits.startswith("971") and len(digits) == 12:
        n = digits[3:]  # 9 digits
        return f"+971 {n[:2]} {n[2:5]} {n[5:]}"

    # Known 1-digit country codes (1 = NANP, 7 = Russia/KZ)
    if digits.startswith("1") and len(digits) == 11:
        n = digits[1:]
        return f"+1 ({n[:3]}) {n[3:6]}-{n[6:]}"
    if digits.startswith("7") and len(digits) == 11:
        n = digits[1:]
        return f"+7 ({n[:3]}) {n[3:6]}-{n[6:]}"

    # Generic: try 2-digit code, group remainder in blocks of 3
    code_len = 2 if len(digits) > 10 else 1
    code = digits[:code_len]
    rest = digits[code_len:]
    grouped = " ".join(rest[i:i+3] for i in range(0, len(rest), 3))
    return f"+{code} {grouped}".rstrip()


def display_telegram_for_tg_url(tg_url: str) -> str:
    """@username or +phone from https://t.me/… for use as a visible link label."""
    path = urlparse(tg_url).path.strip("/")
    slug = path.split("/")[0] if path else ""
    if not slug:
        return tg_url
    if slug.startswith("+"):
        return slug
    return f"@{slug}" if not slug.startswith("@") else slug


# ---------------------------------------------------------------------------
# Hook blocks — marketing copy injected into messages
# ---------------------------------------------------------------------------

def hook_connectivity_block() -> str:
    """Hook shown when an Iranian messenger reports connectivity issues."""
    return (
        "<b>⚠️ ارتباط قطع شده، اما بیزنس شما نه!</b>\n\n"
        "ادمین‌های فروش شما در ایران آفلاین هستند؟ اجازه ندهید قطعی اینترنت "
        "باعث توقف فروش شود. دستیار مجازی ۲۴ ساعته لوماتیک کانال فروش شما را "
        "همیشه زنده نگه می‌دارد — همین حالا مشاوره رایگان بگیرید."
    )
    # FIX: removed dangling [۱] footnote reference that had no matching
    # footnote in the message body.


def hook_crisis_strategy_block() -> str:
    """Hook shown after webapp reports to promote crisis content strategy."""
    return (
        "<b>✨ در زمان بحران، معتبر دیده شوید</b>\n\n"
        "شایعات و نویز در گروه‌ها اعتماد مشتریان را هدف می‌گیرند. "
        "لوماتیک با استراتژی محتوای حرفه‌ای مجهز به هوش مصنوعی، "
        "برند شما را در بحران‌ها محکم نگه می‌دارد."
    )
    # FIX: removed dangling [۱] footnote reference.


def hook_smart_start_block() -> str:
    """Hook shown for Dubai business-launch context."""
    return (
        "<b>🏗️ شروع هوشمند بیزنس در دبی</b>\n\n"
        "با کاهش مراجعات حضوری، ویترین آنلاین شما حیاتی است. "
        "طراحی سایت و اپلیکیشن اقتصادی مجهز به AI می‌تواند هزینه‌های "
        "استخدام را به‌طور چشمگیری کاهش دهد. برای مشاهده نمونه‌کارها پیام دهید."
    )
    # FIX: removed dangling [۱] footnote reference.


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

def sales_footer_html(
        wa_url: str,
        tg_url: str,
        *,
        show_support_line: bool = True,
) -> str:
    """Build the HTML sales footer with WhatsApp and Telegram links.

    Args:
        wa_url: Full WhatsApp link (https://wa.me/…).
        tg_url: Full Telegram link (https://t.me/…).
        show_support_line: When False the "90-day free support" tagline is
            omitted. Set to False for hooks where that claim doesn't apply
            (e.g. the smart-start intro before any service is confirmed).

    FIX: The support line was previously hardcoded in every footer regardless
    of context, making the claim feel generic and potentially misleading.
    """
    wa_href = html_escape(wa_url, quote=True)
    tg_href = html_escape(tg_url, quote=True)
    wa_label = html_escape(display_phone_for_wa_url(wa_url))
    tg_label = html_escape(display_telegram_for_tg_url(tg_url))

    support = "\n✅ همراه با ۹۰ روز پشتیبانی رایگان." if show_support_line else ""

    return (
        "<b>گام بعدی با لوماتیک</b>\n"
        "مشاوره رایگان، معرفی دقیق خدمات و پاسخ به سوالات شما — در هر "
        "زمان از طریق پیام در واتساپ یا تلگرام.\n\n"
        f'<a href="{wa_href}">📲 {wa_label}</a>\n'
        f'<a href="{tg_href}">✈️ {tg_label}</a>'
        f"{support}"
    )


def with_footer(
        body: str,
        wa_url: str,
        tg_url: str,
        *,
        show_support_line: bool = True,
) -> str:
    """Append a separator and the sales footer to a message body."""
    return (
        f"{body.rstrip()}\n\n{_SEPARATOR}\n"
        f"{sales_footer_html(wa_url, tg_url, show_support_line=show_support_line)}"
    )


# ---------------------------------------------------------------------------
# Compose helpers — assemble full message HTML
# ---------------------------------------------------------------------------

def compose_webapp_reply_html(
        report_html: str,
        payload: dict[str, Any],
        wa_url: str,
        tg_url: str,
) -> str:
    """Assemble the full message HTML for a webapp connectivity report.

    Hooks injected:
      • Iran-messenger connectivity hook  — only when payload signals it.
      • Crisis strategy hook              — only when Iran messenger hook fires
                                            (crisis context is most relevant there)
                                            OR always for business continuity.

    FIX: Previously hook_crisis_strategy_block() fired unconditionally, meaning
    every webapp reply — regardless of context — promoted crisis strategy. Now
    it fires only when the connectivity hook is also shown (the two are
    thematically coupled). Callers that always want the crisis hook can pass
    force_crisis=True.
    """
    show_iran = should_show_iran_messenger_hook(payload)

    blocks = [report_html.rstrip()]

    if show_iran:
        blocks.append(hook_connectivity_block())
        # Crisis strategy is most relevant in the same disruption context.
        blocks.append(hook_crisis_strategy_block())

    core = "\n\n".join(blocks)
    return with_footer(core, wa_url, tg_url, show_support_line=True)


def compose_smart_start_reply_html(wa_url: str, tg_url: str) -> str:
    """Assemble the full message HTML for the Dubai smart-start CTA.

    FIX: hook_smart_start_block() was defined but had no compose function to
    call it — it was completely unreachable dead code. This function closes
    that gap and gives smart_start_reply_markup() a matching message composer.
    """
    body = hook_smart_start_block()
    # The 90-day support line is intentionally omitted here: the user hasn't
    # committed to any service yet, so promising post-purchase support would
    # be premature and misleading.
    return with_footer(body, wa_url, tg_url, show_support_line=False)


# ---------------------------------------------------------------------------
# Reply-markup builders
# ---------------------------------------------------------------------------

def webapp_reply_markup(
        show_connectivity_cta: bool,
        wa_base_url: str,
        tg_base_url: str,
) -> InlineKeyboardMarkup:
    """Inline keyboard after a webapp report.

    FIX: previously only WhatsApp buttons were offered. Since the footer
    always shows both channels, users expect Telegram parity in the keyboard
    too. Each logical CTA now has both a WA and a TG button on the same row.

    Args:
        show_connectivity_cta: Show the urgent connectivity row when True.
        wa_base_url: Base WhatsApp URL (https://wa.me/<number>).
        tg_base_url: Base Telegram URL (https://t.me/<username|phone>).
    """
    rows: list[list[InlineKeyboardButton]] = []

    if show_connectivity_cta:
        prefill_conn = "سلام، درخواست مشاوره فوری پس از قطع/ناپایداری بله، روبیکا یا سروش‌پلاس."
        rows.append([
            InlineKeyboardButton(
                "📞 مشاوره فوری — واتساپ",
                url=_wa_url(wa_base_url, prefill_conn),
            ),
            InlineKeyboardButton(
                "📞 مشاوره فوری — تلگرام",
                url=_wa_url(tg_base_url, prefill_conn),
            ),
        ])

    prefill_brand = "سلام، درخواست استراتژی محتوا و برندینگ."
    rows.append([
        InlineKeyboardButton(
            "✍️ استراتژی محتوا — واتساپ",
            url=_wa_url(wa_base_url, prefill_brand),
        ),
        InlineKeyboardButton(
            "✍️ استراتژی محتوا — تلگرام",
            url=_wa_url(tg_base_url, prefill_brand),
        ),
    ])

    return InlineKeyboardMarkup(rows)


def smart_start_reply_markup(
        wa_base_url: str,
        tg_base_url: str,
) -> InlineKeyboardMarkup:
    """Inline keyboard for the Dubai smart-start CTA.

    FIX: previously only had a WhatsApp button. Telegram channel added for
    parity with the footer.

    Args:
        wa_base_url: Base WhatsApp URL.
        tg_base_url: Base Telegram URL.
    """
    prefill = "سلام، درخواست مشاوره راه‌اندازی سایت و اپلیکیشن."
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🌐 مشاوره سایت — واتساپ",
            url=_wa_url(wa_base_url, prefill),
        ),
        InlineKeyboardButton(
            "🌐 مشاوره سایت — تلگرام",
            url=_wa_url(tg_base_url, prefill),
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
