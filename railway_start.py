#!/usr/bin/env python3
"""
Railway Start Script
Runs both the API server (with dashboard) and the prediction engine.
Never exits — restarts subprocesses indefinitely on crash.
"""
import subprocess
import sys
import os
import time
import signal

port = os.environ.get("PORT", "8000")

print(f"🚀 Railway Start: API on port {port} + Prediction Engine", flush=True)

def start_api():
    return subprocess.Popen([
        sys.executable, "-m", "uvicorn", "api:app",
        "--host", "0.0.0.0", "--port", port
    ])

def start_engine():
    return subprocess.Popen([
        sys.executable, "combined_sports_runner.py"
    ])

api_process = start_api()
time.sleep(5)
engine_process = start_engine()

engine_restart_count = 0
api_restart_count = 0

def handle_exit(signum, frame):
    print("🛑 Received shutdown signal", flush=True)
    try:
        api_process.terminate()
        engine_process.terminate()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

while True:
    try:
        if api_process.poll() is not None:
            api_restart_count += 1
            print(f"⚠️ API server exited (code {api_process.returncode}), restart #{api_restart_count}...", flush=True)
            time.sleep(min(30, api_restart_count * 5))
            api_process = start_api()

        if engine_process.poll() is not None:
            engine_restart_count += 1
            wait = min(120, engine_restart_count * 10)
            print(f"⚠️ Engine exited (code {engine_process.returncode}), restart #{engine_restart_count} in {wait}s...", flush=True)
            time.sleep(wait)
            engine_process = start_engine()
            print(f"✅ Engine restarted (attempt #{engine_restart_count})", flush=True)

        time.sleep(15)

    except Exception as e:
        print(f"❌ Supervisor error: {e} — continuing...", flush=True)
        time.sleep(30)
