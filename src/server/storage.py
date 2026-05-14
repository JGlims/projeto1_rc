import sqlite3
import json
import time
import threading


class StorageDB:
    def __init__(self, db_path="drone_telemetry.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drone_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    lat REAL, lon REAL, alt REAL,
                    speed REAL, battery REAL,
                    status TEXT,
                    received_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cmd_id TEXT UNIQUE NOT NULL,
                    drone_id TEXT NOT NULL,
                    cmd_type TEXT NOT NULL,
                    params TEXT,
                    ack_status TEXT,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drone_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    message TEXT,
                    created_at REAL NOT NULL
                );
            """)

    def close(self):
        self._conn.close()

    def save_telemetry(self, packet):
        with self._lock:
            self._conn.execute(
                "INSERT INTO telemetry (drone_id, ts, lat, lon, alt, speed, battery, status, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (packet["drone_id"], packet["ts"], packet["lat"], packet["lon"],
                 packet["alt"], packet["speed"], packet["battery"], packet["status"],
                 time.time()),
            )
            self._conn.commit()

    def get_telemetry(self, drone_id, limit=100):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM telemetry WHERE drone_id = ? ORDER BY ts DESC LIMIT ?",
                (drone_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_latest_telemetry(self, drone_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM telemetry WHERE drone_id = ? ORDER BY ts DESC LIMIT 1",
                (drone_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_drones(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT drone_id FROM telemetry"
            ).fetchall()
        return [r["drone_id"] for r in rows]

    def save_command(self, cmd_id, drone_id, cmd_type, params):
        with self._lock:
            self._conn.execute(
                "INSERT INTO commands (cmd_id, drone_id, cmd_type, params, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cmd_id, drone_id, cmd_type, json.dumps(params), time.time()),
            )
            self._conn.commit()

    def update_command_ack(self, cmd_id, ack_status):
        with self._lock:
            self._conn.execute(
                "UPDATE commands SET ack_status = ? WHERE cmd_id = ?",
                (ack_status, cmd_id),
            )
            self._conn.commit()

    def get_commands(self, drone_id, limit=50):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM commands WHERE drone_id = ? ORDER BY created_at DESC LIMIT ?",
                (drone_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def save_alert(self, drone_id, alert_type, message):
        with self._lock:
            self._conn.execute(
                "INSERT INTO alerts (drone_id, alert_type, message, created_at) VALUES (?, ?, ?, ?)",
                (drone_id, alert_type, message, time.time()),
            )
            self._conn.commit()

    def get_alerts(self, drone_id=None, limit=50):
        with self._lock:
            if drone_id:
                rows = self._conn.execute(
                    "SELECT * FROM alerts WHERE drone_id = ? ORDER BY created_at DESC LIMIT ?",
                    (drone_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in reversed(rows)]
