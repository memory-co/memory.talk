"""works/tree -- nodes, parent/child, forest. See README.md."""


def test_create_root_is_running_without_parent(client):
    w = client.post("/api/works", json={"goal": "把 v5 做出来"}).json()
    assert w["status"] == "running" and w["parent"] is None and "project" not in w


def test_children_are_nested_under_parent_in_forest(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    a = client.post("/api/works", json={"goal": "A", "parent": root["id"]}).json()
    b = client.post("/api/works", json={"goal": "B", "parent": root["id"]}).json()
    forest = client.get("/api/works").json()
    assert [n["id"] for n in forest] == [root["id"]]
    assert sorted(c["id"] for c in forest[0]["children"]) == sorted([a["id"], b["id"]])


def test_root_param_returns_one_tree(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    a = client.post("/api/works", json={"goal": "A", "parent": root["id"]}).json()
    assert client.get("/api/works", params={"root": a["id"]}).json() == [{**a, "children": []}]
    assert client.get("/api/works", params={"root": "work_nope"}).status_code == 404


def test_missing_parent_is_404(client):
    assert client.post("/api/works", json={"goal": "x", "parent": "work_nope"}).status_code == 404


def test_get_and_patch_goal(client):
    w = client.post("/api/works", json={"goal": "旧"}).json()
    assert client.patch(f"/api/works/{w['id']}", json={"goal": "新"}).json()["goal"] == "新"
    assert client.get(f"/api/works/{w['id']}").json()["goal"] == "新"
    assert client.get("/api/works/work_nope").status_code == 404


def test_work_lives_in_two_sqlite_files_under_home(client, home):
    """不管 MEMORY_TALK_STORE 是什么,work 只在 <home>/works.db(现在)和 <home>/worktrace.db(经过)里;没有 works/ 目录树。"""
    root = client.post("/api/works", json={"goal": "根"}).json()
    child = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    base = home / "home"
    assert (base / "works.db").is_file() and (base / "worktrace.db").is_file()
    assert not (base / "works").exists() and not (base / "unmanaged.jsonl").exists()
    info = client.get("/api/system/info").json()
    assert (info["works_db"], info["worktrace_db"]) == (str(base / "works.db"), str(base / "worktrace.db"))
    assert [w["goal"] for w in client.get("/api/works", params={"root": root["id"]}).json()[0]["children"]] == ["子"]
    assert child["parent"] == root["id"]


def test_db_paths_can_be_moved_by_env(home, monkeypatch):
    from fastapi.testclient import TestClient
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    monkeypatch.setenv("MEMORY_TALK_WORKS_DB", str(home / "elsewhere" / "w.db"))
    monkeypatch.setenv("MEMORY_TALK_WORKTRACE_DB", str(home / "big-disk" / "t.db"))
    with TestClient(create_app(load_config(), load_runtime_config())):
        pass
    assert (home / "elsewhere" / "w.db").is_file() and (home / "big-disk" / "t.db").is_file()
    assert not (home / "home" / "works.db").exists()
