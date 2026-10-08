"""
Root entrypoint for Railway and cloud deployments.
Supports both dual service (FastAPI + Streamlit) and standalone API modes.
"""
import os
import subprocess
import sys
import time
import urllib.request

def main():
    public_port = int(os.environ.get("PORT", "8000"))
    app_mode = os.environ.get("APP_MODE", "").lower()

    # 1. Standalone API mode
    if app_mode in ("api", "backend"):
        print(f"[*] APP_MODE={app_mode}: Launching FastAPI standalone on 0.0.0.0:{public_port}...", flush=True)
        cmd = [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", str(public_port),
        ]
        sys.exit(subprocess.run(cmd).returncode)

    # 2. Dual Mode: FastAPI Backend + Streamlit Dashboard
    print("[*] Initializing AttendAI production services (Dual Mode)...", flush=True)

    # Prevent port collision with Railway's public port
    if public_port == 8000:
        internal_backend_port = 8001
    else:
        internal_backend_port = int(os.environ.get("BACKEND_PORT", "8000"))

    api_base = f"http://127.0.0.1:{internal_backend_port}"
    os.environ["ATTENDAI_API_BASE"] = api_base
    print(f"[*] Configured ATTENDAI_API_BASE={api_base}", flush=True)

    print(f"[*] Launching FastAPI backend on 127.0.0.1:{internal_backend_port}...", flush=True)
    backend_proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", "127.0.0.1",
        "--port", str(internal_backend_port),
    ])

    try:
        # Health check probe before starting frontend
        print("[*] Verifying FastAPI backend startup...", flush=True)
        max_retries = 30
        healthy = False
        health_url = f"{api_base}/api/health"

        for _ in range(max_retries):
            if backend_proc.poll() is not None:
                print(f"[!] CRITICAL: FastAPI backend process died with exit code {backend_proc.returncode}!", flush=True)
                sys.exit(backend_proc.returncode or 1)

            try:
                with urllib.request.urlopen(health_url, timeout=2) as resp:
                    if resp.status == 200:
                        healthy = True
                        break
            except Exception:
                pass
            time.sleep(1)

        if not healthy:
            print(f"[!] ERROR: FastAPI backend failed to respond at {health_url} within {max_retries}s.", flush=True)
            backend_proc.terminate()
            sys.exit(1)

        print("[+] FastAPI backend is online and healthy!", flush=True)

        # Launch Streamlit on Railway's public port
        print(f"[*] Launching Streamlit dashboard on public port {public_port}...", flush=True)
        streamlit_cmd = [
            sys.executable, "-m", "streamlit", "run",
            "frontend/app.py",
            "--server.port", str(public_port),
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ]
        sys.exit(subprocess.run(streamlit_cmd).returncode)

    finally:
        if backend_proc.poll() is None:
            backend_proc.terminate()
            backend_proc.wait(timeout=5)

if __name__ == "__main__":
    main()
