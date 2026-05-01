"""CLI entry point for the Iran-side reference publisher.

Run once and print the JSON without writing a file (useful for the first
manual sanity check from inside Iran)::

    python -m ping_luma.publish_iran_reference --dry-run --pretty

Write to a file the workflow will commit::

    python -m ping_luma.publish_iran_reference \\
        --output iran-ref.json --pretty
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from ping_luma.checker import run_full_scan, to_iran_reference_payload
from ping_luma.messengers import MESSENGERS

log = logging.getLogger("PingLuma.publish_iran_reference")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ping_luma.publish_iran_reference",
        description=(
            "Probe every messenger from THIS machine's network and write the "
            "result as JSON in the shape consumed by the bot's "
            "IRAN_REFERENCE_URL. Run only on a device routed through Iran."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Path to write the JSON to (e.g. iran-ref.json). "
             "Required unless --dry-run is given.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON for human inspection. The bot accepts "
             "either form.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Probe and print to stdout; do not touch the filesystem.",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only log warnings and errors.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.dry_run and args.output is None:
        log.error("--output is required (or pass --dry-run to print to stdout)")
        return 2

    log.info("Probing %d messengers from this network", len(MESSENGERS))
    report = run_full_scan()
    payload = to_iran_reference_payload(report)

    n_total = len(payload["results"])
    n_chat = sum(1 for v in payload["results"].values() if v["chat_ok"])
    n_call = sum(1 for v in payload["results"].values() if v["call_ok"])
    log.info(
        "Probe done: %d/%d chat reachable, %d/%d call reachable",
        n_chat, n_total, n_call, n_total,
    )

    indent = 2 if args.pretty else None
    text = json.dumps(payload, indent=indent, sort_keys=True)

    if args.dry_run:
        sys.stdout.write(text + "\n")
        return 0

    out_path: Path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    log.info("Wrote %s (%d bytes)", out_path, len(text) + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
