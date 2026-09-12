"""collections/layers -- built-in layer definitions. See README.md."""
import subprocess


def test_three_builtin_layers_bottom_first(client):
    assert [l["name"] for l in client.get("/api/collections/layers").json()] == ["origin", "issue", "card"]


def test_origin_has_no_suffix_and_no_files(client):
    origin = client.get("/api/collections/layers").json()[0]
    assert origin["suffix"] is None and origin["files"] == []


def test_issue_and_card_list_their_allowed_files(client):
    _, issue, card = client.get("/api/collections/layers").json()
    assert (issue["suffix"], issue["files"]) == (".issue", ["readme.md", "meta.yaml", "positions/*.md"])
    assert (card["suffix"], card["files"]) == (".card", ["readme.md", "meta.yaml"])
    assert issue["schema"] is None and card["builtin"]


def test_repo_has_a_branch_per_layer_and_stack(svc):
    out = subprocess.run(["git", "branch", "--list"], cwd=svc.collections.repo.root, capture_output=True, text=True).stdout
    assert {b.strip("* ") for b in out.splitlines()} >= {"layer/origin", "layer/issue", "layer/card", "stack"}
