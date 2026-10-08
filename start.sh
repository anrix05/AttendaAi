#!/bin/bash
set -e

# Railway assigned public port (defaults to 8000 if not set)
PUBLIC_PORT="${PORT:-8000}"

# Handle standalone API mode if requested
if [ "${APP_MODE}" = "api" ] || [ "${APP_MODE}" = "backend" ]; then
    echo "[*] APP_MODE=${APP_MODE}: Launching FastAPI standalone on 0.0.0.0:${PUBLIC_PORT}..."
    exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PUBLIC_PORT}"
fi

# Full AttendAI deployment: FastAPI Backend + Streamlit Dashboard
echo "[*] Initializing AttendAI production services..."

# Determine internal backend port without colliding with Railway's PUBLIC_PORT
if [ "${PUBLIC_PORT}" = "8000" ]; then
    INTERNAL_BACKEND_PORT="8001"
else
    INTERNAL_BACKEND_PORT="${BACKEND_PORT:-8000}"
fi

export ATTENDAI_API_BASE="http://127.0.0.1:${INTERNAL_BACKEND_PORT}"
echo "[*] Configured ATTENDAI_API_BASE=${ATTENDAI_API_BASE}"

# Launch FastAPI backend on internal port
echo "[*] Launching FastAPI backend on 127.0.0.1:${INTERNAL_BACKEND_PORT}..."
python -m uvicorn backend.main:app --host 127.0.0.1 --port "${INTERNAL_BACKEND_PORT}" &
BACKEND_PID=$!

# Ensure backend process is cleaned up when this script exits
cleanup() {
    echo "[*] Shutting down backend process (PID ${BACKEND_PID})..."
    kill -TERM "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Health check verification: ensure FastAPI is healthy and running before starting frontend
echo "[*] Verifying FastAPI backend startup..."
MAX_RETRIES=30
COUNT=0
HEALTH_URL="http://127.0.0.1:${INTERNAL_BACKEND_PORT}/api/health"

until curl -sf "${HEALTH_URL}" > /dev/null 2>&1 || [ $COUNT -ge $MAX_RETRIES ]; do
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
        echo "[!] CRITICAL: FastAPI backend process died during startup!"
        wait "${BACKEND_PID}"
        exit 1
    fi
    sleep 1
    COUNT=$((COUNT + 1))
done

if [ $COUNT -ge $MAX_RETRIES ]; then
    echo "[!] ERROR: FastAPI backend failed to respond at ${HEALTH_URL} within ${MAX_RETRIES}s."
    exit 1
fi

echo "[+] FastAPI backend is online and healthy!"

# Launch Streamlit dashboard on Railway's public port
echo "[*] Launching Streamlit dashboard on public port ${PUBLIC_PORT}..."
exec python -m streamlit run frontend/app.py \
    --server.port "${PUBLIC_PORT}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
