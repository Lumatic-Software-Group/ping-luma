from __future__ import annotations

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

log = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def start_background() -> None:
    """Listen on PORT (default 8080) so platforms like Back4app can route health checks."""
    if os.getenv("PINGLUMA_DISABLE_HTTP_HEALTH", "").lower() in ("1", "true", "yes"):
        return
    raw = os.getenv("PORT", "8080")
    try:
        port = int(raw)
    except ValueError:
        port = 8080

    def run() -> None:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        log.info("Health endpoint http://0.0.0.0:%s/health", port)
        server.serve_forever()

    threading.Thread(target=run, name="paas-health-http", daemon=True).start()
