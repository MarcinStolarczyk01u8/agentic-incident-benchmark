import logging
import time

import psutil

from app.state import state

logger = logging.getLogger(__name__)

NAME = "ram"
DURATION = 1800  # 30-minute safety net
TARGET_PERCENT = 90.0
CHUNK_MB = 50


def run(stop_event):
    logger.info("[RAM] Starting allocation to %.0f%% target", TARGET_PERCENT)
    start = time.time()
    chunk_size = CHUNK_MB * 1024 * 1024

    while not stop_event.is_set():
        if psutil.virtual_memory().percent >= TARGET_PERCENT:
            break
        with state.lock:
            state.ram_buffers.append(bytearray(chunk_size))
        logger.info(
            "[RAM] +%dMB allocated — total usage: %.1f%%",
            CHUNK_MB,
            psutil.virtual_memory().percent,
        )
        time.sleep(0.2)

    logger.info("[RAM] Holding at %.1f%% RAM", psutil.virtual_memory().percent)
    remaining = max(0.0, DURATION - (time.time() - start))
    stop_event.wait(timeout=remaining)

    with state.lock:
        state.ram_buffers.clear()
    state.clear_active(NAME)
    logger.info("[RAM] Released — usage now %.1f%%", psutil.virtual_memory().percent)
