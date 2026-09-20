"""work_servers/bash_worklet -- tmux-backed terminal. See README.md."""
import subprocess

import pytest

from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def work(client):
    return client.post("/api/works", json={"goal": "跑个终端"}).json()


@pytest.fixture
def worklet(client, work, home):
    r = client.post(f"/api/works/{work['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"})
    assert r.status_code == 201, r.text
    return r.json()


def test_attach_reports_cwd_and_a_ttyd_window(worklet, home):
    assert worklet["alive"] and worklet["cwd"] == str(home / "ws")
    assert worklet["window"]["url"].startswith("http://127.0.0.1:") and worklet["window"]["url"].endswith(f"/?arg={worklet['id']}")   # tmuxd 自带的 ttyd
    assert worklet["handle"]["capabilities"] == ["send"]
    assert "server" not in worklet                     # 由谁建的不对外


def test_worklet_id_is_the_tmux_session_name(client, worklet):
    sock = client.get("/api/system/info").json()["tmux_socket"]
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={worklet['id']}"]).returncode == 0


def test_no_capture_endpoint_reading_is_for_people(client, work, worklet):
    assert client.get(f"/api/works/{work['id']}/worklets/{worklet['id']}/capture").status_code == 404


def test_reattach_is_idempotent(client, work, worklet):
    again = client.post(f"/api/works/{work['id']}/worklets/{worklet['id']}/attach").json()
    assert again["id"] == worklet["id"] and again["alive"]
    assert len(client.get(f"/api/works/{work['id']}/worklets").json()) == 1


def test_detach_reclaims_everything(client, work, worklet):
    sock = client.get("/api/system/info").json()["tmux_socket"]
    assert client.delete(f"/api/works/{work['id']}/worklets/{worklet['id']}").status_code == 200
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={worklet['id']}"]).returncode != 0
    assert client.get(f"/api/works/{work['id']}/worklets").json() == []


def test_worklet_ids_are_numbered_within_the_work(client, work, worklet, home):
    s2 = client.post(f"/api/works/{work['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    assert worklet["id"].endswith("-w1") and s2["id"].endswith("-w2")
