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

# Auto refresh
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Title
st.title("🏆 Real Football Champion Dashboard")
st.markdown("### Live Football Betting Opportunities")

# Load data
df = load_opportunities()

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