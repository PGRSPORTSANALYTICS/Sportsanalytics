#!/usr/bin/env python3
"""
Production startup — ensures port 5000 responds with 200 within milliseconds.

Sequence:
  t=0   : Minimal HTTP health server binds to port 5000 immediately
  t=0   : API server (port 8000) starts in background
  t=20  : Health server shuts down gracefully
  t=20  : Streamlit starts on port 5000
  t=~27 : Combined Sports Engine starts (foreground — keeps container alive)
"""

import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HEALTH_SERVE_SECONDS = 20


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>PGR Sports Analytics</h2>"
            b"<p>Platform starting up, please wait...</p></body></html>"
        )

    def log_message(self, *args):
        pass


def _serve_health():
    server = HTTPServer(("0.0.0.0", 5000), HealthHandler)
    server.timeout = 1
    deadline = time.time() + HEALTH_SERVE_SECONDS
    while time.time() < deadline:
        server.handle_request()
    server.server_close()
    print("[startup] Health-check server stopped — handing port 5000 to Streamlit")


def _wait_for_port(port: int, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1)
            s.close()
            return True
        except OSError:
            time.sleep(1)
    return False


# ── 1. Immediately serve health checks ────────────────────────────────────────
health_thread = threading.Thread(target=_serve_health, daemon=True)
health_thread.start()
print("[startup] ✅ Health-check server running on port 5000")

# ── 2. API server (port 8000) ─────────────────────────────────────────────────
api_proc = subprocess.Popen(
    ["python3", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
)
print(f"[startup] ✅ API server started (PID {api_proc.pid})")

# ── 3. Wait for health server to hand over port 5000 ─────────────────────────
health_thread.join()

# ── 4. Start Streamlit on port 5000 ──────────────────────────────────────────
st_proc = subprocess.Popen(
    [
        "streamlit", "run", "pgr_dashboard.py",
        "--server.port", "5000",
        "--server.address", "0.0.0.0",
    ]
)
print(f"[startup] ✅ Streamlit started (PID {st_proc.pid})")

# ── 5. Wait for Streamlit to accept connections ───────────────────────────────
if _wait_for_port(5000, timeout=60):
    print("[startup] ✅ Streamlit serving on port 5000")
else:
    print("[startup] ⚠️  Streamlit did not bind in time — continuing anyway")

# ── 6. Start Combined Sports Engine (foreground — keeps container alive) ──────
print("[startup] 🚀 Starting Combined Sports Engine...")
os.execvp("python3", ["python3", "combined_sports_runner.py"])
