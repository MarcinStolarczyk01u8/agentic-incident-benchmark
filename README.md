# Incident Simulation App

FastAPI app that triggers real system-level incidents on an EC2 instance so CloudWatch alarms fire and the AWS DevOps Agent can investigate them autonomously.

## Prerequisites

- Ubuntu 24.04, Python 3.11+
- `stress` installed: `sudo apt install -y stress`
- Port 8000 open in the EC2 security group

## Deploy on a fresh EC2

```bash
# 1. Clone
git clone <repo-url> ~/agentic-incident-benchmark
cd ~/agentic-incident-benchmark

# 2. Make run.sh executable
chmod +x run.sh

# 3. Install systemd service (for auto-restart after crash scenario)
sudo cp incident-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable incident-app
sudo systemctl start incident-app

# 4. Verify
sudo systemctl status incident-app
curl http://localhost:8000/health
```

The service restarts automatically within 3 seconds if the process crashes (crash scenario).

To run without systemd during development:
```bash
./run.sh
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Current time, uptime, active incident, CPU/RAM/disk % |
| GET | `/incidents/cpu` | Max-core CPU stress via `stress` for up to 12 min |
| GET | `/incidents/ram` | Allocate RAM until ~90% consumed, hold for up to 12 min |
| GET | `/incidents/disk` | Fill `/tmp/fill_disk` to ~95% disk, hold for up to 12 min |
| GET | `/incidents/crash` | SIGKILL self after 2 s (systemd restarts the service) |
| GET | `/incidents/bad_url` | Loop HTTP errors to a dead URL for up to 12 min |
| GET | `/reset` | Stop all incidents, free resources, return to clean state |

All incident endpoints return **202 Accepted** immediately (work runs in background).  
A second incident while one is active returns **409 Conflict** with the active incident name.  
All incidents auto-reset after **12 minutes** even if `/reset` is never called.

### Example curl commands

```bash
BASE=http://<EC2-PUBLIC-IP>:8000

# Health check
curl $BASE/health

# Trigger incidents
curl $BASE/incidents/cpu
curl $BASE/incidents/ram
curl $BASE/incidents/disk
curl $BASE/incidents/crash
curl $BASE/incidents/bad_url

# Reset to clean state
curl $BASE/reset

# Check status during an incident
curl $BASE/health | python3 -m json.tool
```

### Sample /health response

```json
{
  "time": "2026-04-20T02:15:00+00:00",
  "uptime_seconds": 3742,
  "active_incident": "cpu",
  "incident_running_seconds": 47,
  "cpu_percent": 99.8,
  "ram_percent": 23.1,
  "disk_percent": 18.4
}
```

## Notes

- **Disk incident**: `/tmp` on some Ubuntu images is a `tmpfs` mount (RAM-backed). If you need to fill a real EBS volume, change `DISK_FILE` in [app/incidents/disk.py](app/incidents/disk.py) to a path outside `/tmp`, e.g. `/var/tmp/fill_disk`.
- **Crash recovery**: After `GET /incidents/crash`, the process is killed with SIGKILL. systemd restarts it within 3 seconds. No `/reset` call is needed.
- **No authentication**: This app is intentionally unauthenticated. Restrict access via EC2 security groups.
- **Portability**: No AWS SDK calls in the app. The same code runs unchanged on Azure or any Linux VM.
