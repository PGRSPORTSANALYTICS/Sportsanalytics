#!/bin/bash
# Production startup script
# Starts Streamlit first so health checks pass, then starts the engine

echo "[startup] Starting PGR Sports Analytics Platform..."

# Start API server in background
python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 &
API_PID=$!
echo "[startup] API server started (PID $API_PID)"

# Start Streamlit in background FIRST so health checks pass immediately
streamlit run pgr_dashboard.py --server.port 5000 --server.address 0.0.0.0 &
STREAMLIT_PID=$!
echo "[startup] Streamlit started (PID $STREAMLIT_PID)"

# Wait for Streamlit to bind to port 5000 before starting heavy engine
echo "[startup] Waiting for Streamlit to be ready..."
for i in $(seq 1 60); do
    if python3 -c "import socket; s=socket.socket(); s.connect(('127.0.0.1',5000)); s.close()" 2>/dev/null; then
        echo "[startup] Streamlit ready after ${i}s"
        break
    fi
    sleep 1
done

# Start Combined Sports Engine in foreground (keeps container alive)
echo "[startup] Starting Combined Sports Engine..."
exec python3 combined_sports_runner.py
