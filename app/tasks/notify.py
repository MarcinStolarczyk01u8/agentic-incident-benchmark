import logging
import time
import urllib.error
import urllib.request

from app.state import state

logger = logging.getLogger(__name__)

NAME = "notify"
DURATION = 1800
WEBHOOK_URL = "http://192.0.2.1/api/data"
WEBHOOK_TIMEOUT = 3
NOTIFY_INTERVAL = 10


def run(stop_event):
    logger.info("[NOTIFY] Starting customer notification dispatch to %s", WEBHOOK_URL)
    start = time.time()

    while not stop_event.is_set() and (time.time() - start) < DURATION:
        try:
            urllib.request.urlopen(WEBHOOK_URL, timeout=WEBHOOK_TIMEOUT)
            logger.warning("[NOTIFY] Unexpected response from %s", WEBHOOK_URL)
        except Exception as exc:
            logger.error(
                "[NOTIFY] %s Delivery failed to %s: %s",
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                WEBHOOK_URL,
                exc,
            )
        stop_event.wait(timeout=NOTIFY_INTERVAL)

    state.finish_task(NAME)
    logger.info("[NOTIFY] Stopped after %.0f seconds", time.time() - start)
