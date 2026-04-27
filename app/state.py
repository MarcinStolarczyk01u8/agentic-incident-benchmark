import threading
import time


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.active_task: str | None = None
        self.stop_event: threading.Event = threading.Event()
        self.start_time: float | None = None
        self.app_start_time: float = time.time()

    def finish_task(self, name: str) -> None:
        with self.lock:
            if self.active_task == name:
                self.active_task = None
                self.start_time = None


state = AppState()
