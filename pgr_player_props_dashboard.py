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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Top Edge Props", "By Sport/Market", "Top Players", "Collection History", "Raw Data"
    ])

    with tab1:
        st.markdown('<div class="section-title">Top Edge Player Props</div>', unsafe_allow_html=True)

        fcol1, fcol2 = st.columns(2)
        with fcol1:
            sport_filter = st.selectbox("Sport", ["All", "Basketball", "Football"], key="prop_sport")
        with fcol2:
            market_filter = st.selectbox("Market", ["All", "player_points", "player_rebounds", "player_anytime_goalscorer", "player_shots_on_goal"], key="prop_market")

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
                if edge >= 8:
                    edge_class = "edge-high"
                elif edge >= 5:
                    edge_class = "edge-mid"
                else:
                    edge_class = "edge-low"

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

    with tab2:
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

    with tab3:
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

    with tab4:
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

    with tab5:
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
