#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from stats_master import get_all_time_stats, get_todays_exact_score_stats, get_exact_score_results, get_sgp_results

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
    """Load overall performance for both products - BULLETPROOF VERSION"""
    try:
        # Use stats_master for 100% accuracy
        stats = get_all_time_stats()
        
        # Calculate avg odds manually from database for backwards compatibility
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT AVG(odds) FROM football_opportunities WHERE market = "exact_score" AND result IS NOT NULL')
        exact_avg_odds = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT AVG(bookmaker_odds) FROM sgp_predictions WHERE result IS NOT NULL')
        sgp_avg_odds = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'exact': {
                'total': stats['exact_score']['total'],
                'wins': stats['exact_score']['wins'],
                'losses': stats['exact_score']['losses'],
                'staked': stats['exact_score']['total'] * 160,  # All bets are 160 SEK
                'profit': stats['exact_score']['profit'],
                'avg_odds': exact_avg_odds
            },
            'sgp': {
                'total': stats['sgp']['total'],
                'wins': stats['sgp']['wins'],
                'losses': stats['sgp']['losses'],
                'staked': stats['sgp']['total'] * 160,  # All bets are 160 SEK
                'profit': stats['sgp']['profit'],
                'avg_odds': sgp_avg_odds
            }
        }
    except Exception as e:
        st.error(f"Error loading stats: {e}")
        return None

