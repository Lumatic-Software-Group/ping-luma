"""Decision-table tests for the VPN advice helper."""
from ping_luma.advice import (
    Advice,
    CallAdvice,
    ChatAdvice,
    decide_advice,
    decide_call_advice,
    decide_chat_advice,
)
from ping_luma.messengers import MESSENGER_BY_ID

BALE = MESSENGER_BY_ID["bale"]  # webrtc, expected yes
EITAA = MESSENGER_BY_ID["eitaa"]  # webrtc, expected vpn
GAP = MESSENGER_BY_ID["gap"]  # webrtc, expected partial
RUBIKA = MESSENGER_BY_ID["rubika"]  # proprietary, expected vpn
SOROUSH = MESSENGER_BY_ID["soroush"]  # proprietary, expected no


# ---------- chat advice ----------------------------------------------------

def test_chat_user_ok_means_no_vpn():
    assert decide_chat_advice(True, None) is ChatAdvice.NO_VPN_NEEDED
    assert decide_chat_advice(True, True) is ChatAdvice.NO_VPN_NEEDED
    assert decide_chat_advice(True, False) is ChatAdvice.NO_VPN_NEEDED


def test_chat_user_blocked_iran_ok_means_iranian_vpn():
    assert decide_chat_advice(False, True) is ChatAdvice.NEEDS_IRANIAN_VPN


def test_chat_user_blocked_iran_blocked_means_globally_down():
    assert decide_chat_advice(False, False) is ChatAdvice.GLOBALLY_DOWN


def test_chat_user_blocked_iran_unknown_means_inconclusive():
    assert decide_chat_advice(False, None) is ChatAdvice.INCONCLUSIVE


# ---------- call advice ----------------------------------------------------

def test_call_user_ok_means_no_vpn():
    assert decide_call_advice(BALE, True, None) is CallAdvice.NO_VPN_NEEDED


def test_call_user_blocked_iran_ok_means_iranian_vpn():
    assert decide_call_advice(BALE, False, True) is CallAdvice.NEEDS_IRANIAN_VPN


def test_call_user_blocked_iran_blocked_means_globally_down():
    assert decide_call_advice(BALE, False, False) is CallAdvice.GLOBALLY_DOWN


def test_call_user_blocked_iran_unknown_means_inconclusive():
    assert decide_call_advice(BALE, False, None) is CallAdvice.INCONCLUSIVE


def test_call_proprietary_falls_back_to_prior():
    # Rubika: expected_call_outside_iran="vpn"
    assert decide_call_advice(RUBIKA, None, None) is CallAdvice.NEEDS_IRANIAN_VPN
    # Soroush+: expected_call_outside_iran="no"
    assert decide_call_advice(SOROUSH, None, None) is CallAdvice.GLOBALLY_DOWN


def test_call_prior_yes_maps_to_no_vpn():
    # Even without a measurement, a "yes" prior says no VPN needed.
    # We synthesise this via a fake messenger by using a real one with a
    # "yes" expectation: Bale.
    assert decide_call_advice(BALE, None, None) is CallAdvice.NO_VPN_NEEDED


def test_call_prior_partial_maps_to_any_vpn():
    assert decide_call_advice(GAP, None, None) is CallAdvice.NEEDS_ANY_VPN


# ---------- combined advice ------------------------------------------------

def test_decide_advice_marks_measured_when_user_call_known():
    a = decide_advice(BALE, user_chat_ok=True, user_call_ok=True)
    assert isinstance(a, Advice)
    assert a.measured is True
    assert a.chat is ChatAdvice.NO_VPN_NEEDED
    assert a.call is CallAdvice.NO_VPN_NEEDED


def test_decide_advice_marks_unmeasured_for_proprietary():
    a = decide_advice(RUBIKA, user_chat_ok=False, user_call_ok=None)
    assert a.measured is False
    # call falls back to prior "vpn"
    assert a.call is CallAdvice.NEEDS_IRANIAN_VPN


def test_decide_advice_persian_labels_are_present():
    a = decide_advice(BALE, user_chat_ok=False, user_call_ok=False, iran_chat_ok=True, iran_call_ok=True)
    assert "VPN" in a.chat_label_fa or "ایرانی" in a.chat_label_fa
    assert "VPN" in a.call_label_fa or "ایرانی" in a.call_label_fa
    assert a.chat is ChatAdvice.NEEDS_IRANIAN_VPN
    assert a.call is CallAdvice.NEEDS_IRANIAN_VPN
