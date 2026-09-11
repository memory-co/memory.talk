"""users/work_ownership -- created_by. See README.md."""


def test_created_by_comes_from_the_header(client, H):
    w = client.post("/api/works", json={"goal": "A 的事"}, headers=H("alice")).json()
    assert w["created_by"] == "alice"


def test_forest_filters_by_created_by(client, H):
    a = client.post("/api/works", json={"goal": "A"}, headers=H("alice")).json()
    client.post("/api/works", json={"goal": "B"}, headers=H("bob"))
    assert [w["id"] for w in client.get("/api/works", params={"created_by": "alice"}).json()] == [a["id"]]
    assert client.get("/api/works", params={"created_by": "carol"}).json() == []


def test_child_has_its_own_creator(client, H):
    a = client.post("/api/works", json={"goal": "A"}, headers=H("alice")).json()
    c = client.post("/api/works", json={"goal": "子", "parent": a["id"]}, headers=H("bob")).json()
    assert c["created_by"] == "bob"


def test_creator_is_first_in_users_list(client, H):
    a = client.post("/api/works", json={"goal": "A"}, headers=H("alice")).json()
    assert [u["user"] for u in client.get(f"/api/works/{a['id']}/users").json()["history"]] == ["alice"]


def test_created_by_does_not_change_on_update(client, H):
    a = client.post("/api/works", json={"goal": "A"}, headers=H("alice")).json()
    assert client.patch(f"/api/works/{a['id']}", json={"goal": "改了"}, headers=H("bob")).json()["created_by"] == "alice"
