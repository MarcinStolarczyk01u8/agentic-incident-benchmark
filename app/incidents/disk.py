import logging
import os
import time

import psutil

from app.state import state

logger = logging.getLogger(__name__)

NAME = "disk"
DURATION = 1800  # 30-minute safety net
TARGET_PERCENT = 95.0
DISK_FILE = "/tmp/fill_disk"
CHUNK_SIZE = 100 * 1024 * 1024  # 100 MB per write


def run(stop_event):
    logger.info("[DISK] Writing to %s until %.0f%% disk full", DISK_FILE, TARGET_PERCENT)
    start = time.time()
    try:
        with open(DISK_FILE, "wb") as f:
            while not stop_event.is_set():
                usage = psutil.disk_usage(os.path.dirname(DISK_FILE) or "/")
                if usage.percent >= TARGET_PERCENT:
                    logger.info("[DISK] Reached %.1f%% disk usage", usage.percent)
                    break
                f.write(b"\x00" * CHUNK_SIZE)
                f.flush()
                logger.info(
                    "[DISK] Disk usage: %.1f%%",
                    psutil.disk_usage(os.path.dirname(DISK_FILE) or "/").percent,
                )

        remaining = max(0.0, DURATION - (time.time() - start))
        stop_event.wait(timeout=remaining)
    finally:
        try:
            os.remove(DISK_FILE)
            logger.info("[DISK] Deleted %s", DISK_FILE)
        except FileNotFoundError:
            pass
        state.clear_active(NAME)
        logger.info(
            "[DISK] Stopped — disk usage: %.1f%%",
            psutil.disk_usage(os.path.dirname(DISK_FILE) or "/").percent,
        )
