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


@st.cache_data(ttl=300)
def load_clv_hero_stats():
    db = DatabaseHelper()
    row = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE clv_pct IS NOT NULL)                          AS clv_total,
            COUNT(*) FILTER (WHERE clv_pct > 0)                                  AS clv_positive,
            COALESCE(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL), 0)         AS avg_clv,
            COUNT(*) FILTER (WHERE mode = 'PROD')                                AS total_prod
        FROM football_opportunities
        WHERE mode = 'PROD'
    """, fetch='one')
    return row or (0, 0, 0.0, 0)


@st.cache_data(ttl=300)
def load_clv_proof_of_edge(days: int = 30):
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT
            clv_pct,
            match_date,
            market,
            league,
            clv_status
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND clv_pct IS NOT NULL
          AND timestamp >= NOW() - (%s || ' days')::INTERVAL
        ORDER BY timestamp DESC
    """, (str(days),), fetch='all')
    return rows or []


@st.cache_data(ttl=300)
def load_clv_coverage():
    db = DatabaseHelper()
    row = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE UPPER(status) = 'SETTLED')          AS total_settled,
            COUNT(*) FILTER (WHERE clv_pct IS NOT NULL
                             AND UPPER(status) = 'SETTLED')             AS clv_covered
        FROM football_opportunities
        WHERE mode = 'PROD'
    """, fetch='one')
    return row or (0, 0)


@st.cache_data(ttl=120)
def load_todays_picks():
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT home_team, away_team, league, market, selection, odds,
               confidence, edge_percentage, status, result, kickoff_time,
               fair_odds, model_prob, best_odds_value, best_odds_bookmaker,
               odds_by_bookmaker
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND match_date = CURRENT_DATE::text
        ORDER BY
            CASE WHEN UPPER(status)='PENDING' THEN 0 ELSE 1 END,
            timestamp DESC
        LIMIT 40
    """, fetch='all')
    return rows or []


@st.cache_data(ttl=120)
def load_market_scanner():
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT home_team, away_team, league, market, selection, odds,
               fair_odds, model_prob, edge_percentage,
               best_odds_value, best_odds_bookmaker, odds_by_bookmaker,
               confidence, status, match_date, kickoff_time
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND match_date = CURRENT_DATE::text
          AND fair_odds IS NOT NULL
          AND fair_odds > 0
        ORDER BY COALESCE(edge_percentage, 0) DESC
        LIMIT 100
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


@st.cache_data(ttl=60)
def load_scan_status():
    """Load the latest scan events from the DB for the status bar."""
    db = DatabaseHelper()
    try:
        rows = db.execute("""
            SELECT scan_type, scanned_at
            FROM scan_events
            WHERE scanned_at >= NOW() - INTERVAL '24 hours'
            ORDER BY scanned_at DESC
            LIMIT 200
        """, fetch='all')
    except Exception:
        return None
    if not rows:
        return None

    now = datetime.utcnow()

    def _latest(scan_types):
        for row in rows:
            if row[0] in scan_types:
                return row[1]
        return None

    def _count_today(scan_types):
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(
            1 for row in rows
            if row[0] in scan_types and row[1] >= today_start
        )

    vs_last = _latest({"value_singles_done", "value_singles_skipped", "value_singles_error"})
    co_last = _latest({"corners_done", "corners_skipped", "corners_error"})
    vs_count = _count_today({"value_singles_done", "value_singles_skipped"})
    co_count = _count_today({"corners_done", "corners_skipped"})

    return {
        "value_singles": {"last": vs_last, "count_today": vs_count, "interval_min": 12},
        "corners": {"last": co_last, "count_today": co_count, "interval_min": 15},
    }


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


