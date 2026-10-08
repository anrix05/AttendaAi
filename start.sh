#!/bin/bash
set -e

# 1. Start FastAPI backend on 127.0.0.1:8000 in background
echo "[*] Launching FastAPI Backend on port 8000..."
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# 2. Wait briefly for FastAPI to initialize
sleep 3

# 3. Start Streamlit on Railway assigned public port ($PORT)
PORT="${PORT:-8501}"
echo "[*] Launching Streamlit Dashboard on port $PORT..."
exec python -m streamlit run frontend/app.py \
    --server.port "$PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
