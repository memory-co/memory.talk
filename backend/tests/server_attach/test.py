"""server:协议解析 → 建现场(真 tmux,独立 socket)→ 窗 / 把手 → 重入 → 关闭即回收。"""
import shutil
import subprocess
import time

import pytest

needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="需要 tmux")


def test_registry_and_resolve(client):
    names = sorted(s["name"] for s in client.get("/api/servers").json())
    assert names == ["bash", "claude", "codex", "http", "https", "kimi"]

    assert client.get("/api/servers/resolve", params={"uri": "codex:///w/p"}).json()["server"] == "codex"
    assert client.get("/api/servers/resolve", params={"uri": "kimi:///w/p"}).json()["server"] == "kimi"
    assert client.get("/api/servers/resolve", params={"uri": "https://x.y/z"}).json()["server"] == "https"
    assert client.get("/api/servers/resolve", params={"uri": "bash:///w"}).json()["server"] == "bash"
    r = client.get("/api/servers/resolve", params={"uri": "vim:///w/a.txt"})   # 没有 vim.py → 没有 vim server
    assert r.status_code == 400 and r.json()["error"] == "no_server"
    r = client.get("/api/servers/resolve", params={"uri": "nosuchcmd-zz://"})
    assert r.status_code == 400 and r.json()["error"] == "no_server"
    assert client.get("/api/servers/resolve", params={"uri": "no-scheme"}).status_code == 400


def test_http_members(client):
    t = client.post("/api/tasks", json={"goal": "看文档"}).json()
    m = client.post(f"/api/tasks/{t['id']}/members", json={"uri": "https://localhost:5173/app"}).json()
    assert m["scheme"] == "https" and m["window"]["embed"] == "/proxy/5173/app"
    assert m["handle"] == {"kind": "none", "capabilities": []}
    m2 = client.post(f"/api/tasks/{t['id']}/members", json={"uri": "https://example.com/x"}).json()
    assert m2["window"]["embed"] == "https://example.com/x" and m2["id"].endswith("-m2")
    assert client.get(f"/api/tasks/{t['id']}/members/{m['id']}/capture").status_code == 409


@needs_tmux
def test_terminal_member_lifecycle(client, home):
    t = client.post("/api/tasks", json={"goal": "跑个终端"}).json()
    ws = str(home / "ws")
    r = client.post(f"/api/tasks/{t['id']}/members", json={"uri": f"bash://{ws}"})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["scheme"] == "bash" and m["alive"] is True and m["cwd"] == ws
    assert m["window"]["url"] is None                       # 没配 ttyd → 老实报没有画面
    assert m["handle"]["capabilities"] == ["capture", "send"]

    # 现场真的活着:tmux 会话名 = 成员 id
    sock = client.get("/api/system/info").json()["tmux_socket"]
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={m['id']}"]).returncode == 0

    # 把手能看见;重入幂等
    subprocess.run(["tmux", "-L", sock, "send-keys", "-t", f"{m['id']}:", "echo hello-v5", "Enter"])
    time.sleep(0.3)
    assert "hello-v5" in client.get(f"/api/tasks/{t['id']}/members/{m['id']}/capture").text
    again = client.post(f"/api/tasks/{t['id']}/members/{m['id']}/attach").json()
    assert again["id"] == m["id"] and again["alive"]
    assert len(client.get(f"/api/tasks/{t['id']}/members").json()) == 1

    # 命令不存在 → 明确报错
    r = client.post(f"/api/tasks/{t['id']}/members", json={"uri": "nosuchcmd-zz://"})
    assert r.status_code == 400 and r.json()["error"] == "no_server"

    # 关闭即回收
    assert client.delete(f"/api/tasks/{t['id']}/members/{m['id']}").status_code == 204
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={m['id']}"]).returncode != 0
    assert client.get(f"/api/tasks/{t['id']}/members").json() == []
    assert client.get(f"/api/tasks/{t['id']}/members/{m['id']}/capture").status_code == 404

    # 做完 → 冻结:现场销毁、登记留着
    m = client.post(f"/api/tasks/{t['id']}/members", json={"uri": f"bash://{ws}"}).json()
    client.patch(f"/api/tasks/{t['id']}", json={"status": "done"})
    mem = client.get(f"/api/tasks/{t['id']}/members").json()
    assert len(mem) == 1 and mem[0]["alive"] is False
