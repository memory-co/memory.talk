"""work_servers/freeze -- archiving destroys presences, keeps records. See README.md."""
from tests._util import trace
from tests.conftest import needs_tmux

pytestmark = needs_tmux


def test_archive_destroys_sessions_but_keeps_registry(client, home):
    w = client.post("/api/works", json={"goal": "x"}).json()
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    worklets = client.get(f"/api/works/{w['id']}/worklets").json()
    assert [x["id"] for x in worklets] == [s["id"]] and worklets[0]["alive"] is False
    assert (worklets[0]["column"], worklets[0]["position"]) == ("c1", 0)              # 在哪一列也还在


def test_no_reattach_after_archive(client, svc, home, H):
    w = client.post("/api/works", json={"goal": "x"}).json()
    s = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    r = client.post(f"/api/works/{w['id']}/worklets/{s['id']}/attach", headers=H("carol"))
    assert r.status_code == 409 and not svc.work_servers.alive("bash", s["id"])        # 冻住的不再起现场
    assert [x["alive"] for x in client.get(f"/api/works/{w['id']}/worklets").json()] == [False]
    assert [(x["name"], x["memorytalk.end.reason"]) for x in trace(client, w["id"])[0]] == [("work", "archived"), ("worklet", "archived")]


def test_archive_ends_the_spans_once_not_as_gone(client, home):
    w = client.post("/api/works", json={"goal": "x"}).json()
    client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"})
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"})
    client.get(f"/api/works/{w['id']}/worklets")                       # 现场不在了,但段已经因归档结束,不再记成 gone
    spans, _ = trace(client, w["id"])
    assert [(s["name"], s["memorytalk.end.reason"]) for s in spans] == [("work", "archived"), ("worklet", "archived")]


def test_archived_while_the_site_opens_means_no_worklet(client, svc, home, monkeypatch):
    from memorytalk.backend.models.work import WorkUpdate
    w = client.post("/api/works", json={"goal": "x"}).json()
    real_open, destroyed = svc.work_servers.open, []
    real_destroy = svc.work_servers.destroy

    def open_while_archiving(*a, **kw):                                  # 现场还在建,另一个人把 work 归档了
        svc.works.update(w["id"], WorkUpdate(status="archived"), "bob")
        return real_open(*a, **kw)

    def destroy(server, worklet_id):
        destroyed.append(worklet_id)
        real_destroy(server, worklet_id)
    monkeypatch.setattr(svc.work_servers, "open", open_while_archiving)
    monkeypatch.setattr(svc.work_servers, "destroy", destroy)
    r = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"})
    assert r.status_code == 409
    assert destroyed == [f"{w['id']}-w1"] and not svc.work_servers.alive("bash", destroyed[0])     # 建起来的现场收掉了
    assert client.get(f"/api/works/{w['id']}/worklets").json() == []
    assert [s["name"] for s in trace(client, w["id"])[0]] == ["work"]


def _ends(client, w):
    return [(s["memorytalk.worklet.id"], s["memorytalk.end.reason"], s.get("memorytalk.end.user.id"), s["status"])
            for s in trace(client, w["id"])[0] if s["name"] == "worklet"]


def _poll_after_destroy(svc, monkeypatch, w):
    """每销毁一个现场就列一次清单(前端每个人 8 秒一次,正好落在归档 / 关掉的半中间)。"""
    real = svc.work_servers.destroy

    def destroy(server, worklet_id):
        real(server, worklet_id)
        svc.works.list_worklets(w["id"])
    monkeypatch.setattr(svc.work_servers, "destroy", destroy)


def test_listing_mid_archive_does_not_end_spans_as_gone(client, svc, home, monkeypatch, H):
    w = client.post("/api/works", json={"goal": "x"}).json()
    a, b = (client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()["id"] for _ in range(2))
    _poll_after_destroy(svc, monkeypatch, w)
    client.patch(f"/api/works/{w['id']}", json={"status": "archived"}, headers=H("bob"))
    assert _ends(client, w) == [(a, "archived", "bob", 1), (b, "archived", "bob", 1)]


def test_listing_mid_detach_does_not_end_the_span_as_gone(client, svc, home, monkeypatch, H):
    w = client.post("/api/works", json={"goal": "x"}).json()
    a = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()["id"]
    _poll_after_destroy(svc, monkeypatch, w)
    client.delete(f"/api/works/{w['id']}/worklets/{a}", headers=H("bob"))
    assert _ends(client, w) == [(a, "detached", "bob", 1)]


def test_a_site_reopened_while_listing_is_not_gone(client, svc, home, monkeypatch):
    w = client.post("/api/works", json={"goal": "x"}).json()
    a = client.post(f"/api/works/{w['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"}).json()["id"]
    real_alive, reattached = svc.work_servers.alive, []

    def alive(server, worklet_id):                                     # 清单看到它没了,紧接着有人点了重连
        up = real_alive(server, worklet_id)
        if not up and not reattached:
            reattached.append(worklet_id)
            svc.works.reattach(w["id"], worklet_id)
        return up
    svc.work_servers.destroy("bash", a)                                # 现场先没了(段还开着)
    monkeypatch.setattr(svc.work_servers, "alive", alive)
    assert client.get(f"/api/works/{w['id']}/worklets").json()[0]["alive"] is False
    assert reattached == [a] and real_alive("bash", a)
    [s] = [s for s in trace(client, w["id"])[0] if s["name"] == "worklet"]
    assert s["end"] is None                                            # 重连接着用的那一段没被记成 gone
