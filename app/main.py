import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import psutil
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.database as db_module
from app.database import get_db, Base
from app.models import Order
from app.state import state
from app.tasks import analytics, archive, backup, db_reload, export, notify, restart, sync, warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

BACKUP_FILE = "/tmp/backup_data"


@asynccontextmanager
async def lifespan(_app):
    try:
        if db_module.engine is not None:
            Base.metadata.create_all(db_module.engine)
            logger.info("Database schema initialised")
        else:
            logger.warning("DATABASE_URL not set — skipping schema initialisation")
    except Exception as exc:
        logger.warning("Schema initialisation failed (DB may be unavailable): %s", exc)
    yield


app = FastAPI(title="Order Management Service", lifespan=lifespan)

_TASK_RUNNERS = {
    "export": export.run,
    "warmup": warmup.run,
    "backup": backup.run,
    "restart": restart.run,
    "notify": notify.run,
    "analytics": analytics.run,
    "sync": sync.run,
    "db_reload": db_reload.run,
    "archive": archive.run,
}


def _start_task(name: str):
    with state.lock:
        if state.active_task is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "task_already_running",
                    "active_task": state.active_task,
                },
            )
        stop_ev = threading.Event()
        state.active_task = name
        state.stop_event = stop_ev
        state.start_time = time.time()

    logger.info("[TASK] Starting: %s", name)
    threading.Thread(target=_TASK_RUNNERS[name], args=(stop_ev,), daemon=True).start()
    return JSONResponse(status_code=202, content={"status": "started", "task": name})


# ── Background task endpoints ──────────────────────────────────────────────────

@app.get("/tasks/export")
def task_export():
    return _start_task("export")


@app.get("/tasks/warmup")
def task_warmup():
    return _start_task("warmup")


@app.get("/tasks/backup")
def task_backup():
    return _start_task("backup")


@app.get("/tasks/notify")
def task_notify():
    return _start_task("notify")


@app.get("/tasks/analytics")
def task_analytics():
    return _start_task("analytics")


@app.get("/tasks/sync")
def task_sync():
    return _start_task("sync")


@app.get("/tasks/archive")
def task_archive():
    return _start_task("archive")


@app.get("/maintenance/restart")
def maintenance_restart():
    return _start_task("restart")


@app.get("/maintenance/reload")
def maintenance_reload():
    return _start_task("db_reload")


# ── Orders CRUD ────────────────────────────────────────────────────────────────

@app.post("/orders", status_code=201)
def create_order(
    user_id: int,
    product_name: str,
    quantity: int,
    total_price: float,
    db: Session = Depends(get_db),
):
    order = Order(
        user_id=user_id,
        product_name=product_name,
        quantity=quantity,
        total_price=total_price,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"id": order.id, "status": "created"}


@app.get("/orders/{user_id}")
def get_orders(user_id: int, db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == user_id).all()
    return [
        {
            "id": o.id,
            "user_id": o.user_id,
            "product_name": o.product_name,
            "quantity": o.quantity,
            "total_price": o.total_price,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


@app.delete("/orders/all")
def delete_all_orders(db: Session = Depends(get_db)):
    db.query(Order).delete()
    db.commit()
    return {"status": "deleted", "table": "orders"}


# ── Maintenance ────────────────────────────────────────────────────────────────

@app.get("/maintenance/reset")
def maintenance_reset():
    with state.lock:
        stopped = state.active_task
        state.stop_event.set()
        background_proc = state.background_proc
        state.background_proc = None
        state.memory_cache.clear()
        state.active_task = None
        state.start_time = None

    if background_proc is not None:
        try:
            background_proc.terminate()
            background_proc.wait(timeout=3)
        except Exception:
            background_proc.kill()

    backup_deleted = False
    try:
        os.remove(BACKUP_FILE)
        backup_deleted = True
    except FileNotFoundError:
        pass

    logger.info("[MAINTENANCE] Reset complete — was running: %s", stopped)
    return {
        "status": "reset",
        "was_active": stopped,
        "worker_stopped": background_proc is not None,
        "cache_cleared": stopped == "warmup",
        "backup_deleted": backup_deleted,
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    with state.lock:
        active = state.active_task
        start = state.start_time

    db_health = {
        "db_connected": False,
        "db_pool_size": None,
        "db_pool_checked_out": None,
        "db_size_mb": None,
    }
    try:
        eng = db_module.engine
        if eng is not None:
            pool = eng.pool
            db_health["db_pool_size"] = pool.size()
            db_health["db_pool_checked_out"] = pool.checkedout()
            with eng.connect() as conn:
                row = conn.execute(
                    text("SELECT pg_database_size(current_database()) / (1024*1024.0)")
                ).fetchone()
                db_health["db_size_mb"] = round(float(row[0]), 1) if row else None
            db_health["db_connected"] = True
    except Exception:
        pass

    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time.time() - state.app_start_time),
        "active_task": active,
        "task_running_seconds": int(time.time() - start) if start else None,
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        **db_health,
    }
