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
                st.write(f"⏰ Found: {bet['found_time'][11:16]}")
                st.write(f"📅 {bet['match_date']}")
            
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
            st.plotly_chart(fig, use_column_width=True)

else:
    st.info("📈 Performance tracking will appear after placing bets")

# === HISTORICAL BETS ===
st.header("📚 Historical Bets")

@st.cache_data(ttl=60)
def load_historical_bets():
    """Get all historical betting data with filters"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, confidence,
               stake, outcome, profit_loss, league, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time,
               DATE(datetime(timestamp, 'unixepoch', 'localtime')) as bet_date
        FROM football_opportunities 
        ORDER BY timestamp DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

historical_bets = load_historical_bets()

if not historical_bets.empty:
    # Filter controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Outcome filter
        outcome_options = ['All'] + list(historical_bets['outcome'].dropna().unique())
        selected_outcome = st.selectbox("Filter by Result", outcome_options)
    
    with col2:
        # League filter
        league_options = ['All'] + list(historical_bets['league'].dropna().unique())
        selected_league = st.selectbox("Filter by League", league_options)
    
    with col3:
        # Show count
        show_count = st.selectbox("Show", [20, 50, 100, "All"])
    
    # Apply filters
    filtered_bets = historical_bets.copy()
    
    if selected_outcome != 'All':
        filtered_bets = filtered_bets[filtered_bets['outcome'] == selected_outcome]
    
    if selected_league != 'All':
        filtered_bets = filtered_bets[filtered_bets['league'] == selected_league]
    
    if show_count != "All":
        filtered_bets = filtered_bets.head(show_count)
    
    # Summary stats for filtered data
    if not filtered_bets.empty:
        completed = filtered_bets[filtered_bets['outcome'].notna()]
        
        if not completed.empty:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Filtered Bets", len(filtered_bets))
            
            with col2:
                wins = len(completed[completed['outcome'] == 'win'])
                losses = len(completed[completed['outcome'] == 'loss'])
                win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
                st.metric("Win Rate", f"{win_rate:.1f}%")
            
            with col3:
                total_profit = completed['profit_loss'].sum()
                st.metric("Total P&L", f"${total_profit:.2f}")
            
            with col4:
                avg_edge = filtered_bets['edge_percentage'].mean()
                st.metric("Avg Edge", f"{avg_edge:.1f}%")
    
    # Display historical bets table
    st.subheader("📊 Betting History")
    
    display_df = filtered_bets[['bet_time', 'home_team', 'away_team', 'selection', 
                               'odds', 'edge_percentage', 'stake', 'outcome', 'profit_loss']].copy()
    display_df.columns = ['Timestamp', 'Home Team', 'Away Team', 'Bet', 'Odds', 
                         'Edge %', 'Stake $', 'Result', 'P&L $']
    
    # Format numbers
    display_df['Odds'] = display_df['Odds'].round(2)
    display_df['Edge %'] = display_df['Edge %'].round(1)
    display_df['Stake $'] = display_df['Stake $'].round(2)
    display_df['P&L $'] = display_df['P&L $'].round(2)
    
    # Color coding function
    def highlight_results(row):
        if pd.isna(row['Result']):
            return [''] * len(row)
        elif row['Result'] == 'win':
            return ['background-color: #d4edda'] * len(row)
        elif row['Result'] == 'loss':
            return ['background-color: #f8d7da'] * len(row)
        else:
            return ['background-color: #f0f0f0'] * len(row)
    
    styled_df = display_df.style.apply(highlight_results, axis=1)
    st.dataframe(styled_df)
    
    # Monthly performance breakdown
    if not completed.empty:
        st.subheader("📅 Monthly Performance")
        
        completed_copy = completed.copy()
        completed_copy['month'] = pd.to_datetime(completed_copy['bet_time']).dt.strftime('%Y-%m')
        
        monthly_stats = completed_copy.groupby('month').agg({
            'outcome': 'count',
            'profit_loss': 'sum',
            'stake': 'sum'
        }).round(2)
        
        monthly_stats.columns = ['Bets', 'Profit ($)', 'Staked ($)']
        monthly_stats['ROI %'] = ((monthly_stats['Profit ($)'] / monthly_stats['Staked ($)']) * 100).round(1)
        
        st.dataframe(monthly_stats)

else:
    st.info("📝 Historical betting data will appear here after placing bets")

# Auto-refresh
st.markdown("---")
st.caption("🔄 Dashboard refreshes automatically every 30 seconds")