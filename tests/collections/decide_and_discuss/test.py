"""collections/decide_and_discuss -- two adjacent commits per decision. See README.md."""
from tests._util import git_log

IP = "memory.talk/配置/该走文件还是环境变量"
CP = "memory.talk/配置/配置只来自环境变量"


def _issue_with_position(client):
    client.post(f"/api/collections/issue/{IP}", json={"data": {"question": "q"}})
    client.post(f"/api/collections/act/issue/position/{IP}", json={"claim": "只用环境变量"})


def test_decide_writes_the_card_and_links_both_ways(client, H):
    _issue_with_position(client)
    r = client.post(f"/api/collections/act/issue/decide/{IP}", json={"position": "p1", "card": CP, "context": "v5"}, headers=H("alice"))
    assert r.status_code == 200 and r.json()["card"] == CP
    card = client.get(f"/api/collections/card/{CP}").json()
    assert card["title"] == "只用环境变量" and card["body"]["issue"] == IP


def test_decide_is_two_adjacent_commits_with_one_decision_trailer(client, H):
    _issue_with_position(client)
    client.post(f"/api/collections/act/issue/decide/{IP}", json={"position": "p1", "card": CP, "reason": "够用"}, headers=H("alice"))
    log = git_log(client)
    first, second = log.split("\n\n")[0:2]
    assert first.startswith(f"[card] write {CP}") and f"[issue] decide {IP}#p1" in log
    trailers = [l for l in log.splitlines() if l.startswith("Decision:")]
    assert len(trailers) == 2 and trailers[0] == trailers[1]
    assert "Reason: 够用" in log


def test_decide_refuses_an_existing_card(client):
    _issue_with_position(client)
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "已有"}})
    assert client.post(f"/api/collections/act/issue/decide/{IP}", json={"position": "p1", "card": CP}).status_code == 409


def test_discuss_opens_an_issue_on_a_card(client):
    client.post(f"/api/collections/card/{CP}", json={"data": {"title": "t"}})
    r = client.post(f"/api/collections/act/card/discuss/{CP}", json={"issue": "memory.talk/配置/要不要加配置文件", "question": "要不要加?"})
    assert r.status_code == 200 and r.json()["card"] == CP
    assert client.get(f"/api/collections/card/{CP}").json()["body"]["issue"] == "memory.talk/配置/要不要加配置文件"
    log = git_log(client)
    assert log.count("Discussion:") == 2 and "[issue] raise" in log and "[card] link" in log
