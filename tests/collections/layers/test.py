"""collections/layers -- built-in layer definitions. See README.md."""
import subprocess


def test_three_builtin_layers_bottom_first(client):
    assert [l["name"] for l in client.get("/api/collections/layers").json()] == ["origin", "issue", "card"]


def test_origin_has_no_suffix_and_no_body_file(client):
    origin = client.get("/api/collections/layers").json()[0]
    assert origin["suffix"] is None and origin["body"] is None and origin["format"] == "raw"


def test_issue_and_card_shapes(client):
    _, issue, card = client.get("/api/collections/layers").json()
    assert (issue["suffix"], issue["body"], issue["format"], issue["title"]) == (".issue", "issue.json", "json", "question")
    assert (card["suffix"], card["body"], card["format"], card["title"]) == (".card", "card.md", "markdown", "title")
    assert sorted(issue["behaviors"]) == ["argue", "decide", "link", "position", "spawn"] and card["behaviors"] == ["discuss"]


def test_repo_has_a_branch_per_layer_and_stack(svc):
    out = subprocess.run(["git", "branch", "--list"], cwd=svc.collections.repo.root, capture_output=True, text=True).stdout
    assert {b.strip("* ") for b in out.splitlines()} >= {"layer/origin", "layer/issue", "layer/card", "stack"}
