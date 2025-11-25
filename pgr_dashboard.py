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
from db_connection import DatabaseConnection

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

@st.cache_data(ttl=300)
def get_rolling_roi_data(days=30):
    """Get daily ROI data for the rolling chart"""
    # Get all settled bets from last 30 days (PROD mode only)
    # Note: football_opportunities stores timestamps in seconds, sgp_predictions in milliseconds
    query = """
        SELECT 
            bet_date,
            market,
            profit_loss,
            stake
        FROM (
            SELECT DATE(TO_TIMESTAMP(settled_timestamp)) as bet_date, market, profit_loss, stake
            FROM football_opportunities
            WHERE outcome IN (%s, %s) AND settled_timestamp IS NOT NULL
              AND mode = 'PROD'
              AND TO_TIMESTAMP(settled_timestamp) >= NOW() - INTERVAL '%s days'
            
            UNION ALL
            
            SELECT DATE(TO_TIMESTAMP(settled_timestamp/1000)) as bet_date, 'sgp' as market, profit_loss, stake
            FROM sgp_predictions
            WHERE outcome IN (%s, %s) AND settled_timestamp IS NOT NULL
              AND mode = 'PROD'
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
              AND TO_TIMESTAMP(settled_timestamp/1000) >= NOW() - INTERVAL '%s days'
        ) combined
        ORDER BY bet_date DESC
    """
    
    rows = db_helper.execute(query, ('win', 'loss', days, 'win', 'loss', '%Monster%', '%BEAST%', days), fetch='all')
    
    if not rows:
        return None
    
    df = pd.DataFrame(rows, columns=['bet_date', 'market', 'profit_loss', 'stake'])
    df['bet_date'] = pd.to_datetime(df['bet_date'])
    
    # Calculate cumulative ROI for each product
    df_sorted = df.sort_values('bet_date')
    
    # ES only (exact_score market)
    df_es = df_sorted[df_sorted['market'] == 'exact_score'].copy()
    df_es['cumulative_profit'] = df_es['profit_loss'].cumsum()
    df_es['cumulative_stake'] = df_es['stake'].cumsum()
    df_es['roi'] = (df_es['cumulative_profit'] / df_es['cumulative_stake'] * 100).fillna(0)
    
    # Value Singles only
    df_vs = df_sorted[df_sorted['market'] == 'Value Single'].copy()
    df_vs['cumulative_profit'] = df_vs['profit_loss'].cumsum()
    df_vs['cumulative_stake'] = df_vs['stake'].cumsum()
    df_vs['roi'] = (df_vs['cumulative_profit'] / df_vs['cumulative_stake'] * 100).fillna(0)
    
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
        'value_singles': df_vs[['bet_date', 'roi']],
        'sgp': df_sgp[['bet_date', 'roi']],
        'combined': df_combined[['bet_date', 'roi']]
    }

def get_last_n_hit_rate(n=200, product='all'):
    """Get hit rate for last N bets from unified results_roi table (PROD mode only)"""
    product_map = {
        'exact_score': 'football_single',
        'sgp': 'sgp',
        'value_singles': 'value_single'
    }
    
    if product == 'all':
        query = """
            SELECT is_won
            FROM results_roi
            WHERE mode = 'PROD'
            ORDER BY created_at DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, (n,), fetch='all')
    else:
        product_type = product_map.get(product, product)
        query = """
            SELECT is_won
            FROM results_roi
            WHERE product_type = %s AND mode = 'PROD'
            ORDER BY created_at DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, (product_type, n), fetch='all')
    
    if not rows:
        return 0.0
    
    wins = sum(1 for row in rows if row[0])
    return (wins / len(rows) * 100) if rows else 0.0

