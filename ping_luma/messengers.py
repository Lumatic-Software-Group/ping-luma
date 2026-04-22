from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Messenger:
    id: str  # short slug used as a stable identifier, e.g. "bale"
    name: str  # english display name
    name_fa: str  # persian display name shown to users
    probe_urls: List[str]  # https endpoints to probe, in priority order
    dns_hosts: List[str]  # hostnames to resolve via DNS
    availability: str  # "global" | "iran" | "mixed"
    description: str  # one-line English description (internal use)
    website: str  # canonical homepage URL

    call_capable: bool = False
    stun_hosts: List[str] = field(default_factory=list)
    turn_hosts: List[str] = field(default_factory=list)
    calls_global: bool = False


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
        call_capable=True,
        stun_hosts=["stun.bale.ai", "tapi.bale.ai"],
        turn_hosts=["turn.bale.ai:3478", "turn.bale.ai:5349"],
        calls_global=True,
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
        call_capable=True,
        stun_hosts=["stun.eitaa.com"],
        turn_hosts=["turn.eitaa.com:3478"],
        calls_global=False,
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
        call_capable=True,
        stun_hosts=["stun.rubika.ir"],
        turn_hosts=["turn.rubika.ir:3478"],
        calls_global=False,
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
        call_capable=True,
        stun_hosts=["stun.gap.im"],
        turn_hosts=["turn.gap.im:3478", "turn.gap.im:5349"],
        calls_global=True,
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
        call_capable=True,
        stun_hosts=["stun.igap.net", "stun2.igap.net"],
        turn_hosts=["turn.igap.net:3478", "turn.igap.net:5349"],
        calls_global=True,
    ),
    Messenger(
        id="soroush",
        name="Soroush Plus",
        name_fa="سروش‌پلاس",
        probe_urls=["https://soroushapp.com", "https://api.soroushapp.com"],
        dns_hosts=["soroushapp.com", "api.soroushapp.com"],
        availability="mixed",
        description="State-affiliated messenger from IRIB (Iranian state broadcasting)",
        website="https://soroushapp.com",
        call_capable=True,
        stun_hosts=["stun.soroushapp.com"],
        turn_hosts=["turn.soroushapp.com:3478"],
        calls_global=False,
    ),
]

# fast lookup by id — used throughout the codebase.
MESSENGER_BY_ID: Dict[str, Messenger] = {m.id: m for m in MESSENGERS}
