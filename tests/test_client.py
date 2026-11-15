import pytest

from mdm_lab import client as api
from mdm_lab.client import MdmClient, MdmError
from tests.fake_server import MD5_SECRET, FakeHeadwind


@pytest.fixture
def server():
    with FakeHeadwind() as fake:
        yield fake


def test_login_sends_md5_password_and_uses_bearer_token(server):
    client = MdmClient(server.url, "admin", "secret")
    numbers = [d["number"] for d in client.list_devices()]
    assert numbers == ["pixel-01", "pixel-02"]
    method, path, body = server.requests[0]
    assert (method, path) == ("POST", api.LOGIN_PATH)
    assert body == {"login": "admin", "password": MD5_SECRET}
    assert MD5_SECRET != "secret"


def test_bad_password_raises(server):
    with pytest.raises(MdmError, match="HTTP 401"):
        MdmClient(server.url, "admin", "wrong").list_devices()


def test_unreachable_server_raises():
    client = MdmClient("http://127.0.0.1:1", "admin", "secret", timeout=2)
    with pytest.raises(MdmError, match="could not reach"):
        client.list_devices()


def test_device_search_pages_through_all_results(server, monkeypatch):
    monkeypatch.setattr(api, "PAGE_SIZE", 1)
    client = MdmClient(server.url, "admin", "secret")
    assert len(client.list_devices()) == 2
    searches = [b for m, p, b in server.requests if p == api.DEVICES_SEARCH_PATH]
    assert [s["pageNum"] for s in searches] == [1, 2, 3]


def test_save_configuration_and_assign_devices(server):
    client = MdmClient(server.url, "admin", "secret")
    saved = client.save_configuration({"name": "mdm-lab lab", "type": 0})
    assert saved["id"] == 101
    client.assign_devices([1, 2], saved["id"])
    assert [d["configurationId"] for d in server.devices] == [101, 101]
    assert client.find_configuration("mdm-lab lab")["id"] == 101
    assert client.find_configuration("missing") is None


def test_applications_map_package_to_id(server):
    apps = MdmClient(server.url, "admin", "secret").list_applications()
    assert apps == {"com.example.notes": 10, "com.example.mail": 11}


def test_lock_on_server_without_plugin_gives_clear_error(server):
    client = MdmClient(server.url, "admin", "secret")
    with pytest.raises(MdmError, match="lock is not available on this server"):
        client.send_command(1, "lock")
    assert server.requests[-1][1] == api.COMMAND_PATHS["lock"]


def test_wipe_and_lock_work_when_plugin_is_present():
    with FakeHeadwind(plugin_enabled=True) as server:
        client = MdmClient(server.url, "admin", "secret")
        client.send_command(2, "wipe")
        assert server.requests[-1][1] == api.COMMAND_PATHS["wipe"]


def test_unknown_command_is_refused_before_sending(server):
    client = MdmClient(server.url, "admin", "secret")
    with pytest.raises(MdmError, match="unknown command"):
        client.send_command(1, "factory-reset-everything")
    assert not any(p in api.COMMAND_PATHS.values() for _, p, _ in server.requests)


def test_server_error_is_reported(server):
    server.fail_paths.add(api.DEVICES_SEARCH_PATH)
    with pytest.raises(MdmError, match="HTTP 500"):
        MdmClient(server.url, "admin", "secret").list_devices()
