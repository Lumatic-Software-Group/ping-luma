"""Registry-shape invariants for the messenger list."""
from ping_luma.domain.messengers import MESSENGER_BY_ID, MESSENGERS


def test_six_messengers():
    assert len(MESSENGERS) == 6


def test_all_expected_ids_present():
    ids = {m.id for m in MESSENGERS}
    assert ids == {"bale", "eitaa", "rubika", "gap", "igap", "soroush"}


def test_lookup_by_id():
    assert MESSENGER_BY_ID["bale"].name == "Bale"
    assert MESSENGER_BY_ID.get("doesnotexist") is None


def test_availability_values_are_valid():
    valid = {"global", "mixed", "iran"}
    for m in MESSENGERS:
        assert m.availability in valid, f"{m.id} has invalid availability"


def test_all_have_probe_urls():
    for m in MESSENGERS:
        assert len(m.probe_urls) > 0, f"{m.id} has no probe_urls"


def test_all_have_dns_hosts():
    for m in MESSENGERS:
        assert len(m.dns_hosts) > 0, f"{m.id} has no dns_hosts"


def test_bale_gap_igap_are_global():
    for mid in ("bale", "gap", "igap"):
        assert MESSENGER_BY_ID[mid].availability == "global"


def test_proprietary_call_protocol_has_no_stun():
    for m in MESSENGERS:
        if m.call_protocol == "proprietary":
            assert m.stun_hosts == [], f"{m.id} should not declare STUN"
            assert m.turn_host is None, f"{m.id} should not declare TURN"


def test_expected_call_outside_iran_values_are_valid():
    valid = {"yes", "vpn", "partial", "no", "unknown"}
    for m in MESSENGERS:
        assert m.expected_call_outside_iran in valid


def test_expected_registration_values_are_valid():
    valid = {"yes", "no", "sms"}
    for m in MESSENGERS:
        assert m.expected_registration_outside_iran in valid
