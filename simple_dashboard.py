#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date

# Database path
DB_PATH = 'data/real_football.db'

# Page setup
st.set_page_config(
    page_title="🏆 Premium Football Tips",
    page_icon="🏆",
    layout="wide"
)

@st.cache_data(ttl=30)
def load_recent_tips():
    """Load recent betting tips"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, kickoff_time, outcome, profit_loss,
               datetime(timestamp, 'unixepoch', 'localtime') as discovered,
               CASE 
                   WHEN outcome = 'win' THEN '✅ Win'
                   WHEN outcome = 'loss' THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 Live'
               END as status
        FROM football_opportunities 
        WHERE recommended_tier IS NOT NULL
        ORDER BY timestamp DESC 
        LIMIT 20
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30) 
def load_performance():
    """Get betting performance stats"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            COUNT(*) as total_tips,
            COUNT(CASE WHEN outcome IN ('win', 'won') THEN 1 END) as wins,
            COUNT(CASE WHEN outcome IN ('loss', 'lost') THEN 1 END) as losses,
            COUNT(CASE WHEN outcome IS NULL OR outcome = '' THEN 1 END) as pending,
            SUM(CASE WHEN outcome IS NOT NULL THEN profit_loss ELSE 0 END) as net_profit,
            SUM(stake) as total_staked
        FROM football_opportunities 
        WHERE recommended_tier IS NOT NULL
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

# Main Dashboard
st.title("🏆 Premium Football Tips")
st.markdown("**AI-Powered Quality Tips with Authentic Performance Tracking**")

# Refresh button
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Refresh", help="Update data"):
        st.cache_data.clear()
        st.rerun()

# Performance Overview
st.header("📊 Performance Overview")

stats = load_performance()
if stats is not None:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📝 Total Tips", int(stats['total_tips']))
    
    with col2:
        win_rate = (stats['wins'] / (stats['wins'] + stats['losses']) * 100) if (stats['wins'] + stats['losses']) > 0 else 0
        st.metric("🏆 Win Rate", f"{win_rate:.1f}%")
    
    with col3:
        st.metric("💰 Net Profit", f"${stats['net_profit']:.2f}")
    
    with col4:
        roi = (stats['net_profit'] / stats['total_staked'] * 100) if stats['total_staked'] > 0 else 0
        st.metric("📈 ROI", f"{roi:.1f}%")

# Recent Tips
st.header("🌟 Recent Tips")

tips = load_recent_tips()
if not tips.empty:
    st.success(f"Showing {len(tips)} recent tips")
    
    for idx, tip in tips.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.write(f"**{tip['home_team']} vs {tip['away_team']}**")
                st.caption(f"{tip['selection']}")
            
            with col2:
                st.write(f"**Odds:** {tip['odds']:.2f}")
                st.caption(f"Edge: {tip['edge_percentage']:.1f}%")
            
            with col3:
                st.write(f"**Confidence:** {tip['confidence']}%")
                st.caption(f"Date: {tip['match_date']}")
            
            with col4:
                st.write(f"**{tip['status']}**")
                if tip['outcome'] in ['win', 'loss']:
                    profit_color = "green" if tip['profit_loss'] > 0 else "red"
                    st.markdown(f"<span style='color: {profit_color}'>${tip['profit_loss']:.2f}</span>", unsafe_allow_html=True)
            
            st.divider()

else:
    st.info("🔍 No recent tips found. New opportunities will appear here.")

# Footer
st.markdown("---")
st.caption("🔄 Dashboard auto-refreshes every 30 seconds")