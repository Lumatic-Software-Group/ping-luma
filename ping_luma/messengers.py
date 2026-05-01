from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Messenger:
    id: str
    name: str
    name_fa: str
    probe_urls: list[str]
    dns_hosts: list[str]
    availability: str
    description: str
    website: str

    call_protocol: str = "webrtc"
    call_capable: bool = False

    expected_call_outside_iran: str = "unknown"
    expected_call_vpn_any: bool = False
    expected_registration_outside_iran: str = "no"
    call_notes: str = ""

    stun_hosts: list[str] = field(default_factory=list)
    turn_host: Optional[str] = None


MESSENGERS: list[Messenger] = [
    Messenger(
        id="bale",
        name="Bale",
        name_fa="بله",
        probe_urls=["https://tapi.bale.ai", "https://web.bale.ai"],
        dns_hosts=["tapi.bale.ai", "web.bale.ai", "cdn.bale.ai"],
        availability="global",
        description="Messaging and mobile-payment app by Bank Melli Iran",
        website="https://bale.ai",
        call_protocol="webrtc",
        call_capable=True,
        expected_call_outside_iran="yes",
        expected_call_vpn_any=True,
        expected_registration_outside_iran="sms",
        call_notes="CDN-fronted — calls usually work from outside Iran without VPN",
        stun_hosts=["stun.bale.ai", "tapi.bale.ai"],
        turn_host="turn.bale.ai",
    ),
    Messenger(
        id="eitaa",
        name="Eitaa",
        name_fa="ایتا",
        probe_urls=["https://eitaa.com", "https://api.eitaa.com"],
        dns_hosts=["eitaa.com", "api.eitaa.com"],
        availability="mixed",
        description="Messaging app with an Islamic-values focus",
        website="https://eitaa.com",
        call_protocol="webrtc",
        call_capable=True,
        expected_call_outside_iran="vpn",
        expected_call_vpn_any=False,
        expected_registration_outside_iran="no",
        call_notes="TURN servers on Iranian IPs — only Iranian-exit VPN typically works",
        stun_hosts=["stun.eitaa.com"],
        turn_host="turn.eitaa.com",
    ),
    Messenger(
        id="rubika",
        name="Rubika",
        name_fa="روبیکا",
        probe_urls=["https://rubika.ir", "https://getapp.rubika.ir"],
        dns_hosts=["rubika.ir", "getapp.rubika.ir"],
        availability="mixed",
        description="Social messaging platform by MCI (Hamrah-e-Aval)",
        website="https://rubika.ir",
        call_protocol="proprietary",
        call_capable=True,
        expected_call_outside_iran="vpn",
        expected_call_vpn_any=False,
        expected_registration_outside_iran="no",
        call_notes="Proprietary binary protocol — only Iranian-exit VPN typically works",
        stun_hosts=[],
        turn_host=None,
    ),
    Messenger(
        id="gap",
        name="Gap",
        name_fa="گپ",
        probe_urls=["https://gap.im", "https://api.gap.im"],
        dns_hosts=["gap.im", "api.gap.im"],
        availability="global",
        description="Cross-platform messenger with channel support",
        website="https://gap.im",
        call_protocol="webrtc",
        call_capable=True,
        expected_call_outside_iran="partial",
        expected_call_vpn_any=True,
        expected_registration_outside_iran="sms",
        call_notes="Intermittent relay coverage — commercial VPN improves reliability",
        stun_hosts=["stun.gap.im"],
        turn_host="turn.gap.im",
    ),
    Messenger(
        id="igap",
        name="iGap",
        name_fa="آی‌گپ",
        probe_urls=["https://igap.net", "https://api.igap.net"],
        dns_hosts=["igap.net", "api.igap.net"],
        availability="global",
        description="Feature-rich messenger with voice and video calls",
        website="https://igap.net",
        call_protocol="webrtc",
        call_capable=True,
        expected_call_outside_iran="yes",
        expected_call_vpn_any=True,
        expected_registration_outside_iran="yes",
        call_notes="International STUN/TURN — typically the best option for calls from abroad",
        stun_hosts=["stun.igap.net", "stun2.igap.net"],
        turn_host="turn.igap.net",
    ),
    Messenger(
        id="soroush",
        name="Soroush+",
        name_fa="سروش‌پلاس",
        probe_urls=["https://soroushapp.com", "https://api.soroushapp.com"],
        dns_hosts=["soroushapp.com", "api.soroushapp.com"],
        availability="mixed",
        description="State-affiliated messenger from IRIB",
        website="https://soroushapp.com",
        call_protocol="proprietary",
        call_capable=True,
        expected_call_outside_iran="no",
        expected_call_vpn_any=False,
        expected_registration_outside_iran="no",
        call_notes="State IRIB infrastructure — calls unreliable even with Iranian VPN",
        stun_hosts=[],
        turn_host=None,
    ),
]

MESSENGER_BY_ID: dict[str, Messenger] = {m.id: m for m in MESSENGERS}
