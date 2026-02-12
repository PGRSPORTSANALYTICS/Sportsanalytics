"""
Learning Sports Dashboard
==========================
Separate sections for Tennis, Hockey (NHL/SHL), and MMA
Each with performance tracker and learning curve graphs.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from db_connection import DatabaseConnection

SPORT_CONFIGS = {
    'TENNIS': {'emoji': '🎾', 'label': 'Tennis', 'color': '#4CAF50', 'color_light': 'rgba(76,175,80,0.15)'},
    'HOCKEY': {'emoji': '🏒', 'label': 'Hockey', 'color': '#2196F3', 'color_light': 'rgba(33,150,243,0.15)'},
    'MMA': {'emoji': '🥊', 'label': 'MMA', 'color': '#FF5722', 'color_light': 'rgba(255,87,34,0.15)'},
}

st.markdown("""
<style>
    .ls-header {
        text-align: center;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
        color: #E0E0E0;
    }
    .ls-subtitle {
        text-align: center;
        color: #64748B;
        font-size: 0.85rem;
        margin-bottom: 1.5rem;
    }
    .ls-card {
        background: rgba(30,41,59,0.7);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        border: 1px solid rgba(100,116,139,0.2);
    }
    .ls-metric {
        text-align: center;
        padding: 12px 8px;
    }
    .ls-metric .val {
        font-size: 1.6rem;
        font-weight: 700;
    }
    .ls-metric .lbl {
        font-size: 0.7rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .ls-green { color: #22C55E; }
    .ls-red { color: #EF4444; }
    .ls-blue { color: #3B82F6; }
    .ls-orange { color: #F59E0B; }
    .ls-gray { color: #94A3B8; }
    .ls-pick {
        background: rgba(30,41,59,0.5);
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 6px;
        border-left: 3px solid;
        font-size: 0.85rem;
    }
    .ls-section {
        font-size: 1.1rem;
        font-weight: 600;
        margin: 16px 0 8px 0;
        color: #CBD5E1;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="ls-header">🌐 Learning Sports</div>', unsafe_allow_html=True)
st.markdown('<div class="ls-subtitle">Simulated 1u flat stakes &bull; Data collection for AI training &bull; Tennis, Hockey, MMA</div>', unsafe_allow_html=True)


@st.cache_data(ttl=120)
def get_overview_stats():
    try:
        with DatabaseConnection.get_connection() as conn:
            return pd.read_sql("""
                SELECT sport_category,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE outcome = 'won') as wins,
                    COUNT(*) FILTER (WHERE outcome = 'lost') as losses,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE outcome = 'void' OR status = 'void') as voids,
                    COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END), 0) as net_profit,
                    ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric, 2) as avg_odds
                FROM learning_bets
                GROUP BY sport_category
                ORDER BY sport_category
            """, conn)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_sport_daily(sport_cat):
    try:
        with DatabaseConnection.get_connection() as conn:
            return pd.read_sql("""
                SELECT DATE(created_at) as date,
                    COUNT(*) FILTER (WHERE outcome IN ('won','lost')) as settled,
                    COUNT(*) FILTER (WHERE outcome = 'won') as wins,
                    COUNT(*) FILTER (WHERE outcome = 'lost') as losses,
                    COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END), 0) as daily_profit
                FROM learning_bets
                WHERE sport_category = %s
                GROUP BY DATE(created_at)
                ORDER BY date
            """, conn, params=(sport_cat,))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_sport_by_market(sport_cat):
    try:
        with DatabaseConnection.get_connection() as conn:
            return pd.read_sql("""
                SELECT market,
                    COUNT(*) FILTER (WHERE outcome IN ('won','lost')) as settled,
                    COUNT(*) FILTER (WHERE outcome = 'won') as wins,
                    COUNT(*) FILTER (WHERE outcome = 'lost') as losses,
                    COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END), 0) as profit,
                    ROUND(AVG(CASE WHEN outcome IN ('won','lost') THEN odds END)::numeric, 2) as avg_odds
                FROM learning_bets
                WHERE sport_category = %s
                GROUP BY market
                ORDER BY profit DESC
            """, conn, params=(sport_cat,))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_sport_by_league(sport_cat):
    try:
        with DatabaseConnection.get_connection() as conn:
            return pd.read_sql("""
                SELECT league,
                    COUNT(*) FILTER (WHERE outcome IN ('won','lost')) as settled,
                    COUNT(*) FILTER (WHERE outcome = 'won') as wins,
                    COUNT(*) FILTER (WHERE outcome = 'lost') as losses,
                    COALESCE(SUM(CASE WHEN outcome IN ('won','lost') THEN profit_loss ELSE 0 END), 0) as profit
                FROM learning_bets
                WHERE sport_category = %s
                GROUP BY league
                ORDER BY profit DESC
            """, conn, params=(sport_cat,))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_sport_pending(sport_cat):
    try:
        with DatabaseConnection.get_connection() as conn:
            return pd.read_sql("""
                SELECT home_team, away_team, market, selection, line, odds,
                       league, commence_time
                FROM learning_bets
                WHERE sport_category = %s AND status = 'pending'
                ORDER BY commence_time ASC
                LIMIT 30
            """, conn, params=(sport_cat,))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_sport_recent(sport_cat):
    try:
        with DatabaseConnection.get_connection() as conn:
            return pd.read_sql("""
                SELECT home_team, away_team, market, selection, line, odds,
                       outcome, profit_loss, result_notes, settled_at, league
                FROM learning_bets
                WHERE sport_category = %s AND outcome IN ('won', 'lost')
                ORDER BY settled_at DESC NULLS LAST
                LIMIT 20
            """, conn, params=(sport_cat,))
    except Exception:
        return pd.DataFrame()


overview = get_overview_stats()

ocols = st.columns(3)
for i, (cat, cfg) in enumerate(SPORT_CONFIGS.items()):
    with ocols[i]:
        row = overview[overview['sport_category'] == cat].iloc[0] if not overview.empty and cat in overview['sport_category'].values else None
        if row is not None:
            wins = int(row['wins'] or 0)
            losses = int(row['losses'] or 0)
            settled = wins + losses
            pending = int(row['pending'] or 0)
            profit = float(row['net_profit'] or 0)
            hit = (wins / settled * 100) if settled > 0 else 0
            p_color = 'ls-green' if profit >= 0 else 'ls-red'
            h_color = 'ls-green' if hit >= 50 else 'ls-orange'
        else:
            wins = losses = settled = pending = 0
            profit = 0.0
            hit = 0.0
            p_color = 'ls-gray'
            h_color = 'ls-gray'

        st.markdown(f"""
        <div class="ls-card">
            <div style="font-size:1.3rem;font-weight:700;margin-bottom:8px;">{cfg['emoji']} {cfg['label']}</div>
            <div style="display:flex;justify-content:space-between;">
                <div class="ls-metric"><div class="val ls-blue">{settled}</div><div class="lbl">Settled</div></div>
                <div class="ls-metric"><div class="val ls-green">{wins}</div><div class="lbl">Wins</div></div>
                <div class="ls-metric"><div class="val ls-red">{losses}</div><div class="lbl">Losses</div></div>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <div class="ls-metric"><div class="val {h_color}">{hit:.1f}%</div><div class="lbl">Hit Rate</div></div>
                <div class="ls-metric"><div class="val {p_color}">{profit:+.1f}u</div><div class="lbl">Profit</div></div>
                <div class="ls-metric"><div class="val ls-gray">{pending}</div><div class="lbl">Pending</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

sport_tabs = st.tabs([f"{cfg['emoji']} {cfg['label']}" for cfg in SPORT_CONFIGS.values()])

for tab_idx, (cat, cfg) in enumerate(SPORT_CONFIGS.items()):
    with sport_tabs[tab_idx]:
        st.markdown(f'<div class="ls-section">{cfg["emoji"]} {cfg["label"]} Learning Tracker</div>', unsafe_allow_html=True)

        daily = get_sport_daily(cat)
        by_market = get_sport_by_market(cat)
        by_league = get_sport_by_league(cat)
        pending_df = get_sport_pending(cat)
        recent_df = get_sport_recent(cat)

        if not daily.empty and daily['settled'].sum() > 0:
            daily = daily.sort_values('date')
            daily['cumulative_profit'] = daily['daily_profit'].cumsum()
            daily['cumulative_settled'] = daily['settled'].cumsum()
            daily['cumulative_wins'] = daily['wins'].cumsum()
            daily['rolling_hit'] = (daily['cumulative_wins'] / daily['cumulative_settled'] * 100).round(1)

            chart_cols = st.columns(2)

            with chart_cols[0]:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=daily['date'], y=daily['cumulative_profit'],
                    mode='lines+markers',
                    name='Cumulative P/L',
                    line=dict(color=cfg['color'], width=2.5),
                    fill='tozeroy',
                    fillcolor=cfg['color_light'],
                    marker=dict(size=5),
                ))
                fig.add_hline(y=0, line_dash="dash", line_color="rgba(148,163,184,0.4)")
                fig.update_layout(
                    title=f"{cfg['emoji']} Learning Curve (Profit)",
                    xaxis_title="", yaxis_title="Units",
                    template="plotly_dark",
                    height=320,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=40, r=20, t=40, b=30),
                    font=dict(size=11),
                )
                st.plotly_chart(fig, use_container_width=True)

            with chart_cols[1]:
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=daily['date'], y=daily['rolling_hit'],
                    mode='lines+markers',
                    name='Hit Rate %',
                    line=dict(color='#F59E0B', width=2.5),
                    marker=dict(size=5),
                ))
                fig2.add_hline(y=50, line_dash="dash", line_color="rgba(148,163,184,0.4)")
                fig2.update_layout(
                    title=f"{cfg['emoji']} Rolling Hit Rate",
                    xaxis_title="", yaxis_title="%",
                    template="plotly_dark",
                    height=320,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=40, r=20, t=40, b=30),
                    font=dict(size=11),
                    yaxis=dict(range=[0, 100]),
                )
                st.plotly_chart(fig2, use_container_width=True)

            bar_cols = st.columns(2)

            with bar_cols[0]:
                fig3 = go.Figure(data=[
                    go.Bar(
                        x=daily['date'], y=daily['daily_profit'],
                        marker_color=[cfg['color'] if x >= 0 else '#EF4444' for x in daily['daily_profit']],
                    )
                ])
                fig3.update_layout(
                    title="Daily P/L",
                    template="plotly_dark", height=250,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=40, r=20, t=40, b=30), font=dict(size=11),
                )
                st.plotly_chart(fig3, use_container_width=True)

            with bar_cols[1]:
                if not by_market.empty:
                    fig4 = go.Figure(data=[
                        go.Bar(
                            x=by_market['market'], y=by_market['profit'],
                            marker_color=[cfg['color'] if x >= 0 else '#EF4444' for x in by_market['profit']],
                            text=[f"{int(r['wins'])}W/{int(r['losses'])}L" for _, r in by_market.iterrows()],
                            textposition='auto',
                        )
                    ])
                    fig4.update_layout(
                        title="Profit by Market",
                        template="plotly_dark", height=250,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=40, r=20, t=40, b=30), font=dict(size=11),
                    )
                    st.plotly_chart(fig4, use_container_width=True)

        else:
            st.info(f"No settled bets yet for {cfg['label']}. Data will appear once games are completed and settled.")

        if not by_league.empty and by_league['settled'].sum() > 0:
            st.markdown(f'<div class="ls-section">By League</div>', unsafe_allow_html=True)
            for _, lr in by_league.iterrows():
                s = int(lr['settled'])
                if s == 0:
                    continue
                w = int(lr['wins'])
                l = int(lr['losses'])
                p = float(lr['profit'])
                hr = (w / s * 100) if s > 0 else 0
                pc = '#22C55E' if p >= 0 else '#EF4444'
                st.markdown(f"""
                <div class="ls-pick" style="border-color:{cfg['color']};">
                    <strong>{lr['league']}</strong>
                    <span style="float:right;color:{pc};font-weight:600;">{p:+.1f}u</span><br>
                    <span style="color:#94A3B8;font-size:0.8rem;">{w}W/{l}L ({hr:.0f}%) &bull; {s} settled</span>
                </div>
                """, unsafe_allow_html=True)

        sub_tabs = st.tabs(["Pending Picks", "Recent Results"])

        with sub_tabs[0]:
            if pending_df.empty:
                st.info(f"No pending {cfg['label']} picks right now.")
            else:
                for _, row in pending_df.iterrows():
                    match_str = f"{row['home_team']} vs {row['away_team']}"
                    sel_str = row['selection']
                    if pd.notna(row.get('line')) and row['line']:
                        sel_str += f" {row['line']}"
                    mkt = str(row['market']).replace('_', ' ').title()
                    ct = row.get('commence_time', '')
                    ct_str = ct.strftime('%b %d %H:%M') if hasattr(ct, 'strftime') else str(ct)[:16]

                    st.markdown(f"""
                    <div class="ls-pick" style="border-color:{cfg['color']};">
                        <strong>{match_str}</strong>
                        <span style="float:right;font-weight:600;color:{cfg['color']};">@{row['odds']:.2f}</span><br>
                        <span style="color:#CBD5E1;">{mkt}: {sel_str}</span>
                        <span style="float:right;color:#64748B;font-size:0.75rem;">{ct_str}</span>
                    </div>
                    """, unsafe_allow_html=True)

        with sub_tabs[1]:
            if recent_df.empty:
                st.info(f"No settled {cfg['label']} results yet.")
            else:
                for _, row in recent_df.iterrows():
                    is_win = row.get('outcome') == 'won'
                    emoji = "✅" if is_win else "❌"
                    bc = "rgba(34,197,94,0.5)" if is_win else "rgba(239,68,68,0.5)"
                    match_str = f"{row['home_team']} vs {row['away_team']}"
                    sel_str = row['selection']
                    if pd.notna(row.get('line')) and row['line']:
                        sel_str += f" {row['line']}"
                    mkt = str(row['market']).replace('_', ' ').title()
                    note = row.get('result_notes', '') or ''
                    pl = float(row.get('profit_loss', 0) or 0)
                    pl_c = '#22C55E' if pl >= 0 else '#EF4444'

                    st.markdown(f"""
                    <div class="ls-pick" style="border-color:{bc};">
                        {emoji} <strong>{match_str}</strong>
                        <span style="float:right;color:{pl_c};font-weight:600;">{pl:+.1f}u</span><br>
                        <span style="color:#CBD5E1;">{mkt}: {sel_str} @{row['odds']:.2f}</span><br>
                        <span style="color:#64748B;font-size:0.75rem;">{note}</span>
                    </div>
                    """, unsafe_allow_html=True)

st.markdown("---")
st.caption("🌐 Learning mode &bull; Simulated stakes &bull; Data updates every 6 hours &bull; Settlement every 30 minutes")

if st.button("🔄 Refresh Data", key="ls_refresh"):
    st.cache_data.clear()
    st.rerun()
