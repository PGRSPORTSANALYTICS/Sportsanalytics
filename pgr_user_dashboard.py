"""
PGR Sports Analytics — User-facing dashboard
Design: PGR demo theme  |  Data: Live from PostgreSQL
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pgr_theme import inject_pgr_css, PGR_COLORS
from pgr_components import metric_card, section_title, picks_table
from db_helper import DatabaseHelper

st.set_page_config(
    page_title="PGR Sports Analytics",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_pgr_css()

# ── Extra UI polish ──────────────────────────────────────────────────────────
st.markdown("""
<style>
.pgr-hero {
    padding: 2.5rem 0 1.5rem 0;
    text-align: center;
}
.pgr-logo-text {
    font-size: 0.75rem;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: #9BA0B5;
    margin-bottom: 0.3rem;
}
.pgr-hero-title {
    font-size: 2.6rem;
    font-weight: 800;
    color: #F2F5F8;
    line-height: 1.1;
}
.pgr-hero-sub {
    font-size: 1rem;
    color: #9BA0B5;
    margin-top: 0.4rem;
}
.pgr-hero-accent {
    color: #00F59D;
}
.pick-card {
    padding: 18px 20px;
    margin: 8px 0;
    border-radius: 14px;
    border: 1px solid rgba(28,32,48,0.9);
    background: radial-gradient(circle at top left, #151a2c 0%, #101320 60%);
    position: relative;
    overflow: hidden;
}
.pick-card-won {
    border-color: rgba(0,245,157,0.35) !important;
    background: radial-gradient(circle at top left,
        rgba(0,245,157,0.08) 0%, #101320 60%) !important;
}
.pick-card-lost {
    border-color: rgba(255,75,107,0.3) !important;
    background: radial-gradient(circle at top left,
        rgba(255,75,107,0.06) 0%, #101320 60%) !important;
}
.pick-card-pending {
    border-color: rgba(251,191,36,0.25) !important;
}
.pick-match {
    font-size: 1.05rem;
    font-weight: 600;
    color: #F2F5F8;
    margin-bottom: 2px;
}
.pick-selection {
    font-size: 1.1rem;
    font-weight: 700;
    color: #00F59D;
    margin-bottom: 6px;
}
.pick-meta {
    font-size: 0.78rem;
    color: #9BA0B5;
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    align-items: center;
}
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.06em;
}
.badge-won    { background:rgba(0,245,157,0.15); color:#00F59D; border:1px solid rgba(0,245,157,0.4); }
.badge-lost   { background:rgba(255,75,107,0.12); color:#FF4B6B; border:1px solid rgba(255,75,107,0.35); }
.badge-pending{ background:rgba(251,191,36,0.1); color:#FBBF24; border:1px solid rgba(251,191,36,0.3); }
.badge-high   { background:rgba(0,245,157,0.1); color:#00F59D; border:1px solid rgba(0,245,157,0.3); }
.badge-medium { background:rgba(59,130,246,0.1); color:#60A5FA; border:1px solid rgba(59,130,246,0.3); }
.badge-low    { background:rgba(245,158,11,0.1); color:#F59E0B; border:1px solid rgba(245,158,11,0.3); }
.pgr-divider {
    border: none;
    border-top: 1px solid #1C2030;
    margin: 1.2rem 0;
}
.stat-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 14px;
    border-radius: 999px;
    background: rgba(15,23,42,0.8);
    border: 1px solid #1C2030;
    font-size: 0.8rem;
    color: #9BA0B5;
    margin: 3px;
}
.stat-pill b { color: #F2F5F8; }
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #9BA0B5;
}
.empty-state .big { font-size: 2.5rem; }
.empty-state p { margin-top: 8px; font-size: 0.9rem; }
.track-period-btn {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)


# ── DB helpers ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_hero_stats():
    db = DatabaseHelper()
    row = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE UPPER(result) = 'WON')                       AS wins,
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','LOST'))              AS settled,
            COALESCE(SUM(CASE WHEN UPPER(result)='WON' THEN (odds-1.0)
                              WHEN UPPER(result)='LOST' THEN -1.0 ELSE 0 END),0) AS profit_units,
            COUNT(*) FILTER (WHERE UPPER(status) = 'PENDING')                   AS pending
        FROM football_opportunities
        WHERE mode = 'PROD'
    """, fetch='one')
    return row or (0, 0, 0.0, 0)


@st.cache_data(ttl=120)
def load_todays_picks():
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT home_team, away_team, league, market, selection, odds,
               confidence, edge_percentage, status, result, kickoff_time
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND match_date = CURRENT_DATE::text
        ORDER BY
            CASE WHEN UPPER(status)='PENDING' THEN 0 ELSE 1 END,
            timestamp DESC
        LIMIT 40
    """, fetch='all')
    return rows or []


@st.cache_data(ttl=300)
def load_smart_picks():
    db = DatabaseHelper()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = db.execute("""
        SELECT home_team, away_team, league, market, selection, odds,
               smart_score, confidence, model_grade
        FROM smart_picks
        WHERE pick_date = %s
        ORDER BY smart_score DESC
    """, (today,), fetch='all')
    return rows or []


@st.cache_data(ttl=300)
def load_performance(days: int = 30):
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT
            match_date,
            COUNT(*) FILTER (WHERE UPPER(result)='WON')             AS wins,
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','LOST'))  AS settled,
            COALESCE(SUM(CASE WHEN UPPER(result)='WON' THEN (odds-1.0)
                              WHEN UPPER(result)='LOST' THEN -1.0 ELSE 0 END), 0) AS day_units
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND UPPER(status) = 'SETTLED'
          AND timestamp >= NOW() - INTERVAL '%s days'
        GROUP BY match_date
        ORDER BY match_date
    """ % days, fetch='all')
    return rows or []


@st.cache_data(ttl=300)
def load_all_time_summary():
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT
            market,
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','LOST')) AS settled,
            COUNT(*) FILTER (WHERE UPPER(result)='WON')             AS wins,
            COALESCE(SUM(CASE WHEN UPPER(result)='WON' THEN (odds-1.0)
                              WHEN UPPER(result)='LOST' THEN -1.0 ELSE 0 END), 0) AS units
        FROM football_opportunities
        WHERE mode = 'PROD' AND UPPER(status) = 'SETTLED'
        GROUP BY market
        HAVING COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','LOST')) >= 5
        ORDER BY units DESC
    """, fetch='all')
    return rows or []


# ── Helpers ───────────────────────────────────────────────────────────────────
def _clean_market(m: str) -> str:
    label_map = {
        "value single": "Value Single",
        "corners_over": "Corners Over",
        "corners_under": "Corners Under",
        "corners_handicap": "Corners Handicap",
        "cards_over": "Cards Over",
        "cards_under": "Cards Under",
        "btts": "Both Teams Score",
        "double_chance": "Double Chance",
        "asian_handicap": "Asian Handicap",
        "over_2.5": "Over 2.5 Goals",
        "under_2.5": "Under 2.5 Goals",
        "over_3.5": "Over 3.5 Goals",
        "1x2": "1X2",
    }
    return label_map.get(str(m).lower().strip(), str(m).replace("_", " ").title())


def _clean_confidence(c) -> tuple:
    """Returns (label, css_class)."""
    if c is None:
        return "Standard", "low"
    v = str(c).lower()
    if any(x in v for x in ["strong", "high", "very"]):
        return "High", "high"
    if "medium" in v or "mid" in v:
        return "Medium", "medium"
    try:
        pct = float(c)
        if pct >= 75:
            return "High", "high"
        if pct >= 65:
            return "Medium", "medium"
    except Exception:
        pass
    return "Standard", "low"


def _result_badge(status, result) -> str:
    s = str(status).upper()
    r = str(result).upper() if result else ""
    if r == "WON":
        return '<span class="badge badge-won">WIN</span>'
    if r == "LOST":
        return '<span class="badge badge-lost">LOSS</span>'
    if s == "PENDING":
        return '<span class="badge badge-pending">LIVE</span>'
    return '<span class="badge badge-pending">PENDING</span>'


def _pick_card_class(result) -> str:
    r = str(result).upper() if result else ""
    if r == "WON":
        return "pick-card pick-card-won"
    if r == "LOST":
        return "pick-card pick-card-lost"
    return "pick-card pick-card-pending"


# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
wins, settled, profit_units, pending = load_hero_stats()
hit_rate = (wins / settled * 100) if settled > 0 else 0.0
roi = (profit_units / settled * 100) if settled > 0 else 0.0

st.markdown("""
<div class="pgr-hero">
    <div class="pgr-logo-text">PGR Sports Analytics</div>
    <div class="pgr-hero-title">
        AI-Powered <span class="pgr-hero-accent">Edge Detection</span>
    </div>
    <div class="pgr-hero-sub">
        Real-time value scanning across 30+ football leagues. No guesswork — pure data.
    </div>
</div>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("All-Time ROI", f"{roi:+.1f}%", kicker=f"{settled} settled picks",
                variant="good" if roi >= 0 else "bad")
with c2:
    metric_card("Hit Rate", f"{hit_rate:.1f}%", kicker="Wins / total picks",
                variant="good" if hit_rate >= 45 else "bad")
with c3:
    metric_card("Profit", f"{profit_units:+.1f} units",
                kicker="Flat 1-unit staking",
                variant="good" if profit_units >= 0 else "bad")
with c4:
    metric_card("Live Picks", str(pending), kicker="Pending today",
                variant="default")

st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_today, tab_smart, tab_track = st.tabs([
    "⚡ Today's Picks",
    "🧠 Smart Picks",
    "📈 Track Record",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — TODAY'S PICKS
# ─────────────────────────────────────────────────────────────────────────────
with tab_today:
    picks = load_todays_picks()

    today_wins   = sum(1 for p in picks if str(p[9] or "").upper() == "WON")
    today_losses = sum(1 for p in picks if str(p[9] or "").upper() == "LOST")
    today_pend   = sum(1 for p in picks if str(p[8] or "").upper() == "PENDING")
    today_settled_n = today_wins + today_losses
    today_hr = (today_wins / today_settled_n * 100) if today_settled_n > 0 else 0.0

    st.markdown(f"""
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 20px 0;">
        <span class="stat-pill">Total <b>{len(picks)}</b></span>
        <span class="stat-pill">Wins <b style="color:#00F59D;">{today_wins}</b></span>
        <span class="stat-pill">Losses <b style="color:#FF4B6B;">{today_losses}</b></span>
        <span class="stat-pill">Pending <b style="color:#FBBF24;">{today_pend}</b></span>
        {"<span class='stat-pill'>Hit Rate <b>" + f"{today_hr:.0f}%" + "</b></span>" if today_settled_n > 0 else ""}
    </div>
    """, unsafe_allow_html=True)

    if not picks:
        st.markdown("""
        <div class="empty-state">
            <div class="big">⚡</div>
            <p>No picks for today yet.<br>The engine runs multiple times daily — check back soon.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        col_a, col_b = st.columns(2)
        for i, pick in enumerate(picks):
            home, away, league, market, selection, odds, conf, ev, status, result, ko_time = pick
            conf_label, conf_cls = _clean_confidence(conf)
            card_cls = _pick_card_class(result)
            badge = _result_badge(status, result)
            market_clean = _clean_market(market)
            ko_str = ""
            if ko_time:
                try:
                    ko_str = f"KO {str(ko_time)[:5]}"
                except Exception:
                    pass

            html = f"""
            <div class="{card_cls}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                    <div style="font-size:0.75rem;color:#9BA0B5;">{league} {("· " + ko_str) if ko_str else ""}</div>
                    <div style="display:flex;gap:5px;align-items:center;">
                        <span class="badge badge-{conf_cls}">{conf_label}</span>
                        {badge}
                    </div>
                </div>
                <div class="pick-match">{home} vs {away}</div>
                <div class="pick-selection">{selection}</div>
                <div class="pick-meta">
                    <span>Odds <b style="color:#F2F5F8;">{float(odds):.2f}</b></span>
                    <span>{market_clean}</span>
                </div>
            </div>
            """
            if i % 2 == 0:
                col_a.markdown(html, unsafe_allow_html=True)
            else:
                col_b.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — SMART PICKS
# ─────────────────────────────────────────────────────────────────────────────
with tab_smart:
    smart = load_smart_picks()

    st.markdown("""
    <div style="padding:10px 16px;border-radius:10px;
                background:rgba(0,245,157,0.06);
                border:1px solid rgba(0,245,157,0.2);
                margin-bottom:20px;">
        <span style="color:#00F59D;font-size:0.82rem;font-weight:600;">🧠 Smart Picks</span>
        <span style="color:#9BA0B5;font-size:0.82rem;">
            &nbsp;— AI-curated selections. One best pick per match, SmartScore ranked.
            Refreshes daily at 09:00 CET.
        </span>
    </div>
    """, unsafe_allow_html=True)

    if not smart:
        st.markdown("""
        <div class="empty-state">
            <div class="big">🧠</div>
            <p>Smart Picks for today aren't ready yet.<br>
            Check back after 09:00 CET.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        grade_colors = {"A": ("#00F59D", "rgba(0,245,157,0.1)", "rgba(0,245,157,0.3)"),
                        "B": ("#60A5FA", "rgba(59,130,246,0.1)", "rgba(59,130,246,0.3)"),
                        "C": ("#F59E0B", "rgba(245,158,11,0.1)", "rgba(245,158,11,0.3)")}

        col_a, col_b = st.columns(2)
        for i, pick in enumerate(smart):
            home, away, league, market, selection, odds, score, conf, grade = pick
            gc, gb, gbd = grade_colors.get(str(grade), grade_colors["C"])
            conf_label, conf_cls = _clean_confidence(conf)
            market_clean = _clean_market(market)

            html = f"""
            <div style="padding:18px 20px;margin:8px 0;border-radius:14px;
                        background:radial-gradient(circle at top left,{gb} 0%,#101320 60%);
                        border:1px solid {gbd};">
                <div style="display:flex;justify-content:space-between;
                            align-items:flex-start;margin-bottom:6px;">
                    <span style="font-size:0.75rem;color:#9BA0B5;">{league}</span>
                    <div style="display:flex;gap:5px;">
                        <span class="badge badge-{conf_cls}">{conf_label}</span>
                        <span style="padding:2px 10px;border-radius:999px;
                                     background:{gb};color:{gc};
                                     border:1px solid {gbd};font-size:0.72rem;font-weight:600;">
                            Grade {grade}
                        </span>
                    </div>
                </div>
                <div class="pick-match">{home} vs {away}</div>
                <div class="pick-selection">{selection}</div>
                <div class="pick-meta">
                    <span>Odds <b style="color:#F2F5F8;">{float(odds):.2f}</b></span>
                    <span>{market_clean}</span>
                </div>
            </div>
            """
            if i % 2 == 0:
                col_a.markdown(html, unsafe_allow_html=True)
            else:
                col_b.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — TRACK RECORD
# ─────────────────────────────────────────────────────────────────────────────
with tab_track:
    period = st.radio(
        "Period",
        ["7 days", "30 days", "90 days"],
        index=1,
        horizontal=True,
        label_visibility="collapsed",
    )
    day_map = {"7 days": 7, "30 days": 30, "90 days": 90}
    days = day_map[period]

    perf = load_performance(days)

    if not perf:
        st.markdown("""
        <div class="empty-state">
            <div class="big">📈</div>
            <p>Not enough settled picks yet to show performance.<br>
            Check back as results come in.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        df = pd.DataFrame(perf, columns=["date", "wins", "settled", "day_units"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df["cumulative_units"] = df["day_units"].cumsum()
        df["hit_rate"] = df.apply(
            lambda r: (r["wins"] / r["settled"] * 100) if r["settled"] > 0 else None, axis=1
        )

        total_settled = int(df["settled"].sum())
        total_wins    = int(df["wins"].sum())
        total_units   = float(df["day_units"].sum())
        total_hr      = (total_wins / total_settled * 100) if total_settled > 0 else 0
        total_roi     = (total_units / total_settled * 100) if total_settled > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card("ROI", f"{total_roi:+.1f}%", kicker=f"Last {days} days",
                        variant="good" if total_roi >= 0 else "bad")
        with c2:
            metric_card("Profit", f"{total_units:+.1f} units", kicker="Flat staking",
                        variant="good" if total_units >= 0 else "bad")
        with c3:
            metric_card("Hit Rate", f"{total_hr:.1f}%", kicker=f"{total_wins}W / {total_settled - total_wins}L",
                        variant="good" if total_hr >= 45 else "bad")
        with c4:
            metric_card("Picks", str(total_settled), kicker="Settled this period",
                        variant="default")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        # Equity curve
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["cumulative_units"],
            mode="lines",
            fill="tozeroy",
            line=dict(color="#00F59D", width=2.5),
            fillcolor="rgba(0,245,157,0.08)",
            name="Cumulative units",
            hovertemplate="%{x|%b %d}<br>%{y:+.2f} units<extra></extra>",
        ))
        fig.add_hline(y=0, line_dash="dot", line_color="#1C2030", line_width=1)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9BA0B5", size=12),
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
            showlegend=False,
            xaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False),
            yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False,
                       ticksuffix="u"),
        )
        section_title("Equity Curve", icon="📈")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Daily bar chart
        bar_colors = ["#00F59D" if v >= 0 else "#FF4B6B" for v in df["day_units"]]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df["date"],
            y=df["day_units"],
            marker_color=bar_colors,
            hovertemplate="%{x|%b %d}<br>%{y:+.2f}u<extra></extra>",
        ))
        fig2.add_hline(y=0, line_color="#1C2030", line_width=1)
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9BA0B5", size=12),
            margin=dict(l=10, r=10, t=10, b=10),
            height=200,
            showlegend=False,
            xaxis=dict(gridcolor="#1C2030", showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False,
                       ticksuffix="u"),
        )
        section_title("Daily Units", icon="📊")
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

        # Market breakdown
        market_data = load_all_time_summary()
        if market_data:
            st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
            section_title("Performance by Market", icon="🎯")
            mdf = pd.DataFrame(market_data, columns=["Market", "Picks", "Wins", "Units"])
            mdf["Market"] = mdf["Market"].apply(_clean_market)
            mdf["Hit Rate"] = mdf.apply(
                lambda r: f"{r['Wins']/r['Picks']*100:.0f}%" if r["Picks"] > 0 else "-", axis=1
            )
            mdf["Units"] = mdf["Units"].apply(lambda x: f"{x:+.1f}u")
            mdf = mdf.drop(columns=["Wins"])
            st.dataframe(mdf, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center;color:#3D4259;font-size:0.75rem;padding:8px 0 24px 0;">
    PGR Sports Analytics · AI-powered picks for recreational players · No staking advice
</div>
""", unsafe_allow_html=True)
