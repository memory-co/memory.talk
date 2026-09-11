"""collections/user_layer -- schema-defined layers. See README.md."""
from tests._util import git_log

SCHEMA = """
layer: decision
format: markdown+frontmatter
title: title
description: 一个决定
fields:
  title:    {type: string, required: true}
  chosen:   {type: string, required: true}
  rejected: {type: "list[string]"}
  issue:    {type: ref, layer: issue}
"""


def test_add_layer_from_yaml(client):
    r = client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA})
    assert r.status_code == 201
    assert [l["name"] for l in client.get("/api/collections/layers").json()] == ["origin", "issue", "card", "decision"]
    assert r.json()["fields"]["issue"] == {"type": "ref", "required": False, "ref": "issue", "description": ""}
    assert r.json()["behaviors"] == []
    assert client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA}).status_code == 409


def test_objects_of_a_user_layer_follow_the_schema(client):
    client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA})
    r = client.post("/api/collections/decision/memory.talk/配置/定了用环境变量",
                    json={"data": {"title": "定了用环境变量", "chosen": "环境变量", "rejected": ["配置文件", "两者都要"],
                                   "issue": "memory.talk/配置/该走文件还是环境变量", "body": "因为……"}})
    assert r.status_code == 201
    d = client.get("/api/collections/decision/memory.talk/配置/定了用环境变量").json()["body"]
    assert d["rejected"] == ["配置文件", "两者都要"] and d["body"] == "因为……"
    assert client.post("/api/collections/decision/x", json={"data": {"title": "缺 chosen"}}).status_code == 422
    assert "[decision] write" in git_log(client, "layer/decision")


def test_user_layer_survives_restart(client):
    client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA})
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    assert create_app(load_config(), load_runtime_config()).state.collections.order[-1] == "decision"
