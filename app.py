"""
Root entrypoint for Railway and cloud deployments.
Automatically launches FastAPI backend on 127.0.0.1:8000 and Streamlit on $PORT.
"""
import os
import subprocess
import sys
import time

def main():
    # 1. Start FastAPI backend in background on port 8000
    print("[*] Starting AttendAI Backend (FastAPI) on 127.0.0.1:8000...", flush=True)
    backend_proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ])

    # Allow FastAPI to initialize
    time.sleep(3)

    # 2. Start Streamlit on the public port assigned by Railway ($PORT)
    port = os.environ.get("PORT", "8501")
    print(f"[*] Starting AttendAI Dashboard (Streamlit) on port {port}...", flush=True)
    streamlit_cmd = [
        sys.executable, "-m", "streamlit", "run",
        "frontend/app.py",
        "--server.port", str(port),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    ]
    try:
        subprocess.run(streamlit_cmd)
    finally:
        backend_proc.terminate()

if __name__ == "__main__":
    main()
