"""collections/layers -- built-in layer definitions. See README.md."""
import subprocess


def test_three_builtin_layers_bottom_first(client):
    assert [l["name"] for l in client.get("/api/collections/layers").json()] == ["origin", "issue", "card"]


def test_origin_has_no_suffix_and_no_files(client):
    origin = client.get("/api/collections/layers").json()[0]
    assert origin["suffix"] is None and origin["files"] == []


def test_issue_is_a_directory_of_three_kinds_of_files(client):
    issue = client.get("/api/collections/layers").json()[1]
    assert issue["suffix"] == ".issue" and issue["title"] == "dirname"
    assert [(f["pattern"], f["format"], f["required"]) for f in issue["files"]] == [
        ("readme.md", "markdown", True), ("meta.yaml", "yaml", False), ("positions/*.md", "markdown", False)]
    assert issue["behaviors"] == ["argue", "link", "position", "rank"]


def test_card_is_a_single_frontmatter_file(client):
    card = client.get("/api/collections/layers").json()[2]
    assert (card["suffix"], card["title"]) == (".card", "card.md:title")
    assert [(f["pattern"], f["format"], f["required"]) for f in card["files"]] == [("card.md", "markdown+frontmatter", True)]
    assert card["files"][0]["fields"]["title"]["required"] and card["files"][0]["fields"]["issue"]["ref"] == "issue"
    assert card["behaviors"] == ["discuss"]


def test_repo_has_a_branch_per_layer_and_stack(svc):
    out = subprocess.run(["git", "branch", "--list"], cwd=svc.collections.repo.root, capture_output=True, text=True).stdout
    assert {b.strip("* ") for b in out.splitlines()} >= {"layer/origin", "layer/issue", "layer/card", "stack"}
