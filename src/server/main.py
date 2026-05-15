import logging
import threading
import time
from datetime import datetime, timezone

from src.common.config import SERVER_HOST, UDP_TELEMETRY_PORT, TCP_COMMAND_PORT, HTTP_DASHBOARD_PORT
from src.server.udp_telemetry import UDPTelemetryServer
from src.server.tcp_command import TCPCommandServer
from src.server.http_dashboard import create_app
from src.server.storage import StorageDB

logger = logging.getLogger(__name__)

BATTERY_ALERT_THRESHOLD = 20.0
ALERT_COOLDOWN_SEC = 30


class GroundStation:
    def __init__(self, host=SERVER_HOST, udp_port=UDP_TELEMETRY_PORT,
                 tcp_port=TCP_COMMAND_PORT, http_port=HTTP_DASHBOARD_PORT,
                 db_path="drone_telemetry.db"):
        self._host = host
        self._http_port = http_port
        self._db = StorageDB(db_path)
        self._udp = UDPTelemetryServer(host, udp_port)
        self._tcp = TCPCommandServer(host, tcp_port)
        self._app = create_app(self._db, self._tcp, self._udp)
        self._running = False
        self._alert_sent = {}

    def start(self):
        self._udp.start()
        self._tcp.start()
        self._running = True

        self._persist_thread = threading.Thread(target=self._persist_loop, daemon=True)
        self._persist_thread.start()

        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] Ground station started")
        logger.info(f"[{ts}]   UDP telemetry on {self._host}:{self._udp.port}")
        logger.info(f"[{ts}]   TCP commands on {self._host}:{self._tcp.port}")
        logger.info(f"[{ts}]   HTTP dashboard on http://{self._host}:{self._http_port}")

        self._app.run(host=self._host, port=self._http_port, use_reloader=False)

    def stop(self):
        self._running = False
        self._udp.stop()
        self._tcp.stop()
        self._db.close()

    def _persist_loop(self):
        seen = {}
        while self._running:
            time.sleep(0.5)
            for drone_id in self._udp.list_drones():
                latest = self._udp.get_latest(drone_id)
                if not latest:
                    continue
                pkt_ts = latest["ts"]
                if seen.get(drone_id) == pkt_ts:
                    continue
                seen[drone_id] = pkt_ts
                self._db.save_telemetry(latest)
                self._check_alerts(drone_id, latest)

    def _check_alerts(self, drone_id, telemetry):
        battery = telemetry["battery"]
        if battery < BATTERY_ALERT_THRESHOLD:
            last_alert = self._alert_sent.get(drone_id, 0)
            if time.time() - last_alert > ALERT_COOLDOWN_SEC:
                msg = f"Battery critically low: {battery:.1f}%"
                self._db.save_alert(drone_id, "LOW_BATTERY", msg)
                self._alert_sent[drone_id] = time.time()
                ts = datetime.now(timezone.utc).isoformat()
                logger.warning(f"[{ts}] ALERT {drone_id}: {msg}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    station = GroundStation()
    try:
        station.start()
    except KeyboardInterrupt:
        station.stop()


if __name__ == "__main__":
    main()
