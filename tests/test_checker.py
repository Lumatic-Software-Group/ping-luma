"""Tests for the server-side probing utilities.

These tests do not hit the network — all probes are mocked.
"""
import struct
from unittest.mock import patch

from ping_luma.checker import (
    DnsResult,
    StunResult,
    TurnResult,
    UrlResult,
    _check_one_messenger,
    _is_valid_stun_response,
    _score_calls,
    _score_messaging,
    run_full_scan,
    to_iran_reference_payload,
)
from ping_luma.messengers import MESSENGER_BY_ID


def _url(ok: bool, lat: float = 200.0) -> UrlResult:
    return UrlResult(
        url="https://example.com",
        reachable=ok,
        latency_ms=lat if ok else None,
        ssl_valid=ok,
    )


def _dns(ok: bool) -> DnsResult:
    return DnsResult(host="example.com", resolved=ok, ip="1.2.3.4" if ok else None)


def _stun_ok(host: str, **_) -> StunResult:
    return StunResult(host=host, port=3478, reachable=True, latency_ms=50.0)


def _turn_ok(host: str, **_) -> TurnResult:
    return TurnResult(host=host, port=3478, reachable=True, latency_ms=60.0)


# ---------- scoring --------------------------------------------------------

def test_all_ok_low_latency_is_reachable():
    score, verdict = _score_messaging([_url(True, 150)] * 2, [_dns(True)] * 2)
    assert score >= 70
    assert verdict == "REACHABLE"


def test_all_fail_is_blocked():
    score, verdict = _score_messaging([_url(False)] * 2, [_dns(False)] * 2)
    assert score == 0
    assert verdict == "BLOCKED"


def test_mixed_results_are_partial():
    score, verdict = _score_messaging(
        [_url(True, 300), _url(False)],
        [_dns(True), _dns(False)],
    )
    assert 0 < score < 100


def test_fast_latency_scores_higher_than_slow():
    fast, _ = _score_messaging([_url(True, 100)] * 2, [_dns(True)] * 2)
    slow, _ = _score_messaging([_url(True, 2000)] * 2, [_dns(True)] * 2)
    assert fast > slow


def test_calls_unknown_for_proprietary_protocol():
    score, verdict = _score_calls([], None, "proprietary")
    assert verdict == "UNKNOWN"
    assert score == 0


# ---------- STUN response validator ---------------------------------------

def test_stun_validator_accepts_well_formed_response():
    msg_type = 0x0101
    magic = 0x2112A442
    txid = b"\x00" * 12
    data = struct.pack(">HHI12s", msg_type, 0, magic, txid) + b"\x00" * 8
    assert _is_valid_stun_response(data) is True


def test_stun_validator_rejects_wrong_magic():
    data = struct.pack(">HHI12s", 0x0101, 0, 0xDEADBEEF, b"\x00" * 12)
    assert _is_valid_stun_response(data) is False


def test_stun_validator_rejects_wrong_txid():
    data = struct.pack(">HHI12s", 0x0101, 0, 0x2112A442, b"\x11" * 12)
    assert _is_valid_stun_response(data) is False


def test_stun_validator_rejects_short_payload():
    assert _is_valid_stun_response(b"\x00" * 5) is False


def test_stun_validator_rejects_unknown_message_type():
    data = struct.pack(">HHI12s", 0x0001, 0, 0x2112A442, b"\x00" * 12)
    assert _is_valid_stun_response(data) is False


# ---------- one-messenger orchestration ------------------------------------

def test_check_one_messenger_marks_chat_reachable_when_probes_succeed():
    bale = MESSENGER_BY_ID["bale"]
    with patch("ping_luma.checker._probe_url", return_value=_url(True, 120)), \
            patch("ping_luma.checker._probe_dns", return_value=_dns(True)), \
            patch("ping_luma.checker._probe_stun_udp", side_effect=_stun_ok), \
            patch("ping_luma.checker._probe_turn_tcp", side_effect=_turn_ok):
        result = _check_one_messenger(bale)
    assert result.messenger.id == "bale"
    assert result.chat_verdict == "REACHABLE"
    assert result.chat_ok is True
    assert result.best_latency_ms is not None


def test_check_one_messenger_call_unknown_for_proprietary():
    rubika = MESSENGER_BY_ID["rubika"]
    with patch("ping_luma.checker._probe_url", return_value=_url(True, 120)), \
            patch("ping_luma.checker._probe_dns", return_value=_dns(True)):
        result = _check_one_messenger(rubika)
    assert result.call_verdict == "UNKNOWN"
    assert result.call_ok is None


# ---------- iran-reference payload ----------------------------------------

def test_to_iran_reference_payload_round_trip():
    with patch("ping_luma.checker._probe_url", return_value=_url(True, 100)), \
            patch("ping_luma.checker._probe_dns", return_value=_dns(True)), \
            patch("ping_luma.checker._probe_stun_udp", side_effect=_stun_ok), \
            patch("ping_luma.checker._probe_turn_tcp", side_effect=_turn_ok):
        report = run_full_scan()
    payload = to_iran_reference_payload(report)
    assert "ts" in payload
    assert "results" in payload
    assert set(payload["results"].keys()) == {
        "bale", "eitaa", "rubika", "gap", "igap", "soroush",
    }
    assert payload["results"]["bale"]["chat_ok"] is True
    # Rubika is proprietary → call_ok must be None even when probes succeed.
    assert payload["results"]["rubika"]["call_ok"] is None
