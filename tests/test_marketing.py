from ping_luma.marketing import (
    compose_webapp_reply_html,
    hook_connectivity_block,
    hook_crisis_strategy_block,
    hook_smart_start_block,
    sales_footer_html,
    should_show_iran_messenger_hook,
    smart_start_reply_markup,
    webapp_reply_markup,
    with_footer,
)

_WA = "https://wa.me/971500000000"
_TG = "https://t.me/testgroup"


def test_should_show_when_iran_messenger_chat_not_ok():
    for mid in ("bale", "rubika", "soroush"):
        payload = {"results": [{"id": mid, "chat_ok": False}]}
        assert should_show_iran_messenger_hook(payload), mid


def test_should_not_show_when_all_three_ok():
    payload = {
        "results": [
            {"id": "bale", "chat_ok": True},
            {"id": "rubika", "chat_ok": True},
            {"id": "soroush", "chat_ok": True},
        ],
    }
    assert not should_show_iran_messenger_hook(payload)


def test_should_not_show_for_other_messengers_only():
    payload = {"results": [{"id": "eitaa", "chat_ok": False}]}
    assert not should_show_iran_messenger_hook(payload)


def test_should_not_show_when_chat_ok_missing():
    payload = {"results": [{"id": "bale"}]}
    assert not should_show_iran_messenger_hook(payload)


def test_sales_footer_contains_links_and_trust():
    html = sales_footer_html(_WA, _TG)
    assert _WA in html and _TG in html
    assert "۹۰ روز" in html


def test_with_footer_separator_and_sales():
    body = "<b>x</b>"
    out = with_footer(body, _WA, _TG)
    assert body in out
    assert "━━━━━━━━━━━━━━━━━━━" in out
    assert _WA in out


def test_hooks_contain_headers():
    assert "⚠️" in hook_connectivity_block()
    assert "✨" in hook_crisis_strategy_block()
    assert "🏗️" in hook_smart_start_block()


def test_webapp_markup_rows_depends_on_connectivity_flag():
    kb_one = webapp_reply_markup(False, _WA)
    kb_two = webapp_reply_markup(True, _WA)
    assert len(kb_one.inline_keyboard) == 1
    assert len(kb_two.inline_keyboard) == 2


def test_smart_start_markup_single_row():
    kb = smart_start_reply_markup(_WA)
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].url.startswith(_WA)


def test_compose_webapp_includes_both_hooks_when_triggered():
    report = "<b>رپ</b>"
    payload = {"results": [{"id": "bale", "chat_ok": False}]}
    text = compose_webapp_reply_html(report, payload, _WA, _TG)
    assert report in text
    assert "⚠️" in text
    assert "✨" in text
    assert _WA in text


def test_compose_webapp_skips_connectivity_hook_when_ok():
    report = "<b>رپ</b>"
    payload = {"results": [{"id": "bale", "chat_ok": True}]}
    text = compose_webapp_reply_html(report, payload, _WA, _TG)
    assert "⚠️" not in text
    assert "✨" in text
