"""users/crud -- create / read / update, and the deliberate absence of delete. See README.md."""
import re

import pytest

# ====================================================================== C


def test_create_with_all_fields(client):
    r = client.post("/api/users", json={"name": "dave", "display_name": "Dave", "email": "dave@example.com"})
    assert r.status_code == 201
    u = r.json()
    assert (u["name"], u["display_name"], u["email"]) == ("dave", "Dave", "dave@example.com")


def test_create_defaults_optional_fields_to_empty(client):
    u = client.post("/api/users", json={"name": "erin"}).json()
    assert u["display_name"] == "" and u["email"] == ""


def test_created_at_is_utc_iso(client):
    u = client.post("/api/users", json={"name": "erin"}).json()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", u["created_at"])


def test_name_must_be_unique(client):
    r = client.post("/api/users", json={"name": "alice"})
    assert r.status_code == 409 and r.json()["error"] == "exists"


@pytest.mark.parametrize("bad", ["bad name", "张三", "a" * 65, "", "with/slash"])
def test_name_format_is_validated(client, bad):
    assert client.post("/api/users", json={"name": bad}).status_code == 422


def test_name_is_required(client):
    assert client.post("/api/users", json={"display_name": "无名"}).status_code == 422


def test_profile_is_persisted_in_the_store(client, svc):
    client.post("/api/users", json={"name": "dave", "email": "dave@example.com"})
    row = svc.store.user_repo.get("dave")
    assert row["name"] == "dave" and row["email"] == "dave@example.com" and row["created_at"]
    assert svc.store.user_repo.get("nobody") is None


# ====================================================================== R


def test_get_returns_the_profile_as_registered(client):
    client.post("/api/users", json={"name": "dave", "display_name": "Dave", "email": "dave@example.com"})
    p = client.get("/api/users/dave").json()
    assert (p["name"], p["display_name"], p["email"]) == ("dave", "Dave", "dave@example.com")


def test_get_missing_user_is_404(client):
    r = client.get("/api/users/nobody")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_fresh_user_has_zero_activity(client):
    p = client.get("/api/users/carol").json()
    assert (p["works_created"], p["works_touched"], p["commits"]) == (0, 0, 0)
    assert p["active_works"] == [] and p["last_seen"] == ""
    assert p["works_created_ids"] == [] and p["works_touched_ids"] == [] and p["recent_commits"] == []


def test_list_contains_every_registered_user_even_idle(client):
    client.post("/api/users", json={"name": "dave"})
    assert {u["name"] for u in client.get("/api/users").json()} == {"admin", "alice", "bob", "carol", "dave"}


def test_list_orders_active_first_then_by_name(client, H):
    client.post("/api/works", json={"goal": "x"}, headers=H("bob"))            # bob 动了
    names = [u["name"] for u in client.get("/api/users").json()]
    assert names[0] == "bob" and names[1:] == sorted(names[1:], reverse=True)   # 没动过的按名字倒序(同 last_seen 空)


def test_me_is_the_logged_in_user(client, H):
    assert client.get("/api/users/me").json()["name"] == "admin"
    assert client.get("/api/users/me", headers=H("alice")).json()["name"] == "alice"
    assert client.get("/api/users/me", headers=H("nobody")).status_code == 401


# ====================================================================== U


def test_update_display_name_and_email(client):
    client.post("/api/users", json={"name": "dave"})
    u = client.put("/api/users/dave", json={"display_name": "David", "email": "d@example.com"}).json()
    assert (u["display_name"], u["email"]) == ("David", "d@example.com")


def test_update_is_partial(client):
    client.post("/api/users", json={"name": "dave", "display_name": "Dave", "email": "dave@example.com"})
    u = client.put("/api/users/dave", json={"email": "new@example.com"}).json()
    assert u["display_name"] == "Dave" and u["email"] == "new@example.com"


def test_update_with_empty_string_clears_the_field(client):
    client.post("/api/users", json={"name": "dave", "display_name": "Dave"})
    assert client.put("/api/users/dave", json={"display_name": ""}).json()["display_name"] == ""


def test_update_cannot_change_name_or_created_at(client):
    before = client.post("/api/users", json={"name": "dave"}).json()
    after = client.put("/api/users/dave", json={"name": "eve", "created_at": "1999-01-01T00:00:00Z", "display_name": "D"}).json()
    assert after["name"] == "dave" and after["created_at"] == before["created_at"]
    assert client.get("/api/users/eve").status_code == 404


def test_update_missing_user_is_404(client):
    assert client.put("/api/users/nobody", json={"display_name": "x"}).status_code == 404


def test_update_is_visible_in_get_and_list(client, svc):
    client.post("/api/users", json={"name": "dave"})
    client.put("/api/users/dave", json={"display_name": "David"})
    assert client.get("/api/users/dave").json()["display_name"] == "David"
    assert next(u for u in client.get("/api/users").json() if u["name"] == "dave")["display_name"] == "David"
    assert svc.store.user_repo.get("dave")["display_name"] == "David"


# ====================================================================== D


def test_there_is_no_delete_by_design(client):
    client.post("/api/users", json={"name": "dave"})
    assert client.delete("/api/users/dave").status_code == 405
    assert client.get("/api/users/dave").status_code == 200