def _render_value_explanation(
    match: str,
    market: str,
    book_odds: float,
    fair_odds: float,
    model_prob: float | None,
    edge: float,
    league: str,
    bk_name: str,
):
    market_implied = round((1 / book_odds) * 100, 1) if book_odds else None
    model_prob_pct = round(model_prob * 100, 1) if model_prob and model_prob <= 1 else (round(float(model_prob), 1) if model_prob else None)
    diff = round(model_prob_pct - market_implied, 1) if (model_prob_pct and market_implied) else None

    st.markdown(f"""
**Why this is value**

The {bk_name} odds of **{book_odds:.2f}** imply the market thinks this outcome
has a **{market_implied}%** chance of happening.

Our model puts the real probability at **{model_prob_pct}%**
— a difference of **{f'+{diff}%' if diff and diff > 0 else f'{diff}%' if diff else f'{edge:+.1f}% edge'}**.

That gap is what creates the value: the market is underpricing this outcome
by **{edge:+.1f}%** compared to our fair odds of **{fair_odds:.2f}**.
""")

    c1, c2 = st.columns(2)
    c1.metric("Book Odds", f"{book_odds:.2f}", help="Best available price")
    c2.metric("Model Fair Odds", f"{fair_odds:.2f}",
              delta=f"{edge:+.1f}% edge",
              delta_color="normal")

    st.markdown("""
---
⚠️ **This does not guarantee a win.**
Value means profitable over many bets — not every single game.
No hype, no guarantees. Just data.
""")


# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
wins, settled, profit_units, pending = load_hero_stats()
hit_rate = (wins / settled * 100) if settled > 0 else 0.0
roi = (profit_units / settled * 100) if settled > 0 else 0.0

clv_total, clv_positive, avg_clv, _ = load_clv_hero_stats()
clv_hit_rate = (clv_positive / clv_total * 100) if clv_total > 0 else 0.0
total_settled_hero, clv_covered_hero = load_clv_coverage()

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

c1, c2, c3, c4, c5, c6 = st.columns(6)
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
with c5:
    metric_card(
        "CLV Hit Rate",
        f"{clv_hit_rate:.1f}%" if clv_total > 0 else "—",
        kicker=f"{clv_positive} of {clv_total} picks beat closing line",
        variant="good" if clv_hit_rate >= 50 else ("bad" if clv_total > 0 else "default"),
    )
with c6:
    metric_card(
        "Avg CLV%",
        f"{avg_clv:+.2f}%" if clv_total > 0 else "—",
        kicker="vs closing market price",
        variant="good" if avg_clv >= 0 else ("bad" if clv_total > 0 else "default"),
    )

if clv_total > 0:
    hero_cov_pct = (clv_covered_hero / total_settled_hero * 100) if total_settled_hero > 0 else 0
    hero_cov_color = "#00F59D" if hero_cov_pct >= 50 else "#FBBF24"
    hero_cov_label = "" if hero_cov_pct >= 50 else f' · <span style="color:#FBBF24;font-size:0.78rem;">⚠ Preliminary — CLV coverage below 50%</span>'
    st.markdown(f"""
    <div style="margin:12px 0 4px 0;padding:10px 18px;border-radius:10px;
                background:rgba(0,245,157,0.06);border:1px solid rgba(0,245,157,0.18);
                font-size:0.85rem;color:#9BA0B5;text-align:center;">
        <span style="color:#00F59D;font-weight:600;">{clv_hit_rate:.0f}% of our picks</span>
        got a better price than what the market settled on —
        verified against closing odds from sharp bookmakers.
        <span style="color:{hero_cov_color};font-size:0.78rem;margin-left:8px;">
            CLV coverage: {hero_cov_pct:.0f}%
        </span>
        {hero_cov_label}
    </div>
    """, unsafe_allow_html=True)

st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SCAN STATUS BAR
# ─────────────────────────────────────────────────────────────────────────────
scan_status = load_scan_status()

def _fmt_ago(ts) -> str:
    """Return a human-friendly 'X min ago' string for a timestamp."""
    if ts is None:
        return "never"
    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
        from datetime import timezone
        now_aware = datetime.now(timezone.utc)
        diff = now_aware - ts
    else:
        diff = datetime.utcnow() - ts
    secs = int(diff.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}min ago"
    return f"{secs // 3600}h ago"


