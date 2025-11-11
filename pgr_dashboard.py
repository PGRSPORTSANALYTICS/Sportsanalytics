#!/usr/bin/env python3
"""
PGR SPORTS ANALYTICS DASHBOARD
Professional betting analytics platform with dark theme
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from stats_master import get_all_time_stats
from db_helper import db_helper
from launch_ramp import get_thresholds

# Page configuration
st.set_page_config(
    page_title="PGR Sports Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# PGR Dark Theme CSS
st.markdown("""
<style>
    /* Dark Background */
    .stApp {
        background: #0D1117;
        color: #C9D1D9;
    }
    
    /* Header Styling */
    .pgr-header {
        text-align: center;
        padding: 2rem 0;
        margin-bottom: 3rem;
    }
    
    .pgr-logo {
        font-size: 4rem;
        font-weight: 900;
        letter-spacing: 8px;
        color: #3FB68B;
        font-family: 'Arial Black', sans-serif;
    }
    
    .pgr-subtitle {
        font-size: 1.3rem;
        letter-spacing: 6px;
        color: #C9D1D9;
        margin-top: -10px;
    }
    
    /* Hero Metrics */
    .hero-metric {
        text-align: center;
        padding: 1rem;
    }
    
    .hero-value {
        font-size: 3.5rem;
        font-weight: 800;
        color: #3FB68B;
        line-height: 1;
    }
    
    .hero-label {
        font-size: 0.9rem;
        color: #8B949E;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 0.5rem;
    }
    
    /* Section Headers */
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #C9D1D9;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin: 2rem 0 1rem 0;
    }
    
    /* System Status Grid */
    .status-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1.5rem;
        margin: 1.5rem 0;
    }
    
    .status-item {
        padding: 1rem;
        background: #161B22;
        border-radius: 8px;
        border-left: 3px solid #3FB68B;
    }
    
    .status-label {
        color: #8B949E;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .status-value {
        color: #3FB68B;
        font-size: 1.5rem;
        font-weight: 700;
        margin-top: 0.3rem;
    }
    
    /* Bet Cards */
    .bet-card {
        background: #161B22;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        border-left: 3px solid #3FB68B;
    }
    
    .match-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #C9D1D9;
    }
    
    .bet-detail {
        color: #8B949E;
        font-size: 0.9rem;
        margin-top: 0.3rem;
    }
    
    .profit-positive {
        color: #3FB68B;
        font-weight: 700;
    }
    
    .profit-negative {
        color: #F85149;
        font-weight: 700;
    }
    
    /* Hide Streamlit branding and sidebar */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}
    section[data-testid="stSidebar"] {display: none;}
    
    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 3.5rem;
        color: #3FB68B;
    }
    
    [data-testid="stMetricLabel"] {
        color: #8B949E;
    }
