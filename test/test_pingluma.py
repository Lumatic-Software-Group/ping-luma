import unittest
from unittest.mock import patch

from ping_luma.checker import (
    DnsResult,
    MessengerResult,
    ScanReport,
    UrlResult,
    _check_one_messenger,
    _score_messenger,
    format_messenger_detail,
    format_scan_report,
    run_quick_ping,
)
from ping_luma.messengers import MESSENGER_BY_ID, MESSENGERS


def _url(ok: bool, lat: float = 200.0) -> UrlResult:
    return UrlResult(
        url="https://example.com",
        reachable=ok,
        latency_ms=lat if ok else None,
        ssl_valid=ok,
    )


def _dns(ok: bool) -> DnsResult:
    return DnsResult(
        host="example.com",
        resolved=ok,
        ip="1.2.3.4" if ok else None,
    )


class TestRegistry(unittest.TestCase):
    def test_seven_messengers(self):
        self.assertEqual(len(MESSENGERS), 7)

    def test_all_expected_ids_present(self):
        ids = {m.id for m in MESSENGERS}
        for expected in ["bale", "eitaa", "rubika", "gap", "igap", "soroush"]:
            self.assertIn(expected, ids)

    def test_lookup_by_id(self):
        bale = MESSENGER_BY_ID.get("bale")
        self.assertIsNotNone(bale)
        self.assertEqual(bale.name, "Bale")

    def test_availability_values_are_valid(self):
        valid = {"global", "mixed", "iran"}
        for m in MESSENGERS:
            self.assertIn(m.availability, valid, f"{m.id} has invalid availability")

    def test_all_have_probe_urls(self):
        for m in MESSENGERS:
            self.assertGreater(len(m.probe_urls), 0, f"{m.id} has no probe_urls")

    def test_all_have_dns_hosts(self):
        for m in MESSENGERS:
            self.assertGreater(len(m.dns_hosts), 0, f"{m.id} has no dns_hosts")

    def test_bale_gap_igap_are_global(self):
        for mid in ["bale", "gap", "igap"]:
            self.assertEqual(
                MESSENGER_BY_ID[mid].availability, "global",
                f"{mid} should be global",
            )


class TestScoring(unittest.TestCase):
    def test_all_ok_low_latency_is_reachable(self):
        score, verdict = _score_messenger([_url(True, 150)] * 2, [_dns(True)] * 2)
        self.assertGreaterEqual(score, 70)
        self.assertEqual(verdict, "REACHABLE")

    def test_all_fail_is_blocked(self):
        score, verdict = _score_messenger([_url(False)] * 2, [_dns(False)] * 2)
        self.assertEqual(score, 0)
        self.assertEqual(verdict, "BLOCKED")

    def test_mixed_results_are_partial(self):
        score, verdict = _score_messenger(
            [_url(True, 300), _url(False)],
            [_dns(True), _dns(False)],
        )
        self.assertGreater(score, 0)
        self.assertLess(score, 100)

    def test_fast_latency_scores_higher_than_slow(self):
        fast, _ = _score_messenger([_url(True, 100)] * 2, [_dns(True)] * 2)
        slow, _ = _score_messenger([_url(True, 2000)] * 2, [_dns(True)] * 2)
        self.assertGreater(fast, slow)

    def test_reachable_threshold_is_70(self):
        score, verdict = _score_messenger([_url(True, 200)] * 2, [_dns(True)] * 2)
        self.assertGreaterEqual(score, 70)
        self.assertEqual(verdict, "REACHABLE")

    def test_blocked_threshold_is_below_30(self):
        score, verdict = _score_messenger([_url(False)] * 2, [_dns(False)] * 2)
        self.assertLess(score, 30)
        self.assertEqual(verdict, "BLOCKED")


class TestCheckOneMessenger(unittest.TestCase):
    @patch("ping_luma.checker._probe_url")
    @patch("ping_luma.checker._probe_dns")
    def test_bale_reachable_when_probes_succeed(self, mock_dns, mock_url):
        mock_url.return_value = _url(True, 120)
        mock_dns.return_value = _dns(True)
        result = _check_one_messenger(MESSENGER_BY_ID["bale"])
        self.assertEqual(result.messenger.id, "bale")
        self.assertEqual(result.verdict, "REACHABLE")
        self.assertIsNotNone(result.best_latency_ms)


