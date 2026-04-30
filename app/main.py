import logging
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
from app.tasks import analytics, db_reload, migrate, notify, sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)


def _ensure_db_optimizations() -> None:
    if db_module.engine is None:
        return

    with db_module.engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id)"))


@asynccontextmanager
async def lifespan(_app):
    try:
        if db_module.engine is not None:
            Base.metadata.create_all(db_module.engine)
            _ensure_db_optimizations()
            logger.info("Database schema initialised")
        else:
            logger.warning("DATABASE_URL not set — skipping schema initialisation")
    except Exception as exc:
        logger.warning("Schema initialisation failed (DB may be unavailable): %s", exc)
    yield


app = FastAPI(title="Order Management Service", lifespan=lifespan)

_TASK_RUNNERS = {
    "notify": notify.run,
    "analytics": analytics.run,
    "sync": sync.run,
    "db_reload": db_reload.run,
    "migrate": migrate.run,
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

@app.get("/tasks/notify")
def task_notify():
    return _start_task("notify")


@app.get("/tasks/analytics")
def task_analytics():
    return _start_task("analytics")


@app.get("/tasks/sync")
def task_sync():
    return _start_task("sync")


@app.get("/tasks/migrate")
def task_migrate():
    return _start_task("migrate")


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
        state.active_task = None
        state.start_time = None

    logger.info("[MAINTENANCE] Reset complete — was running: %s", stopped)
    return {"status": "reset", "was_active": stopped}


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
