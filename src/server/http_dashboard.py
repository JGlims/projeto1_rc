import json
import logging
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, render_template

logger = logging.getLogger(__name__)


def create_app(storage, tcp_server=None, udp_server=None, auth=None):
    app = Flask(
        __name__,
        template_folder="../dashboard/templates",
        static_folder="../dashboard/static",
    )
    app.config["storage"] = storage
    app.config["tcp_server"] = tcp_server
    app.config["udp_server"] = udp_server
    app.config["auth"] = auth

    def require_auth(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_mgr = app.config["auth"]
            if not auth_mgr:
                return f(*args, **kwargs)
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"error": "authentication required"}), 401
            token = header[7:]
            user = auth_mgr.validate_token(token)
            if not user:
                return jsonify({"error": "invalid token"}), 401
            return f(*args, **kwargs)
        return decorated

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/register")
    def register_page():
        return render_template("register.html")

    @app.route("/api/auth/register", methods=["POST"])
    def register():
        auth_mgr = app.config["auth"]
        if not auth_mgr:
            return jsonify({"error": "auth not configured"}), 503
        body = request.get_json(silent=True) or {}
        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            return jsonify({"error": "missing username or password"}), 400
        if auth_mgr.register(username, password):
            return jsonify({"status": "registered"}), 201
        return jsonify({"error": "username already exists"}), 409

    @app.route("/api/auth/login", methods=["POST"])
    def login():
        auth_mgr = app.config["auth"]
        if not auth_mgr:
            return jsonify({"error": "auth not configured"}), 503
        body = request.get_json(silent=True) or {}
        username = body.get("username")
        password = body.get("password")
        if not auth_mgr.authenticate(username, password):
            return jsonify({"error": "invalid credentials"}), 401
        token = auth_mgr.create_token(username)
        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] HTTP login: {username}")
        return jsonify({"token": token})

    @app.route("/api/drones")
    def list_drones():
        db = app.config["storage"]
        drones = db.list_drones()
        return jsonify({"drones": drones})

    @app.route("/api/drones/<drone_id>")
    def get_drone(drone_id):
        db = app.config["storage"]
        latest = db.get_latest_telemetry(drone_id)
        if not latest:
            return jsonify({"error": "drone not found"}), 404
        return jsonify({"drone_id": drone_id, "latest": latest})

    @app.route("/api/drones/<drone_id>/telemetry")
    def get_telemetry(drone_id):
        db = app.config["storage"]
        limit = request.args.get("limit", 100, type=int)
        rows = db.get_telemetry(drone_id, limit=limit)
        return jsonify({"drone_id": drone_id, "telemetry": rows})

    @app.route("/api/drones/<drone_id>/command", methods=["POST"])
    @require_auth
    def send_command(drone_id):
        tcp = app.config["tcp_server"]
        body = request.get_json(silent=True) or {}
        cmd_type = body.get("type")

        if not cmd_type:
            return jsonify({"error": "missing 'type' field"}), 400
        if not tcp:
            return jsonify({"error": "command server unavailable"}), 503

        params = body.get("params", {})
        cmd_id = tcp.send_command(drone_id, cmd_type, params)
        if cmd_id is None:
            return jsonify({"error": "drone not connected"}), 404

        db = app.config["storage"]
        db.save_command(cmd_id, drone_id, cmd_type, params)

        ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"[{ts}] HTTP command sent to {drone_id}: {cmd_type} (cmd_id={cmd_id})")
        return jsonify({"cmd_id": cmd_id, "status": "sent"})

    @app.route("/api/alerts")
    def get_alerts():
        db = app.config["storage"]
        drone_id = request.args.get("drone_id")
        alerts = db.get_alerts(drone_id)
        return jsonify({"alerts": alerts})

    @app.route("/api/metrics")
    def get_metrics():
        result = {}
        tcp = app.config["tcp_server"]
        udp = app.config["udp_server"]
        if tcp:
            result["rtt"] = {
                "measurements": tcp.rtt.all(),
                "average_sec": tcp.rtt.average(),
            }
        if udp:
            result["throughput"] = udp.throughput.summary()
        return jsonify(result)

    return app
