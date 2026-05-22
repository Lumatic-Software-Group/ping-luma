from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from ping_luma.domain.messengers import MESSENGERS, Messenger
from ping_luma.domain.probe_results import MessengerResult, ScanReport
from ping_luma.infrastructure.probe_runner import _check_one_messenger


def run_full_scan(
        messengers: list[Messenger] | None = None,
) -> ScanReport:
    """Probe all messengers concurrently.

    Intended for use by the Iran-side reference service (deployed on an
    Iranian VPS). Do NOT call this from the bot host as a "user network"
    answer — it isn't.
    """
    targets = messengers or MESSENGERS
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results: list[MessengerResult | None] = [None] * len(targets)

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {pool.submit(_check_one_messenger, m): i
                   for i, m in enumerate(targets)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    return ScanReport(
        timestamp=timestamp,
        results=[r for r in results if r is not None],
    )


def to_iran_reference_payload(report: ScanReport) -> dict[str, Any]:
    """Serialize a scan report into the Iran-reference HTTP shape.

    Used by the optional Iran-side reference service to expose its results.
    """
    return {
        "ts": report.timestamp,
        "results": {
            r.messenger.id: {
                "chat_ok": r.chat_ok,
                "call_ok": r.call_ok,
            }
            for r in report.results
        },
    }
