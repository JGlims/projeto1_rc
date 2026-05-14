import json
import time
from src.common.protocol import (
    build_telemetry_packet,
    parse_telemetry_packet,
    build_command_packet,
    parse_command_packet,
    build_ack_packet,
    parse_ack_packet,
)


class TestTelemetryPacket:
    def test_build_contains_required_fields(self):
        pkt = build_telemetry_packet(
            drone_id="DRONE-01",
            lat=-15.7631,
            lon=-47.8729,
            alt=120.5,
            speed=12.3,
            battery=87.2,
            status="flying",
        )
        data = json.loads(pkt)
        assert data["drone_id"] == "DRONE-01"
        assert data["lat"] == -15.7631
        assert data["lon"] == -47.8729
        assert data["alt"] == 120.5
        assert data["speed"] == 12.3
        assert data["battery"] == 87.2
        assert data["status"] == "flying"
        assert "ts" in data

    def test_build_timestamp_is_recent(self):
        before = time.time()
        pkt = build_telemetry_packet("DRONE-01", 0, 0, 0, 0, 100, "idle")
        after = time.time()
        ts = json.loads(pkt)["ts"]
        assert before <= ts <= after

    def test_parse_roundtrip(self):
        pkt = build_telemetry_packet("DRONE-02", -15.0, -47.0, 50.0, 5.0, 90.0, "hovering")
        parsed = parse_telemetry_packet(pkt)
        assert parsed["drone_id"] == "DRONE-02"
        assert parsed["alt"] == 50.0
        assert parsed["status"] == "hovering"

    def test_parse_returns_bytes_input(self):
        pkt = build_telemetry_packet("DRONE-01", 0, 0, 0, 0, 100, "idle")
        parsed = parse_telemetry_packet(pkt.encode("utf-8"))
        assert parsed["drone_id"] == "DRONE-01"

    def test_parse_invalid_json_raises(self):
        import pytest
        with pytest.raises(ValueError):
            parse_telemetry_packet("not json{{{")

    def test_parse_missing_field_raises(self):
        import pytest
        incomplete = json.dumps({"drone_id": "DRONE-01", "ts": time.time()})
        with pytest.raises(ValueError):
            parse_telemetry_packet(incomplete)


class TestCommandPacket:
    def test_build_land_command(self):
        pkt = build_command_packet(cmd_type="LAND")
        data = json.loads(pkt)
        assert data["type"] == "LAND"
        assert data["params"] == {}
        assert "cmd_id" in data
        assert "ts" in data

    def test_build_with_params(self):
        pkt = build_command_packet(cmd_type="MOVE", params={"lat": -15.0, "lon": -47.0})
        data = json.loads(pkt)
        assert data["type"] == "MOVE"
        assert data["params"]["lat"] == -15.0

    def test_cmd_id_is_unique(self):
        pkt1 = build_command_packet("HOVER")
        pkt2 = build_command_packet("HOVER")
        assert json.loads(pkt1)["cmd_id"] != json.loads(pkt2)["cmd_id"]

    def test_parse_roundtrip(self):
        pkt = build_command_packet("RTH", params={"urgency": "high"})
        parsed = parse_command_packet(pkt)
        assert parsed["type"] == "RTH"
        assert parsed["params"]["urgency"] == "high"

    def test_parse_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            parse_command_packet("{bad")


class TestAckPacket:
    def test_build_ack(self):
        pkt = build_ack_packet(cmd_id="abc123", status="ACK")
        data = json.loads(pkt)
        assert data["cmd_id"] == "abc123"
        assert data["status"] == "ACK"
        assert "ts" in data

    def test_build_nack(self):
        pkt = build_ack_packet(cmd_id="xyz", status="NACK")
        data = json.loads(pkt)
        assert data["status"] == "NACK"

    def test_parse_roundtrip(self):
        pkt = build_ack_packet("cmd-999", "ACK")
        parsed = parse_ack_packet(pkt)
        assert parsed["cmd_id"] == "cmd-999"
        assert parsed["status"] == "ACK"

    def test_parse_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            parse_ack_packet("garbage")
