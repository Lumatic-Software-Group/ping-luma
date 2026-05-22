"""Entry point shim: ``python -m ping_luma.publish_iran_reference``."""

from ping_luma.application.scanning import run_full_scan, to_iran_reference_payload
from ping_luma.interfaces.cli.publish_iran_reference import main

__all__ = ["main", "run_full_scan", "to_iran_reference_payload"]

if __name__ == "__main__":
    raise SystemExit(main())
