#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime

# Page config
st.set_page_config(
    page_title="🏆 Real Football Champion Dashboard",
    page_icon="🏆",
    layout="wide"
)

# Connect to database
@st.cache_data(ttl=10)  # Cache for 10 seconds only
def load_opportunities():
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = "SELECT * FROM football_opportunities ORDER BY timestamp DESC LIMIT 50"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=10)
def load_performance_stats():
    try:
        conn = sqlite3.connect('data/real_football.db')
        
        # Overall performance
        query = """
            SELECT 
                COUNT(*) as total_bets,
                SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_staked,
                SUM(payout) as total_payout,
                AVG(roi_percentage) as avg_roi,
                SUM(payout) - SUM(stake) as net_profit
            FROM football_opportunities 
            WHERE status = 'settled'
        """
        
        cursor = conn.cursor()
        cursor.execute(query)
        stats = cursor.fetchone()
        
        # Recent results
        recent_query = """
            SELECT home_team, away_team, selection, odds, stake, result, payout, roi_percentage, settled_timestamp
            FROM football_opportunities 
            WHERE status = 'settled' 
            ORDER BY settled_timestamp DESC 
            LIMIT 10
        """
        recent_df = pd.read_sql_query(recent_query, conn)
        
        conn.close()
        
        if stats and stats[0] > 0:
            total_bets, wins, losses, total_staked, total_payout, avg_roi, net_profit = stats
            win_rate = (wins / total_bets) * 100 if total_bets > 0 else 0
            total_roi = ((total_payout - total_staked) / total_staked) * 100 if total_staked > 0 else 0
            
            return {
                'total_bets': total_bets,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'total_staked': total_staked,
                'total_payout': total_payout,
                'net_profit': net_profit,
                'total_roi': total_roi,
                'avg_roi_per_bet': avg_roi or 0,
                'recent_results': recent_df
            }
        
        return {'total_bets': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                'total_staked': 0, 'total_payout': 0, 'net_profit': 0,
                'total_roi': 0, 'avg_roi_per_bet': 0, 'recent_results': pd.DataFrame()}
    
    except Exception as e:
        st.error(f"Performance data error: {e}")
        return {'total_bets': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                'total_staked': 0, 'total_payout': 0, 'net_profit': 0,
                'total_roi': 0, 'avg_roi_per_bet': 0, 'recent_results': pd.DataFrame()}

# Auto refresh
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Title
st.title("🏆 Real Football Champion Dashboard")
st.markdown("### Live Football Betting Opportunities")

# Load data
df = load_opportunities()
performance = load_performance_stats()

# Performance Section
if performance['total_bets'] > 0:
    st.header("📈 Track Record & ROI")
    
    perf_col1, perf_col2, perf_col3, perf_col4, perf_col5 = st.columns(5)
    
    with perf_col1:
        st.metric("🎯 Win Rate", f"{performance['win_rate']:.1f}%", 
                 f"{performance['wins']}/{performance['total_bets']} won")
    
    with perf_col2:
        st.metric("💰 Total ROI", f"{performance['total_roi']:.1f}%",
                 f"${performance['net_profit']:.2f} profit")
    
    with perf_col3:
        st.metric("📊 Total Staked", f"${performance['total_staked']:.2f}")
    
    with perf_col4:
        st.metric("💸 Total Payout", f"${performance['total_payout']:.2f}")
    
    with perf_col5:
        st.metric("📈 Avg ROI/Bet", f"{performance['avg_roi_per_bet']:.1f}%")
    
    # Recent Results
    if not performance['recent_results'].empty:
        st.subheader("🏆 Recent Results")
        
        for idx, row in performance['recent_results'].head(5).iterrows():
            result_color = "🟢" if row['result'] == 'won' else "🔴" if row['result'] == 'lost' else "🟡"
            with st.expander(f"{result_color} {row['home_team']} vs {row['away_team']} - {row['result'].upper()}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Selection:** {row['selection']}")
                    st.write(f"**Odds:** {row['odds']:.2f}")
                with col2:
                    st.write(f"**Stake:** ${row['stake']:.2f}")
                    st.write(f"**Payout:** ${row['payout']:.2f}")
                with col3:
                    st.write(f"**ROI:** {row['roi_percentage']:.1f}%")
                    profit = row['payout'] - row['stake']
                    st.write(f"**Profit:** ${profit:.2f}")
    
    st.markdown("---")

if df.empty:
    st.warning("No opportunities found in database")
    st.info("Checking database connection...")
    
    # Debug info
    try:
        conn = sqlite3.connect('data/real_football.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM football_opportunities")
        count = cursor.fetchone()[0]
        st.info(f"Total opportunities in database: {count}")
        conn.close()
    except Exception as e:
        st.error(f"Database connection failed: {e}")
else:
    # Show summary stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Opportunities", len(df))
    
    with col2:
        avg_edge = df['edge_percentage'].mean() if 'edge_percentage' in df.columns else 0
        st.metric("Average Edge", f"{avg_edge:.1f}%")
    
    with col3:
        avg_conf = df['confidence'].mean() if 'confidence' in df.columns else 0
        st.metric("Average Confidence", f"{avg_conf:.0f}/100")
    
    with col4:
        total_stake = df['stake'].sum() if 'stake' in df.columns else 0
        st.metric("Total Stakes", f"${total_stake:.2f}")

    st.markdown("---")
    
    # Show recent opportunities
    st.subheader("🎯 Recent Opportunities")
    
    # Display each opportunity
    for idx, row in df.head(10).iterrows():
        with st.expander(f"⚽ {row['home_team']} vs {row['away_team']} - {row['selection']}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write("**Match Info:**")
                st.write(f"🏠 {row['home_team']}")
                st.write(f"✈️ {row['away_team']}")
                st.write(f"🏆 {row['league']}")
            
            with col2:
                st.write("**Betting Details:**")
                st.write(f"🎯 {row['market']}: {row['selection']}")
                st.write(f"📊 Odds: {row['odds']:.2f}")
                st.write(f"💰 Stake: ${row['stake']:.2f}")
            
            with col3:
                st.write("**Analysis:**")
                st.write(f"📈 Edge: {row['edge_percentage']:.1f}%")
                st.write(f"🎯 Confidence: {row['confidence']}/100")
                st.write(f"📋 Status: {row['status']}")
    
    # Show all data in table
    st.markdown("---")
    st.subheader("📊 All Opportunities")
    
    # Select key columns for display
    display_cols = ['home_team', 'away_team', 'league', 'selection', 'odds', 'edge_percentage', 'confidence', 'stake']
    available_cols = [col for col in display_cols if col in df.columns]
    
    if available_cols:
        st.dataframe(df[available_cols], use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

# Footer
st.markdown("---")
st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.markdown("**Real Football Champion** - Advanced AI Football Analytics")