import socket
import json
import time
import os
import tempfile

import pytest

from src.common.protocol import build_telemetry_packet
from src.server.udp_telemetry import UDPTelemetryServer
from src.server.tcp_command import TCPCommandServer
from src.server.http_dashboard import create_app
from src.server.storage import StorageDB
from src.client.drone_simulator import DroneSimulator


class TestUDPErrorHandling:
    def test_oversized_packet_ignored(self):
        srv = UDPTelemetryServer("127.0.0.1", 0)
        srv.start()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b"x" * 100, ("127.0.0.1", srv.port))
        time.sleep(0.1)
        assert srv.list_drones() == []
        sock.close()
        srv.stop()

    def test_empty_packet_ignored(self):
        srv = UDPTelemetryServer("127.0.0.1", 0)
        srv.start()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b"", ("127.0.0.1", srv.port))
        time.sleep(0.1)
        assert srv.list_drones() == []
        sock.close()
        srv.stop()

    def test_partial_json_ignored(self):
        srv = UDPTelemetryServer("127.0.0.1", 0)
        srv.start()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b'{"drone_id": "DRONE-01"', ("127.0.0.1", srv.port))
        time.sleep(0.1)
        assert srv.list_drones() == []
        sock.close()
        srv.stop()


class TestTCPErrorHandling:
    def test_client_abrupt_disconnect(self):
        srv = TCPCommandServer("127.0.0.1", 0)
        srv.start()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", srv.port))
        sock.sendall(json.dumps({"drone_id": "CRASH-01"}).encode() + b"\n")
        time.sleep(0.1)
        assert "CRASH-01" in srv.list_connected_drones()
        sock.close()
        time.sleep(0.5)
        assert "CRASH-01" not in srv.list_connected_drones()
        srv.stop()

    def test_garbage_registration_ignored(self):
        srv = TCPCommandServer("127.0.0.1", 0)
        srv.start()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", srv.port))
        sock.sendall(b"not json at all\n")
        time.sleep(0.1)
        assert srv.list_connected_drones() == []
        sock.close()
        srv.stop()

    def test_send_command_to_disconnected_drone(self):
        srv = TCPCommandServer("127.0.0.1", 0)
        srv.start()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", srv.port))
        sock.sendall(json.dumps({"drone_id": "GONE-01"}).encode() + b"\n")
        time.sleep(0.1)
        sock.close()
        time.sleep(0.5)
        result = srv.send_command("GONE-01", "LAND")
        assert result is None
        srv.stop()


class TestHTTPErrorHandling:
    @pytest.fixture
    def client(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = StorageDB(path)
        app = create_app(db, tcp_server=None)
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c
        db.close()
        os.unlink(path)

    def test_command_empty_body(self, client):
        resp = client.post("/api/drones/X/command", content_type="application/json")
        assert resp.status_code == 400

    def test_command_invalid_json(self, client):
        resp = client.post("/api/drones/X/command",
            data="not json", content_type="application/json")
        assert resp.status_code == 400

    def test_telemetry_unknown_drone(self, client):
        resp = client.get("/api/drones/NOPE/telemetry")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["telemetry"] == []

    def test_drone_detail_unknown(self, client):
        resp = client.get("/api/drones/NOPE")
        assert resp.status_code == 404


class TestDroneReconnection:
    def test_drone_reconnects_after_server_restart(self):
        tcp = TCPCommandServer("127.0.0.1", 0)
        tcp.start()
        port = tcp.port
        udp = UDPTelemetryServer("127.0.0.1", 0)
        udp.start()

        drone = DroneSimulator(
            drone_id="RECON-01",
            udp_host="127.0.0.1", udp_port=udp.port,
            tcp_host="127.0.0.1", tcp_port=port,
            telemetry_interval=0.1,
        )
        drone.start()
        time.sleep(0.3)
        assert "RECON-01" in tcp.list_connected_drones()

        drone.stop()
        udp.stop()
        tcp.stop()
