import logging
import os
import time

import psutil

from app.state import state

logger = logging.getLogger(__name__)

NAME = "backup"
DURATION = 1800
TARGET_PERCENT = 95.0
BACKUP_FILE = "/tmp/backup_data"
CHUNK_SIZE = 100 * 1024 * 1024  # 100 MB per write


def run(stop_event):
    logger.info("[BACKUP] Writing backup to %s", BACKUP_FILE)
    start = time.time()
    try:
        with open(BACKUP_FILE, "wb") as f:
            while not stop_event.is_set():
                usage = psutil.disk_usage(os.path.dirname(BACKUP_FILE) or "/")
                if usage.percent >= TARGET_PERCENT:
                    logger.info("[BACKUP] Storage at %.1f%%, pausing writes", usage.percent)
                    break
                f.write(b"\x00" * CHUNK_SIZE)
                f.flush()
                logger.info(
                    "[BACKUP] Disk usage: %.1f%%",
                    psutil.disk_usage(os.path.dirname(BACKUP_FILE) or "/").percent,
                )

        remaining = max(0.0, DURATION - (time.time() - start))
        stop_event.wait(timeout=remaining)
    finally:
        try:
            os.remove(BACKUP_FILE)
            logger.info("[BACKUP] Removed %s", BACKUP_FILE)
        except FileNotFoundError:
            pass
        state.finish_task(NAME)
        logger.info(
            "[BACKUP] Stopped — disk usage: %.1f%%",
            psutil.disk_usage(os.path.dirname(BACKUP_FILE) or "/").percent,
        )
