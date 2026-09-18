"""collections/layers -- built-in layer protocols. See README.md."""
import subprocess


def test_three_builtin_layers_bottom_first(client):
    assert [l["name"] for l in client.get("/api/collections/layers").json()] == ["origin", "issue", "card"]


def test_origin_has_no_suffix_and_no_object_rule(client):
    origin = client.get("/api/collections/layers").json()[0]
    assert origin["suffix"] is None and origin["protocol"]["object"] is None and origin["protocol"]["files"] == []


def test_issue_protocol_describes_two_kinds_of_files(client):
    issue = client.get("/api/collections/layers").json()[1]
    assert issue["suffix"] == ".issue" and issue["builtin"]
    assert issue["protocol"]["object"] == {"pattern": "^(?P<name>[^/]+)\\.issue$", "name": "问题", "under": ".*", "example": "{name}.issue"}
    readme, position = issue["protocol"]["files"]
    assert (readme["example"], readme["fixed"], readme["required"]) == ("readme.md", True, True)
    assert set(readme["format"]["fields"]) == {"links", "summary"} and readme["format"]["body"] == "markdown"
    assert (position["example"], position["fixed"], position["name"], position["label"]) == ("positions/{name}.md", False, "主张", "立场")
    assert position["format"]["fields"]["rank"]["type"] == "number" and position["template"].strip() == "## 论证"
    assert readme["format"]["fields"]["links"]["item"]["fields"]["type"]["values"][0] == "specializes"


def test_card_protocol_is_one_file_with_fields(client):
    card = client.get("/api/collections/layers").json()[2]
    assert card["protocol"]["object"]["example"] == "{name}.card" and card["protocol"]["object"]["name"] == "标题"
    [readme] = card["protocol"]["files"]
    assert readme["required"] and set(readme["format"]["fields"]) == {"context", "links", "issue"}
    assert readme["format"]["fields"]["issue"] == {"type": "ref", "layer": "issue", "description": "讨论页:对应的 issue 的 path"}


def test_repo_has_a_branch_per_layer_and_stack(svc):
    out = subprocess.run(["git", "branch", "--list"], cwd=svc.collections.repo.root, capture_output=True, text=True).stdout
    assert {b.strip("* ") for b in out.splitlines()} >= {"layer/origin", "layer/issue", "layer/card", "stack"}
