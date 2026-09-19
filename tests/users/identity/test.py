"""users/identity -- who is operating comes from the token. See README.md."""


def test_unknown_token_is_401(client, H):
    assert client.post("/api/works", json={"goal": "x"}, headers=H("nobody")).status_code == 401
    assert client.post("/api/collections/card/x/y", json={"files": {"readme.md": "y"}}, headers=H("nobody")).json()["error"] == "unauthorized"


def test_no_token_is_401(client):
    bare = {"Authorization": ""}
    assert client.get("/api/works", headers=bare).status_code == 401
    assert client.get("/api/users/me", headers=bare).status_code == 401


def test_self_reported_header_is_ignored(client, H):
    w = client.post("/api/works", json={"goal": "x"}, headers={**H("alice"), "X-Memory-Talk-User": "bob"}).json()
    assert w["created_by"] == "alice"


def test_me_follows_the_token(client, H):
    assert client.get("/api/users/me").json()["name"] == "admin"
    assert client.get("/api/users/me", headers=H("alice")).json()["name"] == "alice"
