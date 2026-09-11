"""works/canvas -- view with optimistic lock. See README.md."""
PANELS = [{"id": "p1", "uri": "file:///w", "x": 0, "y": 0, "w": 12, "h": 16},
          {"id": "p2", "uri": "https://example.com", "x": 12, "y": 0, "w": 12, "h": 16}]


def test_fresh_canvas_is_empty_version_zero(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    assert client.get(f"/api/works/{w['id']}/canvas").json() == {"cols": 24, "rows": 16, "version": 0, "panels": []}


def test_put_bumps_version(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    cv = client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "panels": PANELS}).json()
    assert cv["version"] == 1 and [p["id"] for p in cv["panels"]] == ["p1", "p2"]


def test_stale_version_is_409(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "panels": PANELS})
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "panels": []}).status_code == 409


def test_out_of_grid_panel_is_409(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    bad = [{"id": "p1", "uri": "file:///w", "x": 20, "y": 0, "w": 12, "h": 16}]
    assert client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "panels": bad}).status_code == 409


def test_canvas_does_not_create_sessions(client):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.put(f"/api/works/{w['id']}/canvas", json={"version": 0, "panels": PANELS})
    assert client.get(f"/api/works/{w['id']}/sessions").json() == []
