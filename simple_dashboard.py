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
def load_regular_tips():
    """Load today's regular betting opportunities (excluding exact scores)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        today = date.today().isoformat()
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, tier,
               CASE 
                   WHEN tier = 'premium' THEN '💎 Premium'
                   WHEN tier = 'standard' THEN '⚡ Standard'
                   WHEN tier = 'value' THEN '💰 Value'
                   WHEN tier = 'backup' THEN '🔧 Backup'
                   ELSE '📊 Tip'
               END as tier_label
        FROM football_opportunities 
        WHERE tier IS NOT NULL
        AND tier != 'legacy'
        AND DATE(timestamp, 'unixepoch', 'localtime') = ?
        ORDER BY 
            CASE tier
                WHEN 'premium' THEN 1
                WHEN 'standard' THEN 2
                WHEN 'value' THEN 3
                WHEN 'backup' THEN 4
            END,
            edge_percentage DESC
        """
        df = pd.read_sql_query(query, conn, params=[today])
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_exact_score_tips():
    """Load today's exact score predictions"""
    try:
        conn = sqlite3.connect(DB_PATH)
        today = date.today().isoformat()
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date
        FROM football_opportunities 
        WHERE tier = 'legacy'
        AND DATE(timestamp, 'unixepoch', 'localtime') = ?
        ORDER BY edge_percentage DESC
        """
        df = pd.read_sql_query(query, conn, params=[today])
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30) 
def load_regular_performance():
    """Get regular betting performance stats"""
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
        AND tier != 'legacy'
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

@st.cache_data(ttl=30) 
def load_exact_score_performance():
    """Get exact score performance stats"""
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
        WHERE tier = 'legacy'
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

@st.cache_data(ttl=30)
def load_all_historical():
    """Load all historical betting results"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, tier, outcome, profit_loss, match_date,
               CASE 
                   WHEN tier = 'premium' THEN '💎 Premium'
                   WHEN tier = 'standard' THEN '⚡ Standard'
                   WHEN tier = 'value' THEN '💰 Value'
                   WHEN tier = 'backup' THEN '🔧 Backup'
                   WHEN tier = 'legacy' THEN '🎯 Exact Score'
                   ELSE '📊 Tip'
               END as tier_label,
               CASE 
                   WHEN outcome IN ('win', 'won') THEN '✅ Win'
                   WHEN outcome IN ('loss', 'lost') THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 Pending'
               END as result
        FROM football_opportunities 
        WHERE tier IS NOT NULL
        AND outcome IS NOT NULL 
        AND outcome != ''
        AND outcome != 'unknown'
        ORDER BY timestamp DESC 
        LIMIT 100
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

# ============================================================================
# DASHBOARD LAYOUT
# ============================================================================

st.title("🏆 Premium Football Tips")
st.markdown("**Exclusive AI-Powered Betting Intelligence**")

# Refresh button
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Refresh", help="Update data"):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ============================================================================
# TOP SECTION: REGULAR BETTING TIPS + TRACKER
# ============================================================================

st.header("💎 Premium Betting Tips")

# Regular betting tracker
regular_stats = load_regular_performance()
if regular_stats is not None:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📊 Total Tips", int(regular_stats['total_tips']))
    
    with col2:
        win_rate = (regular_stats['wins'] / (regular_stats['wins'] + regular_stats['losses']) * 100) if (regular_stats['wins'] + regular_stats['losses']) > 0 else 0
        st.metric("🏆 Win Rate", f"{win_rate:.1f}%")
    
    with col3:
        st.metric("💰 Net Profit", f"${regular_stats['net_profit']:.2f}")
    
    with col4:
        roi = (regular_stats['net_profit'] / regular_stats['total_staked'] * 100) if regular_stats['total_staked'] > 0 else 0
        st.metric("📈 ROI", f"{roi:.1f}%")

st.markdown("")

# Today's regular tips
regular_tips = load_regular_tips()
if not regular_tips.empty:
    st.success(f"🌟 {len(regular_tips)} premium tips available today")
    
    for idx, tip in regular_tips.iterrows():
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
            st.write(f"**{tip['tier_label']}**")
        
        st.divider()
else:
    st.info("🔍 No premium tips available. Waiting for quality opportunities...")

st.markdown("---")

# ============================================================================
# MIDDLE SECTION: EXACT SCORE PREDICTIONS + TRACKER
# ============================================================================

st.header("🎯 Exact Score Predictions")

# Exact score tracker
exact_stats = load_exact_score_performance()
if exact_stats is not None and exact_stats['total_tips'] > 0:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🎯 Total Predictions", int(exact_stats['total_tips']))
    
    with col2:
        hit_rate = (exact_stats['wins'] / (exact_stats['wins'] + exact_stats['losses']) * 100) if (exact_stats['wins'] + exact_stats['losses']) > 0 else 0
        st.metric("🎯 Hit Rate", f"{hit_rate:.1f}%")
    
    with col3:
        st.metric("💰 Total Profit", f"${exact_stats['net_profit']:.2f}")
    
    with col4:
        st.metric("📝 Settled", f"{exact_stats['wins'] + exact_stats['losses']}")

st.markdown("")

# Today's exact scores
exact_tips = load_exact_score_tips()
if not exact_tips.empty:
    st.success(f"🎯 {len(exact_tips)} exact score predictions today")
    
    for idx, tip in exact_tips.iterrows():
        col1, col2, col3 = st.columns([3, 2, 2])
        
        with col1:
            st.write(f"**{tip['home_team']} vs {tip['away_team']}**")
            st.caption(f"{tip['selection']}")
        
        with col2:
            st.write(f"**Odds:** {tip['odds']:.2f}")
            st.caption(f"Edge: {tip['edge_percentage']:.1f}%")
        
        with col3:
            st.write(f"**Confidence:** {tip['confidence']}%")
            st.caption(f"Date: {tip['match_date']}")
        
        st.divider()
else:
    st.info("🎯 No exact score predictions available today.")

st.markdown("---")

# ============================================================================
# BOTTOM SECTION: HISTORICAL BETS
# ============================================================================

st.header("📊 Historical Performance")

historical = load_all_historical()
if not historical.empty:
    st.success(f"📈 Track Record: {len(historical)} completed bets")
    
    # Create display table
    display_df = historical.head(50).copy()
    display_df['Match'] = display_df['home_team'] + ' vs ' + display_df['away_team']
    display_df['P&L'] = display_df['profit_loss'].apply(lambda x: f"${x:.2f}")
    
    table_data = display_df[['Match', 'selection', 'tier_label', 'odds', 'result', 'P&L', 'match_date']].copy()
    table_data.columns = ['Match', 'Selection', 'Tier', 'Odds', 'Result', 'P&L', 'Date']
    
    # Color code results
    def color_historical(row):
        if '✅' in str(row['Result']):
            return ['background-color: #d4edda'] * len(row)
        elif '❌' in str(row['Result']):
            return ['background-color: #f8d7da'] * len(row)
        else:
            return [''] * len(row)
    
    styled_table = table_data.style.apply(color_historical, axis=1)
    st.dataframe(styled_table, use_container_width=True, height=600)
else:
    st.info("📊 Historical results will appear here as bets are completed.")

# Footer
st.markdown("---")
st.caption("🔄 Dashboard auto-refreshes every 30 seconds | 🔒 100% Authentic Results")
