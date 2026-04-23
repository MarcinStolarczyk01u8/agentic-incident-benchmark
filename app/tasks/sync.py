import logging
import threading

from sqlalchemy import text

import app.database as db_module
from app.state import state

logger = logging.getLogger(__name__)

NAME = "sync"
DURATION = 1800
SYNC_WORKERS = 20
WORKER_TIMEOUT = 300

_worker_conns = []
_workers_lock = threading.Lock()


def _run_worker(worker_id):
    conn = None
    pconn = None
    try:
        conn = db_module.engine.connect()
        pconn = conn.connection.driver_connection
        with _workers_lock:
            _worker_conns.append(pconn)
        logger.info("[SYNC] Worker %d: connected, waiting for warehouse lock", worker_id)
        conn.execute(text(f"SELECT pg_sleep({WORKER_TIMEOUT})"))
        logger.info("[SYNC] Worker %d: lock released", worker_id)
    except Exception as exc:
        logger.error("[SYNC] Worker %d: %s", worker_id, exc)
    finally:
        if pconn is not None:
            with _workers_lock:
                if pconn in _worker_conns:
                    _worker_conns.remove(pconn)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        logger.info("[SYNC] Worker %d: done", worker_id)


def run(stop_event):
    if db_module.engine is None:
        logger.error("[SYNC] Database unavailable, aborting")
        state.finish_task(NAME)
        return

    with _workers_lock:
        _worker_conns.clear()

    try:
        pool_cap = db_module.engine.pool.size() + db_module.engine.pool._max_overflow
    except AttributeError:
        pool_cap = "?"

    logger.info("[SYNC] Spawning %d sync workers (pool capacity: %s)", SYNC_WORKERS, pool_cap)
    for i in range(SYNC_WORKERS):
        threading.Thread(target=_run_worker, args=(i,), daemon=True).start()

    stop_event.wait(timeout=DURATION)

    logger.info("[SYNC] Stopping — signalling %d workers", len(_worker_conns))
    with _workers_lock:
        for pconn in list(_worker_conns):
            try:
                pconn.cancel()
            except Exception as exc:
                logger.warning("[SYNC] Worker signal failed: %s", exc)

    state.finish_task(NAME)
    logger.info("[SYNC] Stopped")
