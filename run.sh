#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install stress
sudo apt-get update
sudo apt-get install -y stress


pip install -q -r requirements.txt

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
