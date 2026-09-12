"""users/commit_author -- git author = user. See README.md."""
from tests._util import git_authors


def test_author_is_the_user_with_default_email(client, H):
    client.post("/api/collections/card/x/一张卡", json={"files": {"readme.md": "一张卡"}}, headers=H("bob"))
    assert git_authors(client, 1) == ["bob", "<bob@memory.talk>"]


def test_author_email_comes_from_the_profile(client, H):
    client.post("/api/users", json={"name": "dave", "email": "dave@example.com"})
    client.post("/api/collections/card/x/戴夫的卡", json={"files": {"readme.md": "戴夫的卡"}}, headers=H("dave"))
    assert git_authors(client, 1) == ["dave", "<dave@example.com>"]


def test_anonymous_write_uses_service_default(client, svc):
    client.post("/api/collections/card/x/匿名卡", json={"files": {"readme.md": "匿名卡"}})
    assert git_authors(client, 1) == [svc.config.git_author_name, f"<{svc.config.git_author_email}>"]


def test_profile_counts_commits(client, H):
    client.post("/api/collections/card/x/一张卡", json={"files": {"readme.md": "一张卡"}}, headers=H("bob"))
    p = client.get("/api/users/bob").json()
    assert p["commits"] == 1 and p["recent_commits"][0]["subject"].startswith("[card] write x/一张卡")
    assert client.get("/api/users/alice").json()["commits"] == 0
