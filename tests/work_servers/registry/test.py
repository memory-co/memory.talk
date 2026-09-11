"""work_servers/registry -- protocol declaration + default. See README.md."""
from memorytalk.backend.services.work_servers.uri import parse_uri


def test_servers_declare_their_protocols(client):
    infos = {s["name"]: s["protocols"] for s in client.get("/api/works/servers").json()}
    assert infos == {"bash": ["bash"], "claude": ["claude"], "codex": ["codex"], "kimi": ["kimi"],
                     "http": ["http", "https"], "default": []}


def test_default_is_last(client):
    assert client.get("/api/works/servers").json()[-1]["name"] == "default"


def test_resolution_is_internal_not_an_endpoint(client, svc):
    assert client.get("/api/works/servers/resolve").status_code == 404
    reg = svc.work_servers.registry
    assert reg.resolve(parse_uri("codex:///w/p")).name == "codex"
    assert reg.resolve(parse_uri("https://x.y/z")).name == "http"
    assert reg.resolve(parse_uri("vim:///w/a.txt")).name == "default"
