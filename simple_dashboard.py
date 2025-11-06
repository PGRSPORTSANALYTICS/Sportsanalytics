#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date

# Database path
DB_PATH = 'data/real_football.db'

# Page setup
st.set_page_config(
    page_title="🎯 Exact Score Predictions | Premium AI Platform",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Dark Theme CSS
st.markdown("""
<style>
    /* Dark Premium Background */
    .stApp {
        background: #0D1117;
        color: #E6EDF3;
    }
    
    /* Gold Accents for Premium Feel */
    h1 {
        color: #FFD700 !important;
        font-size: 3.5rem !important;
        font-weight: 800 !important;
        text-align: center;
        margin-bottom: 0.5rem !important;
        letter-spacing: -1px;
    }
    
    h2 {
        color: #FFD700 !important;
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        margin-top: 2.5rem !important;
        margin-bottom: 1.5rem !important;
    }
    
    /* Premium Metrics */
    [data-testid="stMetricValue"] {
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        color: #FFD700 !important;
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
    
    /* Premium Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        color: #000;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 0.6rem 1.5rem;
        font-size: 0.95rem;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255, 215, 0, 0.3);
    }
    
    /* Clean Tables */
    [data-testid="stDataFrame"] {
        background: #161B22;
        border-radius: 8px;
        border: 1px solid #21262D;
    }
    
    /* Success boxes */
    .stAlert {
        background: rgba(63, 185, 80, 0.1) !important;
        border: 1px solid rgba(63, 185, 80, 0.3) !important;
        border-radius: 6px;
    }
    
    /* Info boxes */
    .element-container:has(.stMarkdown) .stMarkdown {
        color: #E6EDF3;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0D1117;
        border-right: 1px solid #21262D;
    }
    
    /* Caption text */
    .caption {
        color: #8B949E !important;
        font-size: 0.85rem;
    }
    
    /* Centered subtitle */
    .subtitle {
        text-align: center;
        color: #3FB950;
        font-size: 1.2rem;
        margin-bottom: 1rem;
        font-weight: 600;
        letter-spacing: 1px;
    }
    
    /* Premium badge */
    .premium-badge {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        color: #000;
        padding: 0.4rem 1.2rem;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.85rem;
        display: inline-block;
        margin: 0.5rem 0;
        letter-spacing: 0.5px;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions
def load_performance_summary():
    """Load overall performance for both products"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Exact Score stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN outcome IN ('won', 'win') THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome IN ('lost', 'loss') THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN outcome IN ('won', 'win', 'lost', 'loss') THEN stake ELSE 0 END) as staked,
                SUM(CASE WHEN outcome IN ('won', 'win') THEN stake * (odds - 1) 
                         WHEN outcome IN ('lost', 'loss') THEN -stake 
                         ELSE 0 END) as profit,
                AVG(CASE WHEN outcome IN ('won', 'win', 'lost', 'loss') THEN odds END) as avg_odds
            FROM football_opportunities
            WHERE market = 'exact_score'
        ''')
        exact = cursor.fetchone()
        
        # SGP stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN status = 'settled' THEN stake ELSE 0 END) as staked,
                SUM(profit_loss) as profit,
                AVG(CASE WHEN status = 'settled' THEN bookmaker_odds END) as avg_odds
            FROM sgp_predictions
        ''')
        sgp = cursor.fetchone()
        
        conn.close()
        
        return {
            'exact': {
                'total': exact[0] or 0,
                'wins': exact[1] or 0,
                'losses': exact[2] or 0,
                'staked': exact[3] or 0,
                'profit': exact[4] or 0,
                'avg_odds': exact[5] or 0
            },
            'sgp': {
                'total': sgp[0] or 0,
                'wins': sgp[1] or 0,
                'losses': sgp[2] or 0,
                'staked': sgp[3] or 0,
                'profit': sgp[4] or 0,
                'avg_odds': sgp[5] or 0
            }
        }
    except Exception as e:
        return None

def load_todays_predictions():
    """Load predictions for today"""
    try:
        conn = sqlite3.connect(DB_PATH)
        today = date.today().isoformat()
        
        # Today's exact scores
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                home_team, away_team, selection, odds, 
                edge_percentage, league, timestamp
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND DATE(timestamp) = ?
            ORDER BY timestamp DESC
        ''', (today,))
        
        exact_predictions = []
        for row in cursor.fetchall():
            match_time = datetime.fromtimestamp(row[6]) if isinstance(row[6], (int, float)) else datetime.fromisoformat(row[6])
            exact_predictions.append({
                'Match': f"{row[0]} vs {row[1]}",
                'Prediction': row[2],
                'Odds': f"{row[3]:.2f}x",
                'Edge': f"{row[4]:.1f}%",
                'League': row[5],
                'Time': match_time.strftime('%H:%M')
            })
        
        # Today's SGPs
        cursor.execute('''
            SELECT 
                home_team, away_team, parlay_description,
                bookmaker_odds, ev_percentage, timestamp
            FROM sgp_predictions
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp DESC
        ''', (today,))
        
        sgp_predictions = []
        for row in cursor.fetchall():
            match_time = datetime.fromtimestamp(row[5]) if isinstance(row[5], (int, float)) else datetime.fromisoformat(row[5])
            sgp_predictions.append({
                'Match': f"{row[0]} vs {row[1]}",
                'Parlay': row[2],
                'Odds': f"{row[3]:.2f}x",
                'Edge': f"{row[4]:.1f}%",
                'Time': match_time.strftime('%H:%M')
            })
        
        conn.close()
        return exact_predictions, sgp_predictions
    except Exception as e:
        return [], []

# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

with st.sidebar:
    st.markdown("## 📋 Navigation")
    page = st.radio(
        "Choose Section:",
        ["📊 Dashboard", "📜 Terms & Legal"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### 🎯 Premium AI Platform")
    st.caption("Exact Score & SGP Predictions")
    st.caption("100% Data-Driven Analysis")
    
    st.markdown("---")
    st.markdown("### 📱 Telegram Bot")
    st.caption("Track bets on mobile:")
    st.code("/active - All active bets")
    st.code("/live - Matches in play")
    st.code("/today - Today's bets")
    
    st.markdown("---")
    st.caption("🔒 Subscriber Access Only")
    st.caption("Premium Predictions Platform")

# ============================================================================
# TERMS & LEGAL PAGE
# ============================================================================

if page == "📜 Terms & Legal":
    st.markdown("# 📜 Terms & Legal Information")
    
    st.markdown("## 🇬🇧 English")
    st.markdown("### Terms of Service")
    try:
        with open('legal/terms_of_service_en.md', 'r', encoding='utf-8') as f:
            st.markdown(f.read())
    except:
        st.error("Terms of Service not found")
    
    st.markdown("---")
    st.markdown("### Risk Disclaimer")
    try:
        with open('legal/risk_disclaimer_en.md', 'r', encoding='utf-8') as f:
            st.markdown(f.read())
    except:
        st.error("Risk Disclaimer not found")
    
    st.markdown("---")
    st.markdown("### Privacy Policy")
    try:
        with open('legal/privacy_policy_en.md', 'r', encoding='utf-8') as f:
            st.markdown(f.read())
    except:
        st.error("Privacy Policy not found")
    
    st.markdown("---")
    st.markdown("## 🇸🇪 Svenska")
    st.markdown("### Användarvillkor")
    try:
        with open('legal/terms_of_service_sv.md', 'r', encoding='utf-8') as f:
            st.markdown(f.read())
    except:
        st.error("Användarvillkor hittades inte")
    
    st.markdown("---")
    st.markdown("### Riskvarning")
    try:
        with open('legal/risk_disclaimer_sv.md', 'r', encoding='utf-8') as f:
            st.markdown(f.read())
    except:
        st.error("Riskvarning hittades inte")
    
    st.markdown("---")
    st.markdown("### Integritetspolicy")
    try:
        with open('legal/privacy_policy_sv.md', 'r', encoding='utf-8') as f:
            st.markdown(f.read())
    except:
        st.error("Integritetspolicy hittades inte")
    
    st.markdown("---")
    st.markdown("## 🇸🇪 Responsible Gambling Support")
    st.info("""
    **Stödlinjen (Swedish Gambling Support):**
    - Phone: 020-819 100
    - Website: [stodlinjen.se](https://www.stodlinjen.se)
    
    **Important:** Gambling involves risk. Only bet what you can afford to lose.
    """)
    
    st.markdown("---")
    st.caption("Last Updated: October 26, 2025")
    st.caption("Governed by Swedish Law | All Rights Reserved")
    
    st.stop()

# ============================================================================
# MAIN DASHBOARD PAGE
# ============================================================================

# Hero Banner with Logo
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    try:
        st.image("assets/logo.png", use_container_width=True)
    except:
        st.markdown("# 🎯 AI PREDICTIONS PLATFORM")

st.markdown("")  # Spacing

# Load performance data
stats = load_performance_summary()

if stats:
    exact = stats['exact']
    sgp = stats['sgp']
    
    # Calculate combined ROI
    total_staked = exact['staked'] + sgp['staked']
    total_profit = exact['profit'] + sgp['profit']
    combined_roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    
    st.markdown(f'<div class="premium-badge">⚡ VERIFIED +{combined_roi:.0f}% ROI</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">100% Authentic Results | AI-Powered Analysis</p>', unsafe_allow_html=True)
else:
    st.markdown('<p class="subtitle">Premium AI-Powered Predictions</p>', unsafe_allow_html=True)

# Refresh button
col1, col2 = st.columns([5, 1])
with col2:
    if st.button("🔄 REFRESH"):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ============================================================================
# PERFORMANCE SUMMARY (Clean & Simple)
# ============================================================================

st.markdown("## 📈 PERFORMANCE SUMMARY")

if stats:
    exact = stats['exact']
    sgp = stats['sgp']
    
    # Calculate 30-day performance
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN outcome IN ('won', 'win', 'lost', 'loss') THEN stake ELSE 0 END) as staked,
                SUM(CASE WHEN outcome IN ('won', 'win') THEN stake * (odds - 1) 
                         WHEN outcome IN ('lost', 'loss') THEN -stake 
                         ELSE 0 END) as profit
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND timestamp >= datetime('now', '-30 days')
        ''')
        exact_30d = cursor.fetchone()
        
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN status = 'settled' THEN stake ELSE 0 END) as staked,
                SUM(profit_loss) as profit
            FROM sgp_predictions
            WHERE timestamp >= datetime('now', '-30 days')
        ''')
        sgp_30d = cursor.fetchone()
        conn.close()
        
        total_30d_staked = (exact_30d[0] or 0) + (sgp_30d[0] or 0)
        total_30d_profit = (exact_30d[1] or 0) + (sgp_30d[1] or 0)
        roi_30d = (total_30d_profit / total_30d_staked * 100) if total_30d_staked > 0 else 0
    except:
        roi_30d = None
    
    # Two-product layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### ⚽ EXACT SCORE")
        
        exact_settled = exact['wins'] + exact['losses']
        exact_hit_rate = (exact['wins'] / exact_settled * 100) if exact_settled > 0 else 0
        exact_roi = (exact['profit'] / exact['staked'] * 100) if exact['staked'] > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Predictions", int(exact['total']))
        with m2:
            st.metric("Hit Rate", f"{exact_hit_rate:.1f}%")
        with m3:
            st.metric("ROI", f"{exact_roi:+.0f}%")
        
        st.caption(f"💰 Profit: {exact['profit']:,.0f} SEK | Avg Odds: {exact['avg_odds']:.1f}x")
    
    with col2:
        st.markdown("### 🎲 SGP PARLAYS")
        
        sgp_settled = sgp['wins'] + sgp['losses']
        sgp_hit_rate = (sgp['wins'] / sgp_settled * 100) if sgp_settled > 0 else 0
        sgp_roi = (sgp['profit'] / sgp['staked'] * 100) if sgp['staked'] > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Predictions", int(sgp['total']))
        with m2:
            st.metric("Hit Rate", f"{sgp_hit_rate:.1f}%")
        with m3:
            st.metric("ROI", f"{sgp_roi:+.0f}%")
        
        st.caption(f"💰 Profit: {sgp['profit']:,.0f} SEK | Avg Odds: {sgp['avg_odds']:.1f}x")
    
    # 30-day performance badge
    if roi_30d is not None and roi_30d != 0:
        st.success(f"✅ **All results verified** from API-Football | 📊 Last 30 days: {roi_30d:+.0f}% ROI")
    else:
        st.success("✅ **All results verified** from API-Football & live scores")

else:
    st.info("Loading performance data...")

st.markdown("---")

# ============================================================================
# TODAY'S PREDICTIONS (Most Important for Subscribers)
# ============================================================================

st.markdown("## 🎯 TODAY'S PREDICTIONS")

exact_today, sgp_today = load_todays_predictions()

# Top Edge Picks - Spotlight highest value plays
if exact_today or sgp_today:
    all_today = exact_today + sgp_today
    if all_today:
        # Find highest EV plays
        for pred in all_today:
            pred['edge_val'] = float(pred['Edge'].replace('%', ''))
        
        top_picks = sorted(all_today, key=lambda x: x['edge_val'], reverse=True)[:2]
        
        if top_picks:
            st.markdown("### ⭐ TOP EDGE PICKS")
            cols = st.columns(len(top_picks))
            for idx, pick in enumerate(top_picks):
                with cols[idx]:
                    st.markdown(f"**{pick['Match']}**")
                    if 'Prediction' in pick:
                        st.markdown(f"🎯 {pick['Prediction']} @ {pick['Odds']}")
                    else:
                        st.markdown(f"🎲 {pick['Parlay'][:30]}... @ {pick['Odds']}")
                    st.markdown(f"<div class='premium-badge'>+{pick['Edge']} EDGE</div>", unsafe_allow_html=True)
            st.markdown("")

if exact_today or sgp_today:
    
    tab1, tab2 = st.tabs(["⚽ Exact Score", "🎲 SGP Parlays"])
    
    with tab1:
        if exact_today:
            st.markdown(f"**{len(exact_today)} exact score predictions today**")
            df_exact = pd.DataFrame(exact_today)
            st.dataframe(df_exact, width='stretch', hide_index=True)
        else:
            st.info("No exact score predictions today")
    
    with tab2:
        if sgp_today:
            st.markdown(f"**{len(sgp_today)} SGP predictions today**")
            df_sgp = pd.DataFrame(sgp_today)
            st.dataframe(df_sgp, width='stretch', hide_index=True)
        else:
            st.info("No SGP predictions today")

else:
    st.info("📅 No predictions generated yet today. Check back soon!")
    st.caption("Predictions typically drop in the morning (09:00 CET)")

st.markdown("---")

# ============================================================================
# ALL ACTIVE PREDICTIONS
# ============================================================================

st.markdown("## 📋 ALL ACTIVE PREDICTIONS")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # Get all pending exact scores
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            home_team, away_team, selection, odds, 
            edge_percentage, league, timestamp, stake
        FROM football_opportunities
        WHERE market = 'exact_score'
        AND result IS NULL
        ORDER BY timestamp DESC
        LIMIT 50
    ''')
    
    all_exact = []
    for row in cursor.fetchall():
        # Convert Unix timestamp to datetime
        match_time = datetime.fromtimestamp(row[6]) if isinstance(row[6], (int, float)) else datetime.fromisoformat(row[6])
        all_exact.append({
            'Match': f"{row[0]} vs {row[1]}",
            'Prediction': row[2],
            'Odds': f"{row[3]:.2f}x",
            'Edge': f"{row[4]:.1f}%",
            'League': row[5],
            'Date': match_time.strftime('%Y-%m-%d'),
            'Time': match_time.strftime('%H:%M'),
            'Stake': f"{row[7]:.0f} SEK"
        })
    
    # Get all pending SGPs
    cursor.execute('''
        SELECT 
            home_team, away_team, parlay_description,
            bookmaker_odds, ev_percentage, timestamp, stake
        FROM sgp_predictions
        WHERE status = 'pending'
        ORDER BY timestamp DESC
        LIMIT 50
    ''')
    
    all_sgp = []
    for row in cursor.fetchall():
        # Convert Unix timestamp to datetime
        match_time = datetime.fromtimestamp(row[5]) if isinstance(row[5], (int, float)) else datetime.fromisoformat(row[5])
        all_sgp.append({
            'Match': f"{row[0]} vs {row[1]}",
            'Parlay': row[2][:50] + '...' if len(row[2]) > 50 else row[2],
            'Odds': f"{row[3]:.2f}x",
            'Edge': f"{row[4]:.1f}%",
            'Date': match_time.strftime('%Y-%m-%d'),
            'Time': match_time.strftime('%H:%M'),
            'Stake': f"{row[6]:.0f} SEK"
        })
    
    conn.close()
    
    if all_exact or all_sgp:
        tab1, tab2 = st.tabs([f"⚽ Exact Score ({len(all_exact)})", f"🎲 SGP ({len(all_sgp)})"])
        
        with tab1:
            if all_exact:
                df_all_exact = pd.DataFrame(all_exact)
                st.dataframe(df_all_exact, width='stretch', hide_index=True)
                
                total_stake = sum([float(p['Stake'].replace(' SEK', '')) for p in all_exact])
                st.caption(f"💰 Total Active Stake: {total_stake:,.0f} SEK across {len(all_exact)} predictions")
            else:
                st.info("No active exact score predictions")
        
        with tab2:
            if all_sgp:
                df_all_sgp = pd.DataFrame(all_sgp)
                st.dataframe(df_all_sgp, width='stretch', hide_index=True)
                
                total_stake = sum([float(p['Stake'].replace(' SEK', '')) for p in all_sgp])
                st.caption(f"💰 Total Active Stake: {total_stake:,.0f} SEK across {len(all_sgp)} predictions")
            else:
                st.info("No active SGP predictions")
    else:
        st.info("No active predictions at the moment")

