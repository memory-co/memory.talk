"""collections/user_layer -- schema-defined layers. See README.md."""
from tests._util import git_log

SCHEMA = """
layer: experiment
description: 一次实验
files:
  readme.md:   {format: markdown, required: true}
  result.yaml:
    format: yaml
    fields:
      verdict: {type: string, required: true}
      tags:    {type: "list[string]"}
      issue:   {type: ref, layer: issue}
  "runs/*.md": {format: markdown, append_only: true}
"""
OK = {"readme.md": "测什么", "result.yaml": "verdict: 支持\ntags: [a, b]", "runs/1.md": "第一次"}


def test_add_layer_from_yaml(client):
    r = client.post("/api/collections/layers", json={"name": "experiment", "schema_yaml": SCHEMA})
    assert r.status_code == 201
    assert [l["name"] for l in client.get("/api/collections/layers").json()] == ["origin", "issue", "card", "experiment"]
    assert r.json()["files"] == ["readme.md", "result.yaml", "runs/*.md"] and r.json()["schema"]["files"]["runs/*.md"]["append_only"]
    assert client.post("/api/collections/layers", json={"name": "experiment", "schema_yaml": SCHEMA}).status_code == 409
    assert client.post("/api/collections/layers", json={"name": "bad", "schema_yaml": "layer: bad\nfiles: {}\n"}).status_code == 400


def test_objects_follow_the_compiled_check(client):
    client.post("/api/collections/layers", json={"name": "experiment", "schema_yaml": SCHEMA})
    r = client.post("/api/collections/experiment/基准/跑一次", json={"files": OK})
    assert r.status_code == 201 and r.json()["title"] == "跑一次" and set(r.json()["files"]) == set(OK)
    assert "[experiment] write" in git_log(client, "layer/experiment")
    bad = lambda files: client.post("/api/collections/experiment/基准/坏", json={"files": files})
    assert "缺 readme.md" in bad({"result.yaml": "verdict: x"}).json()["message"]
    assert "verdict" in bad({"readme.md": "", "result.yaml": "tags: [a]"}).json()["message"]
    assert "extra.txt" in bad({"readme.md": "", "extra.txt": "x"}).json()["message"]
    assert "score" in bad({"readme.md": "", "result.yaml": "verdict: x\nscore: 1"}).json()["message"]


def test_append_only_and_required_rules(client):
    client.post("/api/collections/layers", json={"name": "experiment", "schema_yaml": SCHEMA})
    client.post("/api/collections/experiment/基准/跑一次", json={"files": OK})
    put = lambda files: client.put("/api/collections/experiment/基准/跑一次", json={"files": files})
    assert put({"runs/1.md": "第一次\n第二行"}).status_code == 200
    assert "追加" in put({"runs/1.md": "重写"}).json()["message"]
    assert "不能删" in put({"readme.md": None}).json()["message"]
    assert put({"result.yaml": None}).status_code == 200                      # 非必需的可以删


def test_user_layer_survives_restart(client):
    client.post("/api/collections/layers", json={"name": "experiment", "schema_yaml": SCHEMA})
    from memorytalk.backend.config import load_config, load_runtime_config
    from memorytalk.backend.main import create_app
    assert create_app(load_config(), load_runtime_config()).state.collections.order[-1] == "experiment"
