import os
import json
import tempfile

import pytest

from src.server.auth import AuthManager
from src.server.http_dashboard import create_app
from src.server.storage import StorageDB


@pytest.fixture
def auth():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    mgr = AuthManager(path)
    yield mgr
    mgr.close()
    os.unlink(path)


@pytest.fixture
def app_client(auth):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = StorageDB(db_path)
    app = create_app(db, tcp_server=None, udp_server=None, auth=auth)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    db.close()
    os.unlink(db_path)


class TestAuthManager:
    def test_register_user(self, auth):
        ok = auth.register("operator1", "securepass123")
        assert ok is True

    def test_register_duplicate_fails(self, auth):
        auth.register("operator1", "pass1")
        ok = auth.register("operator1", "pass2")
        assert ok is False

    def test_authenticate_valid(self, auth):
        auth.register("operator1", "mypass")
        assert auth.authenticate("operator1", "mypass") is True

    def test_authenticate_wrong_password(self, auth):
        auth.register("operator1", "mypass")
        assert auth.authenticate("operator1", "wrongpass") is False

    def test_authenticate_unknown_user(self, auth):
        assert auth.authenticate("ghost", "pass") is False

    def test_password_not_stored_plaintext(self, auth):
        auth.register("operator1", "secret")
        row = auth._get_user("operator1")
        assert row["password_hash"] != "secret"

    def test_create_and_validate_token(self, auth):
        auth.register("op1", "pass")
        token = auth.create_token("op1")
        assert token is not None
        user = auth.validate_token(token)
        assert user == "op1"

    def test_invalid_token_returns_none(self, auth):
        assert auth.validate_token("bogus-token") is None


class TestAuthHTTP:
    def test_register_endpoint(self, app_client):
        resp = app_client.post("/api/auth/register",
            data=json.dumps({"username": "testuser", "password": "testpass"}),
            content_type="application/json")
        assert resp.status_code == 201

    def test_register_duplicate_returns_409(self, app_client):
        payload = json.dumps({"username": "dup", "password": "pass"})
        app_client.post("/api/auth/register", data=payload, content_type="application/json")
        resp = app_client.post("/api/auth/register", data=payload, content_type="application/json")
        assert resp.status_code == 409

    def test_login_returns_token(self, app_client):
        app_client.post("/api/auth/register",
            data=json.dumps({"username": "u1", "password": "p1"}),
            content_type="application/json")
        resp = app_client.post("/api/auth/login",
            data=json.dumps({"username": "u1", "password": "p1"}),
            content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "token" in data

    def test_login_wrong_password_returns_401(self, app_client):
        app_client.post("/api/auth/register",
            data=json.dumps({"username": "u2", "password": "p2"}),
            content_type="application/json")
        resp = app_client.post("/api/auth/login",
            data=json.dumps({"username": "u2", "password": "wrong"}),
            content_type="application/json")
        assert resp.status_code == 401

    def test_command_without_token_returns_401(self, app_client):
        resp = app_client.post("/api/drones/DRONE-01/command",
            data=json.dumps({"type": "LAND"}),
            content_type="application/json")
        assert resp.status_code == 401

    def test_command_with_valid_token(self, app_client):
        app_client.post("/api/auth/register",
            data=json.dumps({"username": "op", "password": "pw"}),
            content_type="application/json")
        resp = app_client.post("/api/auth/login",
            data=json.dumps({"username": "op", "password": "pw"}),
            content_type="application/json")
        token = resp.get_json()["token"]
        resp = app_client.post("/api/drones/DRONE-01/command",
            data=json.dumps({"type": "LAND"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token}"})
        # 503 because no tcp server, but NOT 401
        assert resp.status_code == 503
