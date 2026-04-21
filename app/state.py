import threading
import time


class IncidentState:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_incident: str | None = None
        self.stop_event: threading.Event = threading.Event()
        self.stress_proc = None  # subprocess.Popen, set by cpu incident
        self.ram_buffers: list = []  # bytearrays held to consume RAM
        self.start_time: float | None = None
        self.app_start_time: float = time.time()

    def begin(self, name: str) -> threading.Event:
        stop_ev = threading.Event()
        with self.lock:
            self.active_incident = name
            self.stop_event = stop_ev
            self.start_time = time.time()
        return stop_ev

    def clear_active(self, name: str) -> None:
        with self.lock:
            if self.active_incident == name:
                self.active_incident = None
                self.start_time = None


state = IncidentState()
