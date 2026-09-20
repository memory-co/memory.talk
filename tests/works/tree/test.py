"""works/tree -- nodes, parent/child, forest. See README.md."""


def test_create_root_is_todo_without_parent(client):
    w = client.post("/api/works", json={"goal": "把 v5 做出来"}).json()
    assert w["status"] == "todo" and w["parent"] is None and "project" not in w


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


def test_fs_layout_mirrors_the_tree(client, home):
    """MEMORY_TALK_STORE=fs 时,子 work 住在父目录的 subs/ 下;sqlite 时不看磁盘。"""
    import os
    from pathlib import Path
    if os.environ["MEMORY_TALK_STORE"] != "fs":
        return
    root = client.post("/api/works", json={"goal": "根"}).json()
    child = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    grand = client.post("/api/works", json={"goal": "孙", "parent": child["id"]}).json()
    base = Path(os.environ["MEMORY_TALK_HOME"]) / "works"
    assert (base / root["id"] / "work.json").is_file()
    assert (base / root["id"] / "subs" / child["id"] / "work.json").is_file()
    assert (base / root["id"] / "subs" / child["id"] / "subs" / grand["id"] / "work.json").is_file()
    assert not (base / child["id"]).exists()
    client.post(f"/api/works/{grand['id']}/worklets", json={"uri": "https://example.com"})
    assert (base / root["id"] / "subs" / child["id"] / "subs" / grand["id"] / "worklets.json").is_file()
    assert [w["goal"] for w in client.get("/api/works", params={"root": root["id"]}).json()[0]["children"]] == ["子"]
