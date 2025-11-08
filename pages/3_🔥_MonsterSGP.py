#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date

# Database path
DB_PATH = 'data/real_football.db'

# Page setup
st.set_page_config(
    page_title="🔥 MonsterSGP | 1st Half Parlays",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Dark Theme CSS with Orange Fire Accents
st.markdown("""
<style>
    /* Dark Premium Background */
    .stApp {
        background: #0D1117;
        color: #E6EDF3;
    }
    
    /* Orange Fire Accents for MonsterSGP */
    h1 {
        color: #FF6B35 !important;
        font-size: 3.5rem !important;
        font-weight: 800 !important;
        text-align: center;
        margin-bottom: 0.5rem !important;
        letter-spacing: -1px;
    }
    
    h2 {
        color: #FF6B35 !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        margin-top: 2.5rem !important;
        margin-bottom: 1.5rem !important;
    }
    
    /* Premium Metrics */
    [data-testid="stMetricValue"] {
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        color: #FF6B35 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #8B949E !important;
        font-size: 0.9rem !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
    }
    
    /* Clean Cards */
    [data-testid="stMetricDelta"] {
        color: #3FB950 !important;
    }
    
    /* Subtle Dividers */
    hr {
        border-color: #21262D !important;
        margin: 2rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("# 🔥 MONSTERSGP")
st.caption("1st Half Only Parlays - Results in 45 Minutes! (MonsterSGP 3-7 leg BEAST)")

st.markdown("---")

# ============================================================================
# WHAT IS MONSTERSGP?
# ============================================================================

with st.expander("🔥 WHAT IS MONSTERSGP?", expanded=False):
    st.markdown("""
    **MonsterSGP** is a specialized parlay product focusing exclusively on **1st half markets** for maximum entertainment and instant gratification!
    
    ### 🎯 Key Features:
    - **Pure 1st Half:** All legs focus on 1st half outcomes (goals, BTTS, corners)
    - **Instant Results:** Know your outcome in 45 minutes instead of 90+ minutes
    - **Monster Odds:** Average 38x odds, with 7-leg BEAST hitting 145x!
    - **AI-Powered:** Poisson-based probabilities with correlation matrices
    
    ### 📊 MonsterSGP Combinations:
    - **3-leg:** 1H Over 0.5 + 1H BTTS + 1H Corners 4.5+
    - **4-leg:** 1H Over 0.5/1.5 + 1H BTTS + 1H Corners 4.5+
    - **5-leg:** 1H Over 0.5/1.5 + 1H BTTS + 1H Corners 3.5/4.5
    - **6-leg:** 1H Over 0.5/1.5/2.5 + 1H BTTS + 1H Corners 3.5/4.5
    - **7-leg BEAST:** 1H Over 0.5/1.5/2.5 + 1H BTTS + 1H Corners 3.5/4.5/5.5
    
    ### 🎰 Why MonsterSGP?
    Perfect for bettors who want:
    - **Fast action** - results during halftime!
    - **Entertainment value** - monster parlays with huge upside
    - **Less time commitment** - watch 45 mins instead of full match
    """)

st.markdown("---")

# ============================================================================
# TODAY'S MONSTERSGP STATS
# ============================================================================

st.markdown("## 📊 TODAY'S MONSTERSGP PREDICTIONS")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get today's MonsterSGP stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN result IS NOT NULL THEN 1 END) as settled,
            COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
            COUNT(CASE WHEN result = 'LOSS' THEN 1 END) as losses,
            SUM(CASE WHEN result IS NOT NULL THEN profit_loss ELSE 0 END) as profit,
            AVG(bookmaker_odds) as avg_odds,
            MAX(bookmaker_odds) as max_odds,
            AVG(ev_percentage) as avg_ev
        FROM sgp_predictions
        WHERE DATE(match_date) = DATE('now')
          AND parlay_description LIKE '%MonsterSGP%'
    ''')
    
    row = cursor.fetchone()
    total_today = row[0]
    settled_today = row[1]
    wins_today = row[2]
    losses_today = row[3]
    profit_today = row[4] or 0
    avg_odds_today = row[5] or 0
    max_odds_today = row[6] or 0
    avg_ev_today = row[7] or 0
    
    hit_rate_today = (wins_today / settled_today * 100) if settled_today > 0 else 0
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total MonsterSGPs", total_today)
        st.caption(f"🔥 1st Half Only")
    
    with col2:
        st.metric("Avg Odds", f"{avg_odds_today:.2f}x")
        st.caption(f"Max: {max_odds_today:.2f}x")
    
    with col3:
        if settled_today > 0:
            st.metric("Settled", settled_today, delta=f"{wins_today}W / {losses_today}L")
        else:
            st.metric("Settled", "Pending")
    
    with col4:
        profit_color = "🟢" if profit_today > 0 else "🔴" if profit_today < 0 else "⚪"
        st.metric("P/L Today", f"{profit_today:+.0f} SEK", delta=profit_color)
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading today's stats: {e}")

st.markdown("---")

# ============================================================================
# ACTIVE MONSTERSGP PREDICTIONS
# ============================================================================

st.markdown("## 🎯 ACTIVE MONSTERSGP PREDICTIONS")
st.caption("1st half parlays waiting for results")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # Get active MonsterSGPs
    df_active = pd.read_sql_query('''
        SELECT 
            home_team,
            away_team,
            parlay_description,
            bookmaker_odds,
            ev_percentage,
            stake,
            pricing_mode,
            match_date
        FROM sgp_predictions
        WHERE result IS NULL
          AND DATE(match_date) >= DATE('now')
          AND parlay_description LIKE '%MonsterSGP%'
        ORDER BY bookmaker_odds DESC
        LIMIT 50
    ''', conn)
    
    if not df_active.empty:
        st.success(f"🔥 {len(df_active)} active MonsterSGP predictions")
        
        # Format dataframe
        df_display = df_active.copy()
        df_display['Match'] = df_display['home_team'] + ' vs ' + df_display['away_team']
        df_display['MonsterSGP'] = df_display['parlay_description']
        df_display['Odds'] = df_display['bookmaker_odds'].apply(lambda x: f"{x:.2f}x")
        df_display['EV'] = df_display['ev_percentage'].apply(lambda x: f"{x:.1f}%")
        df_display['Stake'] = df_display['stake'].apply(lambda x: f"{x:.0f} SEK")
        
        # Add pricing mode indicator
        df_display['Mode'] = df_display['pricing_mode'].apply(
            lambda x: '🟢 Live' if x == 'live' else '🟡 Hybrid' if x == 'hybrid' else '⚪ Sim'
        )
        
        # Display table
        st.dataframe(
            df_display[['Match', 'MonsterSGP', 'Odds', 'EV', 'Stake', 'Mode']],
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("📭 No active MonsterSGP predictions. Next generation cycle starts soon!")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading active MonsterSGPs: {e}")

st.markdown("---")

# ============================================================================
# ALL-TIME MONSTERSGP STATISTICS
# ============================================================================

st.markdown("## 🏆 ALL-TIME MONSTERSGP STATISTICS")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all-time MonsterSGP stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN result IS NOT NULL THEN 1 END) as settled,
            COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
            COUNT(CASE WHEN result = 'LOSS' THEN 1 END) as losses,
            SUM(CASE WHEN result IS NOT NULL THEN profit_loss ELSE 0 END) as total_profit,
            SUM(CASE WHEN result IS NOT NULL THEN stake ELSE 0 END) as total_staked,
            AVG(CASE WHEN result IS NOT NULL THEN bookmaker_odds END) as avg_odds,
            MAX(CASE WHEN result IS NOT NULL THEN bookmaker_odds END) as max_odds,
            AVG(CASE WHEN result IS NOT NULL THEN ev_percentage END) as avg_ev
        FROM sgp_predictions
        WHERE parlay_description LIKE '%MonsterSGP%'
    ''')
    
    row = cursor.fetchone()
    total_sgps = row[0]
    total_settled = row[1]
    total_wins = row[2]
    total_losses = row[3]
    total_profit = row[4] or 0
    total_staked = row[5] or 0
    avg_odds = row[6] or 0
    max_odds = row[7] or 0
    avg_ev = row[8] or 0
    
    hit_rate_all = (total_wins / total_settled * 100) if total_settled > 0 else 0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    
    # Display metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total MonsterSGPs", total_sgps)
        st.caption(f"{total_settled} settled")
    
    with col2:
        st.metric("Avg Odds", f"{avg_odds:.2f}x")
        st.caption(f"Max: {max_odds:.2f}x")
    
    with col3:
        if total_settled > 0:
            st.metric("Hit Rate", f"{hit_rate_all:.1f}%")
            st.caption(f"{total_wins}W / {total_losses}L")
        else:
            st.metric("Hit Rate", "Pending")
    
    with col4:
        st.metric("Total Profit", f"{total_profit:+.0f} SEK")
        st.caption(f"{total_staked:.0f} SEK staked")
    
    with col5:
        st.metric("ROI", f"{roi:+.1f}%")
        st.caption(f"Avg EV: {avg_ev:.1f}%")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading all-time stats: {e}")

st.markdown("---")

# ============================================================================
# RECENT MONSTERSGP RESULTS
# ============================================================================

st.markdown("## 📜 RECENT MONSTERSGP RESULTS")
st.caption("Last 20 settled MonsterSGP predictions")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # Get recent settled MonsterSGPs
    df_recent = pd.read_sql_query('''
        SELECT 
            home_team,
            away_team,
            parlay_description,
            bookmaker_odds,
            result,
            outcome,
            profit_loss,
            match_date
        FROM sgp_predictions
        WHERE result IS NOT NULL
          AND parlay_description LIKE '%MonsterSGP%'
        ORDER BY timestamp DESC
        LIMIT 20
    ''', conn)
    
    if not df_recent.empty:
        # Format dataframe
        df_display = df_recent.copy()
        df_display['Match'] = df_display['home_team'] + ' vs ' + df_display['away_team']
        df_display['MonsterSGP'] = df_display['parlay_description'].apply(
            lambda x: x[:60] + '...' if len(x) > 60 else x
        )
        df_display['Odds'] = df_display['bookmaker_odds'].apply(lambda x: f"{x:.2f}x")
        df_display['Result'] = df_display['result'].apply(
            lambda x: '✅ WIN' if x == 'WIN' else '❌ LOSS' if x == 'LOSS' else x
        )
        df_display['P/L'] = df_display['profit_loss'].apply(lambda x: f"{x:+.0f} SEK")
        
        # Display table
        st.dataframe(
            df_display[['Match', 'MonsterSGP', 'Odds', 'Result', 'P/L']],
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("📭 No settled MonsterSGP predictions yet. Check back after 1st half ends!")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading recent results: {e}")

st.markdown("---")

# ============================================================================
# MONSTERSGP BY LEG COUNT
# ============================================================================

st.markdown("## 🔢 MONSTERSGP BY LEG COUNT")
st.caption("Performance breakdown by parlay size")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # Get MonsterSGP stats by leg count
    df_legs = pd.read_sql_query('''
        SELECT 
            CASE 
                WHEN parlay_description LIKE '%3-leg%' THEN '3-Leg'
                WHEN parlay_description LIKE '%4-leg%' THEN '4-Leg'
                WHEN parlay_description LIKE '%5-Leg%' THEN '5-Leg'
                WHEN parlay_description LIKE '%6-Leg%' THEN '6-Leg'
                WHEN parlay_description LIKE '%7-LEG BEAST%' THEN '7-Leg BEAST'
                ELSE 'Unknown'
            END as leg_count,
            COUNT(*) as total,
            COUNT(CASE WHEN result IS NOT NULL THEN 1 END) as settled,
            COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
            AVG(bookmaker_odds) as avg_odds,
            MAX(bookmaker_odds) as max_odds,
            SUM(CASE WHEN result IS NOT NULL THEN profit_loss ELSE 0 END) as profit
        FROM sgp_predictions
        WHERE parlay_description LIKE '%MonsterSGP%'
        GROUP BY leg_count
        ORDER BY 
            CASE leg_count
                WHEN '3-Leg' THEN 1
                WHEN '4-Leg' THEN 2
                WHEN '5-Leg' THEN 3
                WHEN '6-Leg' THEN 4
                WHEN '7-Leg BEAST' THEN 5
                ELSE 6
            END
    ''', conn)
    
    if not df_legs.empty:
        # Format dataframe
        df_display = df_legs.copy()
        df_display['Total'] = df_display['total']
        df_display['Settled'] = df_display['settled']
        df_display['Win Rate'] = df_display.apply(
            lambda x: f"{x['wins'] / x['settled'] * 100:.1f}%" if x['settled'] > 0 else "Pending",
            axis=1
        )
        df_display['Avg Odds'] = df_display['avg_odds'].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
        df_display['Max Odds'] = df_display['max_odds'].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
        df_display['P/L'] = df_display['profit'].apply(lambda x: f"{x:+.0f} SEK" if pd.notna(x) else "0 SEK")
        
        # Display table
        st.dataframe(
            df_display[['leg_count', 'Total', 'Settled', 'Win Rate', 'Avg Odds', 'Max Odds', 'P/L']].rename(columns={'leg_count': 'Leg Count'}),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("📭 No MonsterSGP data yet by leg count.")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading leg count breakdown: {e}")

st.markdown("---")

# Footer
st.caption("🔥 MonsterSGP | 1st Half Only Parlays - Results in 45 Minutes!")
