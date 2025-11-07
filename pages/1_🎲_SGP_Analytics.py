#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from stats_master import get_sgp_results

# Database path
DB_PATH = 'data/real_football.db'

# Page setup
st.set_page_config(
    page_title="🎲 SGP Analytics | Premium AI Platform",
    page_icon="🎲",
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
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("# 🎲 SGP ANALYTICS")
st.caption("Same Game Parlay predictions powered by AI and live bookmaker odds")

st.markdown("---")

# ============================================================================
# TODAY'S SGP STATS
# ============================================================================

st.markdown("## 📊 TODAY'S SGP PREDICTIONS")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get today's SGP stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN result IS NOT NULL THEN 1 END) as settled,
            COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
            COUNT(CASE WHEN result = 'LOSS' THEN 1 END) as losses,
            SUM(CASE WHEN result IS NOT NULL THEN profit_loss ELSE 0 END) as profit,
            AVG(bookmaker_odds) as avg_odds,
            AVG(ev_percentage) as avg_ev
        FROM sgp_predictions
        WHERE DATE(match_date) = DATE('now')
    ''')
    
    row = cursor.fetchone()
    total_today = row[0]
    settled_today = row[1]
    wins_today = row[2]
    losses_today = row[3]
    profit_today = row[4] or 0
    avg_odds_today = row[5] or 0
    avg_ev_today = row[6] or 0
    
    hit_rate_today = (wins_today / settled_today * 100) if settled_today > 0 else 0
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total SGPs Today", total_today)
        st.caption(f"Avg Odds: {avg_odds_today:.2f}x")
    
    with col2:
        st.metric("Settled", settled_today, delta=f"{wins_today}W / {losses_today}L")
    
    with col3:
        if settled_today > 0:
            st.metric("Hit Rate", f"{hit_rate_today:.1f}%")
        else:
            st.metric("Hit Rate", "Pending")
    
    with col4:
        profit_color = "🟢" if profit_today > 0 else "🔴" if profit_today < 0 else "⚪"
        st.metric("P/L Today", f"{profit_today:+.0f} SEK", delta=profit_color)
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading today's stats: {e}")

st.markdown("---")

# ============================================================================
# ACTIVE SGP PREDICTIONS
# ============================================================================

st.markdown("## 🎯 ACTIVE SGP PREDICTIONS")
st.caption("Live SGP parlays waiting for results")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # Get active SGPs
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
        ORDER BY match_date ASC
        LIMIT 50
    ''', conn)
    
    if not df_active.empty:
        st.success(f"✅ {len(df_active)} active SGP predictions")
        
        # Format dataframe
        df_display = df_active.copy()
        df_display['Match'] = df_display['home_team'] + ' vs ' + df_display['away_team']
        df_display['Parlay'] = df_display['parlay_description']
        df_display['Odds'] = df_display['bookmaker_odds'].apply(lambda x: f"{x:.2f}x")
        df_display['EV'] = df_display['ev_percentage'].apply(lambda x: f"{x:.1f}%")
        df_display['Stake'] = df_display['stake'].apply(lambda x: f"{x:.0f} SEK")
        
        # Add pricing mode indicator
        df_display['Mode'] = df_display['pricing_mode'].apply(
            lambda x: '🟢 Live' if x == 'live' else '🟡 Hybrid' if x == 'hybrid' else '⚪ Sim'
        )
        
        # Display table
        st.dataframe(
            df_display[['Match', 'Parlay', 'Odds', 'EV', 'Stake', 'Mode']],
            hide_index=True,
            width='stretch'
        )
    else:
        st.info("📭 No active SGP predictions. Next generation cycle starts soon!")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading active SGPs: {e}")

st.markdown("---")

# ============================================================================
# ALL-TIME SGP STATISTICS
# ============================================================================