def _next_scan_str(last_ts, interval_min: int) -> str:
    """Return how long until the next scheduled scan."""
    if last_ts is None:
        return "soon"
    if hasattr(last_ts, 'tzinfo') and last_ts.tzinfo is not None:
        from datetime import timezone
        now_aware = datetime.now(timezone.utc)
        diff = now_aware - last_ts
    else:
        diff = datetime.utcnow() - last_ts
    elapsed_min = diff.total_seconds() / 60
    remaining_min = interval_min - elapsed_min
    if remaining_min <= 0:
        return "now"
    remaining_sec = int(remaining_min * 60)
    if remaining_sec < 60:
        return f"~{remaining_sec}s"
    return f"~{int(remaining_min)}min"


if scan_status:
    vs = scan_status["value_singles"]
    co = scan_status["corners"]
    vs_ago = _fmt_ago(vs["last"])
    co_ago = _fmt_ago(co["last"])
    vs_next = _next_scan_str(vs["last"], vs["interval_min"])
    co_next = _next_scan_str(co["last"], co["interval_min"])
    st.markdown(f"""
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px 0;align-items:center;">
        <span style="font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;
                     color:#9BA0B5;margin-right:4px;">Scan status</span>
        <span class="stat-pill">
            💰 Value Singles &nbsp;·&nbsp;
            <b>Last:</b>&nbsp;<b style="color:#F2F5F8;">{vs_ago}</b>
            &nbsp;·&nbsp;
            <b>Next:</b>&nbsp;<b style="color:#00F59D;">{vs_next}</b>
            &nbsp;·&nbsp;
            <b>Today:</b>&nbsp;<b style="color:#F2F5F8;">{vs["count_today"]}</b>
        </span>
        <span class="stat-pill">
            🔢 Corners &nbsp;·&nbsp;
            <b>Last:</b>&nbsp;<b style="color:#F2F5F8;">{co_ago}</b>
            &nbsp;·&nbsp;
            <b>Next:</b>&nbsp;<b style="color:#00F59D;">{co_next}</b>
            &nbsp;·&nbsp;
            <b>Today:</b>&nbsp;<b style="color:#F2F5F8;">{co["count_today"]}</b>
        </span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px 0;align-items:center;">
        <span style="font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;
                     color:#9BA0B5;margin-right:4px;">Scan status</span>
        <span class="stat-pill" style="color:#9BA0B5;">Engine starting up — first scan pending</span>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_today, tab_scanner, tab_smart, tab_track, tab_clv = st.tabs([
    "⚡ Today's Picks",
    "🔍 Market Scanner",
    "🧠 Smart Picks",
    "📈 Track Record",
    "🎯 Proof of Edge",
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
        <span class="stat-pill"><b>{len(picks)}</b> av max 10 möjligheter identifierade idag</span>
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
            (home, away, league, market, selection, odds, conf, ev, status, result, ko_time,
             fair_odds, model_prob, best_odds_value, best_odds_bookmaker, odds_by_bookmaker) = pick
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

            fair_html = ""
            edge_html = ""
            edge_val = None
            fo = None
            bk_odds = None
            bk_name = "Best"
            if fair_odds and float(fair_odds) > 0:
                fo = float(fair_odds)
                bk_odds = float(best_odds_value) if best_odds_value else float(odds)
                edge_val = (bk_odds / fo - 1) * 100
                edge_color = "#00F59D" if edge_val >= 10 else ("#FBBF24" if edge_val >= 5 else "#9BA0B5")
                edge_weight = "700" if edge_val >= 5 else "400"
                bk_name = str(best_odds_bookmaker) if best_odds_bookmaker else "Best"
                fair_html = f'<span>Fair <b style="color:#60A5FA;">{fo:.2f}</b></span>'
                edge_html = f'<span>Edge <b style="color:{edge_color};font-weight:{edge_weight};">{edge_val:+.1f}%</b></span>'
                fair_html += f'<span style="font-size:0.72rem;">{bk_name} <b style="color:#F2F5F8;">{bk_odds:.2f}</b></span>'

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
                    {fair_html}
                    {edge_html}
                    <span>{market_clean}</span>
                </div>
            </div>
            """

            col = col_a if i % 2 == 0 else col_b
            with col:
                st.markdown(html, unsafe_allow_html=True)
                if fo is not None and edge_val is not None:
                    with st.expander("🧠 Why is this value?"):
                        _render_value_explanation(
                            match=f"{home} vs {away}",
                            market=market_clean,
                            book_odds=bk_odds,
                            fair_odds=fo,
                            model_prob=float(model_prob) if model_prob else None,
                            edge=edge_val,
                            league=league,
                            bk_name=bk_name,
                        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — MARKET SCANNER
# ─────────────────────────────────────────────────────────────────────────────
with tab_scanner:
    scanner_rows = load_market_scanner()

    st.markdown("""
    <div style="padding:10px 16px;border-radius:10px;
                background:rgba(59,130,246,0.06);
                border:1px solid rgba(59,130,246,0.2);
                margin-bottom:20px;">
        <span style="color:#60A5FA;font-size:0.82rem;font-weight:600;">🔍 Market Scanner</span>
        <span style="color:#9BA0B5;font-size:0.82rem;">
            &nbsp;— All scanned markets today, sorted by edge. Green = edge &gt;10%, grey = &lt;5%.
            Edge = (Best odds / Fair odds − 1) × 100.
        </span>
    </div>
    """, unsafe_allow_html=True)

    if not scanner_rows:
        st.markdown("""
        <div class="empty-state">
            <div class="big">🔍</div>
            <p>No market data with fair odds available yet.<br>
            Markets are scanned as the engine runs throughout the day.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        import json as _json

        rows_with_edge = []
        for r in scanner_rows:
            (s_home, s_away, s_league, s_market, s_selection, s_odds,
             s_fair, s_model_prob, s_edge, s_best_val, s_best_bk,
             s_odds_by_bk, s_conf, s_status, s_match_date, s_ko_time) = r
            try:
                fo = float(s_fair) if s_fair else None
                bk = float(s_best_val) if s_best_val else float(s_odds)
                edge_val = (bk / fo - 1) * 100 if fo and fo > 0 else (float(s_edge) if s_edge else None)
            except Exception:
                edge_val = float(s_edge) if s_edge else None
            rows_with_edge.append((r, edge_val))

        rows_with_edge.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)

        has_edge = [x for x in rows_with_edge if x[1] is not None and x[1] >= 5]
        no_edge = [x for x in rows_with_edge if x[1] is None or x[1] < 5]

        total_scanned = len(rows_with_edge)
        edge_5 = sum(1 for x in rows_with_edge if x[1] is not None and x[1] >= 5)
        edge_10 = sum(1 for x in rows_with_edge if x[1] is not None and x[1] >= 10)

        st.markdown(f"""
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 20px 0;">
            <span class="stat-pill">Scanned <b>{total_scanned}</b></span>
            <span class="stat-pill">Edge ≥5% <b style="color:#FBBF24;">{edge_5}</b></span>
            <span class="stat-pill">Edge ≥10% <b style="color:#00F59D;">{edge_10}</b></span>
        </div>
        """, unsafe_allow_html=True)

        def _scanner_row_html(r, edge_val):
            (s_home, s_away, s_league, s_market, s_selection, s_odds,
             s_fair, s_model_prob, s_edge, s_best_val, s_best_bk,
             s_odds_by_bk, s_conf, s_status, s_match_date, s_ko_time) = r

            fo = float(s_fair) if s_fair else None
            bk_odds = float(s_best_val) if s_best_val else float(s_odds)
            mkt_clean = _clean_market(s_market)

            if edge_val is None or edge_val < 5:
                card_bg = "rgba(15,20,36,0.6)"
                border_color = "rgba(28,32,48,0.7)"
                edge_color = "#9BA0B5"
                edge_weight = "400"
                row_opacity = "opacity:0.65;"
            elif edge_val >= 10:
                card_bg = "rgba(0,245,157,0.05)"
                border_color = "rgba(0,245,157,0.35)"
                edge_color = "#00F59D"
                edge_weight = "700"
                row_opacity = ""
            else:
                card_bg = "rgba(251,191,36,0.04)"
                border_color = "rgba(251,191,36,0.25)"
                edge_color = "#FBBF24"
                edge_weight = "600"
                row_opacity = ""

            fair_str = f"{fo:.2f}" if fo else "—"
            bk_name = str(s_best_bk) if s_best_bk else "Best"
            edge_str = f"{edge_val:+.1f}%" if edge_val is not None else "—"
            prob_str = f"{float(s_model_prob)*100:.1f}%" if s_model_prob else "—"

            bk_breakdown = ""
            spread_html = ""
            if s_odds_by_bk and fo and fo > 0:
                try:
                    bk_data = _json.loads(s_odds_by_bk) if isinstance(s_odds_by_bk, str) else s_odds_by_bk
                    if isinstance(bk_data, dict) and bk_data:
                        items = sorted(bk_data.items(), key=lambda x: float(x[1]) if x[1] else 0, reverse=True)[:5]
                        parts = []
                        edge_vals_bk = []
                        for k, v in items:
                            try:
                                bk_o = float(v)
                                bk_edge = (bk_o / fo - 1) * 100
                                edge_vals_bk.append(bk_edge)
                                ec = "#00F59D" if bk_edge >= 10 else ("#FBBF24" if bk_edge >= 5 else "#9BA0B5")
                                parts.append(
                                    f'<span style="font-size:0.7rem;color:#9BA0B5;">'
                                    f'{k}: <b style="color:#F2F5F8;">{bk_o:.2f}</b>'
                                    f' <b style="color:{ec};">({bk_edge:+.0f}%)</b></span>'
                                )
                            except Exception:
                                pass
                        bk_breakdown = ' &nbsp;'.join(parts)
                        if len(edge_vals_bk) >= 2:
                            spread = max(edge_vals_bk) - min(edge_vals_bk)
                            spread_html = f'<span style="font-size:0.72rem;color:#9BA0B5;">Spread <b style="color:#F2F5F8;">{spread:.1f}pp</b></span>'
                except Exception:
                    pass

            return f"""
            <div style="padding:12px 16px;margin:6px 0;border-radius:12px;
                        background:{card_bg};border:1px solid {border_color};{row_opacity}">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <div style="font-size:0.75rem;color:#9BA0B5;">{s_league} · {mkt_clean}</div>
                    <div style="display:flex;gap:8px;align-items:center;">
                        {spread_html}
                        <b style="color:{edge_color};font-weight:{edge_weight};font-size:0.95rem;">{edge_str}</b>
                    </div>
                </div>
                <div style="font-size:0.95rem;font-weight:600;color:#F2F5F8;">{s_home} vs {s_away}</div>
                <div style="font-size:0.88rem;color:#00F59D;margin:2px 0 6px 0;">{s_selection}</div>
                <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:0.78rem;color:#9BA0B5;align-items:center;">
                    <span>Model odds <b style="color:#F2F5F8;">{float(s_odds):.2f}</b></span>
                    <span>Fair <b style="color:#60A5FA;">{fair_str}</b></span>
                    <span>{bk_name} <b style="color:#F2F5F8;">{bk_odds:.2f}</b></span>
                    <span>Model prob <b style="color:#9BA0B5;">{prob_str}</b></span>
                </div>
                {f'<div style="margin-top:5px;display:flex;gap:8px;flex-wrap:wrap;">{bk_breakdown}</div>' if bk_breakdown else ""}
            </div>
            """

        if has_edge:
            st.markdown("#### Value Markets")
            for row, ev in has_edge:
                st.markdown(_scanner_row_html(row, ev), unsafe_allow_html=True)

        if no_edge:
            with st.expander(f"No significant edge ({len(no_edge)} markets)", expanded=False):
                for row, ev in no_edge:
                    st.markdown(_scanner_row_html(row, ev), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — SMART PICKS
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
# TAB 4 — PROOF OF EDGE (CLV)
# ─────────────────────────────────────────────────────────────────────────────
with tab_clv:
    # ── CLV explanation ──────────────────────────────────────────────────────
    st.markdown("""
    <div style="padding:16px 20px;border-radius:12px;
                background:rgba(0,245,157,0.05);
                border:1px solid rgba(0,245,157,0.2);
                margin-bottom:24px;">
        <div style="font-size:1.05rem;font-weight:700;color:#00F59D;margin-bottom:8px;">
            What is Closing Line Value (CLV)?
        </div>
        <div style="font-size:0.88rem;color:#C4C9DC;line-height:1.65;">
            When you place a bet, the odds you get are compared to the odds right before the match
            starts — the <b style="color:#F2F5F8;">closing line</b>. Sharp bookmakers set extremely
            accurate prices as kick-off approaches, because they've absorbed all public and sharp money.
            <br><br>
            If you consistently get <b style="color:#00F59D;">better odds than the closing price</b>,
            it means the market agreed with you — and priced the bet even lower later.
            That's positive CLV: the clearest, most objective proof that a system finds mispriced markets.
            <br><br>
            <span style="color:#9BA0B5;">
                A sustained CLV of +3–5%+ across a large sample is statistically significant
                evidence of genuine edge — independent of short-term win/loss results.
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── CLV coverage banner ──────────────────────────────────────────────────
    total_settled_cov, clv_covered = load_clv_coverage()
    if total_settled_cov > 0:
        coverage_pct = clv_covered / total_settled_cov * 100
        cov_color = "#00F59D" if coverage_pct >= 50 else "#FBBF24"
        cov_label = "Solid CLV sample" if coverage_pct >= 50 else "Preliminary data — CLV coverage below 50%"
        st.markdown(f"""
        <div style="padding:8px 16px;border-radius:8px;margin-bottom:20px;
                    background:rgba(0,0,0,0.2);border:1px solid #1C2030;
                    display:flex;align-items:center;gap:12px;font-size:0.82rem;">
            <span style="color:{cov_color};font-weight:700;">{coverage_pct:.0f}% CLV coverage</span>
            <span style="color:#9BA0B5;">{clv_covered} of {total_settled_cov} settled picks have closing line data</span>
            <span style="color:{cov_color};font-size:0.75rem;">· {cov_label}</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Period selector ──────────────────────────────────────────────────────
    clv_period = st.radio(
        "CLV period",
        ["30 days", "90 days"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
    )
    clv_days = 30 if clv_period == "30 days" else 90

    clv_rows = load_clv_proof_of_edge(clv_days)

    if not clv_rows:
        st.markdown("""
        <div class="empty-state">
            <div class="big">🎯</div>
            <p>No CLV data yet for this period.<br>
            CLV is captured automatically as matches approach kick-off.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        clv_df = pd.DataFrame(clv_rows, columns=["clv_pct", "match_date", "market", "league", "clv_status"])
        clv_df["clv_pct"] = clv_df["clv_pct"].astype(float)
        clv_df["match_date"] = pd.to_datetime(clv_df["match_date"], errors="coerce")

        total_clv = len(clv_df)
        pos_clv = int((clv_df["clv_pct"] > 0).sum())
        avg_clv_period = float(clv_df["clv_pct"].mean())
        clv_hr_period = pos_clv / total_clv * 100 if total_clv > 0 else 0.0

        # Summary KPIs
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            metric_card("CLV Hit Rate", f"{clv_hr_period:.1f}%",
                        kicker=f"{pos_clv} of {total_clv} beat closing",
                        variant="good" if clv_hr_period >= 50 else "bad")
        with k2:
            metric_card("Avg CLV%", f"{avg_clv_period:+.2f}%",
                        kicker="Mean vs closing line",
                        variant="good" if avg_clv_period >= 0 else "bad")
        with k3:
            best_clv = float(clv_df["clv_pct"].max())
            metric_card("Best CLV", f"{best_clv:+.2f}%",
                        kicker="Top single pick",
                        variant="good")
        with k4:
            metric_card("Picks", str(total_clv),
                        kicker=f"Last {clv_days} days with CLV",
                        variant="default")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        # ── CLV distribution histogram ────────────────────────────────────────
        section_title("CLV Distribution", icon="📊")
        clv_vals = clv_df["clv_pct"].tolist()
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=clv_vals,
            nbinsx=30,
            marker_color=[
                "#00F59D" if v > 0 else "#FF4B6B"
                for v in clv_vals
            ],
            opacity=0.8,
            hovertemplate="CLV: %{x:.1f}%<br>Count: %{y}<extra></extra>",
        ))
        fig_hist.add_vline(x=0, line_dash="dot", line_color="#9BA0B5", line_width=1.5)
        fig_hist.add_vline(x=avg_clv_period, line_dash="dash",
                           line_color="#00F59D", line_width=1.5,
                           annotation_text=f"Avg {avg_clv_period:+.1f}%",
                           annotation_font_color="#00F59D",
                           annotation_position="top right")
        fig_hist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9BA0B5", size=12),
            margin=dict(l=10, r=10, t=20, b=10),
            height=250,
            showlegend=False,
            xaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False,
                       ticksuffix="%", title="CLV%"),
            yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False,
                       title="Picks"),
            bargap=0.05,
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

        # ── CLV trend over time ───────────────────────────────────────────────
        clv_time = clv_df.dropna(subset=["match_date"]).copy()
        if not clv_time.empty:
            st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
            section_title(f"CLV Trend — Last {clv_days} Days", icon="📈")
            clv_daily = (
                clv_time.groupby("match_date")["clv_pct"]
                .mean()
                .reset_index()
                .rename(columns={"clv_pct": "avg_clv"})
                .sort_values("match_date")
            )
            clv_daily["rolling_avg"] = clv_daily["avg_clv"].rolling(window=7, min_periods=1).mean()

            fig_trend = go.Figure()
            bar_clr = ["#00F59D" if v >= 0 else "#FF4B6B" for v in clv_daily["avg_clv"]]
            fig_trend.add_trace(go.Bar(
                x=clv_daily["match_date"],
                y=clv_daily["avg_clv"],
                marker_color=bar_clr,
                opacity=0.5,
                name="Daily avg CLV",
                hovertemplate="%{x|%b %d}<br>%{y:+.2f}%<extra></extra>",
            ))
            fig_trend.add_trace(go.Scatter(
                x=clv_daily["match_date"],
                y=clv_daily["rolling_avg"],
                mode="lines",
                line=dict(color="#00F59D", width=2.5),
                name="7-day rolling avg",
                hovertemplate="%{x|%b %d}<br>Rolling: %{y:+.2f}%<extra></extra>",
            ))
            fig_trend.add_hline(y=0, line_dash="dot", line_color="#1C2030", line_width=1)
            fig_trend.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#9BA0B5", size=12),
                margin=dict(l=10, r=10, t=10, b=10),
                height=240,
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1, font=dict(size=11)),
                xaxis=dict(gridcolor="#1C2030", showgrid=False, zeroline=False),
                yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False,
                           ticksuffix="%"),
            )
            st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

        # ── CLV by market ─────────────────────────────────────────────────────
        st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
        section_title("CLV by Market", icon="🎯")
        mkt_grp = (
            clv_df.groupby("market")["clv_pct"]
            .agg(["mean", "count", lambda x: (x > 0).sum()])
            .reset_index()
        )
        mkt_grp.columns = ["Market", "Avg CLV%", "Picks", "Positive"]
        mkt_grp = mkt_grp[mkt_grp["Picks"] >= 3].sort_values("Avg CLV%", ascending=False)
        mkt_grp["Market"] = mkt_grp["Market"].apply(_clean_market)
        mkt_grp["Hit Rate"] = mkt_grp.apply(
            lambda r: f"{r['Positive']/r['Picks']*100:.0f}%" if r["Picks"] > 0 else "-", axis=1
        )
        mkt_grp["Avg CLV%"] = mkt_grp["Avg CLV%"].apply(lambda x: f"{x:+.2f}%")
        mkt_grp = mkt_grp.drop(columns=["Positive"])
        if not mkt_grp.empty:
            st.dataframe(mkt_grp, use_container_width=True, hide_index=True)
        else:
            st.info("Not enough picks per market yet (minimum 3 required).")

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center;color:#3D4259;font-size:0.75rem;padding:8px 0 24px 0;">
    PGR Sports Analytics · AI-powered picks for recreational players · No staking advice
</div>
""", unsafe_allow_html=True)
