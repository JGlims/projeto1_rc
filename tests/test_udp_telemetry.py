import socket
import json
import threading
import time

import pytest

from src.common.config import BUFFER_SIZE
from src.common.protocol import build_telemetry_packet
from src.server.udp_telemetry import UDPTelemetryServer


@pytest.fixture
def server():
    srv = UDPTelemetryServer(host="127.0.0.1", port=0)
    srv.start()
    yield srv
    srv.stop()


def _send_udp(port, data):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(data.encode("utf-8"), ("127.0.0.1", port))
    sock.close()


class TestUDPTelemetryServer:
    def test_server_binds_and_starts(self, server):
        assert server.port > 0
        assert server.running

    def test_receives_telemetry_packet(self, server):
        pkt = build_telemetry_packet("DRONE-01", -15.76, -47.87, 100.0, 10.0, 95.0, "flying")
        _send_udp(server.port, pkt)
        time.sleep(0.1)
        history = server.get_telemetry("DRONE-01")
        assert len(history) == 1
        assert history[0]["alt"] == 100.0

    def test_receives_multiple_drones(self, server):
        pkt1 = build_telemetry_packet("DRONE-01", 0, 0, 50.0, 5.0, 80.0, "hovering")
        pkt2 = build_telemetry_packet("DRONE-02", 1, 1, 75.0, 8.0, 60.0, "flying")
        _send_udp(server.port, pkt1)
        _send_udp(server.port, pkt2)
        time.sleep(0.1)
        assert len(server.get_telemetry("DRONE-01")) == 1
        assert len(server.get_telemetry("DRONE-02")) == 1

    def test_stores_history_in_order(self, server):
        for i in range(5):
            pkt = build_telemetry_packet("DRONE-01", 0, 0, float(i * 10), 0, 100, "flying")
            _send_udp(server.port, pkt)
            time.sleep(0.02)
        time.sleep(0.1)
        history = server.get_telemetry("DRONE-01")
        assert len(history) == 5
        altitudes = [h["alt"] for h in history]
        assert altitudes == [0.0, 10.0, 20.0, 30.0, 40.0]

    def test_get_latest_telemetry(self, server):
        _send_udp(server.port, build_telemetry_packet("DRONE-01", 0, 0, 10.0, 0, 100, "flying"))
        _send_udp(server.port, build_telemetry_packet("DRONE-01", 0, 0, 20.0, 0, 100, "flying"))
        time.sleep(0.1)
        latest = server.get_latest("DRONE-01")
        assert latest["alt"] == 20.0

    def test_get_latest_returns_none_for_unknown(self, server):
        assert server.get_latest("UNKNOWN") is None

    def test_list_known_drones(self, server):
        _send_udp(server.port, build_telemetry_packet("DRONE-A", 0, 0, 0, 0, 100, "idle"))
        _send_udp(server.port, build_telemetry_packet("DRONE-B", 0, 0, 0, 0, 100, "idle"))
        time.sleep(0.1)
        drones = server.list_drones()
        assert set(drones) == {"DRONE-A", "DRONE-B"}

    def test_ignores_malformed_packet(self, server):
        _send_udp(server.port, "this is not json")
        time.sleep(0.1)
        assert server.list_drones() == []

    def test_stop_sets_running_false(self, server):
        server.stop()
        assert not server.running
