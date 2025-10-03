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
def load_todays_tips():
    """Load today's current betting opportunities"""
    try:
        conn = sqlite3.connect(DB_PATH)
        today = date.today().isoformat()
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, kickoff_time, outcome, profit_loss, tier,
               datetime(timestamp, 'unixepoch', 'localtime') as discovered,
               CASE 
                   WHEN tier = 'premium' THEN '💎 Premium'
                   WHEN tier = 'standard' THEN '⚡ Standard'
                   WHEN tier = 'value' THEN '💰 Value'
                   WHEN tier = 'backup' THEN '🔧 Backup'
                   WHEN tier = 'legacy' THEN '🎯 Exact Score'
                   ELSE '📊 Tip'
               END as tier_label,
               CASE 
                   WHEN outcome = 'win' THEN '✅ Win'
                   WHEN outcome = 'loss' THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 Live'
               END as status
        FROM football_opportunities 
        WHERE tier IS NOT NULL
        AND DATE(timestamp, 'unixepoch', 'localtime') = ?
        ORDER BY 
            CASE tier
                WHEN 'premium' THEN 1
                WHEN 'standard' THEN 2
                WHEN 'value' THEN 3
                WHEN 'backup' THEN 4
                WHEN 'legacy' THEN 5
            END,
            edge_percentage DESC
        LIMIT 15
        """
        df = pd.read_sql_query(query, conn, params=[today])
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_historical_bets():
    """Load historical completed betting results"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, outcome, profit_loss, stake, tier,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time,
               CASE 
                   WHEN outcome IN ('win', 'won') THEN '✅ Win'
                   WHEN outcome IN ('loss', 'lost') THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 Live'
               END as result
        FROM football_opportunities 
        WHERE tier IS NOT NULL
        AND outcome IS NOT NULL 
        AND outcome != ''
        AND outcome != 'unknown'
        ORDER BY timestamp DESC 
        LIMIT 50
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
            COUNT(CASE WHEN outcome IS NULL OR outcome = '' OR outcome = 'unknown' THEN 1 END) as pending,
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome != 'unknown' THEN profit_loss ELSE 0 END) as net_profit,
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome != 'unknown' THEN stake ELSE 0 END) as total_staked
        FROM football_opportunities 
        WHERE tier IS NOT NULL
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

# Today's Current Tips
st.header("🔥 Today's Tips")

todays_tips = load_todays_tips()
if not todays_tips.empty:
    st.success(f"🌟 {len(todays_tips)} current opportunities available")
    
    for idx, tip in todays_tips.iterrows():
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
            
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
                st.write(f"**{tip['tier_label']}**")
            
            with col5:
                st.write(f"**{tip['status']}**")
                if tip['outcome'] in ['win', 'loss']:
                    profit_color = "green" if tip['profit_loss'] > 0 else "red"
                    st.markdown(f"<span style='color: {profit_color}'>${tip['profit_loss']:.2f}</span>", unsafe_allow_html=True)
            
            st.divider()
else:
    st.info("🔍 No current tips available. New opportunities will appear here when found.")

st.markdown("---")

# Historical Betting Results
st.header("📊 Historical Results")

historical_bets = load_historical_bets()
if not historical_bets.empty:
    st.success(f"📈 Track record: {len(historical_bets)} completed bets")
    
    # Summary stats for historical performance
    wins = len(historical_bets[historical_bets['outcome'].isin(['win', 'won'])])
    losses = len(historical_bets[historical_bets['outcome'].isin(['loss', 'lost'])])
    total_profit = historical_bets['profit_loss'].sum()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        st.metric("🏆 Historical Win Rate", f"{win_rate:.1f}%")
    with col2:
        st.metric("💰 Total Profit", f"${total_profit:.2f}")
    with col3:
        st.metric("📝 Total Settled", f"{wins + losses}")
    
    # Display historical results in a clean table format
    st.subheader("📋 Recent Completed Bets")
    
    display_historical = historical_bets.head(20).copy()
    display_historical['Match'] = display_historical['home_team'] + ' vs ' + display_historical['away_team']
    display_historical['Profit/Loss'] = display_historical['profit_loss'].apply(lambda x: f"${x:.2f}")
    display_historical['Win Rate'] = display_historical['result']
    
    # Show table with key columns
    table_data = display_historical[['Match', 'selection', 'odds', 'Win Rate', 'Profit/Loss', 'match_date']].copy()
    table_data.columns = ['Match', 'Selection', 'Odds', 'Result', 'P&L', 'Date']
    
    # Color code the results
    def color_results(row):
        if '✅' in str(row['Result']):
            return ['background-color: #d4edda'] * len(row)  # Green for wins
        elif '❌' in str(row['Result']):
            return ['background-color: #f8d7da'] * len(row)  # Red for losses  
        else:
            return [''] * len(row)
    
    styled_table = table_data.style.apply(color_results, axis=1)
    st.dataframe(styled_table, width='stretch')
    
else:
    st.info("📊 Historical betting results will appear here as bets are completed.")

# Footer
st.markdown("---")
st.caption("🔄 Dashboard auto-refreshes every 30 seconds")