def get_avg_odds(product='all'):
    """Get average odds from unified results_roi table (PROD mode only)"""
    product_map = {
        'exact_score': 'football_single',
        'sgp': 'sgp',
        'value_singles': 'value_single'
    }
    
    if product == 'all':
        query = """
            SELECT AVG(CASE WHEN stake > 0 THEN payout / stake ELSE 0 END) as avg_odds
            FROM results_roi
            WHERE is_won = true AND mode = 'PROD'
        """
        row = db_helper.execute(query, fetch='one')
    else:
        product_type = product_map.get(product, product)
        query = """
            SELECT AVG(CASE WHEN stake > 0 THEN payout / stake ELSE 0 END) as avg_odds
            FROM results_roi
            WHERE product_type = %s AND is_won = true AND mode = 'PROD'
        """
        row = db_helper.execute(query, (product_type,), fetch='one')
    
    return row[0] if row and row[0] else 0.0

def get_last_50_roi(product='exact_score'):
    """Get ROI for last 50 bets from unified results_roi table (PROD mode only)"""
    product_map = {
        'exact_score': 'football_single',
        'sgp': 'sgp',
        'value_singles': 'value_single'
    }
    
    if product == 'all':
        query = """
            SELECT SUM(profit) as profit, SUM(stake) as staked
            FROM (
                SELECT profit, stake
                FROM results_roi
                WHERE mode = 'PROD'
                ORDER BY created_at DESC
                LIMIT 50
            ) last_bets
        """
        row = db_helper.execute(query, (), fetch='one')
    else:
        product_type = product_map.get(product, product)
        query = """
            SELECT SUM(profit) as profit, SUM(stake) as staked
            FROM (
                SELECT profit, stake
                FROM results_roi
                WHERE product_type = %s AND mode = 'PROD'
                ORDER BY created_at DESC
                LIMIT 50
            ) last_bets
        """
        row = db_helper.execute(query, (product_type,), fetch='one')
    
    if row and row[0] is not None and row[1] and row[1] > 0:
        return (row[0] / row[1] * 100)
    return 0.0

@st.cache_data(ttl=60)
def get_upcoming_bets(limit=50, product='all'):
    """Get upcoming bets filtered by product type"""
    if product == 'exact_score':
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
        
    elif product == 'sgp':
        query = """
            SELECT home_team, away_team, parlay_description, bookmaker_odds, ev_percentage, match_date
            FROM sgp_predictions
            WHERE outcome IS NULL
              AND match_date >= CURRENT_DATE::text
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
              AND (parlay_description IS NULL OR parlay_description NOT LIKE %s)
            ORDER BY match_date ASC, ev_percentage DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('%Monster%', '%BEAST%', limit), fetch='all')
        
    elif product == 'monstersgp':
        query = """
            SELECT home_team, away_team, parlay_description, bookmaker_odds, ev_percentage, match_date
            FROM sgp_predictions
            WHERE outcome IS NULL
              AND match_date >= CURRENT_DATE::text
              AND (parlay_description LIKE %s OR parlay_description LIKE %s)
            ORDER BY match_date ASC, ev_percentage DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('%Monster%', '%BEAST%', limit), fetch='all')
        
    elif product == 'value_singles':
        query = """
            SELECT home_team, away_team, selection, odds, edge_percentage, match_date
            FROM football_opportunities
            WHERE market = %s
              AND outcome IS NULL
              AND match_date >= CURRENT_DATE::text
            ORDER BY match_date ASC, edge_percentage DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('Value Single', limit), fetch='all')
    
    elif product == 'college_basketball':
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT match, match, selection, odds, ev_percentage, CURRENT_DATE
                FROM basketball_predictions
                WHERE status = 'pending'
                ORDER BY ev_percentage DESC
                LIMIT %s
            """
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
        
    else:  # 'all' - combined
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

