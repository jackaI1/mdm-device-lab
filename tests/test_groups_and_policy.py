import pytest

from mdm_lab.groups import GroupsError, load_groups
from mdm_lab.policy import build_policy

HEADER = "group,device_ids,wifi_ssid,wifi_password,wifi_security,apps,min_password_length,require_password\n"


def write(tmp_path, body):
    path = tmp_path / "groups.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def test_loads_valid_groups(tmp_path):
    path = write(tmp_path,
                 "lab,1;2,LabWifi,pw12345678,WPA2,com.example.notes;com.example.mail,8,yes\n"
                 "guest,3,,,,,,\n")
    groups = load_groups(path)
    assert [g.name for g in groups] == ["lab", "guest"]
    assert groups[0].device_ids == ["1", "2"]
    assert groups[0].apps == ["com.example.notes", "com.example.mail"]
    assert groups[0].require_password is True
    assert groups[1].wifi_ssid == ""


def test_every_problem_is_reported_with_line_numbers(tmp_path):
    path = write(tmp_path,
                 "lab,,LabWifi,,WEP,,99,maybe\n"
                 "lab,4,,,,,,\n")
    with pytest.raises(GroupsError) as info:
        load_groups(path)
    text = "\n".join(info.value.problems)
    assert "line 2: group 'lab' has no device_ids" in text
    assert "line 2: wifi_security must be one of" in text
    assert "line 2: min_password_length must be 1-16" in text
    assert "line 2: require_password must be yes or no" in text
    assert "line 2: wifi_ssid needs a wifi_password" in text
    assert "line 3: group 'lab' appears twice" in text


def test_missing_required_column(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name,devices\nlab,1\n", encoding="utf-8")
    with pytest.raises(GroupsError, match="missing column: group"):
        load_groups(path)


def test_policy_contains_only_what_the_group_sets(tmp_path):
    path = write(tmp_path, "guest,3,,,,,,\nlab,1,LabWifi,pw12345678,WPA3,com.example.notes,10,yes\n")
    guest, lab = load_groups(path)
    assert build_policy(guest) == {"group": "guest"}
    policy = build_policy(lab)
    assert policy["wifi"] == {"ssid": "LabWifi", "password": "pw12345678", "security": "WPA3"}
    assert policy["apps"] == [{"package": "com.example.notes", "action": "install"}]
    assert policy["password"] == {"required": True, "minLength": 10}
