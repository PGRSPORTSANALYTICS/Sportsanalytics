"""
PGR Sports Analytics Dashboard
Main dashboard with Football and College Basketball sections
"""

import streamlit as st

st.set_page_config(
    page_title="PGR Sports Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

page = st.sidebar.radio("Select Dashboard", ["⚽ Football", "🏀 College Basketball"])

if page == "⚽ Football":
    exec(open("pgr_football_dashboard.py").read())
else:
    exec(open("college_basket_dashboard.py").read())
