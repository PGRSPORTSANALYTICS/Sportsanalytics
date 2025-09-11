#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

def confidence_to_stars(confidence):
    """Convert confidence score to stars"""
    if confidence >= 90: return "⭐⭐⭐⭐⭐"
    elif confidence >= 75: return "⭐⭐⭐⭐"
    elif confidence >= 60: return "⭐⭐⭐"
    elif confidence >= 45: return "⭐⭐"
    else: return "⭐"

# Page setup
st.set_page_config(
    page_title="🏆 Football Betting Dashboard",
    page_icon="🏆",
    layout="wide"
)

# Load data functions
@st.cache_data(ttl=30)
def load_current_opportunities():
    """Get recent betting opportunities"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        thirty_min_ago = datetime.now().timestamp() - (30 * 60)
        query = f"""
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, stake, league, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as found_time,
               CASE 
                   WHEN outcome = 'win' THEN '✅ Win'
                   WHEN outcome = 'loss' THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 LIVE'
               END as status
        FROM football_opportunities 
        WHERE timestamp >= {thirty_min_ago}
        ORDER BY timestamp DESC 
        LIMIT 10
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_performance():
    """Get betting performance stats"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(stake) as total_staked,
            SUM(profit_loss) as net_profit,
            AVG(CASE WHEN outcome IN ('win', 'loss') THEN (profit_loss/stake)*100 END) as avg_roi
        FROM football_opportunities 
        WHERE outcome IS NOT NULL
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

@st.cache_data(ttl=60)
def load_recent_bets():
    """Get recent betting history"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT home_team, away_team, selection, odds, stake, outcome, profit_loss,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time
        FROM football_opportunities 
        ORDER BY timestamp DESC 
        LIMIT 20
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

# Main Dashboard
st.title("🏆 Football Betting Dashboard")
st.markdown("**Smart betting opportunities with AI analysis**")

# === CURRENT OPPORTUNITIES ===
st.header("🔥 Current Opportunities")

current_bets = load_current_opportunities()

if not current_bets.empty:
    st.success(f"Found {len(current_bets)} live betting opportunities!")
    
    for _, bet in current_bets.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            
            with col1:
                st.subheader(f"{bet['home_team']} vs {bet['away_team']}")
                st.write(f"**{bet['selection']}** @ {bet['odds']:.2f}")
                
            with col2:
                st.metric("Edge", f"{bet['edge_percentage']:.1f}%")
                st.write(confidence_to_stars(bet['confidence']))
                
            with col3:
                st.metric("Stake", f"${bet['stake']:.2f}")
                potential = (bet['odds'] - 1) * bet['stake']
                st.metric("Potential Win", f"${potential:.2f}")
                
            with col4:
                st.write(f"**{bet['status']}**")
                st.write(f"{bet['league']}")
                st.write(f"Found: {bet['found_time'][11:16]}")
            
            st.divider()
else:
    st.info("⏳ Looking for new betting opportunities...")

# === PERFORMANCE SUMMARY ===
st.header("📊 Performance Summary")

perf = load_performance()

if perf is not None and perf['total_bets'] > 0:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Bets", int(perf['total_bets']))
        
    with col2:
        win_rate = (perf['wins'] / (perf['wins'] + perf['losses']) * 100) if (perf['wins'] + perf['losses']) > 0 else 0
        st.metric("Win Rate", f"{win_rate:.1f}%")
        
    with col3:
        st.metric("Net Profit", f"${perf['net_profit']:.2f}")
        
    with col4:
        roi = perf['avg_roi'] if pd.notna(perf['avg_roi']) else 0
        st.metric("Avg ROI", f"{roi:.1f}%")
        
    # Profit/Loss Chart
    recent = load_recent_bets()
    if not recent.empty and 'profit_loss' in recent.columns:
        completed = recent[recent['outcome'].notna() & recent['profit_loss'].notna()].copy()
        if not completed.empty:
            completed['cumulative_profit'] = completed['profit_loss'].fillna(0).cumsum()
            
            fig = px.line(completed, y='cumulative_profit', 
                         title="Profit Over Time",
                         labels={'cumulative_profit': 'Cumulative Profit ($)'})
            fig.update_traces(line_color='#00cc44')
            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("📈 Performance tracking will appear after placing bets")

# === RECENT ACTIVITY ===
st.header("📋 Recent Activity")

recent = load_recent_bets()

if not recent.empty:
    # Clean up the display
    display_df = recent[['home_team', 'away_team', 'selection', 'odds', 'outcome', 'profit_loss']].copy()
    display_df.columns = ['Home Team', 'Away Team', 'Bet', 'Odds', 'Result', 'P&L ($)']
    
    # Color code the results
    def color_result(val):
        if val == 'win':
            return 'color: green'
        elif val == 'loss':
            return 'color: red'
        else:
            return 'color: gray'
    
    styled_df = display_df.style.applymap(color_result, subset=['Result'])
    st.dataframe(styled_df, use_container_width=True)
else:
    st.info("📝 Recent betting activity will appear here")

# Auto-refresh
st.markdown("---")
st.caption("🔄 Dashboard refreshes automatically every 30 seconds")