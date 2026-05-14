import json
import time
import uuid

TELEMETRY_FIELDS = ("drone_id", "ts", "lat", "lon", "alt", "speed", "battery", "status")
COMMAND_FIELDS = ("cmd_id", "type", "params", "ts")
ACK_FIELDS = ("cmd_id", "status", "ts")


def _decode(raw):
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return raw


def _parse(raw, required_fields):
    try:
        data = json.loads(_decode(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}")
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"missing fields: {missing}")
    return data


def build_telemetry_packet(drone_id, lat, lon, alt, speed, battery, status):
    return json.dumps({
        "drone_id": drone_id,
        "ts": time.time(),
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "speed": speed,
        "battery": battery,
        "status": status,
    })


def parse_telemetry_packet(raw):
    return _parse(raw, TELEMETRY_FIELDS)


def build_command_packet(cmd_type, params=None):
    return json.dumps({
        "cmd_id": uuid.uuid4().hex[:8],
        "type": cmd_type,
        "params": params or {},
        "ts": time.time(),
    })


def parse_command_packet(raw):
    return _parse(raw, COMMAND_FIELDS)


def build_ack_packet(cmd_id, status):
    return json.dumps({
        "cmd_id": cmd_id,
        "status": status,
        "ts": time.time(),
    })


def parse_ack_packet(raw):
    return _parse(raw, ACK_FIELDS)
