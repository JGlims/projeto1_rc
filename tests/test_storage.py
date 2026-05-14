import os
import time
import tempfile

import pytest

from src.server.storage import StorageDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = StorageDB(path)
    yield store
    store.close()
    os.unlink(path)


class TestStorageTelemetry:
    def test_save_and_retrieve_telemetry(self, db):
        db.save_telemetry({
            "drone_id": "DRONE-01", "ts": time.time(),
            "lat": -15.76, "lon": -47.87, "alt": 100.0,
            "speed": 10.0, "battery": 95.0, "status": "flying",
        })
        rows = db.get_telemetry("DRONE-01")
        assert len(rows) == 1
        assert rows[0]["alt"] == 100.0

    def test_retrieve_latest_telemetry(self, db):
        for alt in (50.0, 100.0, 150.0):
            db.save_telemetry({
                "drone_id": "DRONE-01", "ts": time.time(),
                "lat": 0, "lon": 0, "alt": alt,
                "speed": 0, "battery": 80, "status": "flying",
            })
        latest = db.get_latest_telemetry("DRONE-01")
        assert latest["alt"] == 150.0

    def test_latest_returns_none_for_unknown(self, db):
        assert db.get_latest_telemetry("GHOST") is None

    def test_telemetry_limit(self, db):
        for i in range(20):
            db.save_telemetry({
                "drone_id": "DRONE-01", "ts": time.time(),
                "lat": 0, "lon": 0, "alt": float(i),
                "speed": 0, "battery": 80, "status": "flying",
            })
        rows = db.get_telemetry("DRONE-01", limit=5)
        assert len(rows) == 5
        assert rows[-1]["alt"] == 19.0

    def test_list_drones(self, db):
        for d in ("DRONE-A", "DRONE-B"):
            db.save_telemetry({
                "drone_id": d, "ts": time.time(),
                "lat": 0, "lon": 0, "alt": 0,
                "speed": 0, "battery": 100, "status": "idle",
            })
        assert set(db.list_drones()) == {"DRONE-A", "DRONE-B"}


class TestStorageCommands:
    def test_save_and_retrieve_command(self, db):
        db.save_command("cmd-1", "DRONE-01", "LAND", {})
        cmds = db.get_commands("DRONE-01")
        assert len(cmds) == 1
        assert cmds[0]["cmd_type"] == "LAND"
        assert cmds[0]["cmd_id"] == "cmd-1"

    def test_update_command_ack(self, db):
        db.save_command("cmd-2", "DRONE-01", "HOVER", {})
        db.update_command_ack("cmd-2", "ACK")
        cmds = db.get_commands("DRONE-01")
        assert cmds[0]["ack_status"] == "ACK"

    def test_unacked_command_has_null_status(self, db):
        db.save_command("cmd-3", "DRONE-01", "RTH", {})
        cmds = db.get_commands("DRONE-01")
        assert cmds[0]["ack_status"] is None


class TestStorageAlerts:
    def test_save_and_retrieve_alert(self, db):
        db.save_alert("DRONE-01", "LOW_BATTERY", "Battery at 10%")
        alerts = db.get_alerts("DRONE-01")
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "LOW_BATTERY"

    def test_alerts_all_drones(self, db):
        db.save_alert("DRONE-01", "LOW_BATTERY", "10%")
        db.save_alert("DRONE-02", "SIGNAL_LOST", "no response")
        all_alerts = db.get_alerts()
        assert len(all_alerts) == 2
