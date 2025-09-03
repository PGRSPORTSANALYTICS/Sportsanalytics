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
        query = """
        SELECT *, 
               CASE 
                   WHEN match_date IS NOT NULL AND kickoff_time IS NOT NULL 
                   THEN match_date || ' ' || kickoff_time
                   ELSE datetime(timestamp, 'unixepoch', 'localtime')
               END as display_datetime,
               CASE 
                   WHEN outcome = 'win' THEN '✅ Win'
                   WHEN outcome = 'loss' THEN '❌ Loss'
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '⏳ Pending'
               END as bet_status
        FROM football_opportunities 
        ORDER BY timestamp DESC 
        LIMIT 50
        """
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
        
        # Overall performance using new outcome column
        query = """
            SELECT 
                COUNT(*) as total_bets,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_staked,
                SUM(CASE WHEN outcome = 'win' THEN stake * odds ELSE 0 END) as total_payout,
                SUM(profit_loss) as net_profit,
                (SUM(profit_loss) / SUM(stake)) * 100 as roi_percentage
            FROM football_opportunities 
            WHERE outcome IS NOT NULL AND outcome != ''
        """
        
        cursor = conn.cursor()
        cursor.execute(query)
        stats = cursor.fetchone()
        
        # Recent results using new outcome column
        recent_query = """
            SELECT home_team, away_team, selection, odds, stake, outcome, profit_loss, updated_at
            FROM football_opportunities 
            WHERE outcome IS NOT NULL AND outcome != ''
            ORDER BY updated_at DESC 
            LIMIT 10
        """
        recent_df = pd.read_sql_query(recent_query, conn)
        
        conn.close()
        
        if stats and stats[0] > 0:
            total_bets, wins, losses, total_staked, total_payout, net_profit, roi_percentage = stats
            win_rate = (wins / total_bets) * 100 if total_bets > 0 else 0
            total_roi = roi_percentage if roi_percentage else 0
            avg_roi_per_bet = total_roi / total_bets if total_bets > 0 else 0
            
            return {
                'total_bets': total_bets,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'total_staked': total_staked,
                'total_payout': total_payout,
                'net_profit': net_profit,
                'total_roi': total_roi,
                'avg_roi_per_bet': avg_roi_per_bet,
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
            result_color = "🟢" if row.get('outcome') == 'win' else "🔴" if row.get('outcome') == 'loss' else "🟡"
            outcome_text = row.get('outcome', 'pending').upper()
            with st.expander(f"{result_color} {row['home_team']} vs {row['away_team']} - {outcome_text}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Selection:** {row['selection']}")
                    st.write(f"**Odds:** {row['odds']:.2f}")
                with col2:
                    st.write(f"**Stake:** ${row['stake']:.2f}")
                    profit_loss = row.get('profit_loss', 0)
                    st.write(f"**P&L:** ${profit_loss:.2f}")
                with col3:
                    roi = (profit_loss / row['stake'] * 100) if row['stake'] > 0 else 0
                    st.write(f"**ROI:** {roi:.1f}%")
                    st.write(f"**Status:** {row.get('outcome', 'pending').title()}")
    
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
        # Format match date/time display
        date_display = ""
        if pd.notna(row.get('display_datetime', '')):
            date_display = f" | 📅 {row['display_datetime']}"
        elif pd.notna(row.get('match_date', '')) and pd.notna(row.get('kickoff_time', '')):
            date_display = f" | 📅 {row['match_date']} {row['kickoff_time']}"
        else:
            import datetime
            try:
                date_str = datetime.datetime.fromtimestamp(row['timestamp']).strftime("%Y-%m-%d %H:%M")
                date_display = f" | 📅 {date_str}"
            except:
                pass
        
        # Create kickoff time display
        kickoff_display = ""
        if pd.notna(row.get('kickoff_time', '')):
            kickoff_display = f" ⏰ {row['kickoff_time']}"
        
        with st.expander(f"⚽ {row['home_team']} vs {row['away_team']} - {row['selection']}{date_display}{kickoff_display}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write("**Match Info:**")
                st.write(f"🏠 {row['home_team']}")
                st.write(f"✈️ {row['away_team']}")
                st.write(f"🏆 {row['league']}")
                if pd.notna(row.get('match_date', '')):
                    kickoff = row.get('kickoff_time', '')
                    st.write(f"📅 {row['match_date']}")
                    if kickoff:
                        st.write(f"⏰ Kickoff: {kickoff}")
            
            with col2:
                st.write("**Betting Details:**")
                st.write(f"🎯 {row['market']}: {row['selection']}")
                st.write(f"📊 Odds: {row['odds']:.2f}")
                st.write(f"💰 Stake: ${row['stake']:.2f}")
            
            with col3:
                st.write("**Analysis:**")
                st.write(f"📈 Edge: {row['edge_percentage']:.1f}%")
                st.write(f"🎯 Confidence: {row['confidence']}/100")
                st.write(f"📋 Status: {row.get('bet_status', '⏳ Pending')}")
                if pd.notna(row.get('profit_loss', 0)) and row.get('profit_loss', 0) != 0:
                    profit_color = "green" if row['profit_loss'] > 0 else "red"
                    st.markdown(f"**💰 P&L:** <span style='color:{profit_color}'>${row['profit_loss']:.2f}</span>", unsafe_allow_html=True)
    
    # Show all data in table
    st.markdown("---")
    st.subheader("📊 All Opportunities")
    
    # Select key columns for display including bet status and kickoff time
    display_cols = ['home_team', 'away_team', 'league', 'match_date', 'kickoff_time', 'selection', 'odds', 'edge_percentage', 'confidence', 'stake', 'bet_status', 'profit_loss']
    available_cols = [col for col in display_cols if col in df.columns]
    
    if available_cols:
        st.dataframe(df[available_cols], use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)

# Footer
st.markdown("---")
st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.markdown("**Real Football Champion** - Advanced AI Football Analytics")