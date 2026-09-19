"""auth/gate -- setup once, then every /api request needs a token. See README.md."""
import json

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD


def _fresh():
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    return TestClient(create_app(load_config(), load_runtime_config()))


def test_before_setup_everything_is_409(home):
    with _fresh() as c:
        assert c.get("/api/auth/status").json() == {"setup_required": True, "authenticated": False, "user": None}
        assert c.get("/api/works").status_code == 409 and c.get("/api/works").json()["error"] == "setup_required"
        assert c.post("/api/auth/login", json={"name": "admin", "password": "x"}).status_code == 401
        assert c.get("/api/system/health").status_code == 200                       # 健康检查不拦
        assert c.get("/").status_code in (200, 404)                                  # 前端页面不拦(没构建时 404)


def test_setup_creates_admin_and_logs_in(home):
    with _fresh() as c:
        r = c.post("/api/auth/setup", json={"password": PASSWORD, "display_name": "Root"})
        assert r.status_code == 201 and r.json()["user"] == {**r.json()["user"], "name": "admin", "role": "admin", "display_name": "Root"}
        tok = r.json()["token"]
        st = c.get("/api/auth/status", headers={"Authorization": f"Bearer {tok}"}).json()
        assert st["setup_required"] is False and st["authenticated"] and st["user"]["name"] == "admin"
        assert c.post("/api/auth/setup", json={"password": PASSWORD}).status_code == 404       # 只能一次


def test_setup_password_must_be_at_least_six(home):
    with _fresh() as c:
        assert c.post("/api/auth/setup", json={"password": "12345"}).status_code == 422


def test_login_gives_a_token_and_wrong_password_is_401(client):
    assert client.post("/api/auth/login", json={"name": "alice", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"name": "ghost", "password": PASSWORD}).status_code == 401
    tok = client.post("/api/auth/login", json={"name": "alice", "password": PASSWORD}).json()["token"]
    assert client.get("/api/users/me", headers={"Authorization": f"Bearer {tok}"}).json()["name"] == "alice"


def test_logout_revokes_the_token(client):
    tok = client.post("/api/auth/login", json={"name": "bob", "password": PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/works", headers=h).status_code == 401


def test_only_admin_creates_accounts(client, H):
    assert client.post("/api/users", json={"name": "dave", "password": PASSWORD}, headers=H("alice")).json()["error"] == "forbidden"
    assert client.post("/api/users", json={"name": "dave", "password": PASSWORD}).status_code == 201
    assert client.post("/api/auth/login", json={"name": "dave", "password": PASSWORD}).status_code == 200


def test_account_without_password_cannot_log_in(client):
    client.post("/api/users", json={"name": "erin"})
    assert client.post("/api/auth/login", json={"name": "erin", "password": ""}).status_code == 401


def test_changing_own_password_needs_the_old_one_and_revokes_tokens(client, H):
    h = H("alice")
    assert client.put("/api/users/alice/password", json={"new_password": "new-pw-1"}, headers=h).status_code == 401
    assert client.put("/api/users/alice/password", json={"old_password": "wrong", "new_password": "new-pw-1"}, headers=h).status_code == 401
    assert client.put("/api/users/alice/password", json={"old_password": PASSWORD, "new_password": "new-pw-1"}, headers=h).status_code == 200
    assert client.get("/api/works", headers=h).status_code == 401                                # 旧 token 作废
    assert client.post("/api/auth/login", json={"name": "alice", "password": "new-pw-1"}).status_code == 200


def test_admin_sets_others_passwords_members_cannot(client, H):
    assert client.put("/api/users/bob/password", json={"new_password": "new-pw-2"}, headers=H("alice")).status_code == 403
    assert client.put("/api/users/bob/password", json={"new_password": "new-pw-2"}).status_code == 200
    assert client.post("/api/auth/login", json={"name": "bob", "password": "new-pw-2"}).status_code == 200


def test_profile_edits_are_self_or_admin(client, H):
    assert client.put("/api/users/bob", json={"display_name": "x"}, headers=H("alice")).status_code == 403
    assert client.put("/api/users/alice", json={"display_name": "Alice"}, headers=H("alice")).json()["display_name"] == "Alice"
    assert client.put("/api/users/bob", json={"display_name": "Bob"}).json()["display_name"] == "Bob"


def test_password_hash_never_leaves_the_server(client, svc, H):
    for body in (client.get("/api/users").json(), client.get("/api/users/alice").json(), client.get("/api/users/me").json(),
                 client.get("/api/auth/status").json()):
        assert "password" not in json.dumps(body)
    stored = svc.store.user_repo.get("alice")["password"]
    assert stored.startswith("scrypt$") and PASSWORD not in stored