def load_todays_predictions():
    """Load predictions for today"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Calculate today's timestamp range
        from datetime import datetime, time
        today_start = datetime.combine(date.today(), time.min).timestamp()
        today_end = datetime.combine(date.today(), time.max).timestamp()
        
        # Today's exact scores
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                home_team, away_team, selection, odds, 
                edge_percentage, league, timestamp
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        ''', (today_start, today_end))
        
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
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        ''', (today_start, today_end))
        
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
        ["📊 Dashboard", "⚽ Exact Score Analytics", "🎲 SGP Analytics", "📜 Terms & Legal"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    # Historical Results Section - Now clickable
    st.markdown("### 📊 HISTORICAL RESULTS")
    st.caption("Click sections above to view detailed analytics")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Exact Score History
        cursor.execute('''
            SELECT 
                COUNT(*) as settled,
                SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as wins,
                SUM(stake) as total_staked,
                SUM(CASE WHEN payout > 0 THEN payout - stake 
                         ELSE -stake END) as net_profit
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND result IS NOT NULL
        ''')
        exact_hist = cursor.fetchone()
        
        # SGP History
        cursor.execute('''
            SELECT 
                COUNT(*) as settled,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(stake) as total_staked,
                SUM(profit_loss) as net_profit
            FROM sgp_predictions
            WHERE status = 'settled'
        ''')
        sgp_hist = cursor.fetchone()
        
        conn.close()
        
        # Display Exact Score Results
        st.markdown("**⚽ Exact Score**")
        if exact_hist and exact_hist[0] > 0:
            settled = exact_hist[0]
            wins = exact_hist[1] or 0
            staked = exact_hist[2] or 0
            profit = exact_hist[3] or 0
            hit_rate = (wins / settled * 100) if settled > 0 else 0
            roi = (profit / staked * 100) if staked > 0 else 0
            
            st.metric("Settled", f"{settled}", delta=f"{hit_rate:.1f}% hit rate")
            st.metric("ROI", f"{roi:+.0f}%", delta=f"{profit:+.0f} SEK")
        else:
            st.caption("No settled predictions yet")
        
        st.markdown("")
        
        # Display SGP Results
        st.markdown("**🎲 SGP Parlays**")
        if sgp_hist and sgp_hist[0] > 0:
            settled = sgp_hist[0]
            wins = sgp_hist[1] or 0
            staked = sgp_hist[2] or 0
            profit = sgp_hist[3] or 0
            hit_rate = (wins / settled * 100) if settled > 0 else 0
            roi = (profit / staked * 100) if staked > 0 else 0
            
            st.metric("Settled", f"{settled}", delta=f"{hit_rate:.1f}% hit rate")
            st.metric("ROI", f"{roi:+.0f}%", delta=f"{profit:+.0f} SEK")
        else:
            st.caption("No settled predictions yet")
            
    except Exception as e:
        st.caption("Loading results...")
    
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
# PAGE: EXACT SCORE ANALYTICS (Technical Dashboard)
# ============================================================================

if page == "⚽ Exact Score Analytics":
    st.markdown("# ⚽ EXACT SCORE ANALYTICS")
    st.markdown('<p class="subtitle">Detailed Performance Analysis | ROI Tracking</p>', unsafe_allow_html=True)
    
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Overall Stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN payout = 0 THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_staked,
                SUM(CASE WHEN payout > 0 THEN payout - stake 
                         ELSE -stake END) as net_profit,
                AVG(odds) as avg_odds,
                AVG(edge_percentage) as avg_edge
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND result IS NOT NULL
        ''')
        stats = cursor.fetchone()
        
        if stats and stats[0] > 0:
            total = stats[0]
            wins = stats[1] or 0
            losses = stats[2] or 0
            staked = stats[3] or 0
            profit = stats[4] or 0
            avg_odds = stats[5] or 0
            avg_edge = stats[6] or 0
            
            hit_rate = (wins / total * 100) if total > 0 else 0
            roi = (profit / staked * 100) if staked > 0 else 0
            
            # Key Metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total Settled", total)
            with col2:
                st.metric("Hit Rate", f"{hit_rate:.1f}%", delta=f"{wins}W / {losses}L")
            with col3:
                st.metric("ROI", f"{roi:+.1f}%")
            with col4:
                st.metric("Profit", f"{profit:+,.0f} SEK")
            with col5:
                st.metric("Avg Odds", f"{avg_odds:.2f}x")
            
            st.markdown("---")
            
            # ROI Over Time Chart
            st.markdown("### 📈 ROI OVER TIME")
            
            cursor.execute('''
                SELECT 
                    timestamp,
                    stake,
                    CASE WHEN payout > 0 THEN payout - stake 
                         ELSE -stake END as profit
                FROM football_opportunities
                WHERE market = 'exact_score'
                AND result IS NOT NULL
                ORDER BY timestamp ASC
            ''')
            
            cumulative_profit = 0
            cumulative_stake = 0
            roi_data = []
            
            for row in cursor.fetchall():
                ts = row[0]
                stake = row[1]
                profit = row[2]
                
                cumulative_profit += profit
                cumulative_stake += stake
                roi_pct = (cumulative_profit / cumulative_stake * 100) if cumulative_stake > 0 else 0
                
                dt = datetime.fromtimestamp(ts)
                roi_data.append({
                    'Date': dt.strftime('%Y-%m-%d'),
                    'Cumulative Profit': cumulative_profit,
                    'ROI %': roi_pct
                })
            
            if roi_data:
                df_roi = pd.DataFrame(roi_data)
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_roi['Date'],
                    y=df_roi['ROI %'],
                    mode='lines+markers',
                    name='ROI %',
                    line=dict(color='#FFD700', width=3),
                    fill='tozeroy',
                    fillcolor='rgba(255, 215, 0, 0.1)'
                ))
                
                fig.update_layout(
                    plot_bgcolor='#0D1117',
                    paper_bgcolor='#0D1117',
                    font=dict(color='#E6EDF3'),
                    xaxis=dict(showgrid=True, gridcolor='#21262D'),
                    yaxis=dict(showgrid=True, gridcolor='#21262D', title='ROI %'),
                    hovermode='x unified',
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # Profit Distribution by League
            st.markdown("### 🌍 PROFIT BY LEAGUE")
            
            cursor.execute('''
                SELECT 
                    league,
                    COUNT(*) as bets,
                    SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(stake) as staked,
                    SUM(CASE WHEN payout > 0 THEN payout - stake 
                             ELSE -stake END) as profit
                FROM football_opportunities
                WHERE market = 'exact_score'
                AND result IS NOT NULL
                GROUP BY league
                HAVING COUNT(*) >= 2
                ORDER BY profit DESC
            ''')
            
            league_data = []
            for row in cursor.fetchall():
                league_roi = (row[4] / row[3] * 100) if row[3] > 0 else 0
                league_data.append({
                    'League': row[0],
                    'Bets': row[1],
                    'Hit Rate': f"{(row[2]/row[1]*100):.1f}%",
                    'Profit': row[4],
                    'ROI': league_roi
                })
            
            if league_data:
                df_leagues = pd.DataFrame(league_data)
                
                # Bar chart
                fig = px.bar(
                    df_leagues,
                    x='League',
                    y='Profit',
                    color='ROI',
                    color_continuous_scale=['#FF4444', '#FFD700', '#3FB950'],
                    title='Profit by League'
                )
                
                fig.update_layout(
                    plot_bgcolor='#0D1117',
                    paper_bgcolor='#0D1117',
                    font=dict(color='#E6EDF3'),
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Table
                st.dataframe(df_leagues, width='stretch', hide_index=True)
            
            st.markdown("---")
            
            # Historical Bets List
            st.markdown("### 📜 HISTORICAL BETS")
            
            cursor.execute('''
                SELECT 
                    home_team,
                    away_team,
                    selection,
                    actual_score,
                    outcome,
                    odds,
                    profit_loss,
                    match_date
                FROM football_opportunities
                WHERE market = 'exact_score'
                AND result IS NOT NULL
                ORDER BY settled_timestamp DESC
                LIMIT 50
            ''')
            
            st.markdown('<div style="max-height: 600px; overflow-y: auto;">', unsafe_allow_html=True)
            
            for row in cursor.fetchall():
                home = row[0]
                away = row[1]
                selection = row[2]
                actual_score = row[3] or "N/A"
                outcome = row[4]
                odds = row[5]
                profit = row[6]
                match_date = row[7]
                
                # Extract just the score from selection (remove "Exact Score: " prefix if present)
                predicted_score = selection.replace('Exact Score: ', '') if selection else 'N/A'
                
                # Format date from match_date
                try:
                    if isinstance(match_date, str):
                        # Handle ISO format dates like "2025-11-06T20:00:00Z" or "2025-11-06"
                        if 'T' in match_date:
                            dt = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromisoformat(match_date)
                        date_str = dt.strftime('%b %d, %Y')
                    elif isinstance(match_date, (int, float)):
                        dt = datetime.fromtimestamp(match_date)
                        date_str = dt.strftime('%b %d, %Y')
                    else:
                        date_str = "N/A"
                except:
                    date_str = "N/A"
                
                # Color code based on outcome
                if outcome == 'win':
                    bg_color = "#1a4d2e"  # Dark green
                    border_color = "#3FB950"  # Green
                    icon = "🟢"
                    outcome_text = "WIN"
                else:
                    bg_color = "#4d1a1a"  # Dark red
                    border_color = "#FF4444"  # Red
                    icon = "🔴"
                    outcome_text = "LOSS"
                
                # Display bet card
                st.markdown(f'''
                <div style="
                    background: {bg_color};
                    border-left: 4px solid {border_color};
                    padding: 12px 16px;
                    margin-bottom: 8px;
                    border-radius: 6px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="font-size: 0.95rem; font-weight: 600; color: #E6EDF3; margin-bottom: 4px;">
                                {icon} {home} vs {away}
                            </div>
                            <div style="font-size: 0.85rem; color: #8B949E; margin-bottom: 4px;">
                                Predicted: {predicted_score}
                            </div>
                            <div style="font-size: 0.8rem; color: #6E7681;">
                                Result: {actual_score} | {date_str}
                            </div>
                        </div>
                        <div style="text-align: right; min-width: 120px;">
                            <div style="font-size: 0.9rem; font-weight: 700; color: {border_color};">
                                {outcome_text}
                            </div>
                            <div style="font-size: 0.85rem; color: #8B949E;">
                                @{odds:.2f}x
                            </div>
                            <div style="font-size: 0.9rem; font-weight: 600; color: {'#3FB950' if profit > 0 else '#FF4444'};">
                                {profit:+.0f} SEK
                            </div>
                        </div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        else:
            st.info("No settled predictions yet. Check back after matches complete!")
        
        conn.close()
        
    except Exception as e:
        st.error(f"Error loading analytics: {str(e)}")
    
    st.stop()

# ============================================================================
# PAGE: SGP ANALYTICS (Technical Dashboard)
# ============================================================================

if page == "🎲 SGP Analytics":
    st.markdown("# 🎲 SGP ANALYTICS")
    st.markdown('<p class="subtitle">Same Game Parlay Performance | ROI Tracking</p>', unsafe_allow_html=True)
    
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Overall Stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_staked,
                SUM(profit_loss) as net_profit,
                AVG(bookmaker_odds) as avg_odds,
                AVG(ev_percentage) as avg_edge
            FROM sgp_predictions
            WHERE status = 'settled'
        ''')
        stats = cursor.fetchone()
        
        if stats and stats[0] > 0:
            total = stats[0]
            wins = stats[1] or 0
            losses = stats[2] or 0
            staked = stats[3] or 0
            profit = stats[4] or 0
            avg_odds = stats[5] or 0
            avg_edge = stats[6] or 0
            
            hit_rate = (wins / total * 100) if total > 0 else 0
            roi = (profit / staked * 100) if staked > 0 else 0
            
            # Key Metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Total Settled", total)
            with col2:
                st.metric("Hit Rate", f"{hit_rate:.1f}%", delta=f"{wins}W / {losses}L")
            with col3:
                st.metric("ROI", f"{roi:+.1f}%")
            with col4:
                st.metric("Profit", f"{profit:+,.0f} SEK")
            with col5:
                st.metric("Avg Odds", f"{avg_odds:.2f}x")
            
            st.markdown("---")
            
            # ROI Over Time Chart
            st.markdown("### 📈 ROI OVER TIME")
            
            cursor.execute('''
                SELECT 
                    timestamp,
                    stake,
                    profit_loss
                FROM sgp_predictions
                WHERE status = 'settled'
                ORDER BY timestamp ASC
            ''')
            
            cumulative_profit = 0
            cumulative_stake = 0
            roi_data = []
            
            for row in cursor.fetchall():
                ts = row[0]
                stake = row[1]
                profit = row[2]
                
                cumulative_profit += profit
                cumulative_stake += stake
                roi_pct = (cumulative_profit / cumulative_stake * 100) if cumulative_stake > 0 else 0
                
                dt = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.fromisoformat(ts)
                roi_data.append({
                    'Date': dt.strftime('%Y-%m-%d'),
                    'Cumulative Profit': cumulative_profit,
                    'ROI %': roi_pct
                })
            
            if roi_data:
                df_roi = pd.DataFrame(roi_data)
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_roi['Date'],
                    y=df_roi['ROI %'],
                    mode='lines+markers',
                    name='ROI %',
                    line=dict(color='#FFD700', width=3),
                    fill='tozeroy',
                    fillcolor='rgba(255, 215, 0, 0.1)'
                ))
                
                fig.update_layout(
                    plot_bgcolor='#0D1117',
                    paper_bgcolor='#0D1117',
                    font=dict(color='#E6EDF3'),
                    xaxis=dict(showgrid=True, gridcolor='#21262D'),
                    yaxis=dict(showgrid=True, gridcolor='#21262D', title='ROI %'),
                    hovermode='x unified',
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # Historical Bets List
            st.markdown("### 📜 HISTORICAL BETS")
            
            cursor.execute('''
                SELECT 
                    home_team,
                    away_team,
                    parlay_description,
                    result,
                    outcome,
                    bookmaker_odds,
                    profit_loss,
                    match_date
                FROM sgp_predictions
                WHERE status = 'settled'
                ORDER BY match_date DESC
                LIMIT 50
            ''')
            
            st.markdown('<div style="max-height: 600px; overflow-y: auto;">', unsafe_allow_html=True)
            
            for row in cursor.fetchall():
                home = row[0]
                away = row[1]
                parlay = row[2]
                actual_result = row[3] or "N/A"
                outcome = row[4]
                odds = row[5]
                profit = row[6]
                match_date = row[7]
                
                # Format date from match_date
                try:
                    if isinstance(match_date, str):
                        # Handle ISO format dates like "2025-11-06T20:00:00Z" or "2025-11-06"
                        if 'T' in match_date:
                            dt = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromisoformat(match_date)
                        date_str = dt.strftime('%b %d, %Y')
                    elif isinstance(match_date, (int, float)):
                        dt = datetime.fromtimestamp(match_date)
                        date_str = dt.strftime('%b %d, %Y')
                    else:
                        date_str = "N/A"
                except:
                    date_str = "N/A"
                
                # Color code based on outcome
                if outcome == 'win':
                    bg_color = "#1a4d2e"  # Dark green
                    border_color = "#3FB950"  # Green
                    icon = "🟢"
                    outcome_text = "WIN"
                else:
                    bg_color = "#4d1a1a"  # Dark red
                    border_color = "#FF4444"  # Red
                    icon = "🔴"
                    outcome_text = "LOSS"
                
                # Display bet card
                st.markdown(f'''
                <div style="
                    background: {bg_color};
                    border-left: 4px solid {border_color};
                    padding: 12px 16px;
                    margin-bottom: 8px;
                    border-radius: 6px;
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="font-size: 0.95rem; font-weight: 600; color: #E6EDF3; margin-bottom: 4px;">
                                {icon} {home} vs {away}
                            </div>
                            <div style="font-size: 0.85rem; color: #8B949E; margin-bottom: 4px;">
                                {parlay}
                            </div>
                            <div style="font-size: 0.8rem; color: #6E7681;">
                                Result: {actual_result} | {date_str}
                            </div>
                        </div>
                        <div style="text-align: right; min-width: 120px;">
                            <div style="font-size: 0.9rem; font-weight: 700; color: {border_color};">
                                {outcome_text}
                            </div>
                            <div style="font-size: 0.85rem; color: #8B949E;">
                                @{odds:.2f}x
                            </div>
                            <div style="font-size: 0.9rem; font-weight: 600; color: {'#3FB950' if profit > 0 else '#FF4444'};">
                                {profit:+.0f} SEK
                            </div>
                        </div>
                    </div>
                </div>
                ''', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        else:
            st.info("No settled SGP predictions yet. Check back after matches complete!")
        
        conn.close()
        
    except Exception as e:
        st.error(f"Error loading analytics: {str(e)}")
    
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
            edge_percentage, league, match_date, stake
        FROM football_opportunities
        WHERE market = 'exact_score'
        AND result IS NULL
        ORDER BY match_date ASC
        LIMIT 50
    ''')
    
    all_exact = []
    for row in cursor.fetchall():
        # Parse match_date
        try:
            if 'T' in str(row[6]):
                match_dt = datetime.fromisoformat(str(row[6]).replace('Z', '+00:00'))
            else:
                match_dt = datetime.fromisoformat(str(row[6]))
            
            date_str = match_dt.strftime('%a, %b %d')  # "Sat, Nov 08"
            time_str = match_dt.strftime('%H:%M')       # "20:00"
        except:
            date_str = "TBD"
            time_str = "TBD"
        
        all_exact.append({
            'Match': f"{row[0]} vs {row[1]}",
            'Prediction': row[2],
            'Odds': f"{row[3]:.2f}x",
            'Edge': f"{row[4]:.1f}%",
            'League': row[5],
            'Match Date': date_str,
            'Kickoff': time_str,
            'Stake': f"{row[7]:.0f} SEK"
        })
    
    # Get all pending SGPs
    cursor.execute('''
        SELECT 
            home_team, away_team, parlay_description,
            bookmaker_odds, ev_percentage, match_date, stake
        FROM sgp_predictions
        WHERE status = 'pending'
        ORDER BY match_date ASC
        LIMIT 50
    ''')
    
    all_sgp = []
    for row in cursor.fetchall():
        # Parse match_date
        try:
            if 'T' in str(row[5]):
                match_dt = datetime.fromisoformat(str(row[5]).replace('Z', '+00:00'))
            else:
                match_dt = datetime.fromisoformat(str(row[5]))
            
            date_str = match_dt.strftime('%a, %b %d')  # "Sat, Nov 08"
            time_str = match_dt.strftime('%H:%M')       # "20:00"
        except:
            date_str = "TBD"
            time_str = "TBD"
        
        all_sgp.append({
            'Match': f"{row[0]} vs {row[1]}",
            'Parlay': row[2][:50] + '...' if len(row[2]) > 50 else row[2],
            'Odds': f"{row[3]:.2f}x",
            'Edge': f"{row[4]:.1f}%",
            'Match Date': date_str,
            'Kickoff': time_str,
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
