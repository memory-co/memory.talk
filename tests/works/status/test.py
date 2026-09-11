"""works/status -- done rollup. See README.md."""


def _tree(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    a = client.post("/api/works", json={"goal": "A", "parent": root["id"]}).json()
    b = client.post("/api/works", json={"goal": "B", "parent": root["id"]}).json()
    return root, a, b


def test_parent_cannot_finish_before_children(client):
    root, a, b = _tree(client)
    r = client.patch(f"/api/works/{root['id']}", json={"status": "done"})
    assert r.status_code == 409 and a["id"] in r.json()["message"] and b["id"] in r.json()["message"]


def test_parent_finishes_once_children_are_done_or_abandoned(client):
    root, a, b = _tree(client)
    client.patch(f"/api/works/{a['id']}", json={"status": "done"})
    client.patch(f"/api/works/{b['id']}", json={"status": "abandoned"})
    assert client.patch(f"/api/works/{root['id']}", json={"status": "done"}).json()["status"] == "done"


def test_done_at_is_set_and_cleared(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    assert client.patch(f"/api/works/{w['id']}", json={"status": "done"}).json()["done_at"]
    assert client.patch(f"/api/works/{w['id']}", json={"status": "doing"}).json()["done_at"] is None


def test_finished_work_rejects_new_sessions(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "done"})
    assert client.post(f"/api/works/{w['id']}/sessions", json={"uri": "bash://"}).status_code == 409
