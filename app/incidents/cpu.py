import logging
import os
import subprocess

from app.state import state

logger = logging.getLogger(__name__)

NAME = "cpu"
DURATION = 720  # 12-minute safety net


def run(stop_event):
    cores = os.cpu_count() or 1
    logger.info("[CPU] Starting stress --cpu %d", cores)
    proc = subprocess.Popen(["stress", "--cpu", str(cores)])
    with state.lock:
        state.stress_proc = proc
    try:
        stop_event.wait(timeout=DURATION)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        with state.lock:
            state.stress_proc = None
        state.clear_active(NAME)
        logger.info("[CPU] Stopped")
