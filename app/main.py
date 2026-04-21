import logging
import os
import threading
import time
from datetime import datetime, timezone

import psutil
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.state import state
from app.incidents import bad_url, cpu, crash, disk, ram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Incident Simulation App")

DISK_FILE = "/tmp/fill_disk"

_HANDLERS = {
    "cpu": cpu.run,
    "ram": ram.run,
    "disk": disk.run,
    "crash": crash.run,
    "bad_url": bad_url.run,
}


def _launch(name: str):
    with state.lock:
        if state.active_incident is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "incident_already_active",
                    "active_incident": state.active_incident,
                },
            )
        stop_ev = threading.Event()
        state.active_incident = name
        state.stop_event = stop_ev
        state.start_time = time.time()

    logger.info("[INCIDENT] Starting: %s", name)
    threading.Thread(target=_HANDLERS[name], args=(stop_ev,), daemon=True).start()
    return JSONResponse(status_code=202, content={"status": "started", "incident": name})


@app.get("/incidents/cpu")
def incident_cpu():
    return _launch("cpu")


@app.get("/incidents/ram")
def incident_ram():
    return _launch("ram")


@app.get("/incidents/disk")
def incident_disk():
    return _launch("disk")


@app.get("/incidents/crash")
def incident_crash():
    return _launch("crash")


@app.get("/incidents/bad_url")
def incident_bad_url():
    return _launch("bad_url")


@app.get("/reset")
def reset():
    with state.lock:
        stopped = state.active_incident
        state.stop_event.set()
        stress_proc = state.stress_proc
        state.stress_proc = None
        state.ram_buffers.clear()
        state.active_incident = None
        state.start_time = None

    # Terminate stress outside the lock (may block briefly on wait)
    if stress_proc is not None:
        try:
            stress_proc.terminate()
            stress_proc.wait(timeout=3)
        except Exception:
            stress_proc.kill()

    disk_deleted = False
    try:
        os.remove(DISK_FILE)
        disk_deleted = True
    except FileNotFoundError:
        pass

    logger.info("[RESET] Completed — was running: %s", stopped)
    return {
        "status": "reset",
        "was_active": stopped,
        "stress_killed": stress_proc is not None,
        "ram_freed": stopped == "ram",
        "disk_file_deleted": disk_deleted,
    }


@app.get("/health")
def health():
    with state.lock:
        active = state.active_incident
        start = state.start_time

    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time.time() - state.app_start_time),
        "active_incident": active,
        "incident_running_seconds": int(time.time() - start) if start else None,
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
    }
