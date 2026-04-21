import logging
import os
import signal
import time

logger = logging.getLogger(__name__)

NAME = "crash"


def run(stop_event):
    logger.info("[CRASH] Will SIGKILL self in 2 seconds — systemd will restart the service")
    time.sleep(2)
    logger.info("[CRASH] Sending SIGKILL now")
    os.kill(os.getpid(), signal.SIGKILL)
    # Process dies here; state is reset by systemd restart
