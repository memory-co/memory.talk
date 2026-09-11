"""work_servers/http_session -- browser block. See README.md."""


def test_local_service_is_embedded_through_proxy(client):
    w = client.post("/api/works", json={"goal": "看文档"}).json()
    m = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "https://localhost:5173/app"}).json()
    assert m["scheme"] == "https" and m["window"]["embed"] == "/proxy/5173/app"


def test_external_url_is_embedded_directly(client):
    w = client.post("/api/works", json={"goal": "看文档"}).json()
    m = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "https://example.com/x"}).json()
    assert m["window"]["embed"] == "https://example.com/x" and m["window"]["url"] == "https://example.com/x"


def test_no_handle_means_capture_is_409(client):
    w = client.post("/api/works", json={"goal": "看文档"}).json()
    m = client.post(f"/api/works/{w['id']}/sessions", json={"uri": "https://example.com/"}).json()
    assert m["handle"] == {"kind": "none", "capabilities": []} and m["alive"]
    assert client.get(f"/api/works/{w['id']}/sessions/{m['id']}/capture").status_code == 409
