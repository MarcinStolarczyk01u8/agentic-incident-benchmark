import logging
import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.database as db_module
from app.state import state

logger = logging.getLogger(__name__)

NAME = "db_reload"
DURATION = 1800
HEALTH_CHECK_INTERVAL = 3
STANDBY_URL = "postgresql://user:pass@192.0.2.1:5432/db"


def run(stop_event):
    original_url = os.environ.get("DATABASE_URL")

    logger.info("[DB_RELOAD] Reloading database configuration")
    old_engine = db_module.engine
    if old_engine is not None:
        old_engine.dispose()

    standby_engine = create_engine(
        STANDBY_URL,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        pool_pre_ping=False,
        connect_args={"connect_timeout": 3},
    )
    db_module.engine = standby_engine
    db_module.SessionLocal = sessionmaker(standby_engine)

    start = time.time()
    while not stop_event.is_set() and (time.time() - start) < DURATION:
        try:
            with standby_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("[DB_RELOAD] Standby reachable")
        except Exception as exc:
            logger.error("[DB_RELOAD] Standby unreachable: %s", exc)
        stop_event.wait(timeout=HEALTH_CHECK_INTERVAL)

    logger.info("[DB_RELOAD] Restoring primary database connection")
    standby_engine.dispose()

    if original_url:
        primary = create_engine(
            original_url,
            pool_size=10,
            max_overflow=5,
            pool_timeout=30,
            pool_pre_ping=True,
        )
        db_module.engine = primary
        db_module.SessionLocal = sessionmaker(primary)
        logger.info("[DB_RELOAD] Primary connection restored")
    else:
        db_module.engine = None
        db_module.SessionLocal = None
        logger.warning("[DB_RELOAD] DATABASE_URL not set — connection left as None")

    state.finish_task(NAME)
    logger.info("[DB_RELOAD] Stopped")
