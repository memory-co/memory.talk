"""works/events_and_inbox -- timeline + implicit manager chain. See README.md."""


def test_event_order_created_status_frozen(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "done"})
    assert [e["type"] for e in client.get(f"/api/works/{w['id']}/events").json()] == ["created", "status", "frozen"]


def test_child_events_go_to_parent_inbox(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    last = client.get(f"/api/works/{root['id']}/inbox").json()[-1]
    assert (last["layer"], last["path"], last["routed_by"]) == ("work", c["id"], "parent")
    assert last["subject"].startswith("created")


def test_manager_json_overrides_the_parent(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    other = client.post("/api/works", json={"goal": "别处"}).json()
    assert client.put(f"/api/works/{c['id']}/manager", json={"work": other["id"]}).json()["work"] == other["id"]
    client.patch(f"/api/works/{c['id']}", json={"status": "doing"})
    last = client.get(f"/api/works/{other['id']}/inbox").json()[-1]
    assert last["subject"] == "status todo -> doing" and last["routed_by"] == c["id"]


def test_unset_manager_returns_to_parent(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    c = client.post("/api/works", json={"goal": "子", "parent": root["id"]}).json()
    client.put(f"/api/works/{c['id']}/manager", json={"work": "work_x"})
    assert client.put(f"/api/works/{c['id']}/manager", json={"work": None}).json()["work"] == root["id"]


def test_root_has_no_manager(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    assert client.get(f"/api/works/{root['id']}/manager").json()["work"] is None
    assert client.get(f"/api/works/{root['id']}/inbox").json() == []