except Exception as e:
    st.warning(f"Loading predictions... {str(e)}")

st.markdown("---")

# ============================================================================
# LEAGUE BREAKDOWN (Compact View)
# ============================================================================

st.markdown("## 🌍 LEAGUE BREAKDOWN")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            league,
            COUNT(*) as total,
            SUM(CASE WHEN outcome IN ('won', 'win') THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome IN ('lost', 'loss') THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN outcome IN ('won', 'win', 'lost', 'loss') THEN stake ELSE 0 END) as staked,
            SUM(CASE WHEN outcome IN ('won', 'win') THEN stake * (odds - 1) 
                     WHEN outcome IN ('lost', 'loss') THEN -stake 
                     ELSE 0 END) as profit
        FROM football_opportunities
        WHERE market = 'exact_score'
        GROUP BY league
        HAVING COUNT(*) >= 5
        ORDER BY total DESC
        LIMIT 10
    ''')
    
    league_data = []
    for row in cursor.fetchall():
        settled = row[2] + row[3]
        hit_rate = (row[2] / settled * 100) if settled > 0 else 0
        roi = (row[5] / row[4] * 100) if row[4] > 0 else 0
        
        # Status emoji
        if settled >= 10:
            if hit_rate >= 20:
                status = "🟢"
            elif hit_rate >= 15:
                status = "🟡"
            else:
                status = "🔴"
        else:
            status = "⚪"
        
        league_data.append({
            'S': status,
            'League': row[0],
            'Total': row[1],
            'Settled': settled,
            'Hit Rate': f"{hit_rate:.1f}%",
            'ROI': f"{roi:+.0f}%",
            'Profit': f"{row[5]:.0f} SEK"
        })
    
    conn.close()
    
    if league_data:
        df_leagues = pd.DataFrame(league_data)
        st.dataframe(df_leagues, width='stretch', hide_index=True)
        st.caption("🟢 Strong (20%+) | 🟡 Good (15-20%) | 🔴 Weak (<15%) | ⚪ Early (<10 settled)")
    else:
        st.info("No league data available yet")

except Exception as e:
    st.warning("Loading league data...")

st.markdown("---")

# Footer
st.caption("🔒 **Premium Subscriber Dashboard** | All predictions verified with authentic results")
st.caption("For mobile access, use Telegram bot commands: /active, /live, /today")
st.caption(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} CET")
