"""Tests for the Iran-reference publisher CLI."""
import json
from pathlib import Path

import pytest

from ping_luma.interfaces.cli import publish_iran_reference as cli
from ping_luma.domain.messengers import MESSENGERS
from ping_luma.domain.probe_results import MessengerResult, ScanReport


def _fake_report() -> ScanReport:
    """Build a deterministic ScanReport without touching the network."""
    results = []
    for i, m in enumerate(MESSENGERS):
        results.append(MessengerResult(
            messenger=m,
            chat_score=80 if i % 2 == 0 else 10,
            chat_verdict="REACHABLE" if i % 2 == 0 else "BLOCKED",
            call_score=80 if i % 3 == 0 else 0,
            call_verdict=("REACHABLE" if i % 3 == 0
                          else "UNKNOWN" if m.call_protocol == "proprietary"
            else "BLOCKED"),
        ))
    return ScanReport(timestamp="2026-04-26T00:00:00Z", results=results)


@pytest.fixture
def patched_scan(monkeypatch):
    monkeypatch.setattr(cli, "run_full_scan", _fake_report)
    return _fake_report()


def test_dry_run_emits_valid_json_on_stdout(capsys, patched_scan):
    rc = cli.main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "ts" in payload
    assert isinstance(payload["results"], dict)
    # Every messenger must appear in the payload.
    assert set(payload["results"].keys()) == {m.id for m in MESSENGERS}
    for v in payload["results"].values():
        assert "chat_ok" in v
        assert "call_ok" in v


def test_writes_file_in_iran_reference_shape(tmp_path: Path, patched_scan):
    out = tmp_path / "iran-ref.json"
    rc = cli.main(["--output", str(out), "--pretty"])
    assert rc == 0
    assert out.exists()
    payload = json.loads(out.read_text())
    # Pretty print → should contain newlines and indentation.
    assert "\n  " in out.read_text()
    # Shape sanity.
    assert payload["ts"] == "2026-04-26T00:00:00Z"
    bale = payload["results"]["bale"]
    assert isinstance(bale["chat_ok"], bool)


def test_missing_output_is_a_clean_error(patched_scan, caplog):
    rc = cli.main([])
    assert rc == 2


def test_creates_parent_directory_if_missing(tmp_path: Path, patched_scan):
    nested = tmp_path / "deep" / "nested" / "out.json"
    rc = cli.main(["--output", str(nested)])
    assert rc == 0
    assert nested.exists()


def test_quiet_silences_info_logs(patched_scan, caplog):
    cli.main(["--dry-run", "--quiet"])
    info_records = [r for r in caplog.records if r.levelname == "INFO"]
    assert info_records == []


def test_compact_form_has_no_indentation(tmp_path: Path, patched_scan):
    out = tmp_path / "compact.json"
    rc = cli.main(["--output", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "\n  " not in text  # no pretty-print indent
    # Still valid JSON.
    json.loads(text)
