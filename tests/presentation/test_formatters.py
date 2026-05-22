from ping_luma.domain.messengers import MESSENGER_BY_ID, MESSENGERS
from ping_luma.presentation.formatters import (
    format_messenger_info,
    format_messenger_list,
    format_webapp_report,
    get_messenger,
)


def _payload(overrides=None):
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
        assert m.name_fa in text, f"{m.name_fa} missing"


def test_format_webapp_report_includes_country_when_present():
    text = format_webapp_report(_payload())
    assert "DE" in text


def test_format_webapp_report_handles_missing_country():
    payload = _payload()
    payload["country"] = None
    text = format_webapp_report(payload)
    assert "<b>" in text  # still produces output


def test_format_webapp_report_chat_availability_lines_match_payload():
    text = format_webapp_report(_payload())
    assert text.count("✅ در دسترس") == 4


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
    assert "با VPN با خروجی ایرانی" in text


def test_format_webapp_report_says_inconclusive_without_iran_reference():
    payload = _payload({"eitaa": {"chat_ok": False, "call_ok": False, "lat": None}})
    text = format_webapp_report(payload, iran_ref={})
    assert "حدسی" in text or "نتیجه قطعی نیست" in text


def test_format_webapp_report_handles_completely_empty_payload():
    text = format_webapp_report({"kind": "pingluma_result", "results": []})
    for m in MESSENGERS:
        assert m.name_fa in text


def test_format_messenger_info_contains_name_and_website():
    bale = MESSENGER_BY_ID["bale"]
    text = format_messenger_info(bale)
    assert "Bale" in text
    assert bale.website in text


def test_format_messenger_info_does_not_claim_real_time_status():
    """Static info card must not falsely advertise a measurement."""
    bale = MESSENGER_BY_ID["bale"]
    text = format_messenger_info(bale)
    assert "REACHABLE" not in text
    assert "BLOCKED" not in text
    assert "از شبکه شما" in text


def test_format_messenger_list_lists_all_messengers():
    text = format_messenger_list()
    for m in MESSENGERS:
        assert m.name in text


def test_get_messenger_lookup():
    assert get_messenger("bale") is not None
    assert get_messenger("doesnotexist") is None
