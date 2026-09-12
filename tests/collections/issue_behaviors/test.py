"""collections/issue_behaviors -- shortcuts over the issue directory. See README.md."""
import pytest

from tests._util import git_authors, git_log

IP = "memory.talk/配置/该走文件还是环境变量"
A, B = "只用环境变量", "加一个 settings.json"


@pytest.fixture
def issue(client):
    client.post(f"/api/collections/issue/{IP}", json={})
    return IP


def _act(client, action, payload, **kw):
    return client.post(f"/api/collections/act/issue/{action}/{IP}", json=payload, **kw)


def test_position_creates_a_file_named_by_the_claim(client, svc, issue):
    v = _act(client, "position", {"claim": A, "body": "为什么"}).json()
    assert [p["claim"] for p in v["positions"]] == [A] and v["positions"][0]["body"] == "为什么"
    assert svc.collections.repo.read(f"{IP}.issue/positions/{A}.md") == "为什么".encode()
    assert _act(client, "position", {"claim": A}).status_code == 409


def test_argue_appends_a_line_under_the_heading(client, svc, issue):
    _act(client, "position", {"claim": A, "body": "为什么"})
    _act(client, "argue", {"claim": A, "comment": "试了一遍,够用(work_try#9)"})
    v = _act(client, "argue", {"claim": A, "comment": "本地开发要改十几个变量"}).json()
    assert v["positions"][0]["arguments"] == ["试了一遍,够用(work_try#9)", "本地开发要改十几个变量"]
    assert svc.collections.repo.read(f"{IP}.issue/positions/{A}.md").decode() == "为什么\n\n## 论证\n- 试了一遍,够用(work_try#9)\n- 本地开发要改十几个变量\n"


def test_who_and_when_live_in_git(client, H, issue):
    _act(client, "position", {"claim": A}, headers=H("alice"))
    _act(client, "argue", {"claim": A, "comment": "够用"}, headers=H("bob"))
    log = git_log(client, "layer/issue")
    assert f"[issue] argue {IP}#{A}: 够用" in log and f"[issue] position {IP}: {A}" in log
    assert git_authors(client, 2)[0::2] == ["bob", "alice"]


def test_link_adds_an_edge_to_meta_once(client, svc, issue):
    _act(client, "link", {"type": "specializes", "target": "memory.talk/更大的问题"})
    v = _act(client, "link", {"type": "specializes", "target": "memory.talk/更大的问题"}).json()
    assert v["links"] == [{"type": "specializes", "target": "memory.talk/更大的问题"}]
    assert b"links:" in svc.collections.repo.read(f"{IP}.issue/meta.yaml")


def test_rank_orders_positions_and_unranked_follow_by_name(client, issue):
    _act(client, "position", {"claim": A})
    _act(client, "position", {"claim": B})
    _act(client, "position", {"claim": "丙"})
    v = _act(client, "rank", {"positions": [{"claim": B, "note": "灵活"}], "summary": "先看 B"}).json()
    assert [(p["claim"], p["note"]) for p in v["positions"]] == [(B, "灵活"), ("丙", ""), (A, "")]
    assert v["summary"] == "先看 B"
    assert f"[issue] rank {IP}: {B}" in git_log(client, "layer/issue")


def test_rank_must_name_existing_positions(client, issue):
    assert _act(client, "rank", {"positions": [{"claim": "没这个"}]}).status_code == 422


def test_unknown_position_and_action_are_404(client, issue):
    assert _act(client, "argue", {"claim": "没这个", "comment": "x"}).status_code == 404
    r = _act(client, "nope", {})
    assert r.status_code == 404 and r.json()["error"] == "no_action"
