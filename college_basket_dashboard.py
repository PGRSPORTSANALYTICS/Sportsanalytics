"""
College Basketball Dashboard
Displays NCAAB value picks and performance tracking from the database
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from db_connection import DatabaseConnection

st.set_page_config(
    page_title="College Basketball Value Picks",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #FF6B35;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .sub-header {
        text-align: center;
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-card-green {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-card-red {
        background: linear-gradient(135deg, #ee0979 0%, #ff6a00 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .pick-card {
        background: #f8f9fa;
        border-left: 4px solid #FF6B35;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 5px;
        color: #1a1a2e;
    }
    .pick-card small {
        color: #333;
        font-size: 0.85rem;
    }
    .parlay-card {
        background: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 5px;
        color: #1a1a2e;
    }
    .parlay-card small {
        color: #333;
        font-size: 0.85rem;
    }
    .win-card {
        background: #e8f5e9;
        border-left: 5px solid #4CAF50;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.7rem;
        border-radius: 8px;
        font-size: 1.1rem;
        line-height: 1.6;
        color: #1a1a2e;
    }
    .loss-card {
        background: #ffebee;
        border-left: 5px solid #f44336;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.7rem;
        border-radius: 8px;
        font-size: 1.1rem;
        line-height: 1.6;
        color: #1a1a2e;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🏀 College Basketball Value Picks</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">NCAAB • Consensus-Based Value Detection • Live Performance Tracking</div>', unsafe_allow_html=True)


@st.cache_data(ttl=120)
def get_performance_stats():
    """Get overall performance statistics"""
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(*) FILTER (WHERE status = 'won') as wins,
                    COUNT(*) FILTER (WHERE status = 'lost') as losses,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COALESCE(SUM(profit_units), 0) as net_profit,
                    AVG(odds) as avg_odds,
                    AVG(ev_percentage) as avg_ev
                FROM basketball_predictions
            """
            result = pd.read_sql(query, conn)
            return result.iloc[0] if not result.empty else None
    except Exception as e:
        st.error(f"Error loading stats: {e}")
        return None


