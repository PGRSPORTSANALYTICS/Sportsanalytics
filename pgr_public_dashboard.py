import streamlit as st
import pandas as pd
from datetime import datetime, date
import time

from db_helper import DatabaseHelper

st.set_page_config(
    page_title="PGR Value Scanner | Live Market Edge",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PREMIUM_LINK = "https://discord.gg/pgrsports"

LOCK_CSS = """
<style>
body { background: #0e1117; }

.hero {
    background: linear-gradient(135deg, #0d1b2a 0%, #1a2b4a 100%);
    border: 1px solid #1e3a5f;
    border-radius: 12px;
    padding: 2.5rem 2rem 2rem 2rem;
    margin-bottom: 1.5rem;
    text-align: center;
}
.hero h1 { font-size: 2.4rem; font-weight: 800; color: #ffffff; margin: 0 0 0.4rem 0; }
.hero p  { color: #8fa8c8; font-size: 1.05rem; margin: 0; }

.pulse-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 0 0 rgba(34,197,94,0.7);
    animation: pulse 1.8s infinite;
    margin-right: 6px;
    vertical-align: middle;
}
@keyframes pulse {
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.7); }
    70%  { box-shadow: 0 0 0 10px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}

.stat-box {
    background: #131b2e;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 1.2rem 1rem;
    text-align: center;
    margin-bottom: 0.5rem;
}
.stat-box .value { font-size: 2rem; font-weight: 800; color: #38bdf8; }
.stat-box .label { font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 2px; }

.edge-card {
    background: #131b2e;
    border: 1px solid #1e3a5f;
    border-left: 4px solid #38bdf8;
    border-radius: 8px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.5rem;
}
.edge-card.grade-a { border-left-color: #22c55e; }
.edge-card.grade-b { border-left-color: #f59e0b; }
.edge-card.grade-c { border-left-color: #ef4444; }

.edge-meta { font-size: 0.78rem; color: #64748b; }
.edge-league { font-size: 0.88rem; color: #94a3b8; font-weight: 600; }
.edge-market { font-size: 0.82rem; color: #38bdf8; }
.edge-score-pill {
    display: inline-block;
    background: #1e3a5f;
    color: #38bdf8;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.76rem;
    font-weight: 700;
}

.locked-row {
    background: #131b2e;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.5rem;
    filter: blur(0px);
    position: relative;
    overflow: hidden;
}
.locked-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent 0%, #0e1117 60%);
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding-right: 1rem;
}
.lock-badge {
    background: #1e3a5f;
    color: #38bdf8;
    border-radius: 6px;
    padding: 3px 12px;
    font-size: 0.78rem;
    font-weight: 700;
    border: 1px solid #2563eb;
}

.cta-box {
    background: linear-gradient(135deg, #0f2744 0%, #1a3a6e 100%);
    border: 1px solid #2563eb;
    border-radius: 12px;
    padding: 1.8rem 2rem;
    text-align: center;
    margin: 1.5rem 0;
}
.cta-box h3 { color: #fff; font-size: 1.4rem; margin: 0 0 0.4rem 0; }
.cta-box p  { color: #94a3b8; margin: 0 0 1rem 0; font-size: 0.95rem; }

.footer-note { color: #334155; font-size: 0.72rem; text-align: center; margin-top: 1rem; }

a.cta-btn {
    display: inline-block;
    background: #2563eb;
    color: #ffffff !important;
    text-decoration: none;
    border-radius: 8px;
    padding: 0.6rem 2rem;
    font-weight: 700;
    font-size: 1rem;
    transition: background 0.2s;
}
a.cta-btn:hover { background: #1d4ed8; }

.tab-header { color: #94a3b8; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.4rem; }
</style>
"""
st.markdown(LOCK_CSS, unsafe_allow_html=True)


@st.cache_data(ttl=120)
def load_live_data():
    db = DatabaseHelper()

    summary = db.execute("""
        SELECT
          COUNT(*) FILTER (WHERE mode IN ('PROD','VALUE_OPP') AND status='pending' AND match_date::date >= CURRENT_DATE) AS live_edges,
          COUNT(*) FILTER (WHERE mode='PROD' AND status='pending' AND match_date::date >= CURRENT_DATE) AS prod_edges,
          COUNT(DISTINCT league) FILTER (WHERE status='pending' AND match_date::date >= CURRENT_DATE) AS leagues,
          ROUND(
            (AVG(edge_percentage) FILTER (WHERE mode IN ('PROD','VALUE_OPP') AND status='pending' AND match_date::date >= CURRENT_DATE))::numeric,
          1) AS avg_edge
        FROM football_opportunities
    """, fetch='one')

    leagues_data = db.execute("""
        SELECT league, market, COUNT(*) as cnt,
               ROUND(MAX(edge_percentage)::numeric,1) as top_edge
        FROM football_opportunities
        WHERE mode IN ('PROD','VALUE_OPP')
          AND status = 'pending'
          AND match_date::date >= CURRENT_DATE
        GROUP BY league, market
        ORDER BY cnt DESC, top_edge DESC
        LIMIT 30
    """, fetch='all')

    smart_picks_pub = db.execute("""
        SELECT league, market, smart_score, confidence, model_grade, pick_date
        FROM smart_picks
        WHERE pick_date::date >= CURRENT_DATE - 1
        ORDER BY smart_score DESC
        LIMIT 6
    """, fetch='all')

    all_time = db.execute("""
        SELECT
          COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS')) AS settled,
          COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN')) AS won,
          ROUND(SUM(profit_loss)::numeric, 1) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS','VOID','PUSH')) AS total_profit,
          ROUND(
            100.0 * COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))
            / NULLIF(COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS')), 0),
          1) AS hit_rate
        FROM football_opportunities
        WHERE mode = 'PROD' AND bet_placed = true
    """, fetch='one')

    return summary, leagues_data, smart_picks_pub, all_time


def grade_color(score):
    if score >= 80:
        return "grade-a"
    elif score >= 65:
        return "grade-b"
    return "grade-c"


def render_hero(live_edges, avg_edge):
    st.markdown(f"""
    <div class="hero">
        <div><span class="pulse-dot"></span><span style="color:#22c55e;font-size:0.85rem;font-weight:700;letter-spacing:0.1em;">LIVE</span></div>
        <h1>PGR Value Scanner</h1>
        <p>Real-time market inefficiency scanner &mdash; powered by Monte Carlo simulation &amp; ensemble AI</p>
        <p style="margin-top:0.8rem;font-size:1.1rem;color:#38bdf8;font-weight:700;">
            {live_edges or 0} live value edges detected &nbsp;|&nbsp; avg edge {avg_edge or 0:.1f}%
        </p>
    </div>
    """, unsafe_allow_html=True)


def render_stats(summary, all_time):
    live_edges = summary[0] or 0
    prod_edges = summary[1] or 0
    leagues    = summary[2] or 0
    avg_edge   = float(summary[3] or 0)

    settled    = all_time[0] or 0
    hit_rate   = float(all_time[3] or 0)
    total_profit = float(all_time[2] or 0)

    cols = st.columns(5)
    items = [
        (str(live_edges), "Live Value Edges"),
        (str(leagues),    "Leagues Scanned"),
        (f"{avg_edge:.1f}%", "Avg Edge vs Market"),
        (f"{hit_rate:.1f}%", "All-Time Hit Rate"),
        (f"+{total_profit:.0f}u" if total_profit >= 0 else f"{total_profit:.0f}u", "Total Profit (units)"),
    ]
    for col, (val, label) in zip(cols, items):
        with col:
            st.markdown(f"""
            <div class="stat-box">
                <div class="value">{val}</div>
                <div class="label">{label}</div>
            </div>
            """, unsafe_allow_html=True)


def render_live_edges(leagues_data):
    st.markdown("### 📡 Live Value Edges by League")
    st.markdown('<div class="tab-header">Market opportunities detected this scan cycle — selection details are premium</div>', unsafe_allow_html=True)

    if not leagues_data:
        st.info("No live edges at the moment — next scan in progress.")
        return

    for row in leagues_data[:12]:
        league, market, cnt, top_edge = row[0], row[1], row[2], float(row[3] or 0)
        gc = "grade-a" if top_edge >= 20 else ("grade-b" if top_edge >= 12 else "grade-c")
        edge_bar = "🟢" * min(int(top_edge / 5), 5)

        st.markdown(f"""
        <div class="edge-card {gc}">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span class="edge-league">{league}</span>
                    <span class="edge-meta"> &nbsp;·&nbsp; </span>
                    <span class="edge-market">{market}</span>
                </div>
                <div>
                    <span class="edge-score-pill">top edge {top_edge:.1f}%</span>
                </div>
            </div>
            <div class="edge-meta" style="margin-top:4px;">
                {cnt} opportunit{'y' if cnt==1 else 'ies'} &nbsp;·&nbsp; {edge_bar}
                &nbsp; <span style="color:#334155;">Selection &amp; odds: 🔒 Premium</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if len(leagues_data) > 12:
        remaining = sum(r[2] for r in leagues_data[12:])
        st.markdown(f"""
        <div class="locked-row">
            <span class="edge-meta">+ {remaining} more edges in {len(leagues_data)-12} additional leagues</span>
            <span class="lock-badge" style="margin-left:1rem;">🔒 Premium</span>
        </div>
        """, unsafe_allow_html=True)


def render_smart_picks_preview(smart_picks_pub):
    st.markdown("### 🎯 Today's Smart Picks — AI Curated")
    st.markdown('<div class="tab-header">One best pick per match — SmartScore ranked. Full details are premium.</div>', unsafe_allow_html=True)

    if not smart_picks_pub:
        st.info("Smart Picks for today not yet generated.")
        return

    for i, row in enumerate(smart_picks_pub):
        league, market, score, conf, grade, pick_date = row
        score = float(score or 0)
        gc = grade_color(score)
        grade_lbl = grade or "—"
        conf_icon = "🟢" if conf == "Strong" else ("🟡" if conf == "Medium" else "🔴")
        blur_sel = "██████ ████ ██"
        blur_odds = "x.xx"

        if i < 2:
            st.markdown(f"""
            <div class="edge-card {gc}">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <span class="edge-league">{league}</span>
                        <span class="edge-meta"> · {market}</span>
                    </div>
                    <span class="edge-score-pill">SmartScore {score:.1f}</span>
                </div>
                <div class="edge-meta" style="margin-top:4px;">
                    {conf_icon} {conf} &nbsp;·&nbsp; Grade {grade_lbl}
                    &nbsp;·&nbsp; <span style="color:#334155;">Selection &amp; odds: 🔒 Premium</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="locked-row">
                <span class="edge-league" style="filter:blur(3px);user-select:none;">{blur_sel}</span>
                &nbsp; <span class="edge-market" style="filter:blur(3px);">{blur_odds}</span>
                &nbsp;·&nbsp; <span class="edge-meta">SmartScore {score:.1f}</span>
                <span class="lock-badge" style="margin-left:1rem;">🔒 Premium</span>
            </div>
            """, unsafe_allow_html=True)


def render_cta():
    st.markdown(f"""
    <div class="cta-box">
        <h3>🔓 Unlock Full Access</h3>
        <p>See exact selections, odds, stakes &amp; real-time edge — join the PGR premium community.</p>
        <a class="cta-btn" href="{PREMIUM_LINK}" target="_blank">Join PGR Premium →</a>
    </div>
    """, unsafe_allow_html=True)


def render_footer():
    st.markdown("""
    <div class="footer-note">
        PGR Sports Analytics · Data for informational purposes only · Always gamble responsibly · 18+<br>
        Model updates every ~60 min · Edges vs sharp books (Pinnacle / Betfair)
    </div>
    """, unsafe_allow_html=True)


def main():
    summary, leagues_data, smart_picks_pub, all_time = load_live_data()

    live_edges = summary[0] or 0
    avg_edge   = float(summary[3] or 0)

    render_hero(live_edges, avg_edge)
    render_stats(summary, all_time)

    st.divider()

    col_left, col_right = st.columns([3, 2], gap="large")

    with col_left:
        render_live_edges(leagues_data)

    with col_right:
        render_smart_picks_preview(smart_picks_pub)
        render_cta()

    render_footer()

    st.markdown(
        f'<div class="footer-note">Last updated: {datetime.utcnow().strftime("%H:%M UTC")}</div>',
        unsafe_allow_html=True
    )


main()
