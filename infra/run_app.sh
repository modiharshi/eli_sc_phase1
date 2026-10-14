#!/usr/bin/env bash
# Start the ELI web app on 127.0.0.1:8000 (localhost only). Logs to logs/app.log.
cd "$(dirname "$0")/.." || exit 1
exec .venv/bin/python -m uvicorn api.app:app --host 127.0.0.1 --port "${ELI_PORT:-8000}" >> logs/app.log 2>&1