@st.cache_data(ttl=60)
def get_last_settled(limit=3, product='all'):
    """Get last settled bets filtered by product type - order by match_date (PROD mode only)"""
    if product == 'exact_score':
        query = """
            SELECT home_team, away_team, selection, odds, outcome, profit_loss, %s as market
            FROM football_opportunities
            WHERE outcome IN (%s, %s) AND mode = 'PROD'
            ORDER BY match_date DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('Final Score', 'win', 'loss', limit), fetch='all')
        
    elif product == 'sgp':
        query = """
            SELECT home_team, away_team, parlay_description, bookmaker_odds, outcome, profit_loss, %s as market
            FROM sgp_predictions
            WHERE outcome IN (%s, %s) AND mode = 'PROD'
              AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%Monster%%')
              AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%BEAST%%')
            ORDER BY match_date DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('SGP', 'win', 'loss', limit), fetch='all')
        
    elif product == 'monstersgp':
        query = """
            SELECT home_team, away_team, parlay_description, bookmaker_odds, outcome, profit_loss, %s as market
            FROM sgp_predictions
            WHERE outcome IN (%s, %s) AND mode = 'PROD'
              AND (parlay_description LIKE '%%Monster%%' OR parlay_description LIKE '%%BEAST%%')
            ORDER BY match_date DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('MonsterSGP', 'win', 'loss', limit), fetch='all')
        
    elif product == 'value_singles':
        query = """
            SELECT home_team, away_team, selection, odds, outcome, profit_loss, market
            FROM football_opportunities
            WHERE outcome IN (%s, %s) AND mode = 'PROD'
              AND market = %s
            ORDER BY match_date DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('win', 'loss', 'Value Single', limit), fetch='all')
        
    else:  # 'all' - combined
        query = """
            SELECT home_team, away_team, selection, odds, outcome, profit_loss, market, match_date
            FROM (
                SELECT home_team, away_team, selection, odds, outcome, profit_loss, 
                    %s as market, match_date
                FROM football_opportunities
                WHERE outcome IN (%s, %s) AND mode = 'PROD'
                
                UNION ALL
                
                SELECT home_team, away_team, parlay_description, bookmaker_odds, 
                    outcome, profit_loss, %s, match_date
                FROM sgp_predictions
                WHERE outcome IN (%s, %s) AND mode = 'PROD'
                  AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%Monster%%')
                  AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%BEAST%%')
            ) combined
            ORDER BY match_date DESC
            LIMIT %s
        """
        rows = db_helper.execute(query, ('Final Score', 'win', 'loss', 'SGP', 'win', 'loss', limit), fetch='all')
    
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

# Initialize session state for product selection
if 'selected_product' not in st.session_state:
    st.session_state.selected_product = 'exact_score'

