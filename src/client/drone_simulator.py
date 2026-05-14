import socket
import threading
import json
import time
import random
import logging
from datetime import datetime, timezone

from src.common.config import (
    SERVER_HOST, UDP_TELEMETRY_PORT, TCP_COMMAND_PORT,
    BUFFER_SIZE, TELEMETRY_INTERVAL_SEC,
)
from src.common.protocol import build_telemetry_packet, build_ack_packet, parse_command_packet

logger = logging.getLogger(__name__)


class DroneSimulator:
    def __init__(self, drone_id="DRONE-01",
                 udp_host=SERVER_HOST, udp_port=UDP_TELEMETRY_PORT,
                 tcp_host=SERVER_HOST, tcp_port=TCP_COMMAND_PORT,
                 telemetry_interval=TELEMETRY_INTERVAL_SEC):
        self.drone_id = drone_id
        self._udp_host = udp_host
        self._udp_port = udp_port
        self._tcp_host = tcp_host
        self._tcp_port = tcp_port
        self._interval = telemetry_interval

        self._udp_sock = None
        self._tcp_sock = None
        self._running = False

        self._lat = -15.7631 + random.uniform(-0.01, 0.01)
        self._lon = -47.8729 + random.uniform(-0.01, 0.01)
        self._alt = random.uniform(50.0, 150.0)
        self._speed = random.uniform(5.0, 15.0)
        self._battery = 100.0
        self._status = "flying"

    def start(self):
        self._running = True
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_sock.connect((self._tcp_host, self._tcp_port))
        self._tcp_sock.settimeout(0.5)

        reg = json.dumps({"drone_id": self.drone_id}).encode("utf-8") + b"\n"
        self._tcp_sock.sendall(reg)
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] {self.drone_id} registered via TCP to {self._tcp_host}:{self._tcp_port}")

        self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self._command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self._telemetry_thread.start()
        self._command_thread.start()

    def stop(self):
        self._running = False
        if self._telemetry_thread:
            self._telemetry_thread.join(timeout=2)
        if self._command_thread:
            self._command_thread.join(timeout=2)
        if self._udp_sock:
            self._udp_sock.close()
        if self._tcp_sock:
            self._tcp_sock.close()

    def _update_state(self):
        if self._status == "landed":
            self._speed = 0.0
            return

        self._lat += random.uniform(-0.0001, 0.0001)
        self._lon += random.uniform(-0.0001, 0.0001)
        self._alt += random.uniform(-2.0, 2.0)
        self._alt = max(0.0, self._alt)
        self._speed += random.uniform(-1.0, 1.0)
        self._speed = max(0.0, self._speed)
        self._battery -= random.uniform(0.05, 0.2)
        self._battery = max(0.0, self._battery)

    def _telemetry_loop(self):
        while self._running:
            self._update_state()
            pkt = build_telemetry_packet(
                self.drone_id, self._lat, self._lon, self._alt,
                self._speed, self._battery, self._status,
            )
            self._udp_sock.sendto(pkt.encode("utf-8"), (self._udp_host, self._udp_port))
            ts = datetime.now(timezone.utc).isoformat()
            logger.info(
                f"[{ts}] {self.drone_id} UDP sent telemetry | "
                f"alt={self._alt:.1f}m bat={self._battery:.1f}% spd={self._speed:.1f}m/s"
            )
            time.sleep(self._interval)

    def _command_loop(self):
        buf = b""
        while self._running:
            try:
                chunk = self._tcp_sock.recv(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk

            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = parse_command_packet(line)
                except ValueError:
                    continue

                ts = datetime.now(timezone.utc).isoformat()
                logger.info(f"[{ts}] {self.drone_id} TCP recv command: {cmd['type']} (cmd_id={cmd['cmd_id']})")

                self._execute_command(cmd)

                ack = build_ack_packet(cmd["cmd_id"], "ACK")
                self._tcp_sock.sendall(ack.encode("utf-8") + b"\n")
                logger.info(f"[{ts}] {self.drone_id} TCP sent ACK for cmd_id={cmd['cmd_id']}")

    def _execute_command(self, cmd):
        cmd_type = cmd["type"]
        if cmd_type == "LAND":
            self._status = "landed"
            self._alt = 0.0
        elif cmd_type == "HOVER":
            self._status = "hovering"
            self._speed = 0.0
        elif cmd_type == "RTH":
            self._status = "returning"
            self._lat = -15.7631
            self._lon = -47.8729


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    drone = DroneSimulator()
    drone.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        drone.stop()
