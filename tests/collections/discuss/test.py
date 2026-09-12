"""collections/discuss -- card.discuss opens an issue and points at it. See README.md."""
from tests._util import git_log

IP = "memory.talk/配置/要不要加配置文件"
CP = "memory.talk/配置/配置只来自环境变量"


def test_discuss_opens_an_issue_and_the_card_points_at_it(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t"}})
    r = client.post(f"/api/collections/act/card/discuss/{CP}", json={"issue": IP, "readme": "有人不同意"})
    assert r.status_code == 200 and r.json()["issue"] == IP
    assert client.get(f"/api/collections/issue/{IP}").json()["body"]["readme"] == "有人不同意"


def test_discuss_is_two_commits_in_two_layers(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t"}})
    client.post(f"/api/collections/act/card/discuss/{CP}", json={"issue": IP})
    log = git_log(client)
    assert log.split("\n\n")[0].startswith(f"[card] link {CP} -> issue {IP}") and f"[issue] write {IP}" in log
    assert "Discussion:" not in log and "Decision:" not in log


def test_discuss_refuses_an_existing_issue(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t"}})
    client.post(f"/api/collections/issue/{IP}", json={})
    assert client.post(f"/api/collections/act/card/discuss/{CP}", json={"issue": IP}).status_code == 409


def test_writing_a_card_from_an_issue_is_a_plain_create(client):
    client.post(f"/api/collections/issue/{IP}", json={})
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t", "issue": IP}})
    assert client.get(f"/api/collections/card/{CP}").json()["body"]["issue"] == IP
    assert client.get(f"/api/collections/issue/{IP}").json()["body"] == {"readme": "", "positions": [], "links": [], "summary": ""}
