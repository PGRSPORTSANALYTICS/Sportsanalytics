#!/usr/bin/env python3
"""
Railway Start Script
Runs both the API server (with dashboard) and the prediction engine.
"""
import subprocess
import sys
import os
import time

port = os.environ.get("PORT", "8000")

api_process = subprocess.Popen([
    sys.executable, "-m", "uvicorn", "api:app",
    "--host", "0.0.0.0", "--port", port
])

time.sleep(3)

engine_process = subprocess.Popen([
    sys.executable, "combined_sports_runner.py"
])

try:
    while True:
        if api_process.poll() is not None:
            print(f"API server exited with code {api_process.returncode}, restarting...")
            api_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", "api:app",
                "--host", "0.0.0.0", "--port", port
            ])
        if engine_process.poll() is not None:
            print(f"Engine exited with code {engine_process.returncode}, restarting...")
            engine_process = subprocess.Popen([
                sys.executable, "combined_sports_runner.py"
            ])
        time.sleep(10)
except KeyboardInterrupt:
    api_process.terminate()
    engine_process.terminate()
    sys.exit(0)
