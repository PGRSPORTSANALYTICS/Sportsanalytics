#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date

# Database path
DB_PATH = 'data/real_football.db'

# Page setup
st.set_page_config(
    page_title="🏆 Elite Football Intelligence",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for exclusive design
st.markdown("""
<style>
    /* Main background and fonts */
    .stApp {
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
    }
    
    /* Headers */
    h1 {
        color: #FFD700 !important;
        font-size: 3.5rem !important;
        font-weight: 800 !important;
        text-align: center !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        padding: 20px 0;
        margin-bottom: 10px !important;
    }
    
    h2 {
        color: #FFFFFF !important;
        font-size: 2rem !important;
        font-weight: 700 !important;
        border-left: 5px solid #FFD700;
        padding-left: 15px;
        margin-top: 30px !important;
    }
    
    h3 {
        color: #E0E0E0 !important;
        font-size: 1.3rem !important;
    }
    
    /* Metrics styling */
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 700 !important;
        color: #FFD700 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #B0B0B0 !important;
        font-size: 0.9rem !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Cards and containers */
    .stMarkdown {
        color: #E0E0E0;
    }
    
    /* Dividers */
    hr {
        border-color: rgba(255, 215, 0, 0.3) !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        color: #000000;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 10px 30px;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(255, 215, 0, 0.4);
    }
    
    /* Success/Info boxes */
    .stAlert {
        background-color: rgba(255, 215, 0, 0.1) !important;
        border: 1px solid rgba(255, 215, 0, 0.3) !important;
        border-radius: 10px;
        color: #FFD700 !important;
    }
    
    /* DataFrames */
    [data-testid="stDataFrame"] {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 10px;
    }
    
    /* Caption text */
    .caption {
        color: #909090 !important;
        font-size: 0.85rem;
    }
    
    /* Subtitle */
    .subtitle {
        text-align: center;
        color: #B0B0B0;
        font-size: 1.1rem;
        margin-bottom: 30px;
        letter-spacing: 2px;
        text-transform: uppercase;
    }
    
    /* Premium badge */
    .premium-badge {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        color: #000000;
        padding: 8px 20px;
        border-radius: 20px;
        font-weight: 700;
        display: inline-block;
        margin: 5px;
        box-shadow: 0 2px 8px rgba(255, 215, 0, 0.3);
    }
    
    /* Tier badges */
    .tier-premium { 
        background: linear-gradient(135deg, #9333EA 0%, #7C3AED 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .tier-standard {
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .tier-value {
        background: linear-gradient(135deg, #059669 0%, #047857 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .tier-exact {
        background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%);
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def load_regular_tips():
    """Load today's regular betting opportunities"""
    try:
        conn = sqlite3.connect(DB_PATH)
        today = date.today().isoformat()
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, tier
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
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome != 'unknown' THEN profit_loss ELSE 0 END) as net_profit
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
                   WHEN outcome IN ('win', 'won') THEN '✅'
                   WHEN outcome IN ('loss', 'lost') THEN '❌'
                   ELSE '⚪'
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
# HEADER
# ============================================================================

st.markdown("# 🏆 ELITE BETTING INTELLIGENCE")
st.markdown('<p class="subtitle">Premium AI-Powered Football Predictions</p>', unsafe_allow_html=True)

col1, col2 = st.columns([4, 1])
with col2:
    if st.button("🔄 REFRESH"):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ============================================================================
# TOP: PREMIUM BETTING TIPS
# ============================================================================

st.markdown("## 💎 PREMIUM BETTING TIPS")

regular_stats = load_regular_performance()
if regular_stats is not None:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("TOTAL TIPS", int(regular_stats['total_tips']))
    
    with col2:
        win_rate = (regular_stats['wins'] / (regular_stats['wins'] + regular_stats['losses']) * 100) if (regular_stats['wins'] + regular_stats['losses']) > 0 else 0
        st.metric("WIN RATE", f"{win_rate:.1f}%")
    
    with col3:
        st.metric("NET PROFIT", f"${regular_stats['net_profit']:.2f}")
    
    with col4:
        roi = (regular_stats['net_profit'] / regular_stats['total_staked'] * 100) if regular_stats['total_staked'] > 0 else 0
        st.metric("ROI", f"{roi:.1f}%")

st.markdown("")

regular_tips = load_regular_tips()
if not regular_tips.empty:
    for idx, tip in regular_tips.iterrows():
        tier_class = f"tier-{tip['tier']}" if tip['tier'] in ['premium', 'standard', 'value'] else "tier-premium"
        tier_icons = {'premium': '💎', 'standard': '⚡', 'value': '💰', 'backup': '🔧'}
        tier_icon = tier_icons.get(tip['tier'], '📊')
        
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        
        with col1:
            st.markdown(f"### {tip['home_team']} vs {tip['away_team']}")
            st.markdown(f"**{tip['selection']}**")
        
        with col2:
            st.markdown(f"**Odds:** `{tip['odds']:.2f}`")
            st.markdown(f"Edge: **{tip['edge_percentage']:.1f}%**")
        
        with col3:
            st.markdown(f"**Confidence:** {tip['confidence']}%")
            st.caption(f"{tip['match_date']}")
        
        with col4:
            st.markdown(f'<div class="{tier_class}">{tier_icon} {tip["tier"].upper()}</div>', unsafe_allow_html=True)
        
        st.markdown("---")
else:
    st.info("🔍 No premium tips available. Waiting for high-quality opportunities...")

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# MIDDLE: EXACT SCORE PREDICTIONS
# ============================================================================

st.markdown("## 🎯 EXACT SCORE PREDICTIONS")

exact_stats = load_exact_score_performance()
if exact_stats is not None and exact_stats['total_tips'] > 0:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("PREDICTIONS", int(exact_stats['total_tips']))
    
    with col2:
        hit_rate = (exact_stats['wins'] / (exact_stats['wins'] + exact_stats['losses']) * 100) if (exact_stats['wins'] + exact_stats['losses']) > 0 else 0
        st.metric("HIT RATE", f"{hit_rate:.1f}%")
    
    with col3:
        st.metric("PROFIT", f"${exact_stats['net_profit']:.2f}")
    
    with col4:
        st.metric("SETTLED", f"{exact_stats['wins'] + exact_stats['losses']}")

st.markdown("")

exact_tips = load_exact_score_tips()
if not exact_tips.empty:
    for idx, tip in exact_tips.iterrows():
        col1, col2, col3 = st.columns([3, 2, 2])
        
        with col1:
            st.markdown(f"### {tip['home_team']} vs {tip['away_team']}")
            st.markdown(f"**{tip['selection']}**")
        
        with col2:
            st.markdown(f"**Odds:** `{tip['odds']:.2f}`")
            st.markdown(f"Edge: **{tip['edge_percentage']:.1f}%**")
        
        with col3:
            st.markdown(f"**Confidence:** {tip['confidence']}%")
            st.caption(f"{tip['match_date']}")
        
        st.markdown("---")
else:
    st.info("🎯 No exact score predictions today.")

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# BOTTOM: HISTORICAL PERFORMANCE
# ============================================================================

st.markdown("## 📊 HISTORICAL PERFORMANCE")

historical = load_all_historical()
if not historical.empty:
    st.success(f"📈 **{len(historical)} Completed Bets** | Authentic Results Only")
    
    st.markdown("")
    
    display_df = historical.head(50).copy()
    display_df['Match'] = display_df['home_team'] + ' vs ' + display_df['away_team']
    display_df['P&L'] = display_df['profit_loss'].apply(lambda x: f"${x:.2f}")
    display_df['Tier'] = display_df['tier'].apply(lambda x: {'premium': '💎 Premium', 'standard': '⚡ Standard', 'value': '💰 Value', 'backup': '🔧 Backup', 'legacy': '🎯 Exact'}.get(x, '📊 Tip'))
    
    table_data = display_df[['Match', 'selection', 'Tier', 'odds', 'result', 'P&L', 'match_date']].copy()
    table_data.columns = ['Match', 'Selection', 'Tier', 'Odds', 'Result', 'P&L', 'Date']
    
    def color_historical(row):
        if '✅' in str(row['Result']):
            return ['background-color: rgba(16, 185, 129, 0.2)'] * len(row)
        elif '❌' in str(row['Result']):
            return ['background-color: rgba(239, 68, 68, 0.2)'] * len(row)
        else:
            return ['background-color: rgba(255, 255, 255, 0.05)'] * len(row)
    
    styled_table = table_data.style.apply(color_historical, axis=1)
    st.dataframe(styled_table, use_container_width=True, height=600)
else:
    st.info("📊 Historical results will appear as bets settle.")

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("---")
st.markdown('<p style="text-align: center; color: #808080; font-size: 0.9rem;">🔒 100% Authentic Results | 🔄 Auto-refresh every 30s | 🏆 Elite Betting Intelligence</p>', unsafe_allow_html=True)
