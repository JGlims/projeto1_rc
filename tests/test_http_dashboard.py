import json
import time
import tempfile
import os

import pytest

from src.server.http_dashboard import create_app
from src.server.storage import StorageDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = StorageDB(path)
    yield store
    store.close()
    os.unlink(path)


@pytest.fixture
def client(db):
    app = create_app(db, tcp_server=None)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _insert_telemetry(db, drone_id, alt=100.0, battery=90.0):
    db.save_telemetry({
        "drone_id": drone_id, "ts": time.time(),
        "lat": -15.76, "lon": -47.87, "alt": alt,
        "speed": 10.0, "battery": battery, "status": "flying",
    })


class TestDashboardPage:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data

    def test_index_contains_title(self, client):
        resp = client.get("/")
        assert b"Drone" in resp.data

    def test_index_uses_incremental_dom_updates(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "data-drone-id" in html
        assert "updateDroneCard" in html or "updateCard" in html

    def test_index_does_not_wipe_grid_on_refresh(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "while (grid.firstChild) grid.removeChild(grid.firstChild)" not in html

    def test_register_page_exists(self, client):
        resp = client.get("/register")
        assert resp.status_code == 200
        assert b"<html" in resp.data

    def test_register_page_has_form(self, client):
        resp = client.get("/register")
        html = resp.data.decode()
        assert "username" in html.lower() or "usuario" in html.lower()
        assert "password" in html.lower() or "senha" in html.lower()

    def test_index_uses_tailwind(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "tailwindcss" in html

    def test_index_uses_inter_font(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert "Inter" in html

    def test_register_uses_tailwind(self, client):
        resp = client.get("/register")
        html = resp.data.decode()
        assert "tailwindcss" in html


class TestAPIDrones:
    def test_list_drones_empty(self, client):
        resp = client.get("/api/drones")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["drones"] == []

    def test_list_drones_with_data(self, client, db):
        _insert_telemetry(db, "DRONE-01")
        _insert_telemetry(db, "DRONE-02")
        resp = client.get("/api/drones")
        data = json.loads(resp.data)
        assert set(data["drones"]) == {"DRONE-01", "DRONE-02"}

    def test_get_drone_detail(self, client, db):
        _insert_telemetry(db, "DRONE-01", alt=120.0, battery=85.0)
        resp = client.get("/api/drones/DRONE-01")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["drone_id"] == "DRONE-01"
        assert data["latest"]["alt"] == 120.0

    def test_get_drone_not_found(self, client):
        resp = client.get("/api/drones/GHOST")
        assert resp.status_code == 404

    def test_get_drone_telemetry_history(self, client, db):
        for i in range(3):
            _insert_telemetry(db, "DRONE-01", alt=float(i * 10))
        resp = client.get("/api/drones/DRONE-01/telemetry")
        data = json.loads(resp.data)
        assert len(data["telemetry"]) == 3


class TestAPICommands:
    def test_send_command_no_tcp_server(self, client):
        resp = client.post(
            "/api/drones/DRONE-01/command",
            data=json.dumps({"type": "LAND"}),
            content_type="application/json",
        )
        assert resp.status_code == 503

    def test_send_command_missing_type(self, client):
        resp = client.post(
            "/api/drones/DRONE-01/command",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestAPIAlerts:
    def test_get_alerts_empty(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["alerts"] == []

    def test_get_alerts_with_data(self, client, db):
        db.save_alert("DRONE-01", "LOW_BATTERY", "Battery at 10%")
        resp = client.get("/api/alerts")
        data = json.loads(resp.data)
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["alert_type"] == "LOW_BATTERY"
