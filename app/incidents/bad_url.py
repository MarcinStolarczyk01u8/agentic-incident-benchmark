import logging
import time
import urllib.error
import urllib.request

from app.state import state

logger = logging.getLogger(__name__)

NAME = "bad_url"
DURATION = 1800  # 30-minute safety net
TARGET_URL = "http://192.0.2.1/api/data"  # TEST-NET, guaranteed unreachable
REQUEST_TIMEOUT = 3
REQUEST_INTERVAL = 10


def run(stop_event):
    logger.info("[BAD_URL] Starting failed-request loop to %s", TARGET_URL)
    start = time.time()

    while not stop_event.is_set() and (time.time() - start) < DURATION:
        try:
            urllib.request.urlopen(TARGET_URL, timeout=REQUEST_TIMEOUT)
            logger.warning("[BAD_URL] Unexpected success reaching %s", TARGET_URL)
        except Exception as exc:
            logger.error(
                "[BAD_URL] %s ERROR connecting to %s: %s",
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                TARGET_URL,
                exc,
            )
        stop_event.wait(timeout=REQUEST_INTERVAL)

    state.clear_active(NAME)
    logger.info("[BAD_URL] Stopped after %.0f seconds", time.time() - start)
