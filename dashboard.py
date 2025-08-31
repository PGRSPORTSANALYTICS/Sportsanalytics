import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import time
import os
from datetime import datetime, timezone
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
auto_refresh = st.sidebar.checkbox("Auto Refresh (10s)", value=False)

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
    "📊 Live Overview", 
    "🎲 Active Bets", 
    "💹 Performance", 
    "📋 Suggestions", 
    "⚙️ Risk Management"
])

with tab1:
    st.subheader("📊 Live Market Overview")
    
    # Current matches section
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### 🏆 Current Matches")
        if not active_tickets.empty:
            # Group active tickets by match
            match_summary = active_tickets.groupby(['match_id', 'home', 'away', 'league']).agg({
                'stake': 'sum',
                'market_name': 'count',
                'odds': 'mean'
            }).round(2)
            match_summary.columns = ['Total Stake', 'Active Bets', 'Avg Odds']
            match_summary = match_summary.reset_index()
            match_summary['Match'] = match_summary['home'] + ' vs ' + match_summary['away']
            
            st.dataframe(
                match_summary[['Match', 'league', 'Active Bets', 'Total Stake', 'Avg Odds']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No active matches with open positions")
    
    with col2:
        st.markdown("#### 📊 Risk Distribution")
        if not active_tickets.empty:
            # Risk by market type
            market_risk = active_tickets.groupby('market_name')['stake'].sum().reset_index()
            fig_risk = px.pie(
                market_risk, 
                values='stake', 
                names='market_name',
                title="Risk by Market Type"
            )
            fig_risk.update_layout(height=300)
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            st.info("No active risk to display")
    
    # Recent activity
    st.markdown("#### 📈 Recent Activity")
    if not recent_suggestions.empty:
        # Show last 5 suggestions
        display_cols = ['ts_formatted', 'match_title', 'market_name', 'odds', 'stake', 'edge_abs', 'edge_rel']
        recent_display = recent_suggestions[display_cols].head(5)
        recent_display.columns = ['Time', 'Match', 'Market', 'Odds', 'Stake', 'EV %', 'Edge %']
        st.dataframe(recent_display, use_container_width=True, hide_index=True)
    else:
        st.info("No recent suggestions")

with tab2:
    st.subheader("🎲 Active Betting Positions")
    
    if not active_tickets.empty:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Active bets table
            display_tickets = active_tickets.copy()
            display_tickets['Match'] = display_tickets['home'] + ' vs ' + display_tickets['away']
            display_tickets['Open Time'] = pd.to_datetime(display_tickets['open_ts'], unit='s').dt.strftime('%H:%M:%S')
            display_tickets['Potential Win'] = (display_tickets['odds'] - 1) * display_tickets['stake']
            
            cols_to_show = ['Open Time', 'Match', 'League', 'market_name', 'odds', 'stake', 'Potential Win']
            display_df = display_tickets[cols_to_show].round(2)
            display_df.columns = ['Open Time', 'Match', 'League', 'Market', 'Odds', 'Stake', 'Potential Win']
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        
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
    st.subheader("📋 Betting Suggestions History")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        days_filter = st.selectbox("Time Period", [1, 3, 7, 30], index=2)
    with col2:
        market_filter = st.selectbox("Market", ["All"] + data_loader.get_available_markets())
    with col3:
        min_edge_filter = st.slider("Min Edge %", 0.0, 20.0, 0.0, 0.5)
    
    # Get filtered suggestions
    suggestions_df = data_loader.get_suggestions(
        days=days_filter,
        market_filter=market_filter if market_filter != "All" else None,
        min_edge=min_edge_filter/100
    )
    
    if not suggestions_df.empty:
        # Summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Suggestions", len(suggestions_df))
        with col2:
            st.metric("Avg Edge", f"{suggestions_df['edge_rel'].mean()*100:.1f}%")
        with col3:
            st.metric("Avg EV", f"{suggestions_df['edge_abs'].mean()*100:.1f}%")
        with col4:
            st.metric("Total Stake", f"${suggestions_df['stake'].sum():.2f}")
        
        # Suggestions table
        st.markdown("#### 📋 Detailed Suggestions")
        display_suggestions = suggestions_df.copy()
        display_suggestions['Edge %'] = (display_suggestions['edge_rel'] * 100).round(1)
        display_suggestions['EV %'] = (display_suggestions['edge_abs'] * 100).round(1)
        
        cols_to_show = [
            'ts_formatted', 'match_title', 'market_name', 'odds', 
            'stake', 'EV %', 'Edge %', 'model_prob', 'implied_prob'
        ]
        display_df = display_suggestions[cols_to_show]
        display_df.columns = [
            'Time', 'Match', 'Market', 'Odds', 
            'Stake', 'EV %', 'Edge %', 'Model Prob', 'Implied Prob'
        ]
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Edge distribution chart
        st.markdown("#### 📊 Edge Distribution")
        fig_edge = px.histogram(
            suggestions_df, 
            x='edge_rel', 
            nbins=20,
            title="Distribution of Relative Edge",
            labels={'edge_rel': 'Relative Edge', 'count': 'Frequency'}
        )
        fig_edge.update_xaxes(tickformat='.1%')
        st.plotly_chart(fig_edge, use_container_width=True)
    else:
        st.info("📋 No suggestions match the current filters")

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
st.markdown(
    "🤖 **E-Soccer Betting Bot Dashboard** | "
    f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    "Auto-refresh: " + ("✅ Enabled" if auto_refresh else "❌ Disabled")
)

# Auto-refresh timer (runs every 10 seconds when enabled)
if auto_refresh:
    time.sleep(10)
    st.rerun()
