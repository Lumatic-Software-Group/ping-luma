from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Messenger:
    id: str
    name: str
    name_fa: str
    probe_urls: List[str]
    dns_hosts: List[str]
    availability: str
    description: str
    website: str

    call_protocol: str = "webrtc"
    call_capable: bool = False
    call_outside_iran: str = "unknown"
    call_vpn_any: bool = False  # True = any VPN works; False = Iranian-exit only
    registration_outside_iran: str = "no"  # "yes" | "no" | "sms"
    call_notes: str = ""

    stun_hosts: List[str] = field(default_factory=list)
    turn_host: Optional[str] = None  # primary TURN host (no port)


MESSENGERS: List[Messenger] = [
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
        call_outside_iran="yes",
        call_vpn_any=True,
        registration_outside_iran="sms",
        call_notes="CDN-fronted — calls work from outside Iran without VPN",
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
        call_outside_iran="vpn",
        call_vpn_any=False,
        registration_outside_iran="no",
        call_notes="TURN servers on Iranian IPs — only Iranian-exit VPN works",
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
        call_outside_iran="vpn",
        call_vpn_any=False,
        registration_outside_iran="no",
        call_notes="Proprietary binary protocol — only Iranian-exit VPN works",
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
        call_outside_iran="partial",
        call_vpn_any=True,
        registration_outside_iran="sms",
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
        call_outside_iran="yes",
        call_vpn_any=True,
        registration_outside_iran="yes",
        call_notes="Best option for calls from outside — international STUN/TURN",
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
        call_outside_iran="no",
        call_vpn_any=False,
        registration_outside_iran="no",
        call_notes="State IRIB infrastructure — calls unreliable even with Iranian VPN",
        stun_hosts=[],
        turn_host=None,
    ),
]

# fast lookup by id — used throughout the codebase.
MESSENGER_BY_ID: Dict[str, Messenger] = {m.id: m for m in MESSENGERS}
