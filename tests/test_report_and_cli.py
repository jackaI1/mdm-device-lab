from datetime import UTC, datetime, timedelta

from mdm_lab import cli
from mdm_lab.report import build_report, to_markdown
from tests.fake_server import FakeMdm

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def test_report_marks_check_in_freshness():
    recent_ms = int((NOW - timedelta(hours=1)).timestamp() * 1000)
    old_ms = int((NOW - timedelta(days=3)).timestamp() * 1000)
    rows = build_report([
        {"id": 1, "number": "a", "enrolled": True, "lastUpdate": recent_ms},
        {"id": 2, "number": "b", "enrolled": True, "lastUpdate": old_ms},
        {"id": 3, "number": "c", "enrolled": False, "lastUpdate": None},
    ], now=NOW)
    assert [r["check_in_status"] for r in rows] == ["ok", "stale", "never"]
    assert rows[2]["enrollment_status"] == "not enrolled"
    assert rows[0]["last_check_in"] == "2026-11-11T11:00:00+00:00"
    assert "| device_id |" in to_markdown(rows)


def test_report_accepts_iso_timestamps():
    rows = build_report([{"id": 9, "name": "x", "lastCheckIn": "2026-11-11T11:30:00Z"}], now=NOW)
    assert rows[0]["check_in_status"] == "ok"


def test_push_is_dry_run_by_default(tmp_path, capsys, monkeypatch):
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("group,device_ids\nlab,1;2\n", encoding="utf-8")
    assert cli.main(["push", str(csv_path)]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "would send to 1" in out


def test_push_apply_sends_to_known_devices_only(tmp_path, capsys, monkeypatch):
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("group,device_ids\nlab,1;99\n", encoding="utf-8")
    with FakeMdm() as fake:
        monkeypatch.setenv("HMDM_URL", fake.url)
        monkeypatch.setenv("HMDM_LOGIN", "admin")
        monkeypatch.setenv("HMDM_PASSWORD", "secret")
        assert cli.main(["push", str(csv_path), "--apply"]) == 1
        out = capsys.readouterr().out
    assert "sent to 1" in out
    assert "skip 99: not enrolled" in out


def test_wipe_needs_yes_flag(capsys):
    assert cli.main(["wipe", "1"]) == 2
    assert "Re-run with --yes" in capsys.readouterr().err


def test_lock_and_report_end_to_end(tmp_path, capsys, monkeypatch):
    out_csv = tmp_path / "report.csv"
    with FakeMdm() as fake:
        monkeypatch.setenv("HMDM_URL", fake.url)
        monkeypatch.setenv("HMDM_LOGIN", "admin")
        monkeypatch.setenv("HMDM_PASSWORD", "secret")
        assert cli.main(["lock", "1"]) == 0
        assert cli.main(["report", "--out", str(out_csv)]) == 0
    assert "lock sent to 1" in capsys.readouterr().out
    assert out_csv.read_text(encoding="utf-8").splitlines()[0] == (
        "device_id,name,enrollment_status,last_check_in,check_in_status")


def test_missing_settings_gives_clean_error(monkeypatch, capsys):
    for var in ("HMDM_URL", "HMDM_LOGIN", "HMDM_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    assert cli.main(["lock", "1"]) == 1
    assert "set HMDM_URL" in capsys.readouterr().err
