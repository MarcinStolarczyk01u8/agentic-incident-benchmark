import threading
import time


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_task: str | None = None
        self.stop_event: threading.Event = threading.Event()
        self.background_proc = None  # subprocess.Popen, set by export task
        self.memory_cache: list = []  # bytearrays held during warmup task
        self.start_time: float | None = None
        self.app_start_time: float = time.time()

    def start_task(self, name: str) -> threading.Event:
        stop_ev = threading.Event()
        with self.lock:
            self.active_task = name
            self.stop_event = stop_ev
            self.start_time = time.time()
        return stop_ev

    def finish_task(self, name: str) -> None:
        with self.lock:
            if self.active_task == name:
                self.active_task = None
                self.start_time = None


state = AppState()
