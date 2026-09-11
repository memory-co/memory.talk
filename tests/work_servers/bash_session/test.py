"""work_servers/bash_session -- tmux-backed terminal. See README.md."""
import subprocess
import time

import pytest

from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def work(client):
    return client.post("/api/works", json={"goal": "跑个终端"}).json()


@pytest.fixture
def session(client, work, home):
    r = client.post(f"/api/works/{work['id']}/sessions", json={"uri": f"bash://{home / 'ws'}"})
    assert r.status_code == 201, r.text
    return r.json()


def test_attach_reports_cwd_and_no_window_without_ttyd(session, home):
    assert session["alive"] and session["cwd"] == str(home / "ws")
    assert session["window"]["url"] is None
    assert session["handle"]["capabilities"] == ["capture", "send"]
    assert "server" not in session                     # 由谁建的不对外


def test_session_id_is_the_tmux_session_name(client, session):
    sock = client.get("/api/system/info").json()["tmux_socket"]
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={session['id']}"]).returncode == 0


def test_capture_sees_what_happened_in_the_terminal(client, work, session):
    sock = client.get("/api/system/info").json()["tmux_socket"]
    subprocess.run(["tmux", "-L", sock, "send-keys", "-t", f"{session['id']}:", "echo hello-v5", "Enter"])
    time.sleep(0.3)
    assert "hello-v5" in client.get(f"/api/works/{work['id']}/sessions/{session['id']}/capture").json()


def test_reattach_is_idempotent(client, work, session):
    again = client.post(f"/api/works/{work['id']}/sessions/{session['id']}/attach").json()
    assert again["id"] == session["id"] and again["alive"]
    assert len(client.get(f"/api/works/{work['id']}/sessions").json()) == 1


def test_detach_reclaims_everything(client, work, session):
    sock = client.get("/api/system/info").json()["tmux_socket"]
    assert client.delete(f"/api/works/{work['id']}/sessions/{session['id']}").status_code == 200
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={session['id']}"]).returncode != 0
    assert client.get(f"/api/works/{work['id']}/sessions").json() == []
    assert client.get(f"/api/works/{work['id']}/sessions/{session['id']}/capture").status_code == 404


def test_session_ids_are_numbered_within_the_work(client, work, session, home):
    s2 = client.post(f"/api/works/{work['id']}/sessions", json={"uri": f"bash://{home / 'ws'}"}).json()
    assert session["id"].endswith("-s1") and s2["id"].endswith("-s2")
