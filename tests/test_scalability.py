import os
import time
import tempfile

import pytest

from src.server.udp_telemetry import UDPTelemetryServer
from src.server.tcp_command import TCPCommandServer
from src.server.storage import StorageDB
from src.client.drone_simulator import DroneSimulator


NUM_DRONES = 10
TELEMETRY_INTERVAL = 0.1
RUN_DURATION = 2.0


@pytest.fixture
def infrastructure():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = StorageDB(db_path)
    udp = UDPTelemetryServer("127.0.0.1", 0)
    tcp = TCPCommandServer("127.0.0.1", 0)
    udp.start()
    tcp.start()
    yield {"db": db, "udp": udp, "tcp": tcp}
    udp.stop()
    tcp.stop()
    db.close()
    os.unlink(db_path)


class TestScalability:
    def test_multiple_drones_register(self, infrastructure):
        env = infrastructure
        drones = []
        for i in range(NUM_DRONES):
            d = DroneSimulator(
                drone_id=f"SCALE-{i:02d}",
                udp_host="127.0.0.1", udp_port=env["udp"].port,
                tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
                telemetry_interval=TELEMETRY_INTERVAL,
            )
            d.start()
            drones.append(d)

        time.sleep(1.0)
        connected = env["tcp"].list_connected_drones()
        assert len(connected) == NUM_DRONES

        for d in drones:
            d.stop()

    def test_multiple_drones_telemetry(self, infrastructure):
        env = infrastructure
        drones = []
        for i in range(NUM_DRONES):
            d = DroneSimulator(
                drone_id=f"TEL-{i:02d}",
                udp_host="127.0.0.1", udp_port=env["udp"].port,
                tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
                telemetry_interval=TELEMETRY_INTERVAL,
            )
            d.start()
            drones.append(d)

        time.sleep(RUN_DURATION)
        known = env["udp"].list_drones()
        assert len(known) == NUM_DRONES

        for drone_id in known:
            history = env["udp"].get_telemetry(drone_id)
            assert len(history) >= 5

        for d in drones:
            d.stop()

    def test_concurrent_commands(self, infrastructure):
        env = infrastructure
        drones = []
        for i in range(5):
            d = DroneSimulator(
                drone_id=f"CMD-{i:02d}",
                udp_host="127.0.0.1", udp_port=env["udp"].port,
                tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
                telemetry_interval=TELEMETRY_INTERVAL,
            )
            d.start()
            drones.append(d)

        time.sleep(0.5)

        cmd_ids = []
        for i in range(5):
            cid = env["tcp"].send_command(f"CMD-{i:02d}", "HOVER")
            assert cid is not None
            cmd_ids.append(cid)

        time.sleep(1.0)

        for cid in cmd_ids:
            result = env["tcp"].get_command_result(cid)
            assert result is not None
            assert result["status"] == "ACK"

        for d in drones:
            d.stop()

    def test_throughput_under_load(self, infrastructure):
        env = infrastructure
        drones = []
        for i in range(NUM_DRONES):
            d = DroneSimulator(
                drone_id=f"LOAD-{i:02d}",
                udp_host="127.0.0.1", udp_port=env["udp"].port,
                tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
                telemetry_interval=0.05,
            )
            d.start()
            drones.append(d)

        time.sleep(RUN_DURATION)
        summary = env["udp"].throughput.summary()
        assert summary["packet_count"] >= NUM_DRONES * 10
        assert summary["bytes_per_second"] > 0

        for d in drones:
            d.stop()

    def test_rtt_under_load(self, infrastructure):
        env = infrastructure
        drones = []
        for i in range(5):
            d = DroneSimulator(
                drone_id=f"RTT-{i:02d}",
                udp_host="127.0.0.1", udp_port=env["udp"].port,
                tcp_host="127.0.0.1", tcp_port=env["tcp"].port,
                telemetry_interval=TELEMETRY_INTERVAL,
            )
            d.start()
            drones.append(d)

        time.sleep(0.5)

        for i in range(5):
            env["tcp"].send_command(f"RTT-{i:02d}", "LAND")

        time.sleep(1.0)

        avg = env["tcp"].rtt.average()
        assert avg is not None
        assert avg < 1.0

        for d in drones:
            d.stop()
