"""users/identity_header -- who is operating. See README.md."""


def test_unregistered_name_in_header_is_404(client, H):
    assert client.post("/api/works", json={"goal": "x"}, headers=H("nobody")).status_code == 404
    assert client.post("/api/collections/card/x/y", json={"data": {"title": "y"}}, headers=H("nobody")).status_code == 404


def test_anonymous_requests_still_work(client):
    w = client.post("/api/works", json={"goal": "匿名建的"})
    assert w.status_code == 201 and w.json()["created_by"] is None
    assert client.post("/api/collections/card/x/匿名卡", json={"data": {"title": "匿名卡"}}).status_code == 201


def test_me_follows_the_header(client, H):
    assert client.get("/api/users/me").json() is None
    assert client.get("/api/users/me", headers=H("alice")).json()["name"] == "alice"
    assert client.get("/api/users/me", headers=H("nobody")).status_code == 404
