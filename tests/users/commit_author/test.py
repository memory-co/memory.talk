"""users/commit_author -- git author = user. See README.md."""
from tests._util import git_authors


def test_author_is_the_user_with_default_email(client, H):
    client.post("/api/metas/card/x/一张卡", json={"files": {"readme.md": "一张卡"}}, headers=H("bob"))
    assert git_authors(client, 1) == ["bob", "<bob@memory.talk>"]


def test_author_email_comes_from_the_profile(client, H):
    client.post("/api/users", json={"name": "dave", "email": "dave@example.com"})
    client.post("/api/metas/card/x/戴夫的卡", json={"files": {"readme.md": "戴夫的卡"}}, headers=H("dave"))
    assert git_authors(client, 1) == ["dave", "<dave@example.com>"]


def test_default_email_is_name_at_memory_talk(client):
    client.post("/api/metas/card/x/管理员的卡", json={"files": {"readme.md": "admin 建的"}})
    assert git_authors(client, 1) == ["admin", "<admin@memory.talk>"]


def test_profile_counts_commits(client, H):
    client.post("/api/metas/card/x/一张卡", json={"files": {"readme.md": "一张卡"}}, headers=H("bob"))
    p = client.get("/api/users/bob").json()
    assert p["commits"] == 1 and p["recent_commits"][0]["subject"].startswith("[card] write x/一张卡")
    assert client.get("/api/users/alice").json()["commits"] == 0
