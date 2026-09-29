"""work_servers/tty_window -- the terminal window mounted at /tty. See README.md."""
import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import needs_tmux

pytestmark = needs_tmux


@pytest.fixture
def worklet(client, home):
    work = client.post("/api/works", json={"goal": "开个窗"}).json()
    r = client.post(f"/api/works/{work['id']}/worklets", json={"uri": f"bash://{home / 'ws'}"})
    assert r.status_code == 201, r.text
    return r.json()


def test_no_cookie_no_window(client, worklet):
    assert client.get(worklet["window"]["url"]).status_code == 403


def test_bearer_alone_does_not_open_the_window(client, worklet):
    assert client.get(worklet["window"]["url"], headers={"Authorization": f"Bearer {client.tokens['admin']}"}).status_code == 403


def test_status_plants_a_tty_only_httponly_cookie(client):
    set_cookie = client.get("/api/auth/status").headers["set-cookie"]
    assert "mt_tty=" in set_cookie and "Path=/tty" in set_cookie and "HttpOnly" in set_cookie


def test_status_without_a_valid_token_clears_the_cookie(client):
    set_cookie = client.get("/api/auth/status", headers={"Authorization": "Bearer nope"}).headers["set-cookie"]
    assert 'mt_tty=""' in set_cookie and "Max-Age=0" in set_cookie


def test_cookie_opens_the_ttyd_page(client, worklet):
    client.get("/api/auth/status")
    r = client.get(worklet["window"]["url"])
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_cookie_opens_the_websocket(client, worklet):
    client.get("/api/auth/status")
    with client.websocket_connect(f"/tty/ws?arg={worklet['id']}", subprotocols=["tty"]) as ws:
        ws.send_text('{"AuthToken":"","columns":80,"rows":24}')
        assert ws.receive_bytes()                     # ttyd 回的第一帧(标题 / 设置 / 输出),原样转过来


def test_websocket_without_cookie_is_closed(client, worklet):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/tty/ws?arg={worklet['id']}", subprotocols=["tty"]):
            pass
    assert e.value.code == 1008


def test_cross_site_websocket_is_refused_even_with_the_cookie(client, worklet):
    client.get("/api/auth/status")
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/tty/ws?arg={worklet['id']}", subprotocols=["tty"], headers={"origin": "http://evil.example"}):
            pass
    assert e.value.code == 1008


def test_same_origin_websocket_gets_in(client, worklet):
    client.get("/api/auth/status")
    with client.websocket_connect(f"/tty/ws?arg={worklet['id']}", subprotocols=["tty"], headers={"origin": "http://testserver"}) as ws:
        ws.send_text('{"AuthToken":"","columns":80,"rows":24}')
        assert ws.receive_bytes()


def test_logout_shuts_the_window(client, worklet, H):
    token = client.tokens["alice"]
    client.get("/api/auth/status", headers=H("alice"))
    assert client.get(worklet["window"]["url"]).status_code == 200
    client.post("/api/auth/logout", headers=H("alice"))
    client.cookies.set("mt_tty", token, path="/tty")  # 就算 cookie 还留着,token 作废了也不认
    assert client.get(worklet["window"]["url"]).status_code == 403
