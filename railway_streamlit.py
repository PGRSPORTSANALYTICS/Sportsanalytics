#!/usr/bin/env python3
"""
railway_streamlit.py — Streamlit dashboard service for Railway.

Run this as a SEPARATE Railway service (same repo, different start command):
  Start command: python3 railway_streamlit.py

Railway exposes $PORT publicly. Streamlit binds to it.
Auto-restarts on crash via the supervisor loop.
"""
import os
import subprocess
import sys
import time
import signal

port = os.environ.get("PORT", "5000")

print(f"🚀 PGR Dashboard starting on port {port}", flush=True)


def start_streamlit():
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "pgr_dashboard.py",
            "--server.port", port,
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
        ],
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )


proc = start_streamlit()
restart_count = 0


def handle_exit(signum, frame):
    print("🛑 Shutdown signal received", flush=True)
    try:
        proc.terminate()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

while True:
    try:
        if proc.poll() is not None:
            restart_count += 1
            wait = min(60, restart_count * 10)
            print(
                f"⚠️ Streamlit exited (code {proc.returncode}), "
                f"restart #{restart_count} in {wait}s...",
                flush=True,
            )
            time.sleep(wait)
            proc = start_streamlit()
            print(f"✅ Streamlit restarted (attempt #{restart_count})", flush=True)
        time.sleep(10)
    except Exception as e:
        print(f"❌ Supervisor error: {e} — continuing...", flush=True)
        time.sleep(30)
