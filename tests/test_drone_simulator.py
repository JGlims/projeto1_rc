import socket
import json
import threading
import time

import pytest

from src.common.config import BUFFER_SIZE
from src.common.protocol import parse_telemetry_packet, build_command_packet, parse_ack_packet
from src.client.drone_simulator import DroneSimulator


class FakeUDPReceiver:
    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(3)
        self.port = self._sock.getsockname()[1]
        self.packets = []

    def receive(self, count=1):
        for _ in range(count):
            data, _ = self._sock.recvfrom(BUFFER_SIZE)
            self.packets.append(parse_telemetry_packet(data))

    def close(self):
        self._sock.close()


class FakeTCPServer:
    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._sock.settimeout(3)
        self.port = self._sock.getsockname()[1]
        self.conn = None

    def accept_drone(self):
        self.conn, _ = self._sock.accept()
        self.conn.settimeout(3)
        buf = b""
        while b"\n" not in buf:
            buf += self.conn.recv(BUFFER_SIZE)
        reg = json.loads(buf.strip())
        return reg["drone_id"]

    def send_command(self, cmd_type):
        pkt = build_command_packet(cmd_type)
        self.conn.sendall(pkt.encode("utf-8") + b"\n")
        return json.loads(pkt)["cmd_id"]

    def receive_ack(self):
        buf = b""
        while b"\n" not in buf:
            buf += self.conn.recv(BUFFER_SIZE)
        return parse_ack_packet(buf.strip())

    def close(self):
        if self.conn:
            self.conn.close()
        self._sock.close()


@pytest.fixture
def udp_receiver():
    r = FakeUDPReceiver()
    yield r
    r.close()


@pytest.fixture
def tcp_server():
    s = FakeTCPServer()
    yield s
    s.close()


class TestDroneSimulator:
    def test_sends_telemetry_via_udp(self, udp_receiver, tcp_server):
        drone = DroneSimulator(
            drone_id="DRONE-T1",
            udp_host="127.0.0.1", udp_port=udp_receiver.port,
            tcp_host="127.0.0.1", tcp_port=tcp_server.port,
            telemetry_interval=0.1,
        )
        drone.start()
        tcp_server.accept_drone()
        udp_receiver.receive(1)
        drone.stop()
        assert len(udp_receiver.packets) == 1
        assert udp_receiver.packets[0]["drone_id"] == "DRONE-T1"

    def test_telemetry_has_valid_fields(self, udp_receiver, tcp_server):
        drone = DroneSimulator(
            drone_id="DRONE-T2",
            udp_host="127.0.0.1", udp_port=udp_receiver.port,
            tcp_host="127.0.0.1", tcp_port=tcp_server.port,
            telemetry_interval=0.1,
        )
        drone.start()
        tcp_server.accept_drone()
        udp_receiver.receive(1)
        drone.stop()
        pkt = udp_receiver.packets[0]
        assert "lat" in pkt
        assert "lon" in pkt
        assert "alt" in pkt
        assert "speed" in pkt
        assert "battery" in pkt
        assert 0 <= pkt["battery"] <= 100

    def test_battery_decreases_over_time(self, udp_receiver, tcp_server):
        drone = DroneSimulator(
            drone_id="DRONE-T3",
            udp_host="127.0.0.1", udp_port=udp_receiver.port,
            tcp_host="127.0.0.1", tcp_port=tcp_server.port,
            telemetry_interval=0.05,
        )
        drone.start()
        tcp_server.accept_drone()
        udp_receiver.receive(5)
        drone.stop()
        batteries = [p["battery"] for p in udp_receiver.packets]
        assert batteries[0] >= batteries[-1]

    def test_registers_on_tcp(self, udp_receiver, tcp_server):
        drone = DroneSimulator(
            drone_id="DRONE-T4",
            udp_host="127.0.0.1", udp_port=udp_receiver.port,
            tcp_host="127.0.0.1", tcp_port=tcp_server.port,
            telemetry_interval=0.1,
        )
        drone.start()
        reg_id = tcp_server.accept_drone()
        drone.stop()
        assert reg_id == "DRONE-T4"

    def test_responds_ack_to_command(self, udp_receiver, tcp_server):
        drone = DroneSimulator(
            drone_id="DRONE-T5",
            udp_host="127.0.0.1", udp_port=udp_receiver.port,
            tcp_host="127.0.0.1", tcp_port=tcp_server.port,
            telemetry_interval=0.1,
        )
        drone.start()
        tcp_server.accept_drone()
        time.sleep(0.15)
        cmd_id = tcp_server.send_command("LAND")
        ack = tcp_server.receive_ack()
        drone.stop()
        assert ack["cmd_id"] == cmd_id
        assert ack["status"] == "ACK"

    def test_land_command_changes_status(self, udp_receiver, tcp_server):
        drone = DroneSimulator(
            drone_id="DRONE-T6",
            udp_host="127.0.0.1", udp_port=udp_receiver.port,
            tcp_host="127.0.0.1", tcp_port=tcp_server.port,
            telemetry_interval=0.1,
        )
        drone.start()
        tcp_server.accept_drone()
        time.sleep(0.15)
        tcp_server.send_command("LAND")
        tcp_server.receive_ack()
        time.sleep(0.25)
        drone.stop()
        time.sleep(0.1)
        udp_receiver._sock.settimeout(0.3)
        last = None
        while True:
            try:
                data, _ = udp_receiver._sock.recvfrom(BUFFER_SIZE)
                last = parse_telemetry_packet(data)
            except socket.timeout:
                break
        assert last is not None
        assert last["status"] == "landed"
