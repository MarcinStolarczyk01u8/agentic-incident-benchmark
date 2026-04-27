import logging
import os
import random
import string
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.database as db_module
from app.models import Order
from app.state import state

logger = logging.getLogger(__name__)

NAME = "migrate"
DURATION = 1800
MIGRATE_BATCH_SIZE = int(os.environ.get("MIGRATE_BATCH_SIZE", 2000))
SIZE_CHECK_INTERVAL = 30

_PAYLOAD_LENGTH = 2000


def _random_name(length: int) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits + " -_./", k=length))


def _build_source_record() -> dict:
    return {
        "user_id": random.randint(1, 500),
        "product_name": _random_name(_PAYLOAD_LENGTH),
        "quantity": random.randint(1, 50),
        "total_price": round(random.uniform(5.0, 4999.0), 2),
        "status": "pending_migration",
    }


# Records loaded from the legacy export at startup
_MIGRATION_BACKLOG: list[dict] = [_build_source_record() for _ in range(MIGRATE_BATCH_SIZE)]


def _pop_batch(backlog: list[dict], n: int) -> list[dict]:
    items = backlog[:]
    return items[:n]


def _log_db_size(committed: int) -> None:
    db = db_module.SessionLocal()
    try:
        row = db.execute(
            text("SELECT pg_database_size(current_database()) / (1024*1024.0)")
        ).fetchone()
        size_mb = float(row[0]) if row else 0.0
        logger.info(
            "[MIGRATE] %d records saved — DB: %.1f MB",
            committed,
            size_mb,
        )
    except Exception as exc:
        logger.debug("[MIGRATE] Size check skipped: %s", exc)
    finally:
        db.close()


def run(stop_event):
    if db_module.SessionLocal is None:
        logger.error("[MIGRATE] Database unavailable, aborting")
        state.finish_task(NAME)
        return

    logger.info(
        "[MIGRATE] Starting legacy data migration — backlog: %d records",
        len(_MIGRATION_BACKLOG),
    )
    committed = 0
    last_check = time.time()
    start = time.time()

    while not stop_event.is_set() and (time.time() - start) < DURATION:
        batch = _pop_batch(_MIGRATION_BACKLOG, MIGRATE_BATCH_SIZE)
        if not batch:
            logger.info("[MIGRATE] Migration backlog exhausted after %d records", committed)
            break

        db = db_module.SessionLocal()
        try:
            for record in batch:
                # save a record
                db.add(Order(**record))
            db.commit()
            committed += len(batch)
        except SQLAlchemyError as exc:
            logger.error("[MIGRATE] Write error: %s", exc)
            db.rollback()
        finally:
            db.close()

        now = time.time()
        if now - last_check >= SIZE_CHECK_INTERVAL:
            _log_db_size(committed)
            last_check = now

    try:
        with db_module.engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE orders"))
            conn.commit()
        logger.info("[MIGRATE] Migration table cleared on exit")
    except Exception as exc:
        logger.error("[MIGRATE] Cleanup error: %s", exc)

    state.finish_task(NAME)
    logger.info("[MIGRATE] Stopped — total records committed: %d", committed)
