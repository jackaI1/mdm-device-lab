import pytest

from mdm_lab.client import MdmClient, MdmError
from tests.fake_server import FakeMdm


@pytest.fixture
def server():
    with FakeMdm() as fake:
        yield fake


def test_authenticate_and_list_devices(server):
    client = MdmClient(server.url, "admin", "secret")
    devices = client.list_devices()
    assert [d["number"] for d in devices] == ["pixel-01", "pixel-02"]
    assert server.requests[0][1] == "/rest/public/jwt/login"


def test_bad_password_raises(server):
    with pytest.raises(MdmError, match="HTTP 401"):
        MdmClient(server.url, "admin", "wrong").list_devices()


def test_unreachable_server_raises():
    client = MdmClient("http://127.0.0.1:1", "admin", "secret", timeout=2)
    with pytest.raises(MdmError, match="could not reach"):
        client.list_devices()


def test_send_lock_and_policy(server):
    client = MdmClient(server.url, "admin", "secret")
    client.send_command("1", "lock")
    client.apply_policy("2", {"group": "lab"})
    paths = [r[1] for r in server.requests]
    assert "/rest/private/devices/1/command" in paths
    assert "/rest/private/devices/2/configuration" in paths


def test_unknown_command_is_refused_before_sending(server):
    client = MdmClient(server.url, "admin", "secret")
    with pytest.raises(MdmError, match="unknown command"):
        client.send_command("1", "factory-reset-everything")
    assert all("command" not in r[1] for r in server.requests)


def test_server_error_is_reported(server):
    server.fail_paths.add("/rest/private/devices/1/command")
    client = MdmClient(server.url, "admin", "secret")
    with pytest.raises(MdmError, match="HTTP 500"):
        client.send_command("1", "lock")