st.markdown("## 🏆 ALL-TIME SGP STATISTICS")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all-time stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN result IS NOT NULL THEN 1 END) as settled,
            COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
            COUNT(CASE WHEN result = 'LOSS' THEN 1 END) as losses,
            SUM(CASE WHEN result IS NOT NULL THEN profit_loss ELSE 0 END) as total_profit,
            SUM(CASE WHEN result IS NOT NULL THEN stake ELSE 0 END) as total_staked,
            AVG(CASE WHEN result IS NOT NULL THEN bookmaker_odds END) as avg_odds,
            AVG(CASE WHEN result IS NOT NULL THEN ev_percentage END) as avg_ev
        FROM sgp_predictions
    ''')
    
    row = cursor.fetchone()
    total_sgps = row[0]
    total_settled = row[1]
    total_wins = row[2]
    total_losses = row[3]
    total_profit = row[4] or 0
    total_staked = row[5] or 0
    avg_odds = row[6] or 0
    avg_ev = row[7] or 0
    
    hit_rate_all = (total_wins / total_settled * 100) if total_settled > 0 else 0
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
    
    # Display metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total SGPs", total_sgps)
        st.caption(f"{total_settled} settled")
    
    with col2:
        st.metric("Wins", total_wins)
        st.caption(f"{total_losses} losses")
    
    with col3:
        st.metric("Hit Rate", f"{hit_rate_all:.1f}%")
        target = 25.0
        delta_text = f"{hit_rate_all - target:+.1f}% vs target"
        st.caption(delta_text)
    
    with col4:
        st.metric("Total Profit", f"{total_profit:+.0f} SEK")
        st.caption(f"{total_staked:.0f} SEK staked")
    
    with col5:
        st.metric("ROI", f"{roi:+.1f}%")
        st.caption(f"Avg odds: {avg_odds:.2f}x")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading all-time stats: {e}")

st.markdown("---")

# ============================================================================
# RECENT SGP RESULTS
# ============================================================================

st.markdown("## 📜 RECENT SGP RESULTS")
st.caption("Last 20 settled SGP predictions")

try:
    conn = sqlite3.connect(DB_PATH)
    
    # Get recent settled SGPs
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
        ORDER BY timestamp DESC
        LIMIT 20
    ''', conn)
    
    if not df_recent.empty:
        # Format dataframe
        df_display = df_recent.copy()
        df_display['Match'] = df_display['home_team'] + ' vs ' + df_display['away_team']
        df_display['Parlay'] = df_display['parlay_description'].apply(
            lambda x: x[:50] + '...' if len(x) > 50 else x
        )
        df_display['Odds'] = df_display['bookmaker_odds'].apply(lambda x: f"{x:.2f}x")
        df_display['Result'] = df_display['result'].apply(
            lambda x: '✅ WIN' if x == 'WIN' else '❌ LOSS' if x == 'LOSS' else x
        )
        df_display['P/L'] = df_display['profit_loss'].apply(lambda x: f"{x:+.0f} SEK")
        
        # Display table
        st.dataframe(
            df_display[['Match', 'Parlay', 'Odds', 'Result', 'P/L']],
            hide_index=True,
            width='stretch'
        )
    else:
        st.info("📭 No settled SGP predictions yet. Check back after matches finish!")
    
    conn.close()
    
except Exception as e:
    st.error(f"Error loading recent results: {e}")

st.markdown("---")

# ============================================================================
# SGP HISTORICAL PREDICTIONS BY MONTH
# ============================================================================

st.markdown("## 📁 SGP MONTHLY HISTORY")
st.caption("SGP parlays organized by month for easy tracking")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all settled SGPs grouped by month
    cursor.execute('''
        SELECT 
            strftime('%Y-%m', match_date) as month,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
            SUM(profit_loss) as profit
        FROM sgp_predictions
        WHERE result IS NOT NULL
        GROUP BY strftime('%Y-%m', match_date)
        ORDER BY month DESC
    ''')
    
    sgp_months = {}
    for row in cursor.fetchall():
        month_key = row[0]
        sgp_months[month_key] = {
            'total': row[1],
            'wins': row[2],
            'profit': row[3]
        }
    
    if sgp_months:
        for month_key, month_data in sgp_months.items():
            # Parse month name
            try:
                month_date = datetime.strptime(month_key, '%Y-%m')
                month_name = month_date.strftime('%B %Y')
            except:
                month_name = month_key
            
            # Calculate month totals
            month_total = month_data['total']
            month_wins = month_data['wins']
            month_profit = month_data['profit']
            month_hit_rate = (month_wins / month_total * 100) if month_total > 0 else 0
            
            # Create expander for each month
            with st.expander(f"📁 {month_name} - {month_total} SGPs ({month_hit_rate:.1f}% hit rate, {month_profit:+.0f} SEK)", expanded=False):
                
                # Month summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Settled", month_total)
                with col2:
                    st.metric("Win Rate", f"{month_hit_rate:.1f}%", delta=f"{month_wins}W / {month_total - month_wins}L")
                with col3:
                    st.metric("Profit/Loss", f"{month_profit:+.0f} SEK")
                
                st.markdown("---")
                
                # Get detailed SGP predictions for this month
                cursor.execute('''
                    SELECT 
                        home_team, away_team, parlay_description,
                        bookmaker_odds, result, outcome,
                        profit_loss, match_date
                    FROM sgp_predictions
                    WHERE result IS NOT NULL
                    AND strftime('%Y-%m', match_date) = ?
                    ORDER BY match_date DESC
                ''', (month_key,))
                
                sgp_results = []
                for row in cursor.fetchall():
                    try:
                        match_dt = datetime.fromisoformat(str(row[7]).replace('Z', '+00:00'))
                        date_str = match_dt.strftime('%b %d')
                    except:
                        date_str = "Unknown"
                    
                    sgp_results.append({
                        'Date': date_str,
                        'Match': f"{row[0]} vs {row[1]}",
                        'Parlay': row[2][:50] + '...' if len(row[2]) > 50 else row[2],
                        'Result': '✅ WIN' if row[4] == 'WIN' else '❌ LOSS' if row[4] == 'LOSS' else row[4],
                        'Odds': f"{row[3]:.2f}x",
                        'P/L': f"{row[6]:+.0f} SEK"
                    })
                
                if sgp_results:
                    df_sgp = pd.DataFrame(sgp_results)
                    st.dataframe(df_sgp, width='stretch', hide_index=True)
                else:
                    st.info("No SGP predictions this month")
    else:
        st.info("No SGP historical predictions yet. Check back after matches settle!")
    
    conn.close()

except Exception as e:
    st.error(f"Error loading SGP monthly history: {e}")

st.markdown("---")

# Footer
st.caption("🎲 SGP Analytics | Powered by AI + Live Bookmaker Odds")
