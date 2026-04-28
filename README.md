# Order Management Service

FastAPI backend for managing customer orders, running background jobs, and maintaining service health on AWS EC2.

## Prerequisites

- Ubuntu 24.04, Python 3.11+
- `stress` package: `sudo apt install -y stress`
- Port 8000 open in the EC2 security group
- PostgreSQL RDS instance accessible from the EC2

## Deploy on a fresh EC2

```bash
# 1. Clone
git clone <repo-url> ~/agentic-incident-benchmark
cd ~/agentic-incident-benchmark

# 2. Make run.sh executable
chmod +x run.sh

# 3. Install systemd service
sudo cp incident-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable incident-app
sudo systemctl start incident-app

# 4. Verify
sudo systemctl status incident-app
curl http://localhost:8000/health
```

The service restarts automatically within 3 seconds if the process exits unexpectedly.

To run without systemd during development:
```bash
export DATABASE_URL=postgresql://user:password@your-rds-endpoint:5432/dbname
./run.sh
```

## Database

The service connects to PostgreSQL via the `DATABASE_URL` environment variable:

```
DATABASE_URL=postgresql://user:password@rds-endpoint:5432/dbname
```

Schema is created automatically on startup. If the database is unreachable at startup, the service still starts and all non-database endpoints remain available.

Verify database connectivity:
```bash
curl http://localhost:8000/health | python3 -m json.tool
# "db_connected": true
```

`DATABASE_URL` must be exported in the EC2 environment before starting the service.

## Endpoints

### Health & maintenance

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health, resource usage, DB pool stats |
| GET | `/maintenance/reset` | Stop all running background tasks and free resources |
| GET | `/maintenance/reload` | Reload database configuration |

### Background tasks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks/notify` | Dispatch customer notifications via webhook |
| GET | `/tasks/analytics` | Run aggregated sales analytics report |
| GET | `/tasks/sync` | Sync order data with the warehouse system |
| GET | `/tasks/migrate` | Run legacy data migration |

### Orders

| Method | Path | Description |
|--------|------|-------------|
| POST | `/orders` | Create a new order |
| GET | `/orders/{user_id}` | List all orders for a user |
| DELETE | `/orders/all` | Truncate the orders table |

All background task endpoints return **202 Accepted** immediately; work runs in a background thread. Only one task runs at a time — a second request while one is active returns **409 Conflict**.

## Example curl commands

```bash
BASE=http://<EC2-PUBLIC-IP>:8000

# Health check
curl $BASE/health | python3 -m json.tool

# Background tasks
curl $BASE/tasks/notify
curl $BASE/tasks/analytics
curl $BASE/tasks/sync
curl $BASE/tasks/migrate

# Maintenance
curl $BASE/maintenance/reload
curl $BASE/maintenance/reset

# Orders
curl -X POST "$BASE/orders?user_id=1&product_name=widget&quantity=2&total_price=9.99"
curl "$BASE/orders/1"
curl -X DELETE "$BASE/orders/all"
```

## Sample /health response

```json
{
  "time": "2026-04-20T02:15:00+00:00",
  "uptime_seconds": 3742,
  "active_task": null,
  "task_running_seconds": null,
  "cpu_percent": 12.4,
  "ram_percent": 23.1,
  "disk_percent": 18.4,
  "db_connected": true,
  "db_pool_size": 10,
  "db_pool_checked_out": 1,
  "db_size_mb": 42.3
}
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes (for DB endpoints) | — | PostgreSQL connection string |
| `MAX_DB_SIZE_MB` | No | `1000` | Storage ceiling for the archive task |

## Notes

- **No authentication**: Access is controlled via EC2 security groups.
- **Database unavailable**: If `DATABASE_URL` is not set, DB-dependent endpoints return `503 Database not configured`. All other endpoints work normally.
