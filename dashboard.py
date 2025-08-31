import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import time
import os
from datetime import datetime, timezone
import pytz
from pathlib import Path

from data_loader import DataLoader
from charts import ChartGenerator

# Page configuration
st.set_page_config(
    page_title="E-Soccer Betting Bot Dashboard",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize data loader
@st.cache_resource
def get_data_loader():
    return DataLoader()

data_loader = get_data_loader()
chart_generator = ChartGenerator()

# Auto-refresh functionality  
auto_refresh = st.sidebar.checkbox("Auto Refresh (2 min)", value=True)

# Manual refresh button
if st.sidebar.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()

# Export functionality
st.sidebar.markdown("### 📊 Export Data")
if st.sidebar.button("Export All Data"):
    try:
        # Create exports directory
        export_dir = Path("exports")
        export_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export all data
        suggestions_df = data_loader.get_suggestions()
        tickets_df = data_loader.get_tickets()
        pnl_df = data_loader.get_pnl_history()
        
        suggestions_df.to_csv(export_dir / f"suggestions_{timestamp}.csv", index=False)
        tickets_df.to_csv(export_dir / f"tickets_{timestamp}.csv", index=False)
        pnl_df.to_csv(export_dir / f"pnl_{timestamp}.csv", index=False)
        
        st.sidebar.success(f"✅ Data exported to exports/ folder")
    except Exception as e:
        st.sidebar.error(f"❌ Export failed: {str(e)}")

# Main dashboard
st.title("⚽ E-Soccer Betting Bot Dashboard")
st.markdown("---")

# Get current data
current_stats = data_loader.get_current_stats()
active_tickets = data_loader.get_active_tickets()
recent_suggestions = data_loader.get_recent_suggestions(limit=10)
pnl_history = data_loader.get_pnl_history()

# Key metrics row
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "💰 Current Bankroll",
        f"${current_stats['bankroll']:.2f}",
        f"{current_stats['bankroll_change']:+.2f}"
    )

with col2:
    st.metric(
        "🎯 Active Bets",
        current_stats['active_bets'],
        f"{current_stats['new_bets_today']:+d} today"
    )

with col3:
    st.metric(
        "📊 Total Risk",
        f"${current_stats['total_risk']:.2f}",
        f"{current_stats['risk_percentage']:.1f}% of bankroll"
    )

with col4:
    st.metric(
        "📈 Today's P&L",
        f"${current_stats['daily_pnl']:+.2f}",
        f"{current_stats['daily_pnl_percentage']:+.1f}%"
    )

with col5:
    win_rate = current_stats['win_rate']
    st.metric(
        "🎯 Win Rate",
        f"{win_rate:.1f}%",
        f"{current_stats['total_settled']} settled"
    )

st.markdown("---")

# Main content tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 What to Bet", 
    "🎲 Active Bets", 
    "💹 Performance", 
    "📋 History", 
    "⚙️ Risk Management"
])

