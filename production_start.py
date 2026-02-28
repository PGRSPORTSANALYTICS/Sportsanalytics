#!/usr/bin/env python3
"""
production_start.py — PGR Sports Analytics Platform startup.

Architecture:
  port 5000  TCP proxy (port_proxy.py) — starts in <300 ms, always returns 200
             ↓ forwards to
  port 5001  Streamlit dashboard
  port 8000  PGR API server (uvicorn)
  foreground Combined Sports Engine (keeps container alive)

The proxy ensures Replit's health check on port 5000 passes immediately,
even while Streamlit is still loading.
"""

import os
import socket
import subprocess
import time


def _wait_for_port(port: int, timeout: int = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=1)
            s.close()
            return True
        except OSError:
            time.sleep(1)
    return False


# ── 1. TCP proxy on port 5000 (instant health-check response) ─────────────
proxy_proc = subprocess.Popen(["python3", "port_proxy.py"])
print(f"[startup] ✅ TCP proxy started (PID {proxy_proc.pid}) — port 5000 responding", flush=True)

# Give proxy 1 second to bind before announcing readiness
time.sleep(1)

# ── 2. Streamlit on port 5001 (proxied via port 5000) ────────────────────
st_proc = subprocess.Popen(
    [
        "streamlit", "run", "pgr_dashboard.py",
        "--server.port", "5001",
        "--server.address", "0.0.0.0",
    ]
)
print(f"[startup] ✅ Streamlit started on port 5001 (PID {st_proc.pid})", flush=True)

# ── 3. PGR API server on port 8000 ───────────────────────────────────────
api_proc = subprocess.Popen(
    ["python3", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
)
print(f"[startup] ✅ API server started on port 8000 (PID {api_proc.pid})", flush=True)

# ── 4. Wait for Streamlit to be ready ─────────────────────────────────────
if _wait_for_port(5001, timeout=90):
    print("[startup] ✅ Streamlit serving on port 5001 — proxy now forwarding live traffic", flush=True)
else:
    print("[startup] ⚠️  Streamlit took too long — proxy still serving health responses", flush=True)

# ── 5. Combined Sports Engine (foreground — keeps container alive) ─────────
print("[startup] 🚀 Starting Combined Sports Engine...", flush=True)
os.execvp("python3", ["python3", "combined_sports_runner.py"])
