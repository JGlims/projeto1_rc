import os
import time
import tempfile
import threading

import pytest

from src.server.udp_telemetry import UDPTelemetryServer
from src.server.tcp_command import TCPCommandServer
from src.server.http_dashboard import create_app
from src.server.storage import StorageDB
from src.client.drone_simulator import DroneSimulator


@pytest.fixture
def environment():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = StorageDB(db_path)
    udp = UDPTelemetryServer("127.0.0.1", 0)
    tcp = TCPCommandServer("127.0.0.1", 0)
    udp.start()
    tcp.start()
    app = create_app(db, tcp)
    app.config["TESTING"] = True

    yield {
        "db": db, "udp": udp, "tcp": tcp,
        "app": app, "client": app.test_client(),
    }

    udp.stop()
    tcp.stop()
    db.close()
    os.unlink(db_path)


class TestIntegration:
    def test_drone_telemetry_reaches_udp_server(self, environment):
        env = environment
        drone = DroneSimulator(
            drone_id="INTEG-01",
            udp_host="127.0.0.1", udp_port=env["udp"].port,
            tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
            telemetry_interval=0.1,
        )
        drone.start()
        time.sleep(0.5)
        drone.stop()
        assert "INTEG-01" in env["udp"].list_drones()
        latest = env["udp"].get_latest("INTEG-01")
        assert latest is not None
        assert "lat" in latest

    def test_drone_registers_on_tcp(self, environment):
        env = environment
        drone = DroneSimulator(
            drone_id="INTEG-02",
            udp_host="127.0.0.1", udp_port=env["udp"].port,
            tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
            telemetry_interval=0.1,
        )
        drone.start()
        time.sleep(0.3)
        assert "INTEG-02" in env["tcp"].list_connected_drones()
        drone.stop()

    def test_command_flow_end_to_end(self, environment):
        env = environment
        drone = DroneSimulator(
            drone_id="INTEG-03",
            udp_host="127.0.0.1", udp_port=env["udp"].port,
            tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
            telemetry_interval=0.1,
        )
        drone.start()
        time.sleep(0.3)

        cmd_id = env["tcp"].send_command("INTEG-03", "HOVER")
        assert cmd_id is not None
        time.sleep(0.3)

        result = env["tcp"].get_command_result(cmd_id)
        assert result is not None
        assert result["status"] == "ACK"
        drone.stop()

    def test_telemetry_persisted_to_db(self, environment):
        env = environment
        drone = DroneSimulator(
            drone_id="INTEG-04",
            udp_host="127.0.0.1", udp_port=env["udp"].port,
            tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
            telemetry_interval=0.1,
        )
        drone.start()
        time.sleep(0.5)

        latest = env["udp"].get_latest("INTEG-04")
        env["db"].save_telemetry(latest)

        rows = env["db"].get_telemetry("INTEG-04")
        assert len(rows) >= 1
        drone.stop()

    def test_http_api_shows_drone_after_persist(self, environment):
        env = environment
        env["db"].save_telemetry({
            "drone_id": "INTEG-05", "ts": time.time(),
            "lat": -15.76, "lon": -47.87, "alt": 100.0,
            "speed": 10.0, "battery": 90.0, "status": "flying",
        })
        resp = env["client"].get("/api/drones")
        data = resp.get_json()
        assert "INTEG-05" in data["drones"]
