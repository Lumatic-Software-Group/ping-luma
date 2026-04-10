"""
tests/test_checker.py
Unit tests for the core connectivity engine.
All network calls are mocked so tests run offline in CI.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from ping_luma.checker import (
    CheckReport,
    DnsResult,
    EndpointResult,
    _score,
    _verdict,
    report_to_text,
    run_quick_ping,
)


class TestScore(unittest.TestCase):
    def _ep(self, reachable: bool, latency: float = 200.0) -> EndpointResult:
        return EndpointResult(
            name="test", url="https://example.com",
            reachable=reachable, latency_ms=latency if reachable else None,
        )

    def _dns(self, resolved: bool) -> DnsResult:
        return DnsResult(host="example.com", resolved=resolved)

    def test_all_ok_low_latency(self):
        eps  = [self._ep(True, 150)] * 4
        dns  = [self._dns(True)] * 3
        s    = _score(eps, dns)
        self.assertGreaterEqual(s, 75)

    def test_all_fail(self):
        eps = [self._ep(False)] * 4
        dns = [self._dns(False)] * 3
        s   = _score(eps, dns)
        self.assertEqual(s, 0)

    def test_partial(self):
        eps = [self._ep(True), self._ep(False), self._ep(True), self._ep(False)]
        dns = [self._dns(True), self._dns(False), self._dns(True)]
        s   = _score(eps, dns)
        self.assertGreater(s, 0)
        self.assertLess(s, 100)


class TestVerdict(unittest.TestCase):
    def test_online(self):
        status, *_ = _verdict(80)
        self.assertEqual(status, "ONLINE")

    def test_degraded(self):
        status, *_ = _verdict(55)
        self.assertEqual(status, "DEGRADED")

    def test_offline(self):
        status, *_ = _verdict(20)
        self.assertEqual(status, "OFFLINE")

    def test_boundary_75(self):
        self.assertEqual(_verdict(75)[0], "ONLINE")

    def test_boundary_74(self):
        self.assertEqual(_verdict(74)[0], "DEGRADED")

    def test_boundary_40(self):
        self.assertEqual(_verdict(40)[0], "DEGRADED")

    def test_boundary_39(self):
        self.assertEqual(_verdict(39)[0], "OFFLINE")


class TestReportToText(unittest.TestCase):
    def _make_report(self, status: str, score: int) -> CheckReport:
        return CheckReport(
            timestamp="2026-01-01 00:00 UTC",
            overall_status=status,
            score=score,
            endpoints=[
                EndpointResult("سرور API", "https://tapi.bale.ai", True, 120.0, 200, True),
            ],
            dns_results=[
                DnsResult("tapi.bale.ai", True, "1.2.3.4", 30.0),
            ],
            summary="خلاصه",
            advice="توصیه",
        )

    def test_contains_status(self):
        r    = self._make_report("ONLINE", 90)
        text = report_to_text(r)
        self.assertIn("ONLINE", text)
        self.assertIn("90/100", text)

    def test_contains_persian(self):
        r    = self._make_report("OFFLINE", 10)
        text = report_to_text(r)
        self.assertIn("بررسی اتصال بله", text)

    def test_emoji_badge(self):
        self.assertIn("🟢", report_to_text(self._make_report("ONLINE",   80)))
        self.assertIn("🟡", report_to_text(self._make_report("DEGRADED", 50)))
        self.assertIn("🔴", report_to_text(self._make_report("OFFLINE",  10)))


class TestQuickPing(unittest.TestCase):
    @patch("ping_luma.checker.check_endpoint")
    def test_reachable(self, mock_check):
        mock_check.return_value = EndpointResult(
            "سرور API", "https://tapi.bale.ai",
            reachable=True, latency_ms=95.0,
        )
        ok, lat = run_quick_ping()
        self.assertTrue(ok)
        self.assertAlmostEqual(lat, 95.0)

    @patch("ping_luma.checker.check_endpoint")
    def test_unreachable(self, mock_check):
        mock_check.return_value = EndpointResult(
            "سرور API", "https://tapi.bale.ai",
            reachable=False, error="timeout",
        )
        ok, lat = run_quick_ping()
        self.assertFalse(ok)


class TestCache(unittest.TestCase):
    """Tests for the TTL cache logic in bot.py."""

    def setUp(self):
        # Import lazily so we don't need a real bot token
        import importlib
        import sys
        # Patch telegram before import
        self._orig = sys.modules.copy()

    def test_cache_entry_structure(self):
        """CacheEntry must be a (CheckReport, float) tuple."""
        from ping_luma.checker import run_full_check
        import ping_luma.bot as bot_module

        report = CheckReport(
            timestamp="2026-01-01 00:00 UTC",
            overall_status="ONLINE",
            score=90,
        )
        chat_id = 99999
        bot_module._set_cached(chat_id, report)
        entry = bot_module._cache.get(chat_id)
        self.assertIsNotNone(entry)
        stored_report, cached_at = entry
        self.assertIsInstance(stored_report, CheckReport)
        self.assertIsInstance(cached_at, float)

    def test_cache_fresh(self):
        import ping_luma.bot as bot_module
        import ping_luma.config as cfg

        report  = CheckReport("t", "ONLINE", 90)
        chat_id = 11111
        bot_module._set_cached(chat_id, report)
        result = bot_module._get_cached(chat_id)
        self.assertIsNotNone(result)

    def test_cache_expired(self):
        import ping_luma.bot as bot_module
        import ping_luma.config as cfg

        report  = CheckReport("t", "ONLINE", 90)
        chat_id = 22222
        # Manually insert an old entry
        with bot_module._cache_lock:
            bot_module._cache[chat_id] = (report, time.time() - cfg.CACHE_TTL - 1)
        result = bot_module._get_cached(chat_id)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()