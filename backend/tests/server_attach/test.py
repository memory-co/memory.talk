"""server:协议解析 → 建现场(真 tmux,独立 socket)→ 窗 / 把手 → 重入 → 关闭即回收。"""
import shutil
import subprocess
import time

import pytest

needs_tmux = pytest.mark.skipif(shutil.which("tmux") is None, reason="需要 tmux")


def test_registry_and_resolve(client):
    infos = {s["name"]: s["protocols"] for s in client.get("/api/servers").json()}
    assert infos == {"bash": ["bash"], "claude": ["claude"], "codex": ["codex"], "kimi": ["kimi"],
                     "http": ["http", "https"], "default": []}
    assert [s["name"] for s in client.get("/api/servers").json()][-1] == "default"
    assert client.get("/api/servers/resolve").status_code == 404        # 寻址不是端点,open 时自动做

    # 寻址是内部的:服务层按协议找到声明它的 server,没人声明 → default
    from services.servers.uri import parse_uri
    reg = client.app.state.servers.registry
    assert reg.resolve(parse_uri("codex:///w/p")).name == "codex"
    assert reg.resolve(parse_uri("https://x.y/z")).name == "http"
    assert reg.resolve(parse_uri("vim:///w/a.txt")).name == "default"


def test_http_sessions(client):
    t = client.post("/api/tasks", json={"goal": "看文档"}).json()
    m = client.post(f"/api/tasks/{t['id']}/sessions", json={"uri": "https://localhost:5173/app"}).json()
    assert m["scheme"] == "https" and "server" not in m and m["window"]["embed"] == "/proxy/5173/app"
    assert m["handle"] == {"kind": "none", "capabilities": []}
    m2 = client.post(f"/api/tasks/{t['id']}/sessions", json={"uri": "https://example.com/x"}).json()
    assert m2["window"]["embed"] == "https://example.com/x" and m2["id"].endswith("-s2")
    assert client.get(f"/api/tasks/{t['id']}/sessions/{m['id']}/capture").status_code == 409


@needs_tmux
def test_terminal_session_lifecycle(client, home):
    t = client.post("/api/tasks", json={"goal": "跑个终端"}).json()
    ws = str(home / "ws")
    r = client.post(f"/api/tasks/{t['id']}/sessions", json={"uri": f"bash://{ws}"})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["scheme"] == "bash" and m["alive"] is True and m["cwd"] == ws
    assert m["window"]["url"] is None                       # 没配 ttyd → 老实报没有画面
    assert m["handle"]["capabilities"] == ["capture", "send"]

    # 现场真的活着:tmux 会话名 = 会话 id
    sock = client.get("/api/system/info").json()["tmux_socket"]
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={m['id']}"]).returncode == 0

    # 把手能看见;重入幂等
    subprocess.run(["tmux", "-L", sock, "send-keys", "-t", f"{m['id']}:", "echo hello-v5", "Enter"])
    time.sleep(0.3)
    assert "hello-v5" in client.get(f"/api/tasks/{t['id']}/sessions/{m['id']}/capture").text
    again = client.post(f"/api/tasks/{t['id']}/sessions/{m['id']}/attach").json()
    assert again["id"] == m["id"] and again["alive"]
    assert len(client.get(f"/api/tasks/{t['id']}/sessions").json()) == 1

    # 没有专门 server 的协议 → default:协议名当命令。命令不在 PATH → 明确报错
    r = client.post(f"/api/tasks/{t['id']}/sessions", json={"uri": "nosuchcmd-zz://"})
    assert r.status_code == 400 and r.json()["error"] == "cmd_not_found"
    d = client.post(f"/api/tasks/{t['id']}/sessions", json={"uri": f"sleep://{ws}"})
    assert d.status_code == 201 and d.json()["scheme"] == "sleep"         # 走了 default,但调用方不感知
    client.delete(f"/api/tasks/{t['id']}/sessions/{d.json()['id']}")

    # 关闭即回收
    assert client.delete(f"/api/tasks/{t['id']}/sessions/{m['id']}").status_code == 204
    assert subprocess.run(["tmux", "-L", sock, "has-session", "-t", f"={m['id']}"]).returncode != 0
    assert client.get(f"/api/tasks/{t['id']}/sessions").json() == []
    assert client.get(f"/api/tasks/{t['id']}/sessions/{m['id']}/capture").status_code == 404

    # 做完 → 冻结:现场销毁、登记留着
    m = client.post(f"/api/tasks/{t['id']}/sessions", json={"uri": f"bash://{ws}"}).json()
    client.patch(f"/api/tasks/{t['id']}", json={"status": "done"})
    mem = client.get(f"/api/tasks/{t['id']}/sessions").json()
    assert len(mem) == 1 and mem[0]["alive"] is False