with tab1:
    st.subheader("🔴 LIVE Betting Opportunities - Right Now!")
    
    # Get only LIVE/ACTIVE suggestions (last 5 minutes)
    current_time = time.time()
    five_minutes_ago = current_time - 300  # 5 minutes
    latest_suggestions = data_loader.get_recent_suggestions(limit=20)
    
    # Filter to only very recent (live) suggestions
    if not latest_suggestions.empty and 'ts' in latest_suggestions.columns:
        live_suggestions = latest_suggestions[latest_suggestions['ts'] > five_minutes_ago]
    else:
        live_suggestions = latest_suggestions
    
    if not live_suggestions.empty:
        # Filter only over/under goal markets from LIVE suggestions
        goal_markets = live_suggestions[live_suggestions['market_name'].str.contains('Over', na=False)]
        
        if not goal_markets.empty:
            # Show live status indicator
            if 'ts' in goal_markets.columns and len(goal_markets) > 0:
                minutes_since = int((current_time - goal_markets['ts'].max()) / 60)
            else:
                minutes_since = 0
            if minutes_since < 1:
                live_status = "🔴 **LIVE NOW** - Fresh opportunities!"
            elif minutes_since < 3:
                live_status = f"🟡 **{minutes_since}m ago** - Still fresh"
            else:
                live_status = f"🟠 **{minutes_since}m ago** - Check if still available"
            
            st.markdown(f"### 🔥 {live_status}")
            st.markdown("**⚡ Lightning-fast betting opportunities happening RIGHT NOW!**")
            
            # Show each LIVE suggestion as a prominent card
            for idx, row in goal_markets.head(8).iterrows():  # Show more live opportunities
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    
                    with col1:
                        # Add LIVE indicator
                        if 'ts' in goal_markets.columns:
                            age_minutes = int((current_time - row['ts']) / 60)
                            if age_minutes < 1:
                                live_badge = "🔴 LIVE"
                            elif age_minutes < 3:
                                live_badge = f"🟡 {age_minutes}m"
                            else:
                                live_badge = f"🟠 {age_minutes}m"
                        else:
                            live_badge = "🔴 LIVE"
                        
                        # Add game time info and match start time
                        if 'elapsed' in row and row['elapsed'] is not None:
                            game_minutes = int(row['elapsed'] / 60)
                            game_seconds = int(row['elapsed'] % 60)
                            game_time = f"⏱️ {game_minutes}:{game_seconds:02d}"
                            
                            # Calculate match start time
                            match_start_ts = row['ts'] - row['elapsed']
                            stockholm_tz = pytz.timezone('Europe/Stockholm')
                            match_start_time = pd.to_datetime(match_start_ts, unit='s', utc=True).tz_convert(stockholm_tz).strftime('%H:%M')
                            start_display = f"🕐 Started {match_start_time}"
                        else:
                            game_time = "⏱️ --:--"
                            start_display = "🕐 --:--"
                        
                        # Add score if available
                        if 'score' in row and row['score'] is not None:
                            score_display = f"📊 {row['score']}"
                        else:
                            score_display = "📊 0-0"
                        
                        st.markdown(f"{live_badge} **⚽ {row['match_title']}**")
                        st.markdown(f"*{row['league']}*")
                        st.markdown(f"{start_display} | {game_time} | {score_display}")
                    
                    with col2:
                        st.markdown("**Market**")
                        st.markdown(f"🎯 **{row['market_name']}**")
                    
                    with col3:
                        st.markdown("**Odds & Stake**")
                        st.markdown(f"📊 **{row['odds']:.2f}**")
                        st.markdown(f"💰 **${row['stake']:.0f}**")
                    
                    with col4:
                        edge_pct = row['edge_rel'] * 100
                        ev_pct = row['edge_abs'] * 100
                        st.markdown("**Edge**")
                        if edge_pct > 15:
                            st.markdown(f"🔥 **{edge_pct:.1f}%**")
                        elif edge_pct > 8:
                            st.markdown(f"⚡ **{edge_pct:.1f}%**")
                        else:
                            st.markdown(f"✅ **{edge_pct:.1f}%**")
                        st.markdown(f"EV: {ev_pct:.1f}%")
                    
                    st.markdown(f"*⏱️ {row['ts_formatted']} Stockholm time*")
                    st.markdown("---")
            
            # LIVE Summary section
            st.markdown("### 📊 **LIVE Opportunities Summary**")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                live_opportunities = len(goal_markets)
                st.metric("🔴 LIVE Opportunities", live_opportunities)
            
            with col2:
                avg_edge = goal_markets['edge_rel'].mean() * 100
                st.metric("📈 Avg Edge", f"{avg_edge:.1f}%")
            
            with col3:
                total_recommended_stake = goal_markets['stake'].sum()
                st.metric("💰 Total Live Stake", f"${total_recommended_stake:.0f}")
            
            with col4:
                high_value_bets = len(goal_markets[goal_markets['edge_rel'] > 0.15])  # Higher threshold for live
                st.metric("🔥 High Value LIVE", high_value_bets)
            
        else:
            st.warning("⏳ No LIVE over/under opportunities right now")
            st.info("🔍 Bot scans every 2 minutes - check back soon!")
    else:
        st.info("🔍 Bot is scanning for LIVE opportunities... New bets coming soon!")
        
    # Add refresh notice for live data
    st.markdown("---")
    st.markdown("🔄 **Live updates every 10 seconds** | Bot finds new opportunities every 2 minutes")
    
    # LIVE Market focus info  
    st.markdown("### 🎯 **LIVE E-Soccer Markets (TotalCorner Data)**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("**Over 4.5** 🔥\n*E-soccer standard*")
    with col2:
        st.markdown("**Over 5.5** ⚡\n*High value bets*")  
    with col3:
        st.markdown("**Over 6.5** 💎\n*Massive edges*")
    with col4:
        st.markdown("**Over 7.5** 🚀\n*Extreme value*")

with tab2:
    st.subheader("🎲 Active Betting Positions")
    
    if not active_tickets.empty:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Active bets table
            display_tickets = active_tickets.copy()
            display_tickets['Match'] = display_tickets['home'] + ' vs ' + display_tickets['away']
            stockholm_tz = pytz.timezone('Europe/Stockholm')
            display_tickets['Open Time'] = pd.to_datetime(display_tickets['open_ts'], unit='s', utc=True).dt.tz_convert(stockholm_tz).dt.strftime('%H:%M:%S')
            display_tickets['Potential Win'] = (display_tickets['odds'] - 1) * display_tickets['stake']
            
            cols_to_show = ['Open Time', 'Match', 'league', 'market_name', 'odds', 'stake', 'Potential Win']
            display_df = display_tickets[cols_to_show]
            # Only round numeric columns
            numeric_cols = ['odds', 'stake', 'Potential Win']
            for col in numeric_cols:
                if col in display_df.columns:
                    display_df[col] = display_df[col].round(2)
            display_df.columns = ['Open Time', 'Match', 'League', 'Market', 'Odds', 'Stake', 'Potential Win']
            
            st.dataframe(display_df, width="stretch", hide_index=True)
        
        with col2:
            # Summary stats
            total_stake = active_tickets['stake'].sum()
            total_potential = ((active_tickets['odds'] - 1) * active_tickets['stake']).sum()
            avg_odds = active_tickets['odds'].mean()
            
            st.metric("Total Stake", f"${total_stake:.2f}")
            st.metric("Potential Win", f"${total_potential:.2f}")
            st.metric("Avg Odds", f"{avg_odds:.2f}")
            
            # Market distribution
            market_dist = active_tickets['market_name'].value_counts()
            fig_markets = px.bar(
                x=market_dist.values,
                y=market_dist.index,
                orientation='h',
                title="Bets by Market",
                labels={'x': 'Count', 'y': 'Market'}
            )
            fig_markets.update_layout(height=250)
            st.plotly_chart(fig_markets, use_container_width=True)
    else:
        st.info("🎯 No active betting positions")
        st.markdown("The bot is monitoring markets but hasn't found any qualifying opportunities yet.")

with tab3:
    st.subheader("💹 Performance Analytics")
    
    if not pnl_history.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            # Bankroll chart
            fig_bankroll = chart_generator.create_bankroll_chart(pnl_history)
            st.plotly_chart(fig_bankroll, use_container_width=True)
        
        with col2:
            # PnL distribution
            all_tickets = data_loader.get_tickets()
            if not all_tickets.empty:
                settled_tickets = all_tickets[all_tickets['is_settled'] == 1].copy()
            else:
                settled_tickets = pd.DataFrame()
            
            if not settled_tickets.empty:
                fig_pnl = chart_generator.create_pnl_distribution(settled_tickets)
                st.plotly_chart(fig_pnl, use_container_width=True)
            else:
                st.info("No settled bets for PnL distribution")
        
        # Performance metrics table
        st.markdown("#### 📊 Performance Breakdown")
        
        if not settled_tickets.empty:
            perf_metrics = chart_generator.calculate_performance_metrics(settled_tickets)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Bets", perf_metrics['total_bets'])
                st.metric("Win Rate", f"{perf_metrics['win_rate']:.1f}%")
            with col2:
                st.metric("Total PnL", f"${perf_metrics['total_pnl']:+.2f}")
                st.metric("Avg Bet Size", f"${perf_metrics['avg_stake']:.2f}")
            with col3:
                st.metric("ROI", f"{perf_metrics['roi']:.1f}%")
                st.metric("Avg Win", f"${perf_metrics['avg_win']:.2f}")
        
        # Daily performance
        if len(pnl_history) > 1:
            st.markdown("#### 📅 Daily Performance Trend")
            fig_daily = chart_generator.create_daily_performance_chart(pnl_history)
            st.plotly_chart(fig_daily, use_container_width=True)
    else:
        st.info("📊 No performance data available yet")

with tab4:
    st.subheader("📋 Over/Under Goals Betting History")
    
    # Filters focused on goal markets
    col1, col2, col3 = st.columns(3)
    with col1:
        days_filter = st.selectbox("Time Period", [1, 3, 7, 30], index=2)
    with col2:
        goal_markets = ["All", "Over 0.5", "Over 1.5", "Over 2.5", "Over 3.5"]
        market_filter = st.selectbox("Goal Market", goal_markets)
    with col3:
        min_edge_filter = st.slider("Min Edge %", 0.0, 25.0, 5.0, 1.0)
    
    # Get filtered suggestions for over/under markets only
    suggestions_df = data_loader.get_suggestions(
        days=days_filter,
        market_filter=market_filter if market_filter != "All" else None,
        min_edge=min_edge_filter/100
    )
    
    # Filter only over/under goal markets
    if not suggestions_df.empty:
        goal_suggestions = suggestions_df[suggestions_df['market_name'].str.contains('Over', na=False)]
    else:
        goal_suggestions = pd.DataFrame()
    
    if not goal_suggestions.empty:
        # Summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Goal Market Bets", len(goal_suggestions))
        with col2:
            st.metric("Avg Edge", f"{goal_suggestions['edge_rel'].mean()*100:.1f}%")
        with col3:
            st.metric("Total Stake", f"${goal_suggestions['stake'].sum():.0f}")
        with col4:
            high_edge = len(goal_suggestions[goal_suggestions['edge_rel'] > 0.15])
            st.metric("High Edge Bets (>15%)", high_edge)
        
        # Simplified table focused on key info
        st.markdown("#### 📋 Over/Under Goals History")
        display_suggestions = goal_suggestions.copy()
        display_suggestions['Edge %'] = (display_suggestions['edge_rel'] * 100).round(1)
        display_suggestions['EV %'] = (display_suggestions['edge_abs'] * 100).round(1)
        
        if 'ts_formatted' in display_suggestions.columns:
            cols_to_show = ['ts_formatted', 'match_title', 'market_name', 'odds', 'stake', 'Edge %']
            display_df = display_suggestions[cols_to_show]
            display_df.columns = ['Time (Stockholm)', 'Match', 'Market', 'Odds', 'Stake $', 'Edge %']
            st.dataframe(display_df, width="stretch", hide_index=True)
        
        # Market breakdown
        st.markdown("#### 📊 Goal Market Breakdown")
        market_stats = goal_suggestions.groupby('market_name').agg({
            'stake': ['count', 'sum'],
            'edge_rel': 'mean'
        }).round(2)
        market_stats.columns = ['Count', 'Total Stake', 'Avg Edge']
        st.dataframe(market_stats, use_container_width=True)
    else:
        st.info("📋 No over/under goal suggestions match the current filters")

with tab5:
    st.subheader("⚙️ Risk Management")
    
    # Current risk metrics
    risk_metrics = data_loader.get_risk_metrics()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🎯 Current Risk Exposure")
        
        # Risk gauges
        total_risk_pct = (risk_metrics['total_risk'] / risk_metrics['bankroll']) * 100
        max_total_risk_pct = float(os.getenv('MAX_TOTAL_RISK', '0.18')) * 100
        
        fig_risk_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=total_risk_pct,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Total Risk %"},
            delta={'reference': max_total_risk_pct},
            gauge={
                'axis': {'range': [None, max_total_risk_pct * 1.2]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, max_total_risk_pct * 0.7], 'color': "lightgray"},
                    {'range': [max_total_risk_pct * 0.7, max_total_risk_pct], 'color': "yellow"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': max_total_risk_pct
                }
            }
        ))
        fig_risk_gauge.update_layout(height=300)
        st.plotly_chart(fig_risk_gauge, use_container_width=True)
    
    with col2:
        st.markdown("#### 📊 Risk by Match")
        
        if not active_tickets.empty:
            match_risk = active_tickets.groupby(['home', 'away'])['stake'].sum().reset_index()
            match_risk['match'] = match_risk['home'] + ' vs ' + match_risk['away']
            match_risk = match_risk.sort_values('stake', ascending=False)
            
            fig_match_risk = px.bar(
                match_risk.head(10),
                x='stake',
                y='match',
                orientation='h',
                title="Risk by Match (Top 10)",
                labels={'stake': 'Risk ($)', 'match': 'Match'}
            )
            fig_match_risk.update_layout(height=300)
            st.plotly_chart(fig_match_risk, use_container_width=True)
        else:
            st.info("No active positions to show risk distribution")
    
    # Risk parameters
    st.markdown("#### ⚙️ Risk Parameters")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Max Total Risk", 
            f"{max_total_risk_pct:.1f}%",
            f"${risk_metrics['bankroll'] * float(os.getenv('MAX_TOTAL_RISK', '0.18')):.2f}"
        )
    with col2:
        max_per_match_pct = float(os.getenv('MAX_RISK_PER_MATCH', '0.06')) * 100
        st.metric(
            "Max Per Match", 
            f"{max_per_match_pct:.1f}%",
            f"${risk_metrics['bankroll'] * float(os.getenv('MAX_RISK_PER_MATCH', '0.06')):.2f}"
        )
    with col3:
        kelly_factor = float(os.getenv('SAFE_KELLY_FACTOR', '0.25'))
        st.metric("Kelly Factor", f"{kelly_factor:.2f}", "Conservative sizing")
    
    # Risk history
    if not pnl_history.empty:
        st.markdown("#### 📈 Risk Exposure Over Time")
        fig_risk_history = px.line(
            pnl_history,
            x='timestamp',
            y='open_risk',
            title="Risk Exposure History",
            labels={'open_risk': 'Open Risk ($)', 'timestamp': 'Time'}
        )
        st.plotly_chart(fig_risk_history, use_container_width=True)

# Footer
st.markdown("---")
stockholm_tz = pytz.timezone('Europe/Stockholm')
stockholm_time = datetime.now(stockholm_tz)
st.markdown(
    "🤖 **E-Soccer Betting Bot Dashboard** | "
    f"Last updated: {stockholm_time.strftime('%Y-%m-%d %H:%M:%S')} (Stockholm) | "
    "Auto-refresh: " + ("✅ Enabled" if auto_refresh else "❌ Disabled")
)

# Auto-refresh timer (runs every 2 minutes when enabled)
if auto_refresh:
    time.sleep(120)  # 2 minutes = 120 seconds
    st.rerun()
