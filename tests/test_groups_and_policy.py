import pytest

from mdm_lab.groups import GroupsError, load_groups
from mdm_lab.policy import PolicyError, build_configuration, configuration_name, describe

HEADER = "group,device_numbers,wifi_ssid,wifi_password,wifi_security,apps,password_mode\n"
APP_IDS = {"com.example.notes": 10, "com.example.mail": 11}


def write(tmp_path, body):
    path = tmp_path / "groups.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_loads_valid_groups(tmp_path):
    path = write(tmp_path,
                 "lab,pixel-01;pixel-02,LabWifi,pw12345678,WPA2,com.example.notes;com.example.mail,strong\n"
                 "guest,pixel-03,,,,,\n")
    groups = load_groups(path)
    assert [g.name for g in groups] == ["lab", "guest"]
    assert groups[0].device_numbers == ["pixel-01", "pixel-02"]
    assert groups[0].apps == ["com.example.notes", "com.example.mail"]
    assert groups[0].password_mode == "strong"
    assert groups[1].wifi_ssid == ""


def test_every_problem_is_reported_with_line_numbers(tmp_path):
    path = write(tmp_path,
                 "lab,,LabWifi,,WEP,,maybe\n"
                 "lab,pixel-04,,,,,\n")
    with pytest.raises(GroupsError) as info:
        load_groups(path)
    text = "\n".join(info.value.problems)
    assert "line 2: group 'lab' has no device_numbers" in text
    assert "line 2: wifi_security must be one of" in text
    assert "line 2: password_mode must be blank or one of" in text
    assert "line 2: wifi_ssid needs a wifi_password" in text
    assert "line 3: group 'lab' appears twice" in text


def test_missing_required_column(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name,devices\nlab,1\n", encoding="utf-8")
    with pytest.raises(GroupsError, match="missing column: group"):
        load_groups(path)


def test_configuration_contains_only_what_the_group_sets(tmp_path):
    path = write(tmp_path, "guest,pixel-03,,,,,\nlab,pixel-01,LabWifi,pw12345678,WPA3,com.example.notes,present\n")
    guest, lab = load_groups(path)
    guest_cfg = build_configuration(guest, None, APP_IDS)
    assert guest_cfg["name"] == "mdm-lab guest"
    assert "wifiSSID" not in guest_cfg and "applications" not in guest_cfg
    cfg = build_configuration(lab, None, APP_IDS)
    assert cfg["wifiSSID"] == "LabWifi"
    assert cfg["wifiPassword"] == "pw12345678"
    assert cfg["wifiSecurityType"] == "WPA3"
    assert cfg["passwordMode"] == "present"
    assert cfg["applications"] == [{"id": 10, "action": 1}]


def test_existing_server_settings_are_kept(tmp_path):
    path = write(tmp_path, "lab,pixel-01,LabWifi,pw12345678,WPA2,,\n")
    (group,) = load_groups(path)
    current = {"id": 7, "name": "mdm-lab lab", "brightness": 80, "applications": [{"id": 99}]}
    cfg = build_configuration(group, current, APP_IDS)
    assert cfg["id"] == 7 and cfg["brightness"] == 80
    assert cfg["applications"] == [{"id": 99}]
    assert cfg["wifiSSID"] == "LabWifi"


def test_unknown_app_is_refused(tmp_path):
    path = write(tmp_path, "lab,pixel-01,,,,com.example.unknown,\n")
    (group,) = load_groups(path)
    with pytest.raises(PolicyError, match="com.example.unknown"):
        build_configuration(group, None, APP_IDS)


def test_describe_lists_only_the_settings_a_group_sets(tmp_path):
    path = write(tmp_path, "guest,pixel-03,,,,,\nlab,pixel-01,LabWifi,pw12345678,WPA2,com.example.mail,easy\n")
    guest, lab = load_groups(path)
    assert describe(guest) == ["no settings (devices are only assigned)"]
    assert describe(lab) == ["wifi LabWifi (WPA2)", "apps com.example.mail", "password mode easy"]
    assert configuration_name(lab) == "mdm-lab lab"
