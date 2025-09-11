#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def confidence_to_stars(confidence):
    """Convert confidence score (0-100) to star rating (1-5 stars)"""
    if confidence >= 90:
        return "⭐⭐⭐⭐⭐"  # 5 stars
    elif confidence >= 75:
        return "⭐⭐⭐⭐"    # 4 stars
    elif confidence >= 60:
        return "⭐⭐⭐"      # 3 stars
    elif confidence >= 45:
        return "⭐⭐"        # 2 stars
    else:
        return "⭐"          # 1 star

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
            # Fix win rate calculation - exclude void bets
            decided_bets = wins + losses  # Only count wins and losses, exclude voids
            win_rate = (wins / decided_bets) * 100 if decided_bets > 0 else 0
            total_roi = roi_percentage if roi_percentage else 0
            
            # Fix average ROI per bet - calculate mean of individual bet ROIs
            individual_roi_query = """
                SELECT (profit_loss / stake) * 100 as individual_roi 
                FROM football_opportunities 
                WHERE outcome IS NOT NULL AND outcome != '' AND outcome != 'void' AND stake > 0
            """
            cursor.execute(individual_roi_query)
            individual_rois = [row[0] for row in cursor.fetchall() if row[0] is not None]
            avg_roi_per_bet = np.mean(individual_rois) if individual_rois else 0
            
            return {
                'total_bets': total_bets,
                'wins': wins,
                'losses': losses,
                'decided_bets': decided_bets,  # Add decided bets for display
                'win_rate': win_rate,
                'total_staked': total_staked,
                'total_payout': total_payout,
                'net_profit': net_profit,
                'total_roi': total_roi,
                'avg_roi_per_bet': avg_roi_per_bet,
                'recent_results': recent_df
            }
        
        return {'total_bets': 0, 'wins': 0, 'losses': 0, 'decided_bets': 0, 'win_rate': 0,
                'total_staked': 0, 'total_payout': 0, 'net_profit': 0,
                'total_roi': 0, 'avg_roi_per_bet': 0, 'recent_results': pd.DataFrame()}
    
    except Exception as e:
        st.error(f"Performance data error: {e}")
        return {'total_bets': 0, 'wins': 0, 'losses': 0, 'decided_bets': 0, 'win_rate': 0,
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

# Current Betting Opportunities Section
st.header("🎯 Current Betting Opportunities")
st.markdown("**Live opportunities updated every few minutes**")

# Get current opportunities from last 30 minutes
@st.cache_data(ttl=30)  # Cache for 30 seconds only
def load_current_opportunities():
    try:
        conn = sqlite3.connect('data/real_football.db')
        # Get opportunities from last 30 minutes
        thirty_min_ago = datetime.now().timestamp() - (30 * 60)
        query = f"""
        SELECT home_team, away_team, selection, odds, edge_percentage, confidence, 
               stake, league, xg_home, xg_away, datetime(timestamp, 'unixepoch', 'localtime') as created_time,
               CASE 
                   WHEN outcome = 'win' THEN '✅ Win'
                   WHEN outcome = 'loss' THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 LIVE'
               END as status
        FROM football_opportunities 
        WHERE timestamp >= {thirty_min_ago}
        ORDER BY timestamp DESC 
        LIMIT 20
        """
        current_df = pd.read_sql_query(query, conn)
        conn.close()
        return current_df
    except Exception as e:
        st.error(f"Error loading current opportunities: {e}")
        return pd.DataFrame()

current_opps = load_current_opportunities()

if not current_opps.empty:
    st.success(f"🔥 **{len(current_opps)} LIVE betting opportunities** found in the last 30 minutes!")
    
    # Display current opportunities in cards
    for idx, row in current_opps.head(8).iterrows():  # Show top 8 current bets
        with st.container():
            st.markdown(f"""
            <div style="
                border: 3px solid #ff6b35;
                border-radius: 15px;
                padding: 20px;
                margin: 15px 0;
                background: linear-gradient(135deg, #fff8f0 0%, #ffe8d6 100%);
                box-shadow: 0 4px 6px rgba(255, 107, 53, 0.1);
            ">
            """, unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            
            with col1:
                st.markdown(f"### 🔥 {row['home_team']} vs {row['away_team']}")
                st.markdown(f"**🎯 {row['selection']}** @ **{row['odds']:.2f}**")
                st.markdown(f"⚽ xG: {row.get('xg_home', 'N/A')} - {row.get('xg_away', 'N/A')}")
            
            with col2:
                confidence_stars = confidence_to_stars(row['confidence'])
                st.metric("🎯 Confidence", f"{confidence_stars}", f"{row['confidence']}/100")
                st.metric("📈 Edge", f"{row['edge_percentage']:.1f}%")
            
            with col3:
                st.metric("💰 Stake", f"${row['stake']:.2f}")
                potential_win = (row['odds'] - 1) * row['stake']
                st.metric("🏆 Potential Win", f"${potential_win:.2f}")
            
            with col4:
                st.markdown(f"**Status:** {row['status']}")
                st.markdown(f"**League:** {row['league']}")
                st.markdown(f"**⏰ Found:** {row['created_time'].split(' ')[1][:5]}")
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    # Quick action summary
    total_stake = current_opps['stake'].sum()
    avg_edge = current_opps['edge_percentage'].mean()
    st.markdown(f"""### 📊 Current Session Summary
    - **Total opportunities**: {len(current_opps)}
    - **Total recommended stakes**: ${total_stake:.2f}
    - **Average edge**: {avg_edge:.1f}%
    - **Status**: 🔥 All opportunities are LIVE and ready to bet!
    """)

else:
    st.info("⏳ **No current opportunities** - System is analyzing matches for new betting opportunities...")
    st.markdown("""### 🎯 What's Next?
    - The AI is constantly analyzing matches for new opportunities
    - New bets with 1.7+ odds and good edges will appear here
    - Check back in a few minutes for fresh opportunities!
    """)

st.markdown("---")

# Performance Section
if performance['total_bets'] > 0:
    st.header("📈 Track Record & ROI")
    
    perf_col1, perf_col2, perf_col3, perf_col4, perf_col5 = st.columns(5)
    
    with perf_col1:
        st.metric("🎯 Win Rate", f"{performance['win_rate']:.1f}%", 
                 f"{performance['wins']}/{performance['decided_bets']} decided")
    
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
    
    # ROI and Performance Charts
    st.header("📈 ROI & Performance Visualization")
    
    # Check if we have any completed bets for charts
    conn = sqlite3.connect('data/real_football.db')
    completed_bets_query = """
        SELECT home_team, away_team, selection, odds, stake, outcome, profit_loss, 
               datetime(timestamp, 'unixepoch', 'localtime') as bet_date,
               updated_at
        FROM football_opportunities 
        WHERE outcome IS NOT NULL AND outcome != ''
        ORDER BY timestamp
    """
    completed_df = pd.read_sql_query(completed_bets_query, conn)
    conn.close()
    
    if not completed_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Win/Loss Distribution Pie Chart
            win_loss_counts = completed_df['outcome'].value_counts()
            fig_pie = px.pie(
                values=win_loss_counts.values,
                names=win_loss_counts.index,
                title="🏆 Win/Loss Distribution",
                color_discrete_map={'win': '#28a745', 'loss': '#dc3545', 'void': '#6c757d'}
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie)
        
        with col2:
            # Profit/Loss per Bet Bar Chart
            fig_bar = px.bar(
                completed_df,
                x=range(len(completed_df)),
                y='profit_loss',
                title="💰 Profit/Loss per Bet",
                color='profit_loss',
                color_continuous_scale=['red', 'yellow', 'green'],
                labels={'x': 'Bet Number', 'profit_loss': 'Profit/Loss ($)'}
            )
            fig_bar.update_layout(xaxis_title="Bet Number", showlegend=False)
            st.plotly_chart(fig_bar)
        
        # Cumulative ROI and Bankroll Progression
        # Handle NaN values before cumulative calculations
        completed_df['profit_loss'] = completed_df['profit_loss'].fillna(0)
        completed_df['stake'] = completed_df['stake'].fillna(0)
        
        completed_df['cumulative_pl'] = completed_df['profit_loss'].cumsum()
        completed_df['cumulative_stake'] = completed_df['stake'].cumsum()
        completed_df['cumulative_roi'] = (completed_df['cumulative_pl'] / completed_df['cumulative_stake']) * 100
        
        col3, col4 = st.columns(2)
        
        with col3:
            # Cumulative ROI Line Chart
            fig_roi = px.line(
                completed_df,
                x=range(len(completed_df)),
                y='cumulative_roi',
                title="📈 ROI Progression",
                labels={'x': 'Bet Number', 'cumulative_roi': 'Cumulative ROI (%)'}
            )
            fig_roi.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_roi.update_traces(line_color='#007bff', line_width=3)
            fig_roi.update_layout(xaxis_title="Bet Number")
            st.plotly_chart(fig_roi)
        
        with col4:
            # Bankroll Growth Chart
            initial_bankroll = 1000  # Assume $1000 starting bankroll
            completed_df['bankroll'] = initial_bankroll + completed_df['cumulative_pl']
            
            fig_bankroll = px.line(
                completed_df,
                x=range(len(completed_df)),
                y='bankroll',
                title="🏦 Bankroll Progression",
                labels={'x': 'Bet Number', 'bankroll': 'Bankroll ($)'}
            )
            fig_bankroll.add_hline(y=initial_bankroll, line_dash="dash", line_color="gray", annotation_text="Starting Bankroll")
            fig_bankroll.update_traces(line_color='#28a745', line_width=3)
            fig_bankroll.update_layout(xaxis_title="Bet Number")
            st.plotly_chart(fig_bankroll)
        
        # Monthly Performance Summary
        if len(completed_df) > 1:
            st.subheader("📅 Monthly Performance")
            
            # Convert bet_date to datetime and extract month
            completed_df['bet_date'] = pd.to_datetime(completed_df['bet_date'])
            completed_df['month'] = completed_df['bet_date'].dt.to_period('M')
            
            monthly_stats = completed_df.groupby('month').agg({
                'profit_loss': ['sum', 'count'],
                'stake': 'sum',
                'outcome': [lambda x: (x == 'win').sum(), lambda x: ((x == 'win') | (x == 'loss')).sum()]
            }).round(2)
            
            monthly_stats.columns = ['Total P&L', 'Total Bets', 'Total Stake', 'Wins', 'Decided Bets']
            # Fix monthly win rate calculation - exclude voids
            monthly_stats['Win Rate %'] = (monthly_stats['Wins'] / monthly_stats['Decided Bets'] * 100).round(1)
            monthly_stats['ROI %'] = (monthly_stats['Total P&L'] / monthly_stats['Total Stake'] * 100).round(1)
            
            st.dataframe(monthly_stats)
    
    else:
        # Show empty state with example charts
        st.info("📈 **ROI tracking will appear here once you have completed bets!**")
        
        col1, col2 = st.columns(2)
        with col1:
            # Example Win/Loss chart
            example_data = pd.DataFrame({
                'Outcome': ['Wins', 'Losses'],
                'Count': [0, 0]
            })
            fig_example = px.pie(
                example_data, 
                values='Count', 
                names='Outcome',
                title="🏆 Win/Loss Distribution (No Data Yet)"
            )
            st.plotly_chart(fig_example)
        
        with col2:
            # Example ROI chart
            example_roi = pd.DataFrame({
                'Bet': [1, 2, 3, 4, 5],
                'ROI': [0, 0, 0, 0, 0]
            })
            fig_roi_example = px.line(
                example_roi,
                x='Bet',
                y='ROI',
                title="📈 ROI Progression (No Data Yet)"
            )
            fig_roi_example.add_hline(y=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig_roi_example)
        
        st.markdown("""
        **🎯 Track Your Performance:**
        - Win/Loss distribution pie chart
        - ROI progression over time
        - Profit/Loss per bet
        - Bankroll growth tracking
        - Monthly performance summaries
        
        *Start placing bets and results will automatically populate these charts!*
        """)
    
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
        avg_stars = confidence_to_stars(avg_conf)
        st.metric("Average Confidence", f"{avg_stars} ({avg_conf:.0f})")
    
    with col4:
        total_stake = df['stake'].sum() if 'stake' in df.columns else 0
        st.metric("Total Stakes", f"${total_stake:.2f}")

    st.markdown("---")
    
    # Show recent opportunities with better visibility
    st.subheader("🎯 Today's Betting Opportunities")
    
    # Display each opportunity as a prominent card
    for idx, row in df.head(10).iterrows():
        # Get status styling
        status = row.get('bet_status', '⏳ Pending')
        status_str = str(status) if status is not None else '⏳ Pending'
        if '✅' in status_str:
            card_color = "#d4edda"  # Light green
            border_color = "#28a745" # Green
        elif '❌' in status_str:
            card_color = "#f8d7da"  # Light red  
            border_color = "#dc3545" # Red
        else:
            card_color = "#fff3cd"  # Light yellow
            border_color = "#ffc107" # Yellow
        
        # Create prominent bet card
        with st.container():
            st.markdown(f"""
            <div style="
                border: 2px solid {border_color};
                border-radius: 10px;
                padding: 15px;
                margin: 10px 0;
                background-color: {card_color};
            ">
            """, unsafe_allow_html=True)
            
            # Main bet info in large text
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            
            with col1:
                st.markdown(f"### ⚽ {row['home_team']} vs {row['away_team']}")
                st.markdown(f"**🎯 {row['selection']}** @ **{row['odds']:.2f}**")
                match_date = row.get('match_date', '')
                if pd.notna(match_date) and str(match_date) != '' and str(match_date) != 'nan':
                    kickoff = row.get('kickoff_time', '')
                    if kickoff and str(kickoff) != '' and str(kickoff) != 'nan':
                        st.markdown(f"📅 {match_date} ⏰ **{kickoff}**")
                    else:
                        st.markdown(f"📅 {match_date}")
            
            with col2:
                confidence_stars = confidence_to_stars(row['confidence'])
                st.metric("Confidence", f"{confidence_stars}", f"{row['confidence']}/100")
                st.metric("Edge", f"{row['edge_percentage']:.1f}%")
            
            with col3:
                st.metric("Stake", f"${row['stake']:.2f}")
                pl_value = row.get('profit_loss', 0)
                if pd.notna(pl_value) and pl_value != 0 and not pd.isna(pl_value):
                    st.metric("P&L", f"${pl_value:+.2f}", f"{(pl_value/row['stake']*100):+.1f}%")
                else:
                    st.metric("Potential Win", f"${(row['odds']-1)*row['stake']:.2f}")
            
            with col4:
                st.markdown(f"**Status:** {status}")
                st.markdown(f"**League:** {row['league']}")
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    # Quick overview table
    st.markdown("---")
    st.subheader("📊 Quick Overview Table")
    
    if not df.empty:
        # Create a clean summary table
        summary_data = []
        for idx, row in df.iterrows():
            confidence_stars = confidence_to_stars(row['confidence'])
            summary_data.append({
                'Match': f"{row['home_team']} vs {row['away_team']}",
                'Date/Time': f"{row.get('match_date', 'TBD')} {row.get('kickoff_time', '')}".strip(),
                'Bet': row['selection'],
                'Odds': f"{row['odds']:.2f}",
                'Confidence': f"{confidence_stars} ({row['confidence']})",
                'Edge': f"{row['edge_percentage']:.1f}%",
                'Stake': f"${row['stake']:.2f}",
                'Status': row.get('bet_status', '⏳ Pending'),
                'P&L': f"${row.get('profit_loss', 0):+.2f}" if pd.notna(row.get('profit_loss', 0)) and row.get('profit_loss', 0) != 0 and not pd.isna(row.get('profit_loss', 0)) else "Pending"
            })
        
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, hide_index=True)

# Footer
st.markdown("---")
st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.markdown("**Real Football Champion** - Advanced AI Football Analytics")