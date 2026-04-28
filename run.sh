#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install stress
# sudo apt-get update
# sudo apt-get install -y stress

# Install pip
sudo apt install -y python3-pip

# Create venv
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -q -r requirements.txt

exec uvicorn app.main:app --host 0.0.0.0 --port 8000