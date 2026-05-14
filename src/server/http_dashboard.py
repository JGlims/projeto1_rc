import json
import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template

logger = logging.getLogger(__name__)


def create_app(storage, tcp_server=None):
    app = Flask(
        __name__,
        template_folder="../dashboard/templates",
        static_folder="../dashboard/static",
    )
    app.config["storage"] = storage
    app.config["tcp_server"] = tcp_server

    @app.route("/")
    def index():
        return render_template("index.html")

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

    return app
