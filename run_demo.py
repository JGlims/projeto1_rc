import logging
import time
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.common.config import SERVER_HOST, UDP_TELEMETRY_PORT, TCP_COMMAND_PORT, HTTP_DASHBOARD_PORT
from src.server.udp_telemetry import UDPTelemetryServer
from src.server.tcp_command import TCPCommandServer
from src.server.http_dashboard import create_app
from src.server.storage import StorageDB
from src.server.auth import AuthManager
from src.client.drone_simulator import DroneSimulator

NUM_DRONES = 3
DB_PATH = "demo_telemetry.db"


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("demo")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    db = StorageDB(DB_PATH)
    auth = AuthManager(DB_PATH)
    udp = UDPTelemetryServer(SERVER_HOST, UDP_TELEMETRY_PORT)
    tcp = TCPCommandServer(SERVER_HOST, TCP_COMMAND_PORT)

    udp.start()
    tcp.start()

    auth.register("admin", "admin")
    logger.info("=" * 60)
    logger.info("  DRONE TELEMETRY MONITOR - DEMO")
    logger.info("=" * 60)
    logger.info(f"  UDP telemetria:  {SERVER_HOST}:{UDP_TELEMETRY_PORT}")
    logger.info(f"  TCP comandos:    {SERVER_HOST}:{TCP_COMMAND_PORT}")
    logger.info(f"  HTTP dashboard:  http://{SERVER_HOST}:{HTTP_DASHBOARD_PORT}")
    logger.info(f"  Login: admin / admin")
    logger.info(f"  Drones simulados: {NUM_DRONES}")
    logger.info("=" * 60)

    drones = []
    for i in range(NUM_DRONES):
        d = DroneSimulator(drone_id=f"DRONE-{i+1:02d}")
        d.start()
        drones.append(d)
        logger.info(f"  Drone DRONE-{i+1:02d} iniciado")

    persist_running = True

    def persist_loop():
        seen = {}
        while persist_running:
            time.sleep(0.5)
            for drone_id in udp.list_drones():
                latest = udp.get_latest(drone_id)
                if not latest:
                    continue
                if seen.get(drone_id) == latest["ts"]:
                    continue
                seen[drone_id] = latest["ts"]
                db.save_telemetry(latest)
                if latest["battery"] < 20.0:
                    db.save_alert(drone_id, "LOW_BATTERY", f"Battery: {latest['battery']:.1f}%")

    persist_thread = threading.Thread(target=persist_loop, daemon=True)
    persist_thread.start()

    app = create_app(db, tcp, udp, auth)

    try:
        app.run(host=SERVER_HOST, port=HTTP_DASHBOARD_PORT, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        persist_running = False
        for d in drones:
            d.stop()
        udp.stop()
        tcp.stop()
        db.close()
        logger.info("Demo encerrada.")


if __name__ == "__main__":
    main()
