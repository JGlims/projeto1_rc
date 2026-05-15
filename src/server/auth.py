import sqlite3
import hashlib
import secrets
import threading


class AuthManager:
    def __init__(self, db_path="drone_telemetry.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL
                );
            """)

    def close(self):
        self._conn.close()

    def _hash_password(self, password, salt):
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    def register(self, username, password):
        salt = secrets.token_hex(16)
        pw_hash = self._hash_password(password, salt)
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, pw_hash, salt),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def authenticate(self, username, password):
        user = self._get_user(username)
        if not user:
            return False
        expected = self._hash_password(password, user["salt"])
        return expected == user["password_hash"]

    def _get_user(self, username):
        with self._lock:
            return self._conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

    def create_token(self, username):
        token = secrets.token_hex(32)
        with self._lock:
            self._conn.execute(
                "INSERT INTO tokens (token, username) VALUES (?, ?)",
                (token, username),
            )
            self._conn.commit()
        return token

    def validate_token(self, token):
        with self._lock:
            row = self._conn.execute(
                "SELECT username FROM tokens WHERE token = ?", (token,)
            ).fetchone()
        return row["username"] if row else None
