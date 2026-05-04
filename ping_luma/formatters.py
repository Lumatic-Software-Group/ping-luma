from __future__ import annotations

from typing import Any

from ping_luma.advice import Advice, decide_advice
from ping_luma.iran_reference import ResultMap
from ping_luma.messengers import MESSENGER_BY_ID, MESSENGERS, Messenger

CHAT_VERDICT_FA = {
    True: "✅ در دسترس",
    False: "❌ مسدود",
}

EXPECTED_REG_LABEL = {
    "yes": "✅ ثبت‌نام آزاد است",
    "no": "❌ ثبت‌نام از خارج مسدود است",
    "sms": "📱 نیاز به شماره موبایل ایرانی",
}


def _result_for(payload_results: list[dict], messenger_id: str) -> dict | None:
    for r in payload_results:
        if isinstance(r, dict) and r.get("id") == messenger_id:
            return r
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _advice_for(
        m: Messenger,
        user_result: dict | None,
        iran_ref: ResultMap,
) -> Advice:
    if user_result is None:
        # User did not run the probe for this messenger — treat as
        # inconclusive on chat, fall back to prior on call.
        return decide_advice(
            messenger=m,
            user_chat_ok=False,
            user_call_ok=None,
            iran_chat_ok=None,
            iran_call_ok=None,
        )
    user_chat_ok = bool(user_result.get("chat_ok"))
    user_call_ok = _coerce_bool(user_result.get("call_ok"))
    iran_entry = iran_ref.get(m.id, {})
    return decide_advice(
        messenger=m,
        user_chat_ok=user_chat_ok,
        user_call_ok=user_call_ok,
        iran_chat_ok=iran_entry.get("chat_ok"),
        iran_call_ok=iran_entry.get("call_ok"),
    )


def format_webapp_report(
        payload: dict[str, Any],
        iran_ref: ResultMap | None = None,
) -> str:
    """Render the user's WebApp scan into a Persian Telegram-HTML message.

    The message is anchored to the user's measurement; advice for "needs
    Iranian VPN" is computed per-messenger by combining that with the
    optional Iran-side reference.
    """
    iran_ref = iran_ref or {}
    user_results = payload.get("results") or []
    if not isinstance(user_results, list):
        user_results = []
    country = payload.get("country")

    header_parts = ["<b>نتیجه بررسی از شبکه شما</b>"]
    if country:
        header_parts.append(f"<code>کشور تشخیص داده‌شده: {country}</code>")
    if iran_ref:
        header_parts.append(
            "<i>مقایسه با مرجع داخل ایران انجام شد.</i>"
        )
    else:
        header_parts.append(
            "<i>مرجع داخل ایران در دسترس نیست — توصیه‌ها حدسی هستند.</i>"
        )
    lines = header_parts + [""]

    for m in MESSENGERS:
        r = _result_for(user_results, m.id)
        advice = _advice_for(m, r, iran_ref)
        chat_ok = bool(r.get("chat_ok")) if r else False
        lat = r.get("lat") if r else None
        lat_str = (
            f"  <code>{int(lat)}ms</code>"
            if isinstance(lat, (int, float)) and lat
            else ""
        )

        chat_label = CHAT_VERDICT_FA[chat_ok] if r else "❓ تست نشده"
        lines.append(
            f"<b>{m.name}</b> ({m.name_fa}){lat_str}\n"
            f"  💬 {chat_label}  —  {advice.chat_label_fa}\n"
            f"  📞 {advice.call_label_fa}"
        )

    n_total = len(MESSENGERS)
    n_chat_ok = sum(1 for m in MESSENGERS
                    if (r := _result_for(user_results, m.id))
                    and bool(r.get("chat_ok")))
    n_call_ok = sum(1 for m in MESSENGERS
                    if (r := _result_for(user_results, m.id))
                    and r.get("call_ok") is True)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        f"💬 پیام: {n_chat_ok}/{n_total} از شبکه شما در دسترس",
        f"📞 تماس: {n_call_ok}/{n_total} از شبکه شما قابل برقراری",
        "",
        "<i>این نتیجه فقط بازتاب شبکه شما در همین لحظه است.</i>",
    ]
    return "\n".join(lines)


def format_messenger_info(m: Messenger) -> str:
    """Render a static info card for one messenger.

    Used by /list to give the user context BEFORE they run the WebApp probe.
    Anything time-varying ("is it reachable right now?") is intentionally
    omitted here because the bot host cannot answer that for the user.
    """
    reg = EXPECTED_REG_LABEL.get(m.expected_registration_outside_iran, "❓")
    vpn_hint = (
        "هر VPN معمولاً کافی است"
        if m.expected_call_vpn_any
        else "معمولاً فقط VPN با خروجی ایرانی"
    )

    lines = [
        f"<b>{m.name}</b> ({m.name_fa})",
        "",
        f"🌐 <a href=\"{m.website}\">{m.website}</a>",
        f"📝 {reg}",
        f"🔒 پیش‌فرض: {vpn_hint}",
    ]
    lines += [
        "",
        "<i>برای بررسی واقعی از شبکه شما، روی دکمه «بررسی از شبکه شما» بزنید.</i>",
    ]
    return "\n".join(lines)


def format_messenger_list() -> str:
    lines = ["<b>پیام‌رسان‌های پشتیبانی‌شده</b>", ""]
    for m in MESSENGERS:
        lines.append(f"• <b>{m.name}</b> ({m.name_fa})")
    lines += [
        "",
        "<i>برای جزئیات یک پیام‌رسان را انتخاب کنید.</i>",
        "<i>برای بررسی از شبکه خودتان، دکمه «بررسی از شبکه شما» را بزنید.</i>",
    ]
    return "\n".join(lines)


def get_messenger(messenger_id: str) -> Messenger | None:
    return MESSENGER_BY_ID.get(messenger_id)
