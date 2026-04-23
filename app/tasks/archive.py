import logging
import os
import random
import string
import time

from sqlalchemy import text

import app.database as db_module
from app.models import Order
from app.state import state

logger = logging.getLogger(__name__)

NAME = "archive"
DURATION = 1800
ARCHIVE_BATCH_SIZE = 100
MAX_DB_SIZE_MB = int(os.environ.get("MAX_DB_SIZE_MB", 1000))
SIZE_CHECK_INTERVAL = 10


def _archive_record_name(length=500):
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def run(stop_event):
    if db_module.SessionLocal is None:
        logger.error("[ARCHIVE] Database unavailable, aborting")
        state.finish_task(NAME)
        return

    logger.info("[ARCHIVE] Starting order archive — storage limit: %d MB", MAX_DB_SIZE_MB)
    archived = 0
    last_check = time.time()
    start = time.time()

    while not stop_event.is_set() and (time.time() - start) < DURATION:
        db = db_module.SessionLocal()
        try:
            batch = [
                {
                    "user_id": random.randint(1, 1000),
                    "product_name": _archive_record_name(),
                    "quantity": random.randint(1, 10),
                    "total_price": round(random.uniform(1.0, 1000.0), 2),
                    "status": "archived",
                }
                for _ in range(ARCHIVE_BATCH_SIZE)
            ]
            db.bulk_insert_mappings(Order, batch)
            db.commit()
            archived += ARCHIVE_BATCH_SIZE

            now = time.time()
            if now - last_check >= SIZE_CHECK_INTERVAL:
                row = db.execute(
                    text("SELECT pg_database_size(current_database()) / (1024*1024.0)")
                ).fetchone()
                size_mb = float(row[0]) if row else 0.0
                logger.info(
                    "[ARCHIVE] %d records archived — storage: %.1f / %d MB",
                    archived, size_mb, MAX_DB_SIZE_MB,
                )
                last_check = now
                if size_mb >= MAX_DB_SIZE_MB * 0.9:
                    logger.warning(
                        "[ARCHIVE] Storage limit approaching (%.1f MB), pausing archive",
                        size_mb,
                    )
                    break
        except Exception as exc:
            logger.error("[ARCHIVE] Write error: %s", exc)
            db.rollback()
        finally:
            db.close()

    try:
        with db_module.engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE orders"))
            conn.commit()
        logger.info("[ARCHIVE] Archive table cleared")
    except Exception as exc:
        logger.error("[ARCHIVE] Cleanup error: %s", exc)

    state.finish_task(NAME)
    logger.info("[ARCHIVE] Stopped")
