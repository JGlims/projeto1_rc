import socket
import threading
import logging
from datetime import datetime, timezone

from src.common.config import UDP_TELEMETRY_PORT, SERVER_HOST, BUFFER_SIZE
from src.common.protocol import parse_telemetry_packet

logger = logging.getLogger(__name__)


class UDPTelemetryServer:
    def __init__(self, host=SERVER_HOST, port=UDP_TELEMETRY_PORT):
        self._host = host
        self._port = port
        self._sock = None
        self._thread = None
        self._lock = threading.Lock()
        self._telemetry = {}
        self.running = False

    @property
    def port(self):
        return self._port

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._port = self._sock.getsockname()[1]
        self._sock.settimeout(0.5)
        self.running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] UDP telemetry server listening on {self._host}:{self._port}")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._sock:
            self._sock.close()
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] UDP telemetry server stopped")

    def _listen(self):
        while self.running:
            try:
                data, addr = self._sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            ts = datetime.now(timezone.utc).isoformat()
            try:
                packet = parse_telemetry_packet(data)
            except ValueError as e:
                logger.warning(f"[{ts}] UDP malformed packet from {addr}: {e}")
                continue

            drone_id = packet["drone_id"]
            with self._lock:
                if drone_id not in self._telemetry:
                    self._telemetry[drone_id] = []
                self._telemetry[drone_id].append(packet)

            logger.info(
                f"[{ts}] UDP recv from {addr} | drone={drone_id} "
                f"alt={packet['alt']}m bat={packet['battery']}% "
                f"spd={packet['speed']}m/s status={packet['status']}"
            )

    def get_telemetry(self, drone_id):
        with self._lock:
            return list(self._telemetry.get(drone_id, []))

    def get_latest(self, drone_id):
        with self._lock:
            history = self._telemetry.get(drone_id)
            if not history:
                return None
            return history[-1]

    def list_drones(self):
        with self._lock:
            return list(self._telemetry.keys())
