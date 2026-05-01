"""Tests for the user-facing Persian formatters."""
from ping_luma.formatters import (
    format_messenger_info,
    format_messenger_list,
    format_webapp_report,
    get_messenger,
)
from ping_luma.messengers import MESSENGER_BY_ID, MESSENGERS


def _payload(overrides=None):
    """Build a typical WebApp payload. ``overrides`` patches per-messenger."""
    overrides = overrides or {}
    base = {
        "bale": {"chat_ok": True, "call_ok": True, "lat": 240},
        "eitaa": {"chat_ok": False, "call_ok": False, "lat": None},
        "rubika": {"chat_ok": True, "call_ok": None, "lat": 180},
        "gap": {"chat_ok": True, "call_ok": True, "lat": 320},
        "igap": {"chat_ok": True, "call_ok": True, "lat": 220},
        "soroush": {"chat_ok": False, "call_ok": None, "lat": None},
    }
    base.update(overrides)
    return {
        "kind": "pingluma_result",
        "ts": 1700000000000,
        "country": "DE",
        "results": [{"id": mid, **vals} for mid, vals in base.items()],
    }


def test_format_webapp_report_contains_all_messenger_names():
    text = format_webapp_report(_payload())
    for m in MESSENGERS:
        assert m.name in text, f"{m.name} missing"


def test_format_webapp_report_includes_country_when_present():
    text = format_webapp_report(_payload())
    assert "DE" in text


def test_format_webapp_report_handles_missing_country():
    payload = _payload()
    payload["country"] = None
    text = format_webapp_report(payload)
    assert "<b>" in text  # still produces output


def test_format_webapp_report_summary_counts_only_user_truths():
    """3 of 6 chat_ok=True → summary should say 4/6 chat (bale, rubika, gap, igap)."""
    text = format_webapp_report(_payload())
    assert "4/6" in text


def test_format_webapp_report_marks_iranian_vpn_advice_when_appropriate():
    iran_ref = {
        "eitaa": {"chat_ok": True, "call_ok": True},
        "soroush": {"chat_ok": True, "call_ok": True},
    }
    payload = _payload({
        "eitaa": {"chat_ok": False, "call_ok": False, "lat": None},
        "soroush": {"chat_ok": False, "call_ok": None, "lat": None},
    })
    text = format_webapp_report(payload, iran_ref=iran_ref)
    # User blocked locally + Iran reference says reachable → Iranian VPN advice.
    # Persian label includes the word "ایرانی".
    assert "VPN" in text or "ایرانی" in text


def test_format_webapp_report_says_inconclusive_without_iran_reference():
    payload = _payload({"eitaa": {"chat_ok": False, "call_ok": False, "lat": None}})
    text = format_webapp_report(payload, iran_ref={})
    # Without an Iran reference, the user-blocked-locally case should NOT
    # claim the user needs an Iranian VPN — it should be inconclusive.
    assert "حدسی" in text or "نتیجه قطعی نیست" in text


def test_format_webapp_report_handles_completely_empty_payload():
    text = format_webapp_report({"kind": "pingluma_result", "results": []})
    for m in MESSENGERS:
        assert m.name in text


def test_format_messenger_info_contains_name_and_website():
    bale = MESSENGER_BY_ID["bale"]
    text = format_messenger_info(bale)
    assert "Bale" in text
    assert bale.website in text


def test_format_messenger_info_does_not_claim_real_time_status():
    """Static info card must not falsely advertise a measurement."""
    bale = MESSENGER_BY_ID["bale"]
    text = format_messenger_info(bale)
    # No "REACHABLE/BLOCKED" verdicts and no per-network reachability claim.
    assert "REACHABLE" not in text
    assert "BLOCKED" not in text
    assert "از شبکه شما" in text  # tells the user where the truth comes from


def test_format_messenger_list_lists_all_messengers():
    text = format_messenger_list()
    for m in MESSENGERS:
        assert m.name in text


def test_get_messenger_lookup():
    assert get_messenger("bale") is not None
    assert get_messenger("doesnotexist") is None
