import logging
import os
import subprocess

from app.state import state

logger = logging.getLogger(__name__)

NAME = "export"
DURATION = 1800


def run(stop_event):
    cores = os.cpu_count() or 1
    logger.info("[EXPORT] Starting data export on %d workers", cores)
    proc = subprocess.Popen(["stress", "--cpu", str(cores)])
    with state.lock:
        state.background_proc = proc
    try:
        stop_event.wait(timeout=DURATION)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        with state.lock:
            state.background_proc = None
        state.finish_task(NAME)
        logger.info("[EXPORT] Stopped")
