import logging
import random
import time

from sqlalchemy import text

import app.database as db_module
from app.models import Order
from app.state import state

logger = logging.getLogger(__name__)

NAME = "analytics"
DURATION = 1800
REPORT_BATCH_SIZE = 1000
REPORT_SAMPLE_SIZE = 1_000_000
SAMPLE_INTERVAL = 0
REPORT_WINDOW_SECONDS = 600


def run(stop_event):
    if db_module.SessionLocal is None:
        logger.error("[ANALYTICS] Database unavailable, aborting")
        state.finish_task(NAME)
        return

    logger.info("[ANALYTICS] Seeding %d order records for report...", REPORT_SAMPLE_SIZE)
    db = db_module.SessionLocal()
    try:
        seeded = 0
        while seeded < REPORT_SAMPLE_SIZE and not stop_event.is_set():
            batch_size = min(REPORT_BATCH_SIZE, REPORT_SAMPLE_SIZE - seeded)
            batch = [
                {
                    "user_id": random.randint(1, 1000),
                    "product_name": f"product_{random.randint(1, 10000)}",
                    "quantity": random.randint(1, 10),
                    "total_price": round(random.uniform(1.0, 1000.0), 2),
                    "status": "pending",
                }
                for _ in range(batch_size)
            ]
            db.bulk_insert_mappings(Order, batch)
            db.commit()
            seeded += batch_size
            logger.info("[ANALYTICS] Seeded %d / %d records", seeded, REPORT_SAMPLE_SIZE)
    finally:
        db.close()

    if stop_event.is_set():
        state.finish_task(NAME)
        logger.info("[ANALYTICS] Stopped during seeding")
        return

    logger.info("[ANALYTICS] Running report aggregation for %d seconds", REPORT_WINDOW_SECONDS)
    start = time.time()
    while not stop_event.is_set() and (time.time() - start) < REPORT_WINDOW_SECONDS:
        db = db_module.SessionLocal()
        try:
            t0 = time.time()
            db.execute(
                text("""
                    SELECT user_id, COUNT(*) AS order_count,
                           SUM(total_price) AS revenue,
                           AVG(total_price) AS avg_order
                    FROM orders
                    GROUP BY user_id
                    ORDER BY revenue DESC
                """)
            ).fetchall()
            logger.info("[ANALYTICS] full aggregation took %.3fs", time.time() - t0)
        except Exception as exc:
            logger.error("[ANALYTICS] Query error: %s", exc)
        finally:
            db.close()
        stop_event.wait(timeout=SAMPLE_INTERVAL)

    try:
        with db_module.engine.connect() as conn:
            conn.execute(text("DELETE FROM orders"))
            conn.commit()
        logger.info("[ANALYTICS] Report dataset cleared")
    except Exception as exc:
        logger.error("[ANALYTICS] Cleanup error: %s", exc)

    state.finish_task(NAME)
    logger.info("[ANALYTICS] Stopped")
