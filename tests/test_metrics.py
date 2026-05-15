import time

import pytest

from src.common.metrics import RTTTracker, ThroughputTracker


class TestRTTTracker:
    def test_record_and_get_rtt(self):
        rtt = RTTTracker()
        rtt.start("cmd-1")
        time.sleep(0.05)
        rtt.finish("cmd-1")
        result = rtt.get("cmd-1")
        assert 0.04 < result < 0.2

    def test_get_unfinished_returns_none(self):
        rtt = RTTTracker()
        rtt.start("cmd-2")
        assert rtt.get("cmd-2") is None

    def test_get_unknown_returns_none(self):
        rtt = RTTTracker()
        assert rtt.get("nope") is None

    def test_average_rtt(self):
        rtt = RTTTracker()
        for i in range(3):
            key = f"c-{i}"
            rtt.start(key)
            time.sleep(0.02)
            rtt.finish(key)
        avg = rtt.average()
        assert avg is not None
        assert 0.01 < avg < 0.5

    def test_average_empty_returns_none(self):
        rtt = RTTTracker()
        assert rtt.average() is None

    def test_all_rtts(self):
        rtt = RTTTracker()
        for i in range(3):
            key = f"c-{i}"
            rtt.start(key)
            time.sleep(0.01)
            rtt.finish(key)
        results = rtt.all()
        assert len(results) == 3
        assert all(v > 0 for v in results.values())


class TestThroughputTracker:
    def test_record_bytes(self):
        tp = ThroughputTracker()
        tp.record(1024)
        tp.record(2048)
        assert tp.total_bytes == 3072

    def test_throughput_calculation(self):
        tp = ThroughputTracker()
        tp.record(1000)
        time.sleep(0.1)
        tp.record(1000)
        bps = tp.bytes_per_second()
        assert bps > 0

    def test_packet_count(self):
        tp = ThroughputTracker()
        for _ in range(5):
            tp.record(100)
        assert tp.packet_count == 5

    def test_reset(self):
        tp = ThroughputTracker()
        tp.record(500)
        tp.reset()
        assert tp.total_bytes == 0
        assert tp.packet_count == 0

    def test_summary(self):
        tp = ThroughputTracker()
        tp.record(1024)
        tp.record(2048)
        s = tp.summary()
        assert s["total_bytes"] == 3072
        assert s["packet_count"] == 2
        assert "bytes_per_second" in s
        assert "elapsed_sec" in s
