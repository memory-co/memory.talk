"""works/status -- two states: running / archived. See README.md."""


def test_new_work_is_running(client):
    assert client.post("/api/works", json={"goal": "x"}).json()["status"] == "running"


def test_archive_sets_archived_at_and_unarchive_clears_it(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    archived = client.patch(f"/api/works/{w['id']}", json={"status": "archived"}).json()
    assert archived["status"] == "archived" and archived["archived_at"]
    assert client.patch(f"/api/works/{w['id']}", json={"status": "running"}).json()["archived_at"] is None


def test_parent_archives_regardless_of_children(client):
    root = client.post("/api/works", json={"goal": "根"}).json()
    child = client.post("/api/works", json={"goal": "A", "parent": root["id"]}).json()
    assert client.patch(f"/api/works/{root['id']}", json={"status": "archived"}).json()["status"] == "archived"
    assert client.get(f"/api/works/{child['id']}").json()["status"] == "running"


def test_old_statuses_are_rejected_on_write(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    assert client.patch(f"/api/works/{w['id']}", json={"status": "done"}).status_code == 422


def test_archived_work_rejects_new_worklets(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    assert client.post(f"/api/works/{w['id']}/worklets", json={"uri": "bash://"}).status_code == 409
