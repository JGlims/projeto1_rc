import time
import threading


class RTTTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}
        self._results = {}

    def start(self, cmd_id):
        with self._lock:
            self._pending[cmd_id] = time.time()

    def finish(self, cmd_id):
        with self._lock:
            start_time = self._pending.pop(cmd_id, None)
            if start_time is not None:
                self._results[cmd_id] = time.time() - start_time

    def get(self, cmd_id):
        with self._lock:
            return self._results.get(cmd_id)

    def average(self):
        with self._lock:
            if not self._results:
                return None
            return sum(self._results.values()) / len(self._results)

    def all(self):
        with self._lock:
            return dict(self._results)


class ThroughputTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        self.total_bytes = 0
        self.packet_count = 0

    def record(self, nbytes):
        with self._lock:
            self.total_bytes += nbytes
            self.packet_count += 1

    def bytes_per_second(self):
        with self._lock:
            elapsed = time.time() - self._start_time
            if elapsed <= 0:
                return 0.0
            return self.total_bytes / elapsed

    def reset(self):
        with self._lock:
            self._start_time = time.time()
            self.total_bytes = 0
            self.packet_count = 0

    def summary(self):
        with self._lock:
            elapsed = time.time() - self._start_time
            return {
                "total_bytes": self.total_bytes,
                "packet_count": self.packet_count,
                "elapsed_sec": round(elapsed, 3),
                "bytes_per_second": round(self.total_bytes / elapsed, 2) if elapsed > 0 else 0,
            }