class TestQuickPing(unittest.TestCase):
    @patch("ping_luma.checker._probe_url")
    def test_reachable_returns_true_and_latency(self, mock):
        mock.return_value = _url(True, 80)
        ok, lat = run_quick_ping("bale")
        self.assertTrue(ok)
        self.assertAlmostEqual(lat, 80.0)

    @patch("ping_luma.checker._probe_url")
    def test_unreachable_returns_false(self, mock):
        mock.return_value = _url(False)
        ok, _ = run_quick_ping("bale")
        self.assertFalse(ok)

    def test_unknown_messenger_id_returns_false(self):
        ok, lat = run_quick_ping("doesnotexist")
        self.assertFalse(ok)
        self.assertEqual(lat, 0.0)


class TestFormatters(unittest.TestCase):
    def _make_result(self, mid: str, verdict: str, score: int) -> MessengerResult:
        m = MESSENGER_BY_ID[mid]
        reachable = verdict == "REACHABLE"
        return MessengerResult(
            messenger=m,
            verdict=verdict,
            score=score,
            best_latency_ms=150.0 if reachable else None,
            url_results=[_url(reachable)],
            dns_results=[_dns(reachable)],
        )

    def _make_report(self) -> ScanReport:
        return ScanReport(
            timestamp="2026-01-01 00:00 UTC",
            results=[
                self._make_result("bale", "REACHABLE", 90),
                self._make_result("eitaa", "PARTIAL", 50),
                self._make_result("rubika", "BLOCKED", 10),
                self._make_result("gap", "REACHABLE", 85),
                self._make_result("igap", "REACHABLE", 80),
                self._make_result("soroush", "PARTIAL", 40),
            ],
        )

    def test_scan_report_contains_all_messenger_names(self):
        text = format_scan_report(self._make_report())
        for m in MESSENGERS:
            self.assertIn(m.name, text, f"{m.name} missing from scan report")

    def test_scan_report_has_summary_counts(self):
        text = format_scan_report(self._make_report())
        self.assertIn("3/7", text)  # 3 reachable of 7

    def test_detail_format_contains_verdict_and_name(self):
        r = self._make_result("bale", "REACHABLE", 90)
        text = format_messenger_detail(r)
        self.assertIn("در دسترس", text)
        self.assertIn("Bale", text)
        self.assertIn("90/100", text)

    def test_verdict_icons(self):
        for verdict, icon in [("REACHABLE", "✅"), ("PARTIAL", "⚠️"), ("BLOCKED", "❌")]:
            r = self._make_result("bale", verdict, 50)
            self.assertEqual(r.verdict_icon, icon)

    def test_report_counters(self):
        report = self._make_report()
        self.assertEqual(len(report.reachable), 3)
        self.assertEqual(len(report.partial), 2)
        self.assertEqual(len(report.blocked), 2)

    def test_detail_format_contains_url_and_dns_sections(self):
        r = self._make_result("bale", "REACHABLE", 90)
        text = format_messenger_detail(r)
        self.assertIn("سرورها", text)
        self.assertIn("DNS", text)

    def test_scan_report_uses_html_bold_tags(self):
        """Verify the formatter produces HTML, not MarkdownV2."""
        text = format_scan_report(self._make_report())
        self.assertIn("<b>", text)

    def test_detail_format_uses_html_bold_tags(self):
        r = self._make_result("bale", "REACHABLE", 90)
        text = format_messenger_detail(r)
        self.assertIn("<b>", text)


class TestCooldown(unittest.TestCase):
    def test_cooldown_active_immediately_after_scan(self):
        import ping_luma.bot as bot
        chat_id = 11111
        bot._mark_scan(chat_id)
        on_cd, secs = bot._is_on_cooldown(chat_id)
        self.assertTrue(on_cd)
        self.assertGreater(secs, 0)

    def test_cooldown_expired_after_ttl(self):
        import time
        import ping_luma.bot as bot
        chat_id = 22222
        bot._cooldown[chat_id] = time.time() - config.SCAN_COOLDOWN - 1
        on_cd, _ = bot._is_on_cooldown(chat_id)
        self.assertFalse(on_cd)


from ping_luma import config

if __name__ == "__main__":
    unittest.main()
