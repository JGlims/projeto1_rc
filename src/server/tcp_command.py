import socket
import threading
import json
import logging
from datetime import datetime, timezone

from src.common.config import TCP_COMMAND_PORT, SERVER_HOST, BUFFER_SIZE
from src.common.protocol import build_command_packet, parse_ack_packet
from src.common.metrics import RTTTracker

logger = logging.getLogger(__name__)


class TCPCommandServer:
    def __init__(self, host=SERVER_HOST, port=TCP_COMMAND_PORT):
        self._host = host
        self._port = port
        self._sock = None
        self._lock = threading.Lock()
        self._drones = {}
        self._pending_commands = {}
        self._command_results = {}
        self.rtt = RTTTracker()
        self.running = False

    @property
    def port(self):
        return self._port

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._port = self._sock.getsockname()[1]
        self._sock.listen(5)
        self._sock.settimeout(0.5)
        self.running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] TCP command server listening on {self._host}:{self._port}")

    def stop(self):
        self.running = False
        if self._accept_thread:
            self._accept_thread.join(timeout=2)
        with self._lock:
            for drone_id, info in self._drones.items():
                try:
                    info["sock"].close()
                except OSError:
                    pass
            self._drones.clear()
        if self._sock:
            self._sock.close()
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] TCP command server stopped")

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_drone, args=(conn, addr), daemon=True).start()

    def _handle_drone(self, conn, addr):
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] TCP new connection from {addr}")
        conn.settimeout(0.5)
        buf = b""
        drone_id = None

        try:
            while self.running:
                try:
                    chunk = conn.recv(BUFFER_SIZE)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk

                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    if drone_id is None:
                        try:
                            reg = json.loads(line)
                            drone_id = reg["drone_id"]
                        except (json.JSONDecodeError, KeyError):
                            continue
                        with self._lock:
                            self._drones[drone_id] = {"sock": conn, "addr": addr}
                        ts = datetime.now(timezone.utc).isoformat()
                        logger.info(f"[{ts}] TCP drone registered: {drone_id} from {addr}")
                        continue

                    try:
                        ack = parse_ack_packet(line)
                    except ValueError:
                        continue
                    cmd_id = ack["cmd_id"]
                    self.rtt.finish(cmd_id)
                    with self._lock:
                        self._command_results[cmd_id] = ack
                    ts = datetime.now(timezone.utc).isoformat()
                    logger.info(f"[{ts}] TCP ACK from {drone_id}: cmd={cmd_id} status={ack['status']}")
        except OSError:
            pass
        finally:
            with self._lock:
                if drone_id and drone_id in self._drones:
                    del self._drones[drone_id]
            conn.close()
            ts = datetime.now(timezone.utc).isoformat()
            logger.info(f"[{ts}] TCP drone disconnected: {drone_id} from {addr}")

    def send_command(self, drone_id, cmd_type, params=None):
        with self._lock:
            drone_info = self._drones.get(drone_id)
        if not drone_info:
            return None

        pkt = build_command_packet(cmd_type, params)
        cmd_id = json.loads(pkt)["cmd_id"]
        payload = pkt.encode("utf-8") + b"\n"

        self.rtt.start(cmd_id)
        try:
            drone_info["sock"].sendall(payload)
        except OSError:
            return None

        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] TCP sent cmd to {drone_id}: type={cmd_type} cmd_id={cmd_id}")
        return cmd_id

    def get_command_result(self, cmd_id):
        with self._lock:
            return self._command_results.get(cmd_id)

    def list_connected_drones(self):
        with self._lock:
            return list(self._drones.keys())
