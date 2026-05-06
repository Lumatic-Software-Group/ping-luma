from unittest.mock import patch

from ping_luma.marketing import (
    compose_webapp_reply_html,
    hook_connectivity_block,
    hook_crisis_strategy_block,
    hook_smart_start_block,
    pick_marketing_block,
    should_show_iran_messenger_hook,
    smart_start_reply_markup,
    webapp_reply_markup,
    with_sales_footer,
)


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


def test_with_sales_footer_wraps_body():
    body = "<b>x</b>"
    out = with_sales_footer(body)
    assert body in out
    assert "لوماتیک" in out
    assert "۹۰ روز" in out


def test_hooks_contain_headers():
    assert "⚠️" in hook_connectivity_block()
    assert "✨" in hook_crisis_strategy_block()
    assert "🏗️" in hook_smart_start_block()


def test_webapp_markup_rows_depends_on_connectivity_flag():
    kb_one = webapp_reply_markup(False)
    kb_two = webapp_reply_markup(True)
    assert len(kb_one.inline_keyboard) == 1
    assert len(kb_two.inline_keyboard) == 2


def test_smart_start_markup_single_row():
    kb = smart_start_reply_markup()
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].callback_data == "contact:website"


def test_pick_marketing_block_uses_random_choice():
    with patch("ping_luma.marketing.random.choice", return_value="FIXED"):
        assert pick_marketing_block() == "FIXED"


def test_compose_webapp_includes_report_and_picked_block_only():
    report = "<b>رپ</b>"
    payload = {"results": [{"id": "bale", "chat_ok": False}]}
    with patch(
            "ping_luma.marketing.pick_marketing_block",
            return_value=hook_crisis_strategy_block(),
    ):
        text = compose_webapp_reply_html(report, payload)
    assert report in text
    assert "✨" in text
    assert "⚠️" not in text
    assert "۹۰ روز" not in text


def test_webapp_full_message_wraps_compose_with_sales_footer():
    report = "<b>رپ</b>"
    payload = {"results": [{"id": "bale", "chat_ok": False}]}
    with patch(
            "ping_luma.marketing.pick_marketing_block",
            return_value=hook_crisis_strategy_block(),
    ):
        body = compose_webapp_reply_html(report, payload)
        full = with_sales_footer(body)
    assert "لوماتیک" in full
    assert "۹۰ روز" in full
    assert "✨" in full
