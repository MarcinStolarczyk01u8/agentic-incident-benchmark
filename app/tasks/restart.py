import logging
import os
import signal
import time

logger = logging.getLogger(__name__)

NAME = "restart"


def run(stop_event):
    logger.info("[RESTART] Worker restart scheduled in 2 seconds")
    time.sleep(2)
    logger.info("[RESTART] Restarting worker process now")
    os.kill(os.getpid(), signal.SIGKILL)
