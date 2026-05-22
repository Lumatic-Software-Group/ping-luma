from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ping_luma.domain.messengers import Messenger


class ChatAdvice(str, Enum):
    NO_VPN_NEEDED = "chat_no_vpn"
    NEEDS_IRANIAN_VPN = "chat_iranian_vpn"
    GLOBALLY_DOWN = "chat_globally_down"
    INCONCLUSIVE = "chat_inconclusive"


class CallAdvice(str, Enum):
    NO_VPN_NEEDED = "call_no_vpn"
    NEEDS_IRANIAN_VPN = "call_iranian_vpn"
    NEEDS_ANY_VPN = "call_any_vpn"
    GLOBALLY_DOWN = "call_globally_down"
    NOT_TESTABLE = "call_not_testable"
    INCONCLUSIVE = "call_inconclusive"


CHAT_LABEL_FA = {
    ChatAdvice.NO_VPN_NEEDED: "✅ بدون VPN در دسترس است",
    ChatAdvice.NEEDS_IRANIAN_VPN: "🔒 با VPN با خروجی ایرانی در دسترس است",
    ChatAdvice.GLOBALLY_DOWN: "❌ در حال حاضر از داخل ایران هم در دسترس نیست",
    ChatAdvice.INCONCLUSIVE: "❓ نتیجه قطعی نیست",
}

CALL_LABEL_FA = {
    CallAdvice.NO_VPN_NEEDED: "✅ تماس بدون VPN ممکن است",
    CallAdvice.NEEDS_IRANIAN_VPN: "🔒 تماس با VPN با خروجی ایرانی ممکن است",
    CallAdvice.NEEDS_ANY_VPN: "⚠️ تماس ناپایدار — معمولاً با VPN بهتر می‌شود",
    CallAdvice.GLOBALLY_DOWN: "❌ تماس از خارج (و غالباً از ایران هم) در دسترس نیست",
    CallAdvice.NOT_TESTABLE: "❓ تماس از طریق مرورگر قابل تست نیست",
    CallAdvice.INCONCLUSIVE: "❓ نتیجه قطعی نیست",
}


@dataclass(frozen=True)
class Advice:
    chat: ChatAdvice
    call: CallAdvice
    measured: bool

    @property
    def chat_label_fa(self) -> str:
        return CHAT_LABEL_FA[self.chat]

    @property
    def call_label_fa(self) -> str:
        return CALL_LABEL_FA[self.call]


def decide_chat_advice(
        user_chat_ok: bool,
        iran_chat_ok: Optional[bool],
) -> ChatAdvice:
    if user_chat_ok:
        return ChatAdvice.NO_VPN_NEEDED
    if iran_chat_ok is True:
        return ChatAdvice.NEEDS_IRANIAN_VPN
    if iran_chat_ok is False:
        return ChatAdvice.GLOBALLY_DOWN
    return ChatAdvice.INCONCLUSIVE


def decide_call_advice(
        messenger: Messenger,
        user_call_ok: Optional[bool],
        iran_call_ok: Optional[bool],
) -> CallAdvice:
    # Proprietary protocols (Rubika, Soroush+) cannot be probed from a
    # browser. Fall back to the static prior shipped with the registry.
    if user_call_ok is None:
        return _prior_to_call_advice(messenger.expected_call_outside_iran)

    if user_call_ok:
        return CallAdvice.NO_VPN_NEEDED
    if iran_call_ok is True:
        return CallAdvice.NEEDS_IRANIAN_VPN
    if iran_call_ok is False:
        return CallAdvice.GLOBALLY_DOWN
    return CallAdvice.INCONCLUSIVE


def _prior_to_call_advice(prior: str) -> CallAdvice:
    return {
        "yes": CallAdvice.NO_VPN_NEEDED,
        "vpn": CallAdvice.NEEDS_IRANIAN_VPN,
        "partial": CallAdvice.NEEDS_ANY_VPN,
        "no": CallAdvice.GLOBALLY_DOWN,
    }.get(prior, CallAdvice.NOT_TESTABLE)


def decide_advice(
        messenger: Messenger,
        user_chat_ok: bool,
        user_call_ok: Optional[bool],
        iran_chat_ok: Optional[bool] = None,
        iran_call_ok: Optional[bool] = None,
) -> Advice:
    """High-level helper combining chat + call advice for one messenger.

    ``measured`` is True iff the call advice was derived from an actual
    user-side probe (i.e., the messenger uses WebRTC and the browser
    completed an ICE check). If False, the call line is a static prior and
    must be presented as a hint, not a verdict.
    """
    chat = decide_chat_advice(user_chat_ok, iran_chat_ok)
    call = decide_call_advice(messenger, user_call_ok, iran_call_ok)
    return Advice(chat=chat, call=call, measured=user_call_ok is not None)
