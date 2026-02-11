"""
PGR Player Props Dashboard - Learning Mode
Shows player prop data collected from The Odds API
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from db_connection import DatabaseConnection

st.markdown("""
<style>
    .props-header {
        text-align: center;
        color: #e91e63;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .props-sub {
        text-align: center;
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .learning-badge {
        background: linear-gradient(135deg, #ff9800 0%, #f44336 100%);
        color: white;
        padding: 0.3rem 1rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 1rem;
    }
    .prop-card {
        background: #f8f9fa;
        border-left: 4px solid #e91e63;
        padding: 1rem;
        margin-bottom: 0.8rem;
        border-radius: 5px;
    }
    .prop-card-basketball {
        background: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 1rem;
        margin-bottom: 0.8rem;
        border-radius: 5px;
    }
    .metric-card-props {
        background: linear-gradient(135deg, #e91e63 0%, #9c27b0 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-card-orange {
        background: linear-gradient(135deg, #ff9800 0%, #f44336 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-card-blue {
        background: linear-gradient(135deg, #2196F3 0%, #00BCD4 100%);
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
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="props-header">Player Props</div>', unsafe_allow_html=True)
st.markdown('<div class="props-sub">NBA &bull; NCAAB &bull; Football &bull; Learning Mode Data Collection</div>', unsafe_allow_html=True)
st.markdown('<center><span class="learning-badge">LEARNING MODE - No Real Stakes</span></center>', unsafe_allow_html=True)


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
                    MIN(created_at) as first_collected,
                    MAX(created_at) as last_collected
                FROM player_props
                WHERE mode = 'LEARNING'
            """
            result = pd.read_sql(query, conn)
            return result.iloc[0] if not result.empty else None
    except Exception as e:
        st.error(f"Error loading overview: {e}")
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
                    ROUND(MIN(edge_pct)::numeric, 1) as min_edge,
                    ROUND(MAX(edge_pct)::numeric, 1) as max_edge
                FROM player_props
                WHERE mode = 'LEARNING'
                GROUP BY sport, market
                ORDER BY sport, market
            """
            return pd.read_sql(query, conn)
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        return pd.DataFrame()


overview = get_props_overview()

if overview is not None and overview['total_props'] > 0:
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(f"""
        <div class="metric-card-props">
            <div class="metric-value">{int(overview['total_props']):,}</div>
            <div class="metric-label">Total Props</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card-orange">
            <div class="metric-value">{int(overview['unique_players'])}</div>
            <div class="metric-label">Players</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card-blue">
            <div class="metric-value">{int(overview['unique_matches'])}</div>
            <div class="metric-label">Matches</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card-props">
            <div class="metric-value">{overview['avg_edge']}%</div>
            <div class="metric-label">Avg Edge</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        st.markdown(f"""
        <div class="metric-card-orange">
            <div class="metric-value">{overview['avg_odds']}x</div>
            <div class="metric-label">Avg Odds</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Top Edge Props", "By Sport/Market", "Top Players", "Collection History", "Raw Data"
    ])

    with tab1:
        st.subheader("Top Edge Player Props")

        fcol1, fcol2 = st.columns(2)
        with fcol1:
            sport_options = ["All", "Basketball", "Football"]
            sport_filter = st.selectbox("Sport", sport_options, key="prop_sport")
        with fcol2:
            market_options = ["All", "player_points", "player_rebounds", "player_anytime_goalscorer", "player_shots_on_goal"]
            market_filter = st.selectbox("Market", market_options, key="prop_market")

        top_props = get_top_edge_props(sport_filter, market_filter)

        if top_props.empty:
            st.info("No props found with current filters.")
        else:
            for idx, row in top_props.iterrows():
                card_class = "prop-card-basketball" if row['sport'] == 'basketball' else "prop-card"
                sport_emoji = "🏀" if row['sport'] == 'basketball' else "⚽"
                market_display = row['market'].replace('player_', '').replace('_', ' ').title()

                line_str = f" ({row['selection']} {row['line']})" if pd.notna(row['line']) and row['line'] > 0 else f" ({row['selection']})"

                st.markdown(f"""
                <div class="{card_class}">
                    {sport_emoji} <strong>{row['player_name']}</strong> — {market_display}{line_str}<br>
                    <small>{row['home_team']} vs {row['away_team']} | {row['league']}</small><br>
                    <small>
                        Odds: <strong>{row['odds']:.2f}</strong> |
                        Edge: <strong style="color: #e91e63;">{row['edge_pct']:.1f}%</strong> |
                        Model: {row['model_prob']:.1%} vs Implied: {row['implied_prob']:.1%} |
                        Book: {row['bookmaker']}
                    </small>
                </div>
                """, unsafe_allow_html=True)

    with tab2:
        sport_market = get_props_by_sport()
        if sport_market.empty:
            st.info("No data yet.")
        else:
            st.subheader("Props by Sport & Market")

            for sport in sport_market['sport'].unique():
                sport_data = sport_market[sport_market['sport'] == sport]
                emoji = "🏀" if sport == 'basketball' else "⚽"
                st.markdown(f"### {emoji} {sport.title()}")

                cols = st.columns(len(sport_data))
                for i, (_, row) in enumerate(sport_data.iterrows()):
                    with cols[i]:
                        market_name = row['market'].replace('player_', '').replace('_', ' ').title()
                        st.metric(market_name, f"{int(row['total'])} props")
                        st.caption(f"{int(row['players'])} players | {int(row['matches'])} matches")
                        st.caption(f"Edge: {row['avg_edge']}% (range: {row['min_edge']}% to {row['max_edge']}%)")

            fig = px.bar(
                sport_market,
                x='market',
                y='total',
                color='sport',
                title='Props Collected by Market',
                labels={'total': 'Count', 'market': 'Market'},
                color_discrete_map={'basketball': '#ff9800', 'football': '#e91e63'}
            )
            fig.update_layout(template="plotly_white", height=400)
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        top_players = get_top_players()
        if top_players.empty:
            st.info("No player data yet.")
        else:
            st.subheader("Top Players by Average Edge")

            for idx, row in top_players.iterrows():
                emoji = "🏀" if row['sport'] == 'basketball' else "⚽"
                st.markdown(f"""
                <div class="prop-card">
                    {emoji} <strong>{row['player_name']}</strong> ({row['sport'].title()})<br>
                    <small>
                        Avg Edge: <strong style="color: #e91e63;">{row['avg_edge']}%</strong> |
                        Best Edge: {row['best_edge']}% |
                        Props: {int(row['prop_count'])} |
                        Avg Odds: {row['avg_odds']}x |
                        Markets: {int(row['markets'])}
                    </small>
                </div>
                """, unsafe_allow_html=True)

    with tab4:
        daily = get_daily_collection()
        if daily.empty:
            st.info("No collection history yet.")
        else:
            st.subheader("Daily Collection History")

            fig = px.bar(
                daily,
                x='date',
                y='props_collected',
                color='sport',
                title='Props Collected Per Day',
                labels={'props_collected': 'Props', 'date': 'Date'},
                color_discrete_map={'basketball': '#ff9800', 'football': '#e91e63'}
            )
            fig.update_layout(template="plotly_white", height=400)
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(daily, use_container_width=True, hide_index=True)

    with tab5:
        st.subheader("Raw Props Data")
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
    st.info("No player props data collected yet. The engine runs every 6 hours to collect data.")
    st.caption("Markets tracked: player_points, player_rebounds (basketball) | player_anytime_goalscorer, player_shots_on_goal (football)")

st.markdown("---")
st.caption("Data collected every 6 hours from The Odds API | Learning mode — no real stakes")

if st.button("Refresh Data", key="refresh_props"):
    st.cache_data.clear()
    st.rerun()
