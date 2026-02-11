"""
PGR Player Props Dashboard - Learning Mode
Dark neon theme matching football dashboard
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from db_connection import DatabaseConnection

PGR_GREEN = "#00FFC2"
PGR_GREEN2 = "#00FFA6"

st.markdown("""
<style>
    .props-header {
        text-align: center;
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #00FFC2 0%, #00FFA6 50%, #10B981 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
    }
    .props-sub {
        text-align: center;
        color: #64748B;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    .learning-badge {
        background: linear-gradient(135deg, rgba(255,152,0,0.25), rgba(244,67,54,0.15));
        color: #FFA726;
        padding: 0.3rem 1.2rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255,152,0,0.4);
        letter-spacing: 0.06em;
    }
    .prop-card {
        background: linear-gradient(135deg, rgba(15,23,42,0.95), rgba(10,17,28,0.98));
        border: 1px solid rgba(0,255,194,0.15);
        border-left: 3px solid #00FFC2;
        padding: 14px 16px;
        margin-bottom: 10px;
        border-radius: 12px;
        color: #E2E8F0;
    }
    .prop-card:hover {
        border-color: rgba(0,255,194,0.4);
        box-shadow: 0 0 20px rgba(0,255,194,0.08);
    }
    .prop-card-basketball {
        background: linear-gradient(135deg, rgba(15,23,42,0.95), rgba(10,17,28,0.98));
        border: 1px solid rgba(255,152,0,0.2);
        border-left: 3px solid #FF9800;
        padding: 14px 16px;
        margin-bottom: 10px;
        border-radius: 12px;
        color: #E2E8F0;
    }
    .prop-card-basketball:hover {
        border-color: rgba(255,152,0,0.5);
        box-shadow: 0 0 20px rgba(255,152,0,0.08);
    }
    .metric-glass {
        background: radial-gradient(circle at top, rgba(0,255,194,0.12), rgba(15,23,42,0.95));
        border: 1px solid rgba(0,255,194,0.25);
        padding: 1.3rem;
        border-radius: 14px;
        text-align: center;
        color: white;
    }
    .metric-glass-orange {
        background: radial-gradient(circle at top, rgba(255,152,0,0.12), rgba(15,23,42,0.95));
        border: 1px solid rgba(255,152,0,0.25);
        padding: 1.3rem;
        border-radius: 14px;
        text-align: center;
        color: white;
    }
    .metric-glass-blue {
        background: radial-gradient(circle at top, rgba(59,130,246,0.12), rgba(15,23,42,0.95));
        border: 1px solid rgba(59,130,246,0.25);
        padding: 1.3rem;
        border-radius: 14px;
        text-align: center;
        color: white;
    }
    .mv {
        font-size: 1.8rem;
        font-weight: 800;
        color: #00FFC2;
    }
    .mv-orange {
        font-size: 1.8rem;
        font-weight: 800;
        color: #FFA726;
    }
    .mv-blue {
        font-size: 1.8rem;
        font-weight: 800;
        color: #60A5FA;
    }
    .ml {
        font-size: 0.8rem;
        color: #94A3B8;
        margin-top: 4px;
        letter-spacing: 0.04em;
    }
    .edge-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .edge-high {
        background: rgba(0,255,166,0.2);
        color: #00FFA6;
        border: 1px solid rgba(0,255,166,0.4);
    }
    .edge-mid {
        background: rgba(34,197,94,0.15);
        color: #22C55E;
        border: 1px solid rgba(34,197,94,0.3);
    }
    .edge-low {
        background: rgba(59,130,246,0.15);
        color: #60A5FA;
        border: 1px solid rgba(59,130,246,0.3);
    }
    .player-name {
        font-size: 1rem;
        font-weight: 700;
        color: #F1F5F9;
    }
    .match-info {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 2px;
    }
    .odds-val {
        font-weight: 700;
        color: #00FFC2;
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #E2E8F0;
        letter-spacing: -0.01em;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="props-header">Player Props</div>', unsafe_allow_html=True)
st.markdown('<div class="props-sub">NBA &bull; NCAAB &bull; Football &bull; Learning Mode</div>', unsafe_allow_html=True)
st.markdown('<center><span class="learning-badge">LEARNING MODE &mdash; NO REAL STAKES</span></center>', unsafe_allow_html=True)


@st.cache_data(ttl=120)
def get_props_overview():
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    COUNT(*) as total_props,
                    COUNT(DISTINCT player_name) as unique_players,
                    COUNT(DISTINCT home_team || ' vs ' || away_team) as unique_matches,
                    COUNT(DISTINCT league) as unique_leagues,
                    ROUND(AVG(edge_pct)::numeric, 1) as avg_edge,
                    ROUND(AVG(odds)::numeric, 2) as avg_odds,
                    MAX(created_at) as last_collected
                FROM player_props
                WHERE mode = 'LEARNING'
            """
            result = pd.read_sql(query, conn)
            return result.iloc[0] if not result.empty else None
    except Exception:
        return None


@st.cache_data(ttl=120)
def get_props_by_sport():
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    sport, market,
                    COUNT(*) as total,
                    COUNT(DISTINCT player_name) as players,
                    COUNT(DISTINCT home_team || ' vs ' || away_team) as matches,
                    ROUND(AVG(edge_pct)::numeric, 1) as avg_edge,
                    ROUND(AVG(odds)::numeric, 2) as avg_odds,
                    ROUND(MAX(edge_pct)::numeric, 1) as max_edge
                FROM player_props
                WHERE mode = 'LEARNING'
                GROUP BY sport, market
                ORDER BY sport, market
            """
            return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_top_edge_props(sport_filter=None, market_filter=None, limit=50):
    try:
        with DatabaseConnection.get_connection() as conn:
            conditions = ["mode = 'LEARNING'"]
            params = {}
            if sport_filter and sport_filter != "All":
                conditions.append("sport = %(sport)s")
                params['sport'] = sport_filter.lower()
            if market_filter and market_filter != "All":
                conditions.append("market = %(market)s")
                params['market'] = market_filter

            where = " AND ".join(conditions)
            query = f"""
                SELECT 
                    player_name, sport, league, market, line, selection,
                    odds, implied_prob, model_prob, edge_pct, confidence,
                    bookmaker, home_team, away_team, commence_time,
                    status, created_at
                FROM player_props
                WHERE {where}
                ORDER BY edge_pct DESC
                LIMIT {limit}
            """
            return pd.read_sql(query, conn, params=params)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_daily_collection():
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    DATE(created_at) as date,
                    sport,
                    COUNT(*) as props_collected,
                    COUNT(DISTINCT player_name) as players,
                    COUNT(DISTINCT home_team || ' vs ' || away_team) as matches,
                    ROUND(AVG(edge_pct)::numeric, 1) as avg_edge
                FROM player_props
                WHERE mode = 'LEARNING'
                GROUP BY DATE(created_at), sport
                ORDER BY date DESC
            """
            return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_top_players():
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    player_name, sport, 
                    COUNT(*) as prop_count,
                    ROUND(AVG(edge_pct)::numeric, 1) as avg_edge,
                    ROUND(MAX(edge_pct)::numeric, 1) as best_edge,
                    ROUND(AVG(odds)::numeric, 2) as avg_odds,
                    COUNT(DISTINCT market) as markets
                FROM player_props
                WHERE mode = 'LEARNING'
                GROUP BY player_name, sport
                ORDER BY avg_edge DESC
                LIMIT 30
            """
            return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame()


overview = get_props_overview()

if overview is not None and overview['total_props'] > 0:
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(f"""
        <div class="metric-glass">
            <div class="mv">{int(overview['total_props']):,}</div>
            <div class="ml">TOTAL PROPS</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-glass-orange">
            <div class="mv-orange">{int(overview['unique_players'])}</div>
            <div class="ml">PLAYERS</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-glass-blue">
            <div class="mv-blue">{int(overview['unique_matches'])}</div>
            <div class="ml">MATCHES</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-glass">
            <div class="mv">{overview['avg_edge']}%</div>
            <div class="ml">AVG EDGE</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        st.markdown(f"""
        <div class="metric-glass-orange">
            <div class="mv-orange">{overview['avg_odds']}x</div>
            <div class="ml">AVG ODDS</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin:20px 0'></div>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Quality Props", "Performance Tracker", "All Raw Props", "By Sport/Market", "Top Players", "Collection History", "Raw Data"
    ])

    with tab1:
        st.markdown('<div class="section-title">Quality Filtered Props</div>', unsafe_allow_html=True)
        st.markdown("<div style='color:#64748B;font-size:0.78rem;margin-bottom:12px;'>Min 22 min/game &bull; 5/7 games played &bull; Odds 1.70-2.20 &bull; Starter/rotation &bull; +EV only &bull; Ranked by projection vs line</div>", unsafe_allow_html=True)

        @st.cache_data(ttl=120)
        def get_quality_props():
            try:
                with DatabaseConnection.get_connection() as conn:
                    query = """
                        SELECT 
                            player_name, sport, league, market, line, selection,
                            odds, implied_prob, model_prob, edge_pct, confidence,
                            bookmaker, home_team, away_team, commence_time,
                            status, notes, created_at
                        FROM player_props
                        WHERE mode = 'LEARNING'
                          AND notes LIKE 'QUALITY%%'
                          AND status = 'pending'
                        ORDER BY edge_pct DESC
                        LIMIT 50
                    """
                    return pd.read_sql(query, conn)
            except Exception:
                return pd.DataFrame()

        quality_df = get_quality_props()

        if quality_df.empty:
            st.markdown("""
            <div style="text-align:center;padding:2rem;background:radial-gradient(circle at top, rgba(0,255,194,0.06), rgba(15,23,42,0.95));border:1px solid rgba(0,255,194,0.15);border-radius:14px;margin:16px 0;">
                <div style="font-size:1.5rem;margin-bottom:6px;">🎯</div>
                <div style="color:#E2E8F0;font-weight:600;">No quality props yet</div>
                <div style="color:#64748B;font-size:0.82rem;margin-top:6px;">
                    Quality filtering runs after each props cycle (every 6 hours).<br>
                    Props must pass all filters: minutes, games played, odds range, role, injury check, and +EV.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for _, row in quality_df.iterrows():
                is_basketball = row['sport'] == 'basketball'
                card_class = "prop-card-basketball" if is_basketball else "prop-card"
                sport_emoji = "🏀" if is_basketball else "⚽"
                market_display = row['market'].replace('player_', '').replace('_', ' ').title()

                edge = row['edge_pct']
                edge_class = "edge-high" if edge >= 8 else ("edge-mid" if edge >= 5 else "edge-low")

                line_str = f" {row['selection']} {row['line']}" if pd.notna(row['line']) and row['line'] > 0 else f" {row['selection']}"
                accent = "#FF9800" if is_basketball else "#00FFC2"

                notes = row.get('notes', '') or ''
                proj_str = ""
                if 'proj=' in notes:
                    try:
                        parts = {p.split('=')[0]: p.split('=')[1] for p in notes.replace('QUALITY|', '').split('|') if '=' in p}
                        proj_val = parts.get('proj', '?')
                        diff_val = parts.get('diff', '?')
                        hit_val = parts.get('hit', '?')
                        min_val = parts.get('min', '?')
                        g7_val = parts.get('g7', '?')
                        proj_str = f"Proj: <strong style='color:{accent};'>{proj_val}</strong> (diff: {diff_val}) &bull; Hit: {hit_val} &bull; {min_val} min/g &bull; {g7_val}/7 games"
                    except Exception:
                        proj_str = ""

                st.markdown(f"""
                <div class="{card_class}">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span class="player-name">{sport_emoji} {row['player_name']}</span>
                            <span style="color:{accent};font-weight:600;font-size:0.85rem;margin-left:8px;">{market_display}{line_str}</span>
                        </div>
                        <span class="edge-badge {edge_class}">{edge:.1f}%</span>
                    </div>
                    <div class="match-info">{row['home_team']} vs {row['away_team']} &bull; {row['league']}</div>
                    <div style="margin-top:6px;font-size:0.82rem;color:#94A3B8;">
                        Odds: <span class="odds-val">{row['odds']:.2f}</span> &bull;
                        Model: {row['model_prob']:.1%} vs Implied: {row['implied_prob']:.1%} &bull;
                        {row['bookmaker']}
                    </div>
                    {"<div style='margin-top:4px;font-size:0.78rem;color:#64748B;'>" + proj_str + "</div>" if proj_str else ""}
                </div>
                """, unsafe_allow_html=True)

            st.markdown(f"<div style='text-align:center;color:#475569;font-size:0.75rem;margin-top:12px;'>{len(quality_df)} quality props passed all filters</div>", unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="section-title">Performance Tracker (Paper Trading)</div>', unsafe_allow_html=True)
        st.markdown("<div style='color:#64748B;font-size:0.8rem;margin-bottom:16px;'>Simulated 1u flat stakes &bull; Learning mode &mdash; tracking what results would be</div>", unsafe_allow_html=True)

        @st.cache_data(ttl=120)
        def get_tracker_stats():
            try:
                with DatabaseConnection.get_connection() as conn:
                    query = """
                        SELECT 
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE status = 'won') as wins,
                            COUNT(*) FILTER (WHERE status = 'lost') as losses,
                            COUNT(*) FILTER (WHERE status = 'void') as voids,
                            COUNT(*) FILTER (WHERE status = 'pending') as pending,
                            COALESCE(SUM(CASE WHEN status = 'won' THEN (odds - 1) WHEN status = 'lost' THEN -1 ELSE 0 END), 0) as net_profit,
                            ROUND(AVG(CASE WHEN status IN ('won','lost') THEN odds END)::numeric, 2) as avg_settled_odds,
                            ROUND(AVG(CASE WHEN status IN ('won','lost') THEN edge_pct END)::numeric, 1) as avg_settled_edge
                        FROM player_props
                        WHERE mode = 'LEARNING'
                    """
                    return pd.read_sql(query, conn).iloc[0]
            except Exception:
                return None

        @st.cache_data(ttl=120)
        def get_tracker_by_market():
            try:
                with DatabaseConnection.get_connection() as conn:
                    query = """
                        SELECT 
                            sport, market,
                            COUNT(*) FILTER (WHERE status IN ('won','lost')) as settled,
                            COUNT(*) FILTER (WHERE status = 'won') as wins,
                            COUNT(*) FILTER (WHERE status = 'lost') as losses,
                            COUNT(*) FILTER (WHERE status = 'pending') as pending,
                            COALESCE(SUM(CASE WHEN status = 'won' THEN (odds - 1) WHEN status = 'lost' THEN -1 ELSE 0 END), 0) as profit,
                            ROUND(AVG(CASE WHEN status IN ('won','lost') THEN odds END)::numeric, 2) as avg_odds,
                            ROUND(AVG(edge_pct)::numeric, 1) as avg_edge
                        FROM player_props
                        WHERE mode = 'LEARNING'
                        GROUP BY sport, market
                        ORDER BY profit DESC
                    """
                    return pd.read_sql(query, conn)
            except Exception:
                return pd.DataFrame()

        @st.cache_data(ttl=120)
        def get_tracker_daily():
            try:
                with DatabaseConnection.get_connection() as conn:
                    query = """
                        SELECT 
                            DATE(created_at) as date,
                            COUNT(*) FILTER (WHERE status IN ('won','lost')) as settled,
                            COUNT(*) FILTER (WHERE status = 'won') as wins,
                            COUNT(*) FILTER (WHERE status = 'lost') as losses,
                            COUNT(*) FILTER (WHERE status = 'pending') as pending,
                            COALESCE(SUM(CASE WHEN status = 'won' THEN (odds - 1) WHEN status = 'lost' THEN -1 ELSE 0 END), 0) as daily_profit
                        FROM player_props
                        WHERE mode = 'LEARNING'
                        GROUP BY DATE(created_at)
                        ORDER BY date
                    """
                    return pd.read_sql(query, conn)
            except Exception:
                return pd.DataFrame()

        @st.cache_data(ttl=120)
        def get_tracker_recent():
            try:
                with DatabaseConnection.get_connection() as conn:
                    query = """
                        SELECT 
                            player_name, sport, market, selection, line, odds,
                            edge_pct, home_team || ' vs ' || away_team as match,
                            status, profit_loss,
                            COALESCE(settled_at, created_at) as date
                        FROM player_props
                        WHERE mode = 'LEARNING' AND status IN ('won', 'lost')
                        ORDER BY settled_at DESC NULLS LAST
                        LIMIT 30
                    """
                    return pd.read_sql(query, conn)
            except Exception:
                return pd.DataFrame()

        ts = get_tracker_stats()
        if ts is not None:
            wins = int(ts['wins'] or 0)
            losses = int(ts['losses'] or 0)
            voids = int(ts['voids'] or 0)
            pending = int(ts['pending'] or 0)
            settled = wins + losses
            hit_rate = (wins / settled * 100) if settled > 0 else 0
            net_profit = float(ts['net_profit'] or 0)
            roi = (net_profit / settled * 100) if settled > 0 else 0

            mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)

            with mc1:
                st.markdown(f"""
                <div class="metric-glass">
                    <div class="mv">{settled}</div>
                    <div class="ml">SETTLED</div>
                </div>
                """, unsafe_allow_html=True)

            with mc2:
                st.markdown(f"""
                <div class="metric-glass" style="border-color:rgba(34,197,94,0.3);">
                    <div class="mv" style="color:#22C55E;">{wins}</div>
                    <div class="ml">WINS</div>
                </div>
                """, unsafe_allow_html=True)

            with mc3:
                st.markdown(f"""
                <div class="metric-glass" style="border-color:rgba(239,68,68,0.3);">
                    <div class="mv" style="color:#EF4444;">{losses}</div>
                    <div class="ml">LOSSES</div>
                </div>
                """, unsafe_allow_html=True)

            with mc4:
                hr_color = "#00FFC2" if hit_rate >= 50 else "#EF4444"
                st.markdown(f"""
                <div class="metric-glass">
                    <div class="mv" style="color:{hr_color};">{hit_rate:.1f}%</div>
                    <div class="ml">HIT RATE</div>
                </div>
                """, unsafe_allow_html=True)

            with mc5:
                pl_color = "#00FFA6" if net_profit >= 0 else "#F97373"
                st.markdown(f"""
                <div class="metric-glass">
                    <div class="mv" style="color:{pl_color};">{net_profit:+.1f}u</div>
                    <div class="ml">PROFIT</div>
                </div>
                """, unsafe_allow_html=True)

            with mc6:
                roi_color = "#00FFA6" if roi >= 0 else "#F97373"
                st.markdown(f"""
                <div class="metric-glass">
                    <div class="mv" style="color:{roi_color};">{roi:+.1f}%</div>
                    <div class="ml">ROI</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown(f"<div style='text-align:center;color:#475569;font-size:0.75rem;margin:8px 0 16px;'>{pending} pending &bull; {voids} void</div>", unsafe_allow_html=True)

            tm_df = get_tracker_by_market()
            if not tm_df.empty and tm_df['settled'].sum() > 0:
                st.markdown('<div class="section-title" style="margin-top:20px;">By Market</div>', unsafe_allow_html=True)
                for _, mrow in tm_df.iterrows():
                    s = int(mrow['settled'])
                    w = int(mrow['wins'])
                    l = int(mrow['losses'])
                    p = float(mrow['profit'])
                    hr = (w / s * 100) if s > 0 else 0
                    r = (p / s * 100) if s > 0 else 0
                    m_emoji = "🏀" if mrow['sport'] == 'basketball' else "⚽"
                    m_accent = "#FF9800" if mrow['sport'] == 'basketball' else "#00FFC2"
                    mname = mrow['market'].replace('player_', '').replace('_', ' ').title()
                    pl_c = "#00FFA6" if p >= 0 else "#F97373"
                    hr_c = "#00FFC2" if hr >= 50 else "#F97373"

                    st.markdown(f"""
                    <div class="prop-card" style="border-left-color:{m_accent};">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span class="player-name">{m_emoji} {mname}</span>
                            <span style="font-weight:800;color:{pl_c};font-size:1.1rem;">{p:+.1f}u</span>
                        </div>
                        <div style="margin-top:4px;font-size:0.82rem;color:#94A3B8;">
                            {w}W - {l}L &bull;
                            Hit Rate: <span style="color:{hr_c};font-weight:600;">{hr:.1f}%</span> &bull;
                            ROI: <span style="color:{pl_c};font-weight:600;">{r:+.1f}%</span> &bull;
                            Avg Odds: {mrow['avg_odds'] or 0:.2f} &bull;
                            Pending: {int(mrow['pending'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            td_df = get_tracker_daily()
            if not td_df.empty and td_df['settled'].sum() > 0:
                st.markdown('<div class="section-title" style="margin-top:20px;">Profit Curve</div>', unsafe_allow_html=True)
                td_df['cumulative_profit'] = td_df['daily_profit'].cumsum()

                fig_t = go.Figure()
                fig_t.add_trace(go.Scatter(
                    x=td_df['date'], y=td_df['cumulative_profit'],
                    mode='lines+markers',
                    line=dict(color='#00FFC2', width=3),
                    fill='tozeroy',
                    fillcolor='rgba(0,255,194,0.1)',
                    name='Cumulative P/L'
                ))
                fig_t.update_layout(
                    template="plotly_dark", height=350,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#94A3B8'),
                    xaxis_title="Date", yaxis_title="Profit (units)",
                    margin=dict(t=20, b=40)
                )
                st.plotly_chart(fig_t, use_container_width=True)

                tc1, tc2 = st.columns(2)
                with tc1:
                    fig_wl = go.Figure(data=[
                        go.Bar(name='Wins', x=td_df['date'], y=td_df['wins'], marker_color='#22C55E'),
                        go.Bar(name='Losses', x=td_df['date'], y=td_df['losses'], marker_color='#EF4444')
                    ])
                    fig_wl.update_layout(
                        title="Daily W/L", barmode='group',
                        template="plotly_dark", height=280,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='#94A3B8'), margin=dict(t=40, b=30)
                    )
                    st.plotly_chart(fig_wl, use_container_width=True)

                with tc2:
                    fig_dp = go.Figure(data=[
                        go.Bar(x=td_df['date'], y=td_df['daily_profit'],
                               marker_color=['#22C55E' if x >= 0 else '#EF4444' for x in td_df['daily_profit']])
                    ])
                    fig_dp.update_layout(
                        title="Daily P/L", template="plotly_dark", height=280,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='#94A3B8'), margin=dict(t=40, b=30)
                    )
                    st.plotly_chart(fig_dp, use_container_width=True)

            recent = get_tracker_recent()
            if not recent.empty:
                st.markdown('<div class="section-title" style="margin-top:20px;">Recent Settled Props</div>', unsafe_allow_html=True)
                for _, rrow in recent.iterrows():
                    is_win = rrow['status'] == 'won'
                    r_emoji = "✅" if is_win else "❌"
                    r_sport = "🏀" if rrow['sport'] == 'basketball' else "⚽"
                    border_c = "rgba(34,197,94,0.5)" if is_win else "rgba(239,68,68,0.5)"
                    bg_c = "rgba(34,197,94,0.08)" if is_win else "rgba(239,68,68,0.08)"
                    r_profit = float(rrow['profit_loss'] or (rrow['odds'] - 1 if is_win else -1))
                    r_pl_c = "#22C55E" if r_profit >= 0 else "#EF4444"
                    r_mname = rrow['market'].replace('player_', '').replace('_', ' ').title()
                    r_line = f" {rrow['selection']} {rrow['line']}" if pd.notna(rrow['line']) and rrow['line'] > 0 else ""

                    st.markdown(f"""
                    <div style="background:{bg_c};border:1px solid {border_c};border-radius:10px;padding:10px 14px;margin-bottom:6px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="color:#E2E8F0;font-weight:600;">{r_emoji} {r_sport} {rrow['player_name']} — {r_mname}{r_line}</span>
                            <span style="color:{r_pl_c};font-weight:800;">{r_profit:+.2f}u</span>
                        </div>
                        <div style="font-size:0.78rem;color:#64748B;margin-top:2px;">
                            {rrow['match']} &bull; {rrow['odds']:.2f}x &bull; Edge: {rrow['edge_pct']:.1f}%
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            if settled == 0:
                st.markdown("""
                <div style="text-align:center;padding:2rem;background:radial-gradient(circle at top, rgba(255,152,0,0.06), rgba(15,23,42,0.95));border:1px solid rgba(255,152,0,0.15);border-radius:14px;margin:16px 0;">
                    <div style="font-size:1.5rem;margin-bottom:6px;">📊</div>
                    <div style="color:#FFA726;font-weight:600;">No settled props yet</div>
                    <div style="color:#64748B;font-size:0.82rem;margin-top:6px;">
                        ROI, hit rate and profit charts will appear once props are settled.<br>
                        Props auto-void after 3 days if not settled.
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with tab3:
        st.markdown('<div class="section-title">All Raw Props (Unfiltered)</div>', unsafe_allow_html=True)

        fcol1, fcol2 = st.columns(2)
        with fcol1:
            sport_filter = st.selectbox("Sport", ["All", "Basketball", "Football"], key="prop_sport")
        with fcol2:
            market_filter = st.selectbox("Market", ["All", "player_points", "player_rebounds", "player_assists", "player_points_rebounds_assists", "player_anytime_goalscorer", "player_shots_on_goal"], key="prop_market")

        top_props = get_top_edge_props(sport_filter, market_filter)

        if top_props.empty:
            st.info("No props found with current filters.")
        else:
            for _, row in top_props.iterrows():
                is_basketball = row['sport'] == 'basketball'
                card_class = "prop-card-basketball" if is_basketball else "prop-card"
                sport_emoji = "🏀" if is_basketball else "⚽"
                market_display = row['market'].replace('player_', '').replace('_', ' ').title()

                edge = row['edge_pct']
                edge_class = "edge-high" if edge >= 8 else ("edge-mid" if edge >= 5 else "edge-low")

                line_str = f" {row['selection']} {row['line']}" if pd.notna(row['line']) and row['line'] > 0 else f" {row['selection']}"
                accent = "#FF9800" if is_basketball else "#00FFC2"

                st.markdown(f"""
                <div class="{card_class}">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span class="player-name">{sport_emoji} {row['player_name']}</span>
                            <span style="color:{accent};font-weight:600;font-size:0.85rem;margin-left:8px;">{market_display}{line_str}</span>
                        </div>
                        <span class="edge-badge {edge_class}">{edge:.1f}%</span>
                    </div>
                    <div class="match-info">{row['home_team']} vs {row['away_team']} &bull; {row['league']}</div>
                    <div style="margin-top:6px;font-size:0.82rem;color:#94A3B8;">
                        Odds: <span class="odds-val">{row['odds']:.2f}</span> &bull;
                        Model: {row['model_prob']:.1%} vs Implied: {row['implied_prob']:.1%} &bull;
                        {row['bookmaker']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with tab4:
        sport_market = get_props_by_sport()
        if sport_market.empty:
            st.info("No data yet.")
        else:
            st.markdown('<div class="section-title">Props by Sport & Market</div>', unsafe_allow_html=True)

            for sport in sport_market['sport'].unique():
                sport_data = sport_market[sport_market['sport'] == sport]
                emoji = "🏀" if sport == 'basketball' else "⚽"
                accent = "#FF9800" if sport == 'basketball' else "#00FFC2"
                st.markdown(f"<div style='font-size:1.1rem;font-weight:700;color:{accent};margin:16px 0 8px;'>{emoji} {sport.title()}</div>", unsafe_allow_html=True)

                cols = st.columns(len(sport_data))
                for i, (_, row) in enumerate(sport_data.iterrows()):
                    with cols[i]:
                        market_name = row['market'].replace('player_', '').replace('_', ' ').title()
                        st.markdown(f"""
                        <div class="metric-glass" style="padding:1rem;">
                            <div style="font-size:1.4rem;font-weight:800;color:{accent};">{int(row['total'])}</div>
                            <div class="ml">{market_name.upper()}</div>
                            <div style="font-size:0.75rem;color:#64748B;margin-top:6px;">
                                {int(row['players'])} players &bull; {int(row['matches'])} matches<br>
                                Avg edge: {row['avg_edge']}% &bull; Best: {row['max_edge']}%
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            fig = px.bar(
                sport_market,
                x='market',
                y='total',
                color='sport',
                title='Props Collected by Market',
                labels={'total': 'Count', 'market': 'Market'},
                color_discrete_map={'basketball': '#FF9800', 'football': '#00FFC2'}
            )
            fig.update_layout(
                template="plotly_dark",
                height=400,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8')
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab5:
        top_players = get_top_players()
        if top_players.empty:
            st.info("No player data yet.")
        else:
            st.markdown('<div class="section-title">Top Players by Average Edge</div>', unsafe_allow_html=True)

            for _, row in top_players.iterrows():
                is_basketball = row['sport'] == 'basketball'
                emoji = "🏀" if is_basketball else "⚽"
                accent = "#FF9800" if is_basketball else "#00FFC2"
                card_class = "prop-card-basketball" if is_basketball else "prop-card"

                edge = row['avg_edge']
                edge_class = "edge-high" if edge >= 8 else ("edge-mid" if edge >= 5 else "edge-low")

                st.markdown(f"""
                <div class="{card_class}">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span class="player-name">{emoji} {row['player_name']}</span>
                        <span class="edge-badge {edge_class}">avg {row['avg_edge']}%</span>
                    </div>
                    <div style="margin-top:4px;font-size:0.82rem;color:#94A3B8;">
                        Best: <span style="color:{accent};font-weight:600;">{row['best_edge']}%</span> &bull;
                        Props: {int(row['prop_count'])} &bull;
                        Avg Odds: {row['avg_odds']}x &bull;
                        Markets: {int(row['markets'])}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with tab6:
        daily = get_daily_collection()
        if daily.empty:
            st.info("No collection history yet.")
        else:
            st.markdown('<div class="section-title">Daily Collection History</div>', unsafe_allow_html=True)

            fig = px.bar(
                daily,
                x='date',
                y='props_collected',
                color='sport',
                title='Props Collected Per Day',
                labels={'props_collected': 'Props', 'date': 'Date'},
                color_discrete_map={'basketball': '#FF9800', 'football': '#00FFC2'}
            )
            fig.update_layout(
                template="plotly_dark",
                height=400,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94A3B8')
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                daily.style.format({'avg_edge': '{:.1f}%'}),
                use_container_width=True,
                hide_index=True
            )

    with tab7:
        st.markdown('<div class="section-title">Raw Props Data</div>', unsafe_allow_html=True)
        try:
            with DatabaseConnection.get_connection() as conn:
                raw_query = """
                    SELECT 
                        created_at::date as date, sport, league, player_name,
                        market, line, selection, odds, edge_pct, confidence,
                        bookmaker, home_team || ' vs ' || away_team as match,
                        status
                    FROM player_props
                    WHERE mode = 'LEARNING'
                    ORDER BY created_at DESC
                    LIMIT 200
                """
                raw_df = pd.read_sql(raw_query, conn)
                if not raw_df.empty:
                    st.dataframe(raw_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No data available.")
        except Exception as e:
            st.error(f"Error: {e}")

else:
    st.markdown("""
    <div style="text-align:center;padding:3rem;background:radial-gradient(circle at top, rgba(0,255,194,0.06), rgba(15,23,42,0.95));border:1px solid rgba(0,255,194,0.15);border-radius:16px;margin:2rem 0;">
        <div style="font-size:2rem;margin-bottom:8px;">🎯</div>
        <div style="color:#E2E8F0;font-weight:600;">No player props data collected yet</div>
        <div style="color:#64748B;font-size:0.85rem;margin-top:6px;">The engine runs every 6 hours to collect data</div>
        <div style="color:#475569;font-size:0.78rem;margin-top:12px;">
            Markets: player_points, player_rebounds (basketball) | player_anytime_goalscorer, player_shots_on_goal (football)
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin:16px 0;border-top:1px solid rgba(100,116,139,0.2);'></div>", unsafe_allow_html=True)
st.markdown("<div style='text-align:center;color:#475569;font-size:0.75rem;'>Data collected every 6 hours from The Odds API &bull; Learning mode &mdash; no real stakes</div>", unsafe_allow_html=True)

if st.button("Refresh Data", key="refresh_props"):
    st.cache_data.clear()
    st.rerun()
