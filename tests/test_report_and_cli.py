from datetime import UTC, datetime, timedelta

from mdm_lab import cli
from mdm_lab.report import build_report, to_markdown
from tests.fake_server import FakeHeadwind

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _ms(dt):
    return int(dt.timestamp() * 1000)


def test_report_marks_check_in_freshness():
    rows = build_report([
        {"id": 1, "number": "a", "enrollTime": _ms(NOW), "lastUpdate": _ms(NOW - timedelta(hours=1))},
        {"id": 2, "number": "b", "enrollTime": _ms(NOW), "lastUpdate": _ms(NOW - timedelta(days=3))},
        {"id": 3, "number": "c", "enrollTime": 0, "lastUpdate": 0},
    ], now=NOW)
    assert [r["check_in_status"] for r in rows] == ["ok", "stale", "never"]
    assert rows[2]["enrollment_status"] == "not enrolled"
    assert rows[0]["last_check_in"] == "2026-11-11T11:00:00+00:00"
    assert "| device_number |" in to_markdown(rows)


def test_push_is_dry_run_by_default(tmp_path, capsys):
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("group,device_numbers\nlab,pixel-01;pixel-02\n", encoding="utf-8")
    assert cli.main(["push", str(csv_path)]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "would assign pixel-01" in out


def test_push_apply_assigns_known_devices_only(tmp_path, capsys, monkeypatch):
    csv_path = tmp_path / "g.csv"
    csv_path.write_text("group,device_numbers,wifi_ssid,wifi_password,wifi_security,apps,password_mode\n"
                        "lab,pixel-01;pixel-99,LabWifi,pw12345678,WPA2,com.example.notes,present\n",
                        encoding="utf-8")
    with FakeHeadwind() as fake:
        monkeypatch.setenv("HMDM_URL", fake.url)
        monkeypatch.setenv("HMDM_LOGIN", "admin")
        monkeypatch.setenv("HMDM_PASSWORD", "secret")
        assert cli.main(["push", str(csv_path), "--apply"]) == 1
        out = capsys.readouterr().out
        assert fake.devices[0]["configurationId"] == 101
        assert fake.configurations[101]["wifiSSID"] == "LabWifi"
    assert "assigned 1 device(s)" in out
    assert "skip pixel-99: not enrolled on this server" in out


def test_wipe_needs_yes_flag(capsys):
    assert cli.main(["wipe", "pixel-01"]) == 2
    assert "Re-run with --yes" in capsys.readouterr().err


def test_lock_reports_missing_plugin_and_report_still_writes(tmp_path, capsys, monkeypatch):
    out_csv = tmp_path / "report.csv"
    with FakeHeadwind() as fake:
        monkeypatch.setenv("HMDM_URL", fake.url)
        monkeypatch.setenv("HMDM_LOGIN", "admin")
        monkeypatch.setenv("HMDM_PASSWORD", "secret")
        assert cli.main(["lock", "pixel-01"]) == 1
        assert cli.main(["report", "--out", str(out_csv)]) == 0
    captured = capsys.readouterr()
    assert "not available on this server" in captured.err
    assert out_csv.read_text(encoding="utf-8").splitlines()[0] == (
        "device_number,enrollment_status,enrolled_at,last_check_in,check_in_status")


def test_missing_settings_gives_clean_error(monkeypatch, capsys):
    for var in ("HMDM_URL", "HMDM_LOGIN", "HMDM_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    assert cli.main(["lock", "pixel-01"]) == 1
    assert "set HMDM_URL" in capsys.readouterr().err
