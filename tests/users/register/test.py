"""users/register -- registration and profile. See README.md."""


def test_register_returns_profile_with_created_at(client):
    d = client.post("/api/users", json={"name": "dave", "display_name": "Dave", "email": "dave@example.com"})
    assert d.status_code == 201
    assert d.json()["display_name"] == "Dave" and d.json()["created_at"]


def test_duplicate_name_is_409(client):
    assert client.post("/api/users", json={"name": "alice"}).status_code == 409


def test_name_format_is_validated(client):
    assert client.post("/api/users", json={"name": "bad name"}).status_code == 422


def test_update_changes_profile_fields(client):
    client.post("/api/users", json={"name": "dave"})
    assert client.put("/api/users/dave", json={"display_name": "David"}).json()["display_name"] == "David"
    assert client.put("/api/users/nobody", json={"display_name": "x"}).status_code == 404


def test_registered_but_idle_user_is_listed(client):
    names = {u["name"] for u in client.get("/api/users").json()}
    assert names == {"alice", "bob", "carol"}
    assert client.get("/api/users/carol").json()["works_created"] == 0


def test_profile_is_persisted_in_the_store(client, svc):
    assert svc.store.user_repo.get("alice")["name"] == "alice"
    assert svc.store.user_repo.get("nobody") is None
