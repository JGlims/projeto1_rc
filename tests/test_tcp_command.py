import socket
import json
import threading
import time

import pytest

from src.common.config import BUFFER_SIZE
from src.common.protocol import build_ack_packet, parse_command_packet
from src.server.tcp_command import TCPCommandServer


@pytest.fixture
def server():
    srv = TCPCommandServer(host="127.0.0.1", port=0)
    srv.start()
    yield srv
    srv.stop()


def _tcp_connect(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", port))
    return sock


class TestTCPCommandServer:
    def test_server_binds_and_starts(self, server):
        assert server.port > 0
        assert server.running

    def test_accepts_drone_connection(self, server):
        sock = _tcp_connect(server.port)
        drone_id = "DRONE-01"
        sock.sendall(json.dumps({"drone_id": drone_id}).encode("utf-8") + b"\n")
        time.sleep(0.1)
        assert drone_id in server.list_connected_drones()
        sock.close()

    def test_send_command_and_receive_ack(self, server):
        sock = _tcp_connect(server.port)
        sock.sendall(json.dumps({"drone_id": "DRONE-01"}).encode("utf-8") + b"\n")
        time.sleep(0.1)

        cmd_id = server.send_command("DRONE-01", "LAND")
        assert cmd_id is not None

        raw = b""
        sock.settimeout(2)
        while b"\n" not in raw:
            raw += sock.recv(BUFFER_SIZE)
        cmd = parse_command_packet(raw.strip())
        assert cmd["type"] == "LAND"
        assert cmd["cmd_id"] == cmd_id

        ack = build_ack_packet(cmd_id, "ACK")
        sock.sendall(ack.encode("utf-8") + b"\n")
        time.sleep(0.1)

        result = server.get_command_result(cmd_id)
        assert result is not None
        assert result["status"] == "ACK"
        sock.close()

    def test_send_command_with_params(self, server):
        sock = _tcp_connect(server.port)
        sock.sendall(json.dumps({"drone_id": "DRONE-02"}).encode("utf-8") + b"\n")
        time.sleep(0.1)

        cmd_id = server.send_command("DRONE-02", "MOVE", params={"lat": -15.0, "lon": -47.0})
        raw = b""
        sock.settimeout(2)
        while b"\n" not in raw:
            raw += sock.recv(BUFFER_SIZE)
        cmd = parse_command_packet(raw.strip())
        assert cmd["params"]["lat"] == -15.0
        sock.close()

    def test_send_to_unknown_drone_returns_none(self, server):
        result = server.send_command("GHOST", "LAND")
        assert result is None

    def test_multiple_drones_connected(self, server):
        socks = []
        for name in ("DRONE-A", "DRONE-B", "DRONE-C"):
            s = _tcp_connect(server.port)
            s.sendall(json.dumps({"drone_id": name}).encode("utf-8") + b"\n")
            socks.append(s)
        time.sleep(0.2)
        connected = server.list_connected_drones()
        assert set(connected) >= {"DRONE-A", "DRONE-B", "DRONE-C"}
        for s in socks:
            s.close()

    def test_drone_disconnect_removes_from_list(self, server):
        sock = _tcp_connect(server.port)
        sock.sendall(json.dumps({"drone_id": "DRONE-X"}).encode("utf-8") + b"\n")
        time.sleep(0.1)
        assert "DRONE-X" in server.list_connected_drones()
        sock.close()
        time.sleep(0.3)
        assert "DRONE-X" not in server.list_connected_drones()

    def test_stop_sets_running_false(self, server):
        server.stop()
        assert not server.running
