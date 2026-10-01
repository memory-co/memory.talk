"""works/inbox -- a work's own changes go up the tree to whoever manages it. See README.md."""


def test_child_changes_go_to_parent_inbox(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    last = client.get(f"/api/works/{root['id']}/inbox").json()[-1]
    assert (last["layer"], last["path"], last["routed_by"]) == ("work", c["id"], "parent")
    assert last["subject"].startswith("created")


def test_manager_overrides_the_parent(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    other = client.post("/api/works", json={"goal": "别处"}).json()
    assert client.put(f"/api/works/{c['id']}/manager", json={"work": other["id"]}).json()["work"] == other["id"]
    client.patch(f"/api/works/{c['id']}", json={"status": "archived"})
    last = client.get(f"/api/works/{other['id']}/inbox").json()[-1]
    assert last["subject"] == "status running -> archived" and last["routed_by"] == c["id"]


def test_unset_manager_returns_to_parent(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    client.put(f"/api/works/{c['id']}/manager", json={"work": "work_x"})
    assert client.put(f"/api/works/{c['id']}/manager", json={"work": None}).json()["work"] == root["id"]


def test_root_has_no_manager(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    assert client.get(f"/api/works/{root['id']}/manager").json()["work"] is None
    assert client.get(f"/api/works/{root['id']}/inbox").json() == []


def test_inbox_is_oldest_first(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    client.patch(f"/api/works/{c['id']}", json={"status": "archived"})
    client.patch(f"/api/works/{c['id']}", json={"status": "running"})
    assert [i["subject"] for i in client.get(f"/api/works/{root['id']}/inbox").json()] == \
        ["created: 子", "status running -> archived", "status archived -> running"]


def test_goal_change_is_not_delivered(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    client.patch(f"/api/works/{c['id']}", json={"goal": "新子"})
    assert len(client.get(f"/api/works/{root['id']}/inbox").json()) == 1
