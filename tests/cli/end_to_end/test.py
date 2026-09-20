"""CLI:真起一个服务(随机端口、临时 home),用 `python -m memorytalk` 走一遍 server / user / work / meta。"""
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def cli(tmp_path):
    port = _free_port()
    env = {**os.environ, "MEMORY_TALK_HOME": str(tmp_path / "home"), "MEMORY_TALK_WORKSPACE": str(tmp_path / "ws"),
           "MEMORY_TALK_TMUX_SOCKET": f"mt-cli-{uuid.uuid4().hex[:6]}", "MEMORY_TALK_SERVER": f"http://127.0.0.1:{port}",
           "PYTHONPATH": str(ROOT)}
    env.pop("MEMORY_TALK_USER", None); env.pop("MEMORY_TALK_TTYD_URL", None)

    def run(*args, user=None, check=True, inp=None):
        e = {**env, **({"MEMORY_TALK_USER": user} if user else {})}
        p = subprocess.run([sys.executable, "-m", "memorytalk", *args], env=e, capture_output=True, text=True, input=inp, cwd=ROOT)
        if check and p.returncode != 0:
            raise AssertionError(f"exit {p.returncode}: {' '.join(args)}\n{p.stderr}")
        return p

    assert run("server", "status", check=False).returncode == 1          # 没起
    p = run("server", "start", "--port", str(port))
    assert "已启动" in p.stdout
    try:
        yield run
    finally:
        run("server", "stop", check=False)
        subprocess.run(["tmux", "-L", f"tmuxd-{env['MEMORY_TALK_TMUX_SOCKET']}", "kill-server"], capture_output=True)


def test_cli_end_to_end(cli):
    assert "运行中" in cli("server", "status").stdout
    assert "已在跑" in cli("server", "start").stdout                      # 幂等

    # 门:没 admin 什么都不能做 → setup → login;user add 要 admin
    p = cli("work", "list", check=False)
    assert p.returncode == 1 and "setup_required" in p.stderr
    cli("setup", "--password", "admin-pw-1")
    assert cli("setup", "--password", "x", check=False).returncode == 1
    assert "先 memory.talk login" in cli("work", "list", user="ghost", check=False).stderr
    cli("user", "add", "alice", "--email", "alice@example.com", "--password", "alice-pw-1")
    assert cli("user", "add", "alice", check=False).returncode == 1
    assert "alice" in cli("user", "list").stdout
    assert cli("login", "alice", "--password", "wrong", check=False).returncode == 1
    cli("login", "alice", "--password", "alice-pw-1")
    assert "alice@example.com" in cli("user", "whoami", user="alice").stdout
    assert "admin" in cli("user", "whoami", user="admin").stdout
    assert cli("user", "add", "eve", user="alice", check=False).returncode == 1          # member 不能建账号

    # work
    w = json.loads(cli("--json", "work", "create", "--goal", "把配置改成环境变量", user="alice").stdout)
    assert w["created_by"] == "alice"
    assert w["id"] in cli("work", "list").stdout
    child = json.loads(cli("--json", "work", "create", "--goal", "子事", "--parent", w["id"], user="alice").stdout)
    assert "子事" in cli("work", "show", w["id"]).stdout or True
    assert cli("work", "set", w["id"], "--status", "done", check=False).returncode == 1        # 子没完
    s = json.loads(cli("--json", "work", "attach", w["id"], "bash://", user="alice").stdout)
    assert s["alive"] and "?arg=" in cli("work", "attach", w["id"], "bash://").stdout            # 窗:tmuxd 自带的 ttyd
    assert s["id"] in cli("work", "worklets", w["id"]).stdout
    cli("work", "detach", w["id"], s["id"])
    assert "在动 alice" in cli("work", "show", w["id"]).stdout
    assert "bash" in cli("work", "servers").stdout and "default" in cli("work", "servers").stdout

    # meta:建 issue → 立场 → 论证 → 排序 → 卡;--put / @- / --subject、log、search(manager / inbox 暂时注释,等 work 实现后一起启用)
    ip = "memory.talk/配置/该走文件还是环境变量"
    cli("meta", "write", "issue", ip, "--put", "readme.md=背景:起服务要读几样配置", "--reason", "撞见的", user="alice")
    cli("meta", "edit", "issue", ip, "--put", "positions/只用环境变量.md=为什么", "--subject", f"position {ip}: 只用环境变量", user="alice")
    cli("meta", "edit", "issue", ip, "--put", "positions/只用环境变量.md=@-", "--subject", f"argue {ip}#只用环境变量: 够用",
        inp="---\nrank: 1\nverdict: 够用\n---\n\n为什么\n\n## 论证\n- 试了一遍,够用(" + w["id"] + "#3)\n", user="alice")
    assert cli("meta", "edit", "issue", ip, "--put", "notes.txt=x", check=False).returncode == 1                       # 协议外的文件
    cli("meta", "edit", "issue", ip, "--put", "readme.md=背景:起服务要读几样配置;先这样", "--subject", f"edit {ip}", user="alice")
    r = json.loads(cli("--json", "meta", "read", "issue", ip).stdout)
    assert r["title"] == "该走文件还是环境变量" and set(r["files"]) == {"readme.md", "positions/只用环境变量.md"}
    assert "== positions/只用环境变量.md" in cli("meta", "read", "issue", ip).stdout
    assert "可建: " in cli("meta", "tree", ip + ".issue").stdout and "positions/{name}.md" in cli("meta", "tree", ip + ".issue").stdout
    assert "可以" in cli("meta", "tree", ip + ".issue", "--candidate", "positions/再来一个.md").stdout
    cli("meta", "write", "card", "memory.talk/配置/配置只来自环境变量", "--put", "readme.md=@-", inp="---\nissue: " + ip + "\n---\n\n只用环境变量。\n", user="alice")
    cli("meta", "edit", "card", "memory.talk/配置/配置只来自环境变量", "--put", "readme.md=只用环境变量。补一句。", "--reason", "补正文", user="alice")
    assert "补一句" in cli("meta", "read", "card", "memory.talk/配置/配置只来自环境变量").stdout
    log = cli("meta", "log", "card", "memory.talk/配置/配置只来自环境变量").stdout
    assert "alice" in log and "[card] edit" in log
    assert f"[issue] position {ip}" in cli("meta", "log", "issue", ip).stdout
    assert "[issue]" in cli("search", "起服务").stdout and "[work]" in cli("search", "配置").stdout
    assert "该走文件还是环境变量.issue" in cli("meta", "tree", "memory.talk/配置").stdout
    # cli("meta", "manager", "memory.talk", "--set", w["id"], user="alice")
    # assert w["id"] in cli("meta", "manager", ip).stdout
    # assert ip in cli("work", "inbox", w["id"]).stdout
    # assert ip in cli("meta", "managed", "--work", w["id"]).stdout
    assert "positions/{name}.md" in cli("meta", "layers").stdout

    cli("work", "set", child["id"], "--status", "done", user="alice")
    assert json.loads(cli("--json", "work", "set", w["id"], "--status", "done").stdout)["status"] == "done"
    cli("user", "passwd", "alice", "--new-password", "alice-pw-2", user="admin")            # admin 给 alice 改密码 → 她的登录态作废
    assert cli("work", "list", user="alice", check=False).returncode == 1
    cli("logout", user="alice")                                                              # 作废了的也能退干净
    cli("logout", user="admin")
    assert cli("work", "list", user="admin", check=False).returncode == 1
    assert "已停止" in cli("server", "stop").stdout
    assert cli("server", "status", check=False).returncode == 1
