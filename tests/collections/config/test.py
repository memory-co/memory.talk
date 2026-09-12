"""collections/config -- collections.json anchor. See README.md."""
import json
import pytest
import subprocess

SCHEMA = "layer: decision\nformat: json\ntitle: title\nfields:\n  title: {type: string, required: true}\n"


def test_anchor_is_the_only_file_in_the_root_commit(svc):
    root = svc.collections.repo.root
    first = subprocess.run(["git", "rev-list", "--max-parents=0", "stack"], cwd=root, capture_output=True, text=True).stdout.split()[0]
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", first], cwd=root, capture_output=True, text=True).stdout.split()
    assert files == ["collections.json"]


def test_config_lists_builtin_layers_bottom_first(client):
    cfg = client.get("/api/collections/config").json()["config"]
    assert cfg["version"] == 1
    assert [(l["name"], l.get("builtin")) for l in cfg["layers"]] == [("origin", True), ("issue", True), ("card", True)]


def test_adding_a_layer_embeds_its_schema_and_is_a_commit(client, H):
    client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA, "reason": "要记决定"}, headers=H("alice"))
    r = client.get("/api/collections/config").json()
    last = r["config"]["layers"][-1]
    assert last["name"] == "decision" and last["schema"]["fields"]["title"]["required"] and last["added_at"]
    assert r["history"][0]["subject"] == "[origin] collections: add layer decision" and r["history"][0]["author"] == "alice"
    assert r["history"][-1]["subject"].startswith("[origin] collections: init")


def test_no_other_mechanism_files_in_the_repo(client, svc):
    client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA})
    files = set(svc.collections.repo.tree())
    assert files == {"collections.json"}


@pytest.mark.skip(reason="/api/collections/manager 暂时注释掉了,等 work 实现后一起启用")
def test_config_file_is_invisible_to_tree_catalog_and_inbox(client):
    assert client.get("/api/collections/tree").json() == []
    assert client.get("/api/collections/origin").json()["objects"] == []
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.put("/api/collections/manager", params={"path": ""}, json={"work": w["id"]})
    client.post("/api/collections/layers", json={"name": "decision", "schema_yaml": SCHEMA})
    assert client.get(f"/api/works/{w['id']}/inbox").json() == []