# Header with Logo
st.markdown("""
<style>
    .pgr-logo-wrapper {
        max-width: 480px;
        margin: 2rem auto;
        text-align: center;
    }
    
    @media (max-width: 768px) {
        .pgr-logo-wrapper {
            max-width: 320px;
            margin: 1rem auto;
        }
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="pgr-logo-wrapper">', unsafe_allow_html=True)
st.image("assets/pgr_logo.png", use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# Segmented Control for Product Selection
st.markdown("""
<style>
    .product-selector {
        display: flex;
        justify-content: center;
        gap: 0;
        margin: 2rem 0;
        background: #161B22;
        padding: 4px;
        border-radius: 8px;
        width: fit-content;
        margin-left: auto;
        margin-right: auto;
    }
    
    .product-btn {
        padding: 12px 32px;
        background: transparent;
        border: none;
        color: #8B949E;
        font-weight: 600;
        cursor: pointer;
        border-radius: 6px;
        transition: all 0.2s;
        font-size: 0.95rem;
        letter-spacing: 0.5px;
    }
    
    .product-btn:hover {
        color: #C9D1D9;
    }
    
    .product-btn-active {
        background: #3FB68B !important;
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

col1, col2, col3, col4, col5, col6 = st.columns([1, 1, 1, 1, 1, 0.8])

with col1:
    if st.button("⚽ FINAL SCORE", key="btn_exact", use_container_width=True):
        st.session_state.selected_product = 'exact_score'
        st.rerun()
        
with col2:
    if st.button("🎯 SGP", key="btn_sgp", use_container_width=True):
        st.session_state.selected_product = 'sgp'
        st.rerun()

with col3:
    if st.button("💎 VALUE SINGLES", key="btn_value_singles", use_container_width=True):
        st.session_state.selected_product = 'value_singles'
        st.rerun()

with col4:
    if st.button("👩⚽ WOMEN 1X2", key="btn_women", use_container_width=True):
        st.session_state.selected_product = 'women_1x2'
        st.rerun()

with col5:
    if st.button("🏀 COLLEGE BASKETBALL", key="btn_ncaab", use_container_width=True):
        st.session_state.selected_product = 'college_basketball'
        st.rerun()

with col6:
    if st.button("📊 ALL", key="btn_all", use_container_width=True):
        st.session_state.selected_product = 'all'
        st.rerun()

# Show active selection
product_labels = {
    'exact_score': 'Final Score',
    'sgp': 'SGP',
    'value_singles': 'Value Singles',
    'women_1x2': "Women's 1X2",
    'college_basketball': 'College Basketball',
    'all': 'All Products'
}
st.markdown(f"""
<div style="text-align: center; color: #3FB68B; font-size: 0.9rem; margin-top: -1rem; margin-bottom: 2rem;">
    Viewing: <strong>{product_labels[st.session_state.selected_product]}</strong>
</div>
""", unsafe_allow_html=True)

# Get product-specific stats (for now, using combined - will implement filters next)
stats = get_all_time_stats()
selected = st.session_state.selected_product

if selected == 'all':
    # Combined stats across all products
    product_stats = stats['combined']
elif selected == 'exact_score':
    product_stats = stats['exact_score']
elif selected == 'sgp':
    product_stats = stats['sgp']
elif selected == 'value_singles':
    product_stats = stats['value_singles']
elif selected == 'women_1x2':
    # Get women's 1X2 stats from BetStatusService
    try:
        from bet_status_service import BetStatusService
        bet_service = BetStatusService()
        women_stats = bet_service.get_women_1x2_performance()
        
        # Defensive handling for empty data
        product_stats = {
            'total': women_stats.get('total_bets', 0),
            'wins': women_stats.get('wins', 0),
            'losses': women_stats.get('losses', 0),
            'profit': women_stats.get('total_profit', 0.0)
        }
        
        total_roi = women_stats.get('roi', 0.0)
        hit_rate_200 = women_stats.get('hit_rate', 0.0)
        
        # Safe odds calculation
        total_staked = women_stats.get('total_staked', 0.0)
        total_profit = women_stats.get('total_profit', 0.0)
        
        if total_staked > 0 and (total_staked + total_profit) > 0:
            avg_odds = (total_staked + total_profit) / total_staked
        else:
            avg_odds = 0.0
            
    except Exception as e:
        print(f"Error loading women's 1X2 stats: {e}")
        product_stats = {'total': 0, 'wins': 0, 'losses': 0, 'profit': 0.0}
        total_roi = 0.0
        hit_rate_200 = 0.0
        avg_odds = 0.0

elif selected == 'college_basketball':
    # Get College Basketball stats
    try:
        with DatabaseConnection.get_connection() as conn:
            ncaab_query = """
                SELECT 
                    COUNT(*) as total_picks,
                    AVG(ev_percentage) as avg_ev,
                    AVG(odds) as avg_odds,
                    COUNT(CASE WHEN is_parlay THEN 1 END) as parlay_count
                FROM basketball_predictions
                WHERE status = 'pending'
            """
            result = pd.read_sql(ncaab_query, conn)
            
            product_stats = {'total': int(result['total_picks'].iloc[0] if not result.empty else 0), 'wins': 0, 'losses': 0, 'profit': 0.0}
            total_roi = 0.0  # No settled bets yet, so ROI is 0%
            hit_rate_200 = 0.0  # No settled bets yet
            odds_value = result['avg_odds'].iloc[0] if not result.empty else None
            avg_odds = float(odds_value) if odds_value is not None else 0.0
            
    except Exception as e:
        print(f"Error loading College Basketball stats: {e}")
        product_stats = {'total': 0, 'wins': 0, 'losses': 0, 'profit': 0.0}
        total_roi = 0.0
        hit_rate_200 = 0.0
        avg_odds = 0.0

if selected not in ['women_1x2', 'college_basketball']:
    # Calculate ROI using actual staked amounts (not assuming 100 SEK per bet)
    staked = product_stats.get('staked', 0)
    total_roi = (product_stats['profit'] / staked * 100) if staked > 0 else 0
    hit_rate_200 = get_last_n_hit_rate(200, product=selected)
    avg_odds = get_avg_odds(product=selected)

# Platform Total ROI (across all products)
try:
    # Football opportunities (Exact Score + Value Singles) - PROD mode only
    football_query = """
        SELECT 
            SUM(profit_loss) as profit,
            SUM(stake) as staked
        FROM football_opportunities
        WHERE outcome IN ('win', 'loss') AND mode = 'PROD'
    """
    football_row = db_helper.execute(football_query, (), fetch='one')
    
    # SGP predictions - PROD mode only
    sgp_query = """
        SELECT 
            SUM(profit_loss) as profit,
            SUM(stake) as staked
        FROM sgp_predictions
        WHERE outcome IN ('win', 'loss') AND mode = 'PROD'
    """
    sgp_row = db_helper.execute(sgp_query, (), fetch='one')
    
    # Women's 1X2 - PROD mode only
    women_query = """
        SELECT 
            SUM(profit_loss) as profit,
            SUM(stake) as staked
        FROM women_match_winner_predictions
        WHERE outcome IN ('win', 'loss') AND mode = 'PROD'
    """
    women_row = db_helper.execute(women_query, (), fetch='one')
    
    # Calculate platform totals
    platform_profit = 0.0
    platform_staked = 0.0
    
    if football_row and football_row[0]:
        platform_profit += football_row[0]
        platform_staked += football_row[1] or 0
    
    if sgp_row and sgp_row[0]:
        platform_profit += sgp_row[0]
        platform_staked += sgp_row[1] or 0
    
    if women_row and women_row[0]:
        platform_profit += women_row[0]
        platform_staked += women_row[1] or 0
    
    platform_roi = (platform_profit / platform_staked * 100) if platform_staked > 0 else 0.0
    
except Exception as e:
    print(f"Error calculating platform ROI: {e}")
    platform_roi = 0.0

# Display Platform ROI banner if viewing 'all' products
if st.session_state.selected_product == 'all':
    st.markdown(f"""
    <div style="text-align: center; padding: 1.5rem; margin-bottom: 2rem; background: linear-gradient(135deg, #1C2128 0%, #0D1117 100%); border-radius: 12px; border: 1px solid #30363D;">
        <div style="font-size: 0.9rem; color: #8B949E; letter-spacing: 2px; margin-bottom: 0.5rem;">PLATFORM TOTAL ROI</div>
        <div style="font-size: 3rem; font-weight: 900; color: {'#3FB68B' if platform_roi >= 0 else '#F85149'};">{platform_roi:+.1f}%</div>
        <div style="font-size: 0.85rem; color: #8B949E; margin-top: 0.3rem;">Across all products (Football, SGP, Women's 1X2, College Basketball)</div>
    </div>
    """, unsafe_allow_html=True)

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
    product_name = product_labels[st.session_state.selected_product]
    st.markdown(f"""
    <div class="hero-metric">
        <div class="hero-value">{avg_odds:.1f}x</div>
        <div class="hero-label">{product_name}<br>Avg Odds</div>
    </div>
    """, unsafe_allow_html=True)

# ROI Development Chart
st.markdown('<div class="section-header">ROI DEVELOPMENT <span style="color: #8B949E; float: right; font-size: 0.9rem;">Last 30 days ›</span></div>', unsafe_allow_html=True)

roi_data = get_rolling_roi_data(30)

if roi_data:
    fig = go.Figure()
    
    # Show only the selected product's line
    if st.session_state.selected_product == 'exact_score':
        if not roi_data['es'].empty:
            fig.add_trace(go.Scatter(
                x=roi_data['es']['bet_date'],
                y=roi_data['es']['roi'],
                name='Final Score',
                line=dict(color='#3FB68B', width=3),
                mode='lines'
            ))
    elif st.session_state.selected_product == 'sgp':
        if not roi_data['sgp'].empty:
            fig.add_trace(go.Scatter(
                x=roi_data['sgp']['bet_date'],
                y=roi_data['sgp']['roi'],
                name='SGP',
                line=dict(color='#58A6FF', width=3),
                mode='lines'
            ))
    elif st.session_state.selected_product == 'value_singles':
        if not roi_data['value_singles'].empty:
            fig.add_trace(go.Scatter(
                x=roi_data['value_singles']['bet_date'],
                y=roi_data['value_singles']['roi'],
                name='Value Singles',
                line=dict(color='#D29922', width=3),
                mode='lines'
            ))
    else:  # monstersgp - use MonsterSGP-specific data
        if 'monstersgp' in roi_data and not roi_data['monstersgp'].empty:
            fig.add_trace(go.Scatter(
                x=roi_data['monstersgp']['bet_date'],
                y=roi_data['monstersgp']['roi'],
                name='MonsterSGP',
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

# College Basketball Picks Display
if selected == 'college_basketball':
    st.markdown('<div class="section-header">🏀 COLLEGE BASKETBALL PICKS</div>', unsafe_allow_html=True)
    
    try:
        # Get performance stats first - separate singles and parlays ROI (PROD mode only)
        stats_query = """
            SELECT 
                COUNT(*) FILTER (WHERE status IN ('won', 'lost')) as total_settled,
                COUNT(*) FILTER (WHERE status = 'won') as wins,
                COUNT(*) FILTER (WHERE status = 'lost') as losses,
                COUNT(*) FILTER (WHERE status = 'won' AND is_parlay = false) as singles_won,
                COUNT(*) FILTER (WHERE status = 'lost' AND is_parlay = false) as singles_lost,
                COUNT(*) FILTER (WHERE status = 'won' AND is_parlay = true) as parlays_won,
                COUNT(*) FILTER (WHERE status = 'lost' AND is_parlay = true) as parlays_lost,
                COALESCE(SUM(CASE WHEN status = 'won' THEN (odds - 1) * 100 ELSE -100 END) 
                    FILTER (WHERE status IN ('won', 'lost') AND is_parlay = false), 0) as singles_profit,
                COALESCE(SUM(CASE WHEN status = 'won' THEN (odds - 1) * 100 ELSE -100 END) 
                    FILTER (WHERE status IN ('won', 'lost') AND is_parlay = true), 0) as parlays_profit
            FROM basketball_predictions
            WHERE mode = 'PROD'
        """
        stats_row = db_helper.execute(stats_query, (), fetch='one')
        
        if stats_row and stats_row[0] > 0:
            total_settled = int(stats_row[0])
            wins = int(stats_row[1])
            losses = int(stats_row[2])
            singles_won = int(stats_row[3])
            singles_lost = int(stats_row[4])
            parlays_won = int(stats_row[5])
            parlays_lost = int(stats_row[6])
            singles_profit = float(stats_row[7])
            parlays_profit = float(stats_row[8])
            
            win_rate = (wins / total_settled * 100) if total_settled > 0 else 0
            singles_total = singles_won + singles_lost
            parlays_total = parlays_won + parlays_lost
            singles_rate = (singles_won / singles_total * 100) if singles_total > 0 else 0
            parlays_rate = (parlays_won / parlays_total * 100) if parlays_total > 0 else 0
            singles_roi = (singles_profit / (singles_total * 100) * 100) if singles_total > 0 else 0
            parlays_roi = (parlays_profit / (parlays_total * 100) * 100) if parlays_total > 0 else 0
            
            st.markdown(f"""
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <div style="background: #161B22; padding: 1rem; border-radius: 8px; flex: 1; min-width: 180px; text-align: center; border-left: 3px solid #3FB68B;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: {'#3FB68B' if singles_roi >= 0 else '#F85149'};">{singles_roi:+.1f}%</div>
                    <div style="color: #8B949E; font-size: 0.85rem;">⭐ Singles ROI</div>
                    <div style="color: #58A6FF; font-size: 0.9rem; margin-top: 0.3rem; font-weight: 600;">{singles_won}W / {singles_lost}L ({singles_rate:.0f}%)</div>
                </div>
                <div style="background: #161B22; padding: 1rem; border-radius: 8px; flex: 1; min-width: 180px; text-align: center; border-left: 3px solid #58A6FF;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: {'#3FB68B' if parlays_roi >= 0 else '#F85149'};">{parlays_roi:+.1f}%</div>
                    <div style="color: #8B949E; font-size: 0.85rem;">🎯 Parlays ROI</div>
                    <div style="color: #58A6FF; font-size: 0.9rem; margin-top: 0.3rem; font-weight: 600;">{parlays_won}W / {parlays_lost}L ({parlays_rate:.0f}%)</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT match, selection, odds, ev_percentage, is_parlay
                FROM basketball_predictions
                WHERE status = 'pending'
                ORDER BY is_parlay ASC, ev_percentage DESC
            """
            picks_df = pd.read_sql(query, conn)
        
        if not picks_df.empty:
            # Singles section
            singles = picks_df[picks_df['is_parlay'] == False]
            if not singles.empty:
                st.markdown("### ⭐ SINGLE BETS")
                for idx, row in singles.iterrows():
                    st.markdown(f"""
                    <div style="background: #161B22; padding: 1rem; margin-bottom: 0.8rem; border-radius: 8px; border-left: 3px solid #3FB68B;">
                        <div style="font-weight: 600; font-size: 1rem; margin-bottom: 0.3rem;">{row['match']}</div>
                        <div style="color: #58A6FF; font-size: 0.95rem; margin-bottom: 0.5rem;">📍 {row['selection']}</div>
                        <div style="display: flex; gap: 2rem;">
                            <div><span style="color: #8B949E;">Odds:</span> <span style="color: #3FB68B; font-weight: 600;">{row['odds']:.2f}x</span></div>
                            <div><span style="color: #8B949E;">EV:</span> <span style="color: #D29922; font-weight: 600;">+{row['ev_percentage']:.1f}%</span></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Parlays section
            parlays = picks_df[picks_df['is_parlay'] == True]
            if not parlays.empty:
                st.markdown("### 🎯 PARLAY BETS")
                for idx, row in parlays.iterrows():
                    # Parse parlay legs
                    teams = row['match'].replace('PARLAY: ', '').split(' + ')
                    selections = row['selection'].split(' | ')
                    
                    st.markdown(f"""
                    <div style="background: #161B22; padding: 1rem; margin-bottom: 0.8rem; border-radius: 8px; border-left: 3px solid #58A6FF;">
                        <div style="font-weight: 600; font-size: 1rem; margin-bottom: 0.5rem; color: #58A6FF;">
                            {len(teams)}-Leg Parlay • {row['odds']:.2f}x • +{row['ev_percentage']:.1f}% EV
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Display each leg
                    for i, (team, selection) in enumerate(zip(teams, selections), 1):
                        st.markdown(f"""
                        <div style="padding: 0.5rem; margin-left: 1rem; border-left: 2px solid #30363D;">
                            <div style="color: #C9D1D9; font-size: 0.9rem;">Leg {i}: <strong>{team}</strong></div>
                            <div style="color: #8B949E; font-size: 0.85rem; margin-left: 1rem;">→ {selection}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("No pending College Basketball picks. Next cycle generates picks every 2 hours.")
    
    except Exception as e:
        print(f"Error displaying College Basketball picks: {e}")
        st.error("Error loading picks")

# SGP Picks Display
if selected in ['sgp', 'monstersgp']:
    st.markdown('<div class="section-header">🎯 SGP PICKS</div>', unsafe_allow_html=True)
    
    try:
        if selected == 'sgp':
            query = """
                SELECT home_team, away_team, parlay_description, bookmaker_odds, ev_percentage
                FROM sgp_predictions
                WHERE outcome IS NULL
                  AND match_date >= CURRENT_DATE::text
                  AND ev_percentage > 0
                  AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%Monster%%')
                  AND (parlay_description IS NULL OR parlay_description NOT LIKE '%%BEAST%%')
                ORDER BY ev_percentage DESC
                LIMIT 50
            """
        else:  # monstersgp
            query = """
                SELECT home_team, away_team, parlay_description, bookmaker_odds, ev_percentage
                FROM sgp_predictions
                WHERE outcome IS NULL
                  AND match_date >= CURRENT_DATE::text
                  AND ev_percentage > 0
                  AND (parlay_description LIKE '%%Monster%%' OR parlay_description LIKE '%%BEAST%%')
                ORDER BY ev_percentage DESC
                LIMIT 50
            """
        
        sgp_rows = db_helper.execute(query, (), fetch='all')
        
        if sgp_rows and len(sgp_rows) > 0:
            for row in sgp_rows:
                try:
                    home_team = row[0] or ''
                    away_team = row[1] or ''
                    parlay_desc = row[2] or ''
                    odds = float(row[3]) if row[3] else 0
                    ev = float(row[4]) if row[4] else 0
                    
                    if not parlay_desc:
                        continue
                    
                    # Parse parlay legs
                    legs = parlay_desc.split(' + ')
                    num_legs = len(legs)
                    
                    # Determine if it's a Monster parlay
                    is_monster = 'Monster' in parlay_desc or 'BEAST' in parlay_desc
                    border_color = '#D29922' if is_monster else '#58A6FF'
                    
                    st.markdown(f"""
                    <div style="background: #161B22; padding: 1rem; margin-bottom: 0.8rem; border-radius: 8px; border-left: 3px solid {border_color};">
                        <div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 0.5rem; color: #C9D1D9;">
                            {home_team} vs {away_team}
                        </div>
                        <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.7rem; color: {border_color};">
                            {num_legs}-Leg {'Monster ' if is_monster else ''}Parlay • {odds:.2f}x • +{ev:.1f}% EV
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Display each leg
                    for i, leg in enumerate(legs, 1):
                        clean_leg = leg.replace('(5-Leg Monster)', '').replace('(5-Leg)', '').replace('(4-Leg)', '').replace('(3-Leg)', '').strip()
                        
                        st.markdown(f"""
                        <div style="padding: 0.5rem; margin-left: 1rem; border-left: 2px solid #30363D;">
                            <div style="color: #C9D1D9; font-size: 0.9rem;">✓ Leg {i}: <strong>{clean_leg}</strong></div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                except Exception as row_error:
                    print(f"Error processing SGP row: {row_error}")
                    continue
        else:
            st.info("No pending SGP picks with positive EV. System generates picks when value opportunities are detected.")
    
    except Exception as e:
        import traceback
        print(f"Error displaying SGP picks: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        st.info("No pending SGP picks with positive EV. System generates picks when value opportunities are detected.")

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
    
    # Product-specific Last 50 ROI (MonsterSGP excluded)
    if selected == 'monstersgp':
        # MonsterSGP: Show win/loss count only (no ROI)
        monster_stats = stats.get('monstersgp', {})
        st.markdown(f"""
        <div class="status-item">
            <div class="status-label">🎰 MONSTER W/L</div>
            <div class="status-value">{monster_stats.get('wins', 0)}W / {monster_stats.get('total', 0) - monster_stats.get('wins', 0)}L</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Exact Score & SGP: Show Last 50 ROI
        last_50_roi = get_last_50_roi(product=selected)
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
        <div class="status-value">{es_threshold['ev_min']:.2f} (Final Score)</div>
        <div style="color: #58A6FF; margin-top: 0.3rem; font-size: 1.1rem; font-weight: 600;">{sgp_threshold['ev_min']:.2f} (SGP)</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div style="color: #8B949E; font-size: 0.85rem; margin-top: 1rem;">When the system pauses, it protects your bankroll – not its ego.</div>', unsafe_allow_html=True)

# Upcoming Bets & Last Settled
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-header">UPCOMING BETS</div>', unsafe_allow_html=True)
    upcoming = get_upcoming_bets(3, product=st.session_state.selected_product)
    
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
    settled = get_last_settled(3, product=st.session_state.selected_product)
    
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