@st.cache_data(ttl=120)
def get_ncaab_picks():
    """Fetch pending NCAAB picks from database"""
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    match,
                    market,
                    selection,
                    odds,
                    probability,
                    ev_percentage,
                    confidence,
                    bookmaker,
                    is_parlay,
                    parlay_legs,
                    commence_time,
                    created_at
                FROM basketball_predictions
                WHERE status = 'pending'
                ORDER BY ev_percentage DESC, confidence DESC
            """
            df = pd.read_sql(query, conn)
            return df
    except Exception as e:
        st.error(f"Error loading picks: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_recent_results():
    """Get recent settled bets"""
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    match,
                    market,
                    selection,
                    odds,
                    status,
                    profit_units,
                    verified_at,
                    is_parlay
                FROM basketball_predictions
                WHERE status IN ('won', 'lost')
                ORDER BY verified_at DESC NULLS LAST, created_at DESC
                LIMIT 30
            """
            df = pd.read_sql(query, conn)
            return df
    except Exception as e:
        st.error(f"Error loading results: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_daily_performance():
    """Get daily performance for chart"""
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as bets,
                    COUNT(*) FILTER (WHERE status = 'won') as wins,
                    COUNT(*) FILTER (WHERE status = 'lost') as losses,
                    COALESCE(SUM(profit_units), 0) as daily_profit
                FROM basketball_predictions
                WHERE status IN ('won', 'lost')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 14
            """
            df = pd.read_sql(query, conn)
            return df
    except Exception as e:
        return pd.DataFrame()


stats = get_performance_stats()
picks_df = get_ncaab_picks()
results_df = get_recent_results()

if stats is not None:
    wins = int(stats['wins'] or 0)
    losses = int(stats['losses'] or 0)
    pending = int(stats['pending'] or 0)
    total = wins + losses
    hit_rate = (wins / total * 100) if total > 0 else 0
    net_profit = float(stats['net_profit'] or 0)
    avg_odds = float(stats['avg_odds'] or 0)
    
    st.subheader("📊 Performance Overview")
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{wins}</div>
            <div class="metric-label">Wins</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{losses}</div>
            <div class="metric-label">Losses</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{hit_rate:.1f}%</div>
            <div class="metric-label">Hit Rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        profit_class = "metric-card-green" if net_profit >= 0 else "metric-card-red"
        st.markdown(f"""
        <div class="{profit_class}">
            <div class="metric-value">{net_profit:+.1f}u</div>
            <div class="metric-label">Net Profit</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col5:
        roi = (net_profit / total * 100) if total > 0 else 0
        roi_class = "metric-card-green" if roi >= 0 else "metric-card-red"
        st.markdown(f"""
        <div class="{roi_class}">
            <div class="metric-value">{roi:+.1f}%</div>
            <div class="metric-label">ROI</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col6:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{avg_odds:.2f}x</div>
            <div class="metric-label">Avg Odds</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

tab_smart, tab1, tab2, tab3, tab4 = st.tabs(["🎯 Smart Picks", "📈 Today's Picks", "🏆 Recent Results", "📊 Performance Chart", "📋 All Data"])

with tab_smart:
    st.markdown("### Smart Picks — Moneyline Winners")
    st.caption("Who wins? Odds 1.70–2.00 | High probability, clean value. Historical: 64% hit rate.")

    st.markdown("""
    <div style="padding:10px 14px;border-radius:8px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.25);margin-bottom:16px;">
        <span style="color:#FBBF24;font-size:12px;">For informational purposes only. Not betting advice.</span>
    </div>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=300)
    def _load_smart_picks():
        from basketball_smart_picks import fetch_ncaab_moneyline_smart_picks
        return fetch_ncaab_moneyline_smart_picks()

    try:
        smart_picks = _load_smart_picks()
    except Exception as e:
        smart_picks = []
        st.error(f"Could not load smart picks: {e}")

    if not smart_picks:
        st.info("No moneyline picks in the 1.70–2.00 range right now. Check back closer to game time.")
    else:
        scol1, scol2, scol3 = st.columns(3)
        avg_prob = sum(p['probability'] for p in smart_picks) / len(smart_picks)
        avg_odds = sum(p['odds'] for p in smart_picks) / len(smart_picks)
        avg_ev = sum(p['ev_percentage'] for p in smart_picks) / len(smart_picks)

        with scol1:
            st.metric("Picks Found", len(smart_picks))
        with scol2:
            st.metric("Avg Win Prob", f"{avg_prob:.1f}%")
        with scol3:
            st.metric("Avg Odds", f"{avg_odds:.2f}")

        for pick in smart_picks:
            prob = pick['probability']
            ev = pick['ev_percentage']
            odds = pick['odds']

            if prob >= 55:
                prob_color = "#10B981"
            elif prob >= 50:
                prob_color = "#3B82F6"
            else:
                prob_color = "#F59E0B"

            if ev >= 5:
                ev_color = "#10B981"
            elif ev >= 0:
                ev_color = "#3B82F6"
            else:
                ev_color = "#EF4444"

            kickoff = pick.get('commence_time', '')
            if kickoff:
                try:
                    dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
                    kickoff_display = dt.strftime('%b %d, %H:%M UTC')
                except:
                    kickoff_display = kickoff[:16].replace('T', ' ')
            else:
                kickoff_display = 'TBD'

            odds_by_book = pick.get('odds_by_bookmaker', {})
            book_html = '<div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap;">'
            for i, (bname, bodds) in enumerate(odds_by_book.items()):
                if i == 0:
                    book_html += f'''
                    <div style="padding:5px 10px;border-radius:6px;background:rgba(34,197,94,0.2);border:1px solid rgba(34,197,94,0.5);">
                        <div style="font-size:8px;color:#22C55E;font-weight:600;">BEST</div>
                        <div style="font-size:15px;font-weight:700;color:#22C55E;">{float(bodds):.2f}</div>
                        <div style="font-size:8px;color:#6B7280;">{bname}</div>
                    </div>'''
                else:
                    book_html += f'''
                    <div style="padding:5px 10px;border-radius:6px;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);">
                        <div style="font-size:15px;font-weight:700;color:#60A5FA;">{float(bodds):.2f}</div>
                        <div style="font-size:8px;color:#6B7280;">{bname}</div>
                    </div>'''
            book_html += '</div>'

            st.markdown(f"""
            <div style="padding:16px;margin:8px 0;border-radius:12px;background:radial-gradient(circle at top left, rgba(59,130,246,0.1), rgba(15,23,42,0.95));border:1px solid rgba(59,130,246,0.3);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:11px;color:#9CA3AF;">{kickoff_display}</span>
                    <div style="display:flex;gap:8px;">
                        <span style="padding:3px 8px;border-radius:999px;background:{prob_color}22;color:{prob_color};font-size:10px;font-weight:600;">{prob:.0f}% WIN</span>
                        <span style="padding:3px 8px;border-radius:999px;background:{ev_color}22;color:{ev_color};font-size:10px;font-weight:600;">EV {ev:+.1f}%</span>
                    </div>
                </div>
                <div style="font-size:15px;color:#E5E7EB;font-weight:600;margin-bottom:3px;">{pick['match']}</div>
                <div style="font-size:14px;color:#6EE7B7;font-weight:600;">{pick['team']} to win @ {odds:.2f}</div>
                {book_html}
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### Table View")
        table_data = []
        for p in smart_picks:
            best_book_info = list(p.get('odds_by_bookmaker', {}).items())
            best_str = f"{best_book_info[0][0]} @ {float(best_book_info[0][1]):.2f}" if best_book_info else ''
            table_data.append({
                'Match': p['match'],
                'Pick': f"{p['team']} to win",
                'Odds': f"{p['odds']:.2f}",
                'Win Prob': f"{p['probability']:.1f}%",
                'EV': f"{p['ev_percentage']:+.1f}%",
                'Best Book': best_str,
            })
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

with tab1:
    if picks_df.empty:
        st.info("🏀 No pending picks right now. The engine generates picks every 2 hours when games are available.")
    else:
        singles = picks_df[~picks_df['is_parlay']]
        parlays = picks_df[picks_df['is_parlay']]
        
        if not singles.empty:
            st.subheader(f"🎯 Value Singles ({len(singles)})")
            for idx, row in singles.head(15).iterrows():
                st.markdown(f"""
                <div class="pick-card">
                    <strong>{row['match']}</strong><br>
                    <span style="color: #FF6B35; font-weight: 600;">{row['market']}: {row['selection']}</span><br>
                    <small>
                        Odds: {row['odds']:.2f} | EV: <strong>{row['ev_percentage']:.1f}%</strong> | 
                        Confidence: {row['confidence']:.1f}% | Book: {row['bookmaker']}
                    </small>
                </div>
                """, unsafe_allow_html=True)
        
        if not parlays.empty:
            st.subheader(f"🔥 Multi-Game Parlays ({len(parlays)})")
            for idx, row in parlays.head(10).iterrows():
                st.markdown(f"""
                <div class="parlay-card">
                    <strong>{row['match']}</strong><br>
                    <span style="color: #ff9800; font-weight: 600;">{row['market']}</span><br>
                    <span style="font-size: 0.9rem;">{row['selection']}</span><br>
                    <small>
                        Combined Odds: {row['odds']:.2f} | EV: <strong>{row['ev_percentage']:.1f}%</strong> | 
                        Min Confidence: {row['confidence']:.1f}%
                    </small>
                </div>
                """, unsafe_allow_html=True)

with tab2:
    if results_df.empty:
        st.info("No results yet")
    else:
        st.subheader("🏆 Recent Results")
        
        for idx, row in results_df.head(20).iterrows():
            is_win = row['status'] == 'won'
            card_class = "win-card" if is_win else "loss-card"
            emoji = "✅" if is_win else "❌"
            profit = float(row['profit_units'] or 0)
            profit_str = f"+{profit:.2f}u" if profit >= 0 else f"{profit:.2f}u"
            parlay_badge = "🎲 " if row['is_parlay'] else ""
            
            st.markdown(f"""
            <div class="{card_class}">
                <span style="font-size: 1.3rem;">{emoji} {parlay_badge}<strong>{row['match']}</strong></span><br>
                <span style="font-size: 1.1rem;">{row['selection']} @ {row['odds']:.2f}x</span>
                <span style="float: right; font-size: 1.2rem; font-weight: 700;">{profit_str}</span>
            </div>
            """, unsafe_allow_html=True)

with tab3:
    daily_df = get_daily_performance()
    
    if daily_df.empty:
        st.info("Not enough data for chart yet")
    else:
        daily_df = daily_df.sort_values('date')
        daily_df['cumulative_profit'] = daily_df['daily_profit'].cumsum()
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=daily_df['date'],
            y=daily_df['cumulative_profit'],
            mode='lines+markers',
            name='Cumulative Profit',
            line=dict(color='#11998e', width=3),
            fill='tozeroy',
            fillcolor='rgba(17, 153, 142, 0.2)'
        ))
        
        fig.update_layout(
            title="Cumulative Profit (Units)",
            xaxis_title="Date",
            yaxis_title="Profit (Units)",
            template="plotly_white",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig2 = go.Figure(data=[
                go.Bar(name='Wins', x=daily_df['date'], y=daily_df['wins'], marker_color='#4CAF50'),
                go.Bar(name='Losses', x=daily_df['date'], y=daily_df['losses'], marker_color='#f44336')
            ])
            fig2.update_layout(
                title="Daily Wins vs Losses",
                barmode='group',
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        with col2:
            fig3 = go.Figure(data=[
                go.Bar(x=daily_df['date'], y=daily_df['daily_profit'], 
                       marker_color=['#4CAF50' if x >= 0 else '#f44336' for x in daily_df['daily_profit']])
            ])
            fig3.update_layout(
                title="Daily Profit/Loss",
                template="plotly_white",
                height=300
            )
            st.plotly_chart(fig3, use_container_width=True)

with tab4:
    try:
        with DatabaseConnection.get_connection() as conn:
            all_query = """
                SELECT 
                    created_at::date as date,
                    match,
                    market,
                    selection,
                    odds,
                    ev_percentage,
                    status,
                    profit_units
                FROM basketball_predictions
                ORDER BY created_at DESC
                LIMIT 100
            """
            all_df = pd.read_sql(all_query, conn)
            
            if not all_df.empty:
                st.dataframe(all_df, use_container_width=True, hide_index=True)
            else:
                st.info("No data available")
    except Exception as e:
        st.error(f"Error: {e}")

st.markdown("---")
st.caption("🏀 Data updates every 2 hours | Powered by The Odds API consensus devigging")

if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()
