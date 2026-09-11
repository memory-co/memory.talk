"""collections/issue_behaviors -- IBIS actions on an issue. See README.md."""
import pytest

IP = "memory.talk/配置/该走文件还是环境变量"


@pytest.fixture
def issue(client):
    client.post(f"/api/collections/issue/{IP}", json={"data": {"question": "配置该走文件还是环境变量?"}})
    return IP


def _act(client, action, payload):
    return client.post(f"/api/collections/act/issue/{action}/{IP}", json=payload)


def test_positions_are_numbered_and_appended(client, issue):
    _act(client, "position", {"claim": "加一个 settings.json"})
    v = _act(client, "position", {"claim": "只用环境变量"}).json()
    assert [p["id"] for p in v["positions"]] == ["p1", "p2"]


def test_argue_records_stance_and_evidence(client, issue):
    _act(client, "position", {"claim": "只用环境变量"})
    v = _act(client, "argue", {"position": "p1", "stance": 1, "comment": "够用", "evidence": {"work_id": "work_try", "rounds": [9]}}).json()
    a = v["positions"][0]["arguments"][0]
    assert (a["id"], a["stance"], a["evidence"]["rounds"]) == ("a1", 1, [9])


def test_credence_is_computed_and_sorts_positions(client, issue):
    _act(client, "position", {"claim": "加一个 settings.json"})
    _act(client, "position", {"claim": "只用环境变量"})
    _act(client, "argue", {"position": "p2", "stance": 1})
    _act(client, "argue", {"position": "p1", "stance": -1})
    _act(client, "argue", {"position": "p1", "stance": 0})
    v = client.get(f"/api/collections/issue/{IP}").json()["body"]
    assert [(p["id"], p["credence"]) for p in v["positions"]] == [("p2", 1), ("p1", -1)]
    assert v["positions"][1]["neutral"] == 1                              # 中立不进 credence


def test_link_adds_an_ibis_edge_once(client, issue):
    _act(client, "link", {"type": "specializes", "target": "memory.talk/更大的问题"})
    v = _act(client, "link", {"type": "specializes", "target": "memory.talk/更大的问题"}).json()
    assert v["links"] == [{"type": "specializes", "target": "memory.talk/更大的问题"}]


def test_spawn_records_the_work_id(client, issue):
    _act(client, "position", {"claim": "只用环境变量"})
    v = _act(client, "spawn", {"position": "p1", "work_id": "work_try"}).json()
    assert v["positions"][0]["spawned_works"] == ["work_try"]


def test_unknown_position_and_action_are_404(client, issue):
    assert _act(client, "argue", {"position": "p9", "stance": 1}).status_code == 404
    r = _act(client, "nope", {})
    assert r.status_code == 404 and r.json()["error"] == "no_action"