</style>
""", unsafe_allow_html=True)

def get_rolling_roi_data(days=30):
    """Get daily ROI data for the rolling chart"""
    # Get all settled bets from last 30 days
    query = """
        SELECT 
            DATE(TO_TIMESTAMP(settled_timestamp)) as bet_date,
            market,
            profit_loss,
            stake
        FROM (
            SELECT settled_timestamp, 'exact_score' as market, profit_loss, stake
            FROM football_opportunities
            WHERE outcome IN (%s, %s) AND settled_timestamp IS NOT NULL
            
            UNION ALL
            
            SELECT settled_timestamp, 'sgp' as market, profit_loss, stake
            FROM sgp_predictions
            WHERE outcome IN (%s, %s) AND settled_timestamp IS NOT NULL
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
        ) combined
        WHERE TO_TIMESTAMP(settled_timestamp) >= NOW() - INTERVAL '%s days'
        ORDER BY bet_date DESC
    """
    
    rows = db_helper.execute(query, ('win', 'loss', 'win', 'loss', '%Monster%', '%BEAST%', days), fetch='all')
    
    if not rows:
        return None
    
    df = pd.DataFrame(rows, columns=['bet_date', 'market', 'profit_loss', 'stake'])
    df['bet_date'] = pd.to_datetime(df['bet_date'])
    
    # Calculate cumulative ROI for each product
    df_sorted = df.sort_values('bet_date')
    
    # ES only
    df_es = df_sorted[df_sorted['market'] == 'exact_score'].copy()
    df_es['cumulative_profit'] = df_es['profit_loss'].cumsum()
    df_es['cumulative_stake'] = df_es['stake'].cumsum()
    df_es['roi'] = (df_es['cumulative_profit'] / df_es['cumulative_stake'] * 100).fillna(0)
    
    # SGP only
    df_sgp = df_sorted[df_sorted['market'] == 'sgp'].copy()
    df_sgp['cumulative_profit'] = df_sgp['profit_loss'].cumsum()
    df_sgp['cumulative_stake'] = df_sgp['stake'].cumsum()
    df_sgp['roi'] = (df_sgp['cumulative_profit'] / df_sgp['cumulative_stake'] * 100).fillna(0)
    
    # Combined
    df_combined = df_sorted.copy()
    df_combined['cumulative_profit'] = df_combined['profit_loss'].cumsum()
    df_combined['cumulative_stake'] = df_combined['stake'].cumsum()
    df_combined['roi'] = (df_combined['cumulative_profit'] / df_combined['cumulative_stake'] * 100).fillna(0)
    
    return {
        'es': df_es[['bet_date', 'roi']],
        'sgp': df_sgp[['bet_date', 'roi']],
        'combined': df_combined[['bet_date', 'roi']]
    }

def get_last_n_hit_rate(n=200):
    """Get hit rate for last N bets (ES + SGP combined)"""
    query = """
        SELECT outcome
        FROM (
            SELECT outcome, settled_timestamp
            FROM football_opportunities
            WHERE outcome IN (%s, %s)
            
            UNION ALL
            
            SELECT outcome, settled_timestamp
            FROM sgp_predictions
            WHERE outcome IN (%s, %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
        ) combined
        WHERE settled_timestamp IS NOT NULL
        ORDER BY settled_timestamp DESC
        LIMIT %s
    """
    
    rows = db_helper.execute(query, ('win', 'loss', 'win', 'loss', '%Monster%', '%BEAST%', n), fetch='all')
    
    if not rows:
        return 0.0
    
    wins = sum(1 for row in rows if row[0] == 'win')
    return (wins / len(rows) * 100) if rows else 0.0

def get_avg_odds():
    """Get average odds for ES + SGP (excluding MonsterSGP)"""
    query = """
        SELECT AVG(odds) as avg_odds
        FROM (
            SELECT odds
            FROM football_opportunities
            WHERE market = 'exact_score' AND outcome IN ('win', 'loss')
            
            UNION ALL
            
            SELECT bookmaker_odds as odds
            FROM sgp_predictions
            WHERE outcome IN ('win', 'loss')
              AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%Monster%%')
              AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%BEAST%%')
        ) combined
    """
    
    row = db_helper.execute(query, fetch='one')
    return row[0] if row and row[0] else 0.0

def get_last_50_roi():
    """Get ROI for last 50 bets"""
    query = """
        WITH last_bets AS (
            SELECT profit_loss, stake, settled_timestamp
            FROM (
                SELECT profit_loss, stake, settled_timestamp
                FROM football_opportunities
                WHERE outcome IN (%s, %s)
                
                UNION ALL
                
                SELECT profit_loss, stake, settled_timestamp
                FROM sgp_predictions
                WHERE outcome IN (%s, %s)
                  AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
                  AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
            ) all_bets
            WHERE settled_timestamp IS NOT NULL
            ORDER BY settled_timestamp DESC
            LIMIT 50
        )
        SELECT 
            SUM(profit_loss) as profit,
            SUM(stake) as staked
        FROM last_bets
    """
    
    row = db_helper.execute(query, ('win', 'loss', 'win', 'loss', '%Monster%', '%BEAST%'), fetch='one')
    
    if row and row[0] is not None and row[1] and row[1] > 0:
        return (row[0] / row[1] * 100)
    return 0.0

def get_upcoming_bets(limit=3):
    """Get upcoming bets that haven't been played yet"""
    query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, match_date
        FROM football_opportunities
        WHERE market = %s
          AND outcome IS NULL
          AND match_date >= CURRENT_DATE::text
        ORDER BY match_date ASC, edge_percentage DESC
        LIMIT %s
    """
    
    rows = db_helper.execute(query, ('exact_score', limit), fetch='all')
    
    if not rows:
        return []
    
    bets = []
    for row in rows:
        bets.append({
            'match': f"{row[0]} – {row[1]}",
            'selection': row[2],
            'odds': row[3],
            'ev': row[4] if row[4] else 0
        })
    
    return bets

def get_last_settled(limit=3):
    """Get last settled bets"""
    query = """
        SELECT 
            home_team, away_team, selection, odds, outcome, profit_loss, market
        FROM (
            SELECT 
                home_team, away_team, selection, odds, outcome, profit_loss, 
                %s as market, settled_timestamp
            FROM football_opportunities
            WHERE outcome IN (%s, %s)
            
            UNION ALL
            
            SELECT 
                home_team, away_team, parlay_description, bookmaker_odds, 
                outcome, profit_loss, %s, settled_timestamp
            FROM sgp_predictions
            WHERE outcome IN (%s, %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
        ) combined
        WHERE settled_timestamp IS NOT NULL
        ORDER BY settled_timestamp DESC
        LIMIT %s
    """
    
    rows = db_helper.execute(query, ('Exact Score', 'win', 'loss', 'SGP', 'win', 'loss', '%Monster%', '%BEAST%', limit), fetch='all')
    
    if not rows:
        return []
    
    bets = []
    for row in rows:
        bets.append({
            'match': f"{row[0]}–{row[1]}",
            'selection': row[2] if len(row[2]) < 40 else row[2][:37] + "...",
            'odds': row[3],
            'won': row[4] == 'win',
            'profit': row[5],
            'market': row[6]
        })
    
    return bets

# ============================================================================
# MAIN DASHBOARD
# ============================================================================

# Header
st.markdown("""
<div class="pgr-header">
    <div class="pgr-logo">PGR</div>
    <div class="pgr-subtitle">SPORTS ANALYTICS</div>
</div>
""", unsafe_allow_html=True)

# Get all-time stats
stats = get_all_time_stats()
total_roi = (stats['combined']['profit'] / (stats['combined']['total'] * 100)) * 100 if stats['combined']['total'] > 0 else 0
hit_rate_200 = get_last_n_hit_rate(200)
avg_odds = get_avg_odds()

# Hero Metrics
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"""
    <div class="hero-metric">
        <div class="hero-value">{total_roi:+.1f}%</div>
        <div class="hero-label">Total ROI</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="hero-metric">
        <div class="hero-value">{hit_rate_200:.1f}%</div>
        <div class="hero-label">Hit Rate<br>(Last 200)</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="hero-metric">
        <div class="hero-value">{avg_odds:.1f}x</div>
        <div class="hero-label">Exact Score + SGP</div>
    </div>
    """, unsafe_allow_html=True)

# ROI Development Chart
st.markdown('<div class="section-header">ROI DEVELOPMENT <span style="color: #8B949E; float: right; font-size: 0.9rem;">Last 30 days ›</span></div>', unsafe_allow_html=True)

roi_data = get_rolling_roi_data(30)

if roi_data:
    fig = go.Figure()
    
    # ES line (green)
    if not roi_data['es'].empty:
        fig.add_trace(go.Scatter(
            x=roi_data['es']['bet_date'],
            y=roi_data['es']['roi'],
            name='Exact Score',
            line=dict(color='#3FB68B', width=3),
            mode='lines'
        ))
    
    # SGP line (blue)
    if not roi_data['sgp'].empty:
        fig.add_trace(go.Scatter(
            x=roi_data['sgp']['bet_date'],
            y=roi_data['sgp']['roi'],
            name='SGP',
            line=dict(color='#58A6FF', width=3),
            mode='lines'
        ))
    
    # Combined line (orange)
    if not roi_data['combined'].empty:
        fig.add_trace(go.Scatter(
            x=roi_data['combined']['bet_date'],
            y=roi_data['combined']['roi'],
            name='Combined',
            line=dict(color='#D29922', width=3),
            mode='lines'
        ))
    
    fig.update_layout(
        plot_bgcolor='#0D1117',
        paper_bgcolor='#0D1117',
        font=dict(color='#C9D1D9', size=11),
        xaxis=dict(
            showgrid=True,
            gridcolor='#21262D',
            zeroline=False
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#21262D',
            zeroline=True,
            zerolinecolor='#30363D',
            ticksuffix='%'
        ),
        hovermode='x unified',
        margin=dict(l=0, r=0, t=20, b=0),
        height=300,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough data for ROI development chart (need settled bets)")

st.markdown('<div style="text-align: center; color: #8B949E; font-size: 0.85rem; margin-top: -1rem;">AI adjusts parameters daily – more bets, more precision.</div>', unsafe_allow_html=True)

# System Status
st.markdown('<div class="section-header">SYSTEM STATUS</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    <div class="status-item">
        <div class="status-label">🟢 DATA FEED</div>
        <div class="status-value">API Football & OddsAPI</div>
        <div style="color: #8B949E; font-size: 0.8rem;">active</div>
    </div>
    """, unsafe_allow_html=True)
    
    last_50_roi = get_last_50_roi()
    st.markdown(f"""
    <div class="status-item">
        <div class="status-label">🟢 LAST 50 ROI</div>
        <div class="status-value">{last_50_roi:+.1f}%</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    confidence_score = min(5, int((stats['combined']['total'] / 100) + 1)) if stats['combined']['total'] > 0 else 1
    st.markdown(f"""
    <div class="status-item">
        <div class="status-label">🔵 MODEL CONFIDENCE</div>
        <div class="status-value">{confidence_score}/5</div>
    </div>
    """, unsafe_allow_html=True)
    
    es_threshold = get_thresholds('ES')
    sgp_threshold = get_thresholds('SGP')
    st.markdown(f"""
    <div class="status-item">
        <div class="status-label">🟢 EV THRESHOLD</div>
        <div class="status-value">{es_threshold['ev_min']:.2f} (Exact Score)</div>
        <div style="color: #58A6FF; margin-top: 0.3rem; font-size: 1.1rem; font-weight: 600;">{sgp_threshold['ev_min']:.2f} (SGP)</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div style="color: #8B949E; font-size: 0.85rem; margin-top: 1rem;">When the system pauses, it protects your bankroll – not its ego.</div>', unsafe_allow_html=True)

# Upcoming Bets & Last Settled
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">UPCOMING BETS</div>', unsafe_allow_html=True)
    upcoming = get_upcoming_bets(3)
    
    if upcoming:
        for bet in upcoming:
            st.markdown(f"""
            <div class="bet-card">
                <div class="match-title">{bet['match']}</div>
                <div class="bet-detail">
                    {bet['selection']} <br>
                    EV <span class="profit-positive">+{bet['ev']:.1f}%</span><br>
                    Odds <strong>{bet['odds']:.1f}x</strong><br>
                    Confidence <strong>{'⚡' * min(5, int(bet['ev']/4))}</strong>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No upcoming bets at this time")

with col2:
    st.markdown('<div class="section-header">LAST SETTLED</div>', unsafe_allow_html=True)
    settled = get_last_settled(3)
    
    if settled:
        for bet in settled:
            profit_class = "profit-positive" if bet['won'] else "profit-negative"
            profit_sign = "+" if bet['won'] else ""
            result_emoji = "🟢" if bet['won'] else "🔴"
            
            st.markdown(f"""
            <div class="bet-card">
                <div class="match-title">{bet['match']}</div>
                <div class="bet-detail">
                    {bet['market']}: {bet['selection']}<br>
                    Odds <strong>{bet['odds']:.2f}x</strong><br>
                    {result_emoji} <span class="{profit_class}">{profit_sign}{bet['profit']:.0f} SEK</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No settled bets yet")

# Footer
st.markdown('<div style="text-align: center; color: #8B949E; font-size: 0.75rem; margin-top: 3rem; padding-bottom: 2rem;">📊 PGR Sports Analytics • Powered by AI • Real-time data from API-Football & OddsAPI</div>', unsafe_allow_html=True)
