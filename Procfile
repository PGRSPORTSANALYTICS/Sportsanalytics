worker: python3 combined_sports_runner.py
web: streamlit run pgr_dashboard.py --server.port $PORT --server.address 0.0.0.0
api: python3 -m uvicorn api:app --host 0.0.0.0 --port $PORT
