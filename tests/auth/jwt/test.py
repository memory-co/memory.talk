"""auth/jwt -- tokens are HS256 JWTs checked at the outermost gate. See README.md."""
import base64
import json
import time

from memorytalk.backend.services.auth import jwt


def _claims(token):
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_token_is_a_jwt_with_sub_exp_and_jti(client):
    claims = _claims(client.tokens["alice"])
    assert claims["sub"] == "alice" and claims["exp"] > time.time() and claims["jti"]


def test_tampered_signature_is_401(client):
    head, body, sig = client.tokens["alice"].split(".")
    forged = f"{head}.{body}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"
    assert client.get("/api/works", headers=_bearer(forged)).status_code == 401


def test_claims_signed_with_another_key_are_401(client):
    forged = jwt.encode({**_claims(client.tokens["alice"]), "sub": "admin"}, b"not-the-key")
    assert client.get("/api/works", headers=_bearer(forged)).status_code == 401


def test_alg_none_is_401(client):
    head = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    body = client.tokens["alice"].split(".")[1]
    assert client.get("/api/works", headers=_bearer(f"{head}.{body}.")).status_code == 401


def test_expired_token_is_401(client, svc):
    expired = jwt.encode({**_claims(client.tokens["alice"]), "exp": int(time.time()) - 1}, svc.auth.key)
    assert client.get("/api/works", headers=_bearer(expired)).status_code == 401


def test_valid_signature_but_revoked_jti_is_401(client):
    token = client.post("/api/auth/login", json={"name": "bob", "password": "pw-123456"}).json()["token"]
    client.post("/api/auth/logout", headers=_bearer(token))
    assert client.get("/api/works", headers=_bearer(token)).status_code == 401


def test_api_ignores_the_surface_cookie(client):
    client.cookies.set("mt_surface", client.tokens["admin"])
    assert client.get("/api/works", headers={"Authorization": ""}).status_code == 401
