"""
PGR Sports Analytics — Public FOMO dashboard with premium gate.
Free: hero stats, track record, CLV proof, teaser picks.
Premium: full picks, selections, odds, scanner, Smart Value details.
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pgr_theme import inject_pgr_css, PGR_COLORS
from pgr_components import metric_card, section_title
from db_helper import DatabaseHelper

st.set_page_config(
    page_title="PGR Sports Analytics",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_pgr_css()

PREMIUM_CODE  = os.environ.get("PREMIUM_CODE", os.environ.get("ADMIN_PASSWORD", "pgr"))
DISCORD_LINK  = "https://discord.gg/pgrsports"

# ── Extra styles ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* pick cards */
.pick-card {
    padding:18px 20px; margin:8px 0; border-radius:14px;
    border:1px solid rgba(28,32,48,0.9);
    background:radial-gradient(circle at top left,#151a2c 0%,#101320 60%);
    position:relative; overflow:hidden;
}
.pick-card-won   { border-color:rgba(0,245,157,0.35)!important;
                   background:radial-gradient(circle at top left,rgba(0,245,157,0.08) 0%,#101320 60%)!important; }
.pick-card-lost  { border-color:rgba(255,75,107,0.3)!important;
                   background:radial-gradient(circle at top left,rgba(255,75,107,0.06) 0%,#101320 60%)!important; }
.pick-card-pending { border-color:rgba(251,191,36,0.25)!important; }
.pick-match      { font-size:1.05rem;font-weight:600;color:#F2F5F8;margin-bottom:2px; }
.pick-selection  { font-size:1.1rem;font-weight:700;color:#00F59D;margin-bottom:6px; }
.pick-meta       { font-size:0.78rem;color:#9BA0B5;display:flex;gap:14px;flex-wrap:wrap;align-items:center; }

/* badges */
.badge            { display:inline-block;padding:2px 10px;border-radius:999px;
                    font-size:0.72rem;font-weight:600;letter-spacing:0.06em; }
.badge-won        { background:rgba(0,245,157,0.15);color:#00F59D;border:1px solid rgba(0,245,157,0.4); }
.badge-lost       { background:rgba(255,75,107,0.12);color:#FF4B6B;border:1px solid rgba(255,75,107,0.35); }
.badge-pending    { background:rgba(251,191,36,0.1);color:#FBBF24;border:1px solid rgba(251,191,36,0.3); }
.badge-high       { background:rgba(0,245,157,0.1);color:#00F59D;border:1px solid rgba(0,245,157,0.3); }
.badge-medium     { background:rgba(59,130,246,0.1);color:#60A5FA;border:1px solid rgba(59,130,246,0.3); }
.badge-low        { background:rgba(245,158,11,0.1);color:#F59E0B;border:1px solid rgba(245,158,11,0.3); }
.badge-new        { background:rgba(168,85,247,0.18);color:#C084FC;border:1px solid rgba(168,85,247,0.5);
                    animation:pgr-pulse 1.6s ease-in-out infinite; }
@keyframes pgr-pulse {
    0%,100% { box-shadow:0 0 0 0 rgba(168,85,247,0.0); }
    50%      { box-shadow:0 0 6px 2px rgba(168,85,247,0.45); }
}
.pgr-divider { border:none;border-top:1px solid #1C2030;margin:1.2rem 0; }
.stat-pill   { display:inline-flex;align-items:center;gap:6px;padding:5px 14px;
               border-radius:999px;background:rgba(15,23,42,0.8);border:1px solid #1C2030;
               font-size:0.8rem;color:#9BA0B5;margin:3px; }
.stat-pill b { color:#F2F5F8; }
.empty-state { text-align:center;padding:60px 20px;color:#9BA0B5; }
.empty-state .big { font-size:2.5rem; }
.empty-state p { margin-top:8px;font-size:0.9rem; }

/* FOMO lock overlay */
.fomo-card {
    padding:18px 20px;margin:8px 0;border-radius:14px;
    border:1px solid rgba(28,32,48,0.9);
    background:radial-gradient(circle at top left,#151a2c 0%,#101320 60%);
    position:relative;overflow:hidden;
}
.fomo-blur { filter:blur(5px);user-select:none;pointer-events:none; }
.fomo-lock-bar {
    background:linear-gradient(90deg,transparent 0%,#06070A 55%);
    position:absolute;inset:0;
    display:flex;align-items:center;justify-content:flex-end;padding-right:1.2rem;
}
.lock-pill {
    display:inline-flex;align-items:center;gap:6px;
    background:rgba(0,245,157,0.1);border:1px solid rgba(0,245,157,0.4);
    color:#00F59D;border-radius:999px;padding:4px 14px;
    font-size:0.78rem;font-weight:700;
}
.cta-banner {
    background:linear-gradient(135deg,#05100f 0%,#091f1a 100%);
    border:1px solid rgba(0,245,157,0.3);border-radius:14px;
    padding:2rem 2rem;text-align:center;margin:1rem 0;
}
.cta-banner h3 { color:#F2F5F8;font-size:1.4rem;margin:0 0 0.4rem 0; }
.cta-banner p  { color:#9BA0B5;margin:0 0 1.2rem 0;font-size:0.95rem; }
a.pgr-cta {
    display:inline-block;
    background:radial-gradient(circle at top left,#22c55e 0,#00F59D 35%,#059669 90%);
    color:#020617!important;text-decoration:none;
    border-radius:999px;padding:0.6rem 2rem;font-weight:700;font-size:1rem;
    box-shadow:0 12px 35px rgba(34,197,94,0.4);
}

/* pulse dot */
.pulse-dot {
    display:inline-block;width:9px;height:9px;border-radius:50%;
    background:#00F59D;box-shadow:0 0 0 0 rgba(0,245,157,0.7);
    animation:pulseGreen 1.8s infinite;margin-right:5px;vertical-align:middle;
}
@keyframes pulseGreen {
    0%   { box-shadow:0 0 0 0 rgba(0,245,157,0.7); }
    70%  { box-shadow:0 0 0 8px rgba(0,245,157,0); }
    100% { box-shadow:0 0 0 0 rgba(0,245,157,0); }
}
.pgr-hero { padding:2.5rem 0 1.5rem 0;text-align:center; }
.pgr-logo-text { font-size:0.75rem;letter-spacing:0.25em;text-transform:uppercase;color:#9BA0B5;margin-bottom:0.3rem; }
.pgr-hero-title { font-size:2.6rem;font-weight:800;color:#F2F5F8;line-height:1.1; }
.pgr-hero-sub   { font-size:1rem;color:#9BA0B5;margin-top:0.4rem; }
.pgr-hero-accent { color:#00F59D; }
</style>
""", unsafe_allow_html=True)


# ── Premium gate (sidebar) ────────────────────────────────────────────────────
if "is_premium" not in st.session_state:
    st.session_state["is_premium"] = False

with st.sidebar:
    st.markdown("### 🔒 Member Access")
    if st.session_state["is_premium"]:
        st.success("✅ Premium unlocked")
        if st.button("Lock session", use_container_width=True):
            st.session_state["is_premium"] = False
            st.rerun()
    else:
        code_in = st.text_input("Member code", type="password", placeholder="Enter code…")
        if st.button("Unlock", use_container_width=True):
            if code_in.strip() == PREMIUM_CODE.strip():
                st.session_state["is_premium"] = True
                st.rerun()
            else:
                st.error("Invalid code — join Discord to get yours.")
        st.markdown(f'<a href="{DISCORD_LINK}" target="_blank" style="display:block;text-align:center;margin-top:8px;color:#00F59D;font-size:0.85rem;">Get access → Discord</a>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<span style="font-size:0.72rem;color:#334155;">PGR Sports Analytics · 18+ · Gamble responsibly</span>', unsafe_allow_html=True)

is_premium = st.session_state["is_premium"]


# ── DB queries ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_hero_stats():
    db = DatabaseHelper()
    row = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))                       AS wins,
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS'))              AS settled,
            COALESCE(SUM(CASE WHEN UPPER(result) IN ('WON','WIN') THEN (odds-1.0)
                              WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0 ELSE 0 END),0) AS profit_units,
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
            COUNT(*) FILTER (WHERE clv_pct IS NOT NULL
                AND clv_source_book NOT ILIKE '%%api_football%%'
                AND clv_source_book NOT ILIKE '~%%'
                AND clv_source_book NOT ILIKE '%%(line moved%%' AND clv_version = 'v2') AS clv_total,
            COUNT(*) FILTER (WHERE clv_pct > 0
                AND clv_source_book NOT ILIKE '%%api_football%%'
                AND clv_source_book NOT ILIKE '~%%'
                AND clv_source_book NOT ILIKE '%%(line moved%%' AND clv_version = 'v2') AS clv_positive,
            COALESCE(AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL
                AND clv_source_book NOT ILIKE '%%api_football%%'
                AND clv_source_book NOT ILIKE '~%%'
                AND clv_source_book NOT ILIKE '%%(line moved%%' AND clv_version = 'v2'), 0) AS avg_clv,
            COUNT(*) FILTER (WHERE mode = 'PROD')                AS total_prod
        FROM football_opportunities WHERE mode = 'PROD'
    """, fetch='one')
    return row or (0, 0, 0.0, 0)


@st.cache_data(ttl=300)
def load_clv_coverage():
    db = DatabaseHelper()
    row = db.execute("""
        SELECT
            COUNT(*) FILTER (WHERE UPPER(status)='SETTLED')       AS total_settled,
            COUNT(*) FILTER (WHERE clv_pct IS NOT NULL AND UPPER(status)='SETTLED') AS clv_covered
        FROM football_opportunities WHERE mode = 'PROD'
    """, fetch='one')
    return row or (0, 0)


@st.cache_data(ttl=120)
def load_todays_picks():
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT home_team, away_team, league, market, selection, odds,
               confidence, edge_percentage, status, result, kickoff_time,
               fair_odds, model_prob, best_odds_value, best_odds_bookmaker,
               odds_by_bookmaker, timestamp,
               clv_pct, clv_status, disagreement, hidden_value_status, profile_boost_score
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND match_date = CURRENT_DATE::text
        ORDER BY timestamp DESC
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
          AND fair_odds IS NOT NULL AND fair_odds > 0
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
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))             AS wins,
            COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS'))  AS settled,
            COALESCE(SUM(CASE WHEN UPPER(result) IN ('WON','WIN') THEN (odds-1.0)
                              WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0 ELSE 0 END), 0) AS day_units
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND UPPER(status) = 'SETTLED'
          AND TO_TIMESTAMP(timestamp) >= NOW() - INTERVAL '%s days'
        GROUP BY match_date
        ORDER BY match_date
    """ % days, fetch='all')
    return rows or []


@st.cache_data(ttl=60)
def load_scan_status():
    db = DatabaseHelper()
    try:
        rows = db.execute("""
            SELECT scan_type, scanned_at FROM scan_events
            WHERE scanned_at >= NOW() - INTERVAL '24 hours'
            ORDER BY scanned_at DESC LIMIT 200
        """, fetch='all')
    except Exception:
        return None
    if not rows:
        return None
    now = datetime.utcnow()

    def _latest(types):
        for r in rows:
            if r[0] in types:
                return r[1]
        return None

    def _count(types):
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(1 for r in rows if r[0] in types and r[1] >= today)

    return {
        "value_singles": {"last": _latest({"value_singles_done","value_singles_skipped","value_singles_error"}),
                          "count_today": _count({"value_singles_done","value_singles_skipped"}),
                          "interval_min": 12},
        "corners": {"last": _latest({"corners_done","corners_skipped","corners_error"}),
                    "count_today": _count({"corners_done","corners_skipped"}),
                    "interval_min": 15},
    }


@st.cache_data(ttl=300)
def load_all_time_summary():
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT market,
               COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS')) AS settled,
               COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN'))             AS wins,
               COALESCE(SUM(CASE WHEN UPPER(result) IN ('WON','WIN') THEN (odds-1.0)
                                 WHEN UPPER(result) IN ('LOST','LOSS') THEN -1.0 ELSE 0 END), 0) AS units
        FROM football_opportunities
        WHERE mode='PROD' AND UPPER(status)='SETTLED'
        GROUP BY market
        HAVING COUNT(*) FILTER (WHERE UPPER(result) IN ('WON','WIN','LOST','LOSS')) >= 5
        ORDER BY units DESC
    """, fetch='all')
    return rows or []


@st.cache_data(ttl=300)
def load_clv_proof_of_edge(days: int = 30):
    db = DatabaseHelper()
    rows = db.execute("""
        SELECT clv_pct, match_date, market, league, clv_status
        FROM football_opportunities
        WHERE mode='PROD' AND clv_pct IS NOT NULL
          AND timestamp >= NOW() - (%s || ' days')::INTERVAL
        ORDER BY timestamp DESC
    """, (str(days),), fetch='all')
    return rows or []


@st.cache_data(ttl=120)
def load_live_edge_summary():
    db = DatabaseHelper()
    row = db.execute("""
        SELECT
          COUNT(*) FILTER (WHERE mode IN ('PROD','VALUE_OPP') AND status='pending' AND match_date::date >= CURRENT_DATE) AS live_edges,
          COUNT(DISTINCT league) FILTER (WHERE status='pending' AND match_date::date >= CURRENT_DATE) AS leagues,
          (AVG(edge_percentage) FILTER (WHERE mode IN ('PROD','VALUE_OPP') AND status='pending' AND match_date::date >= CURRENT_DATE))::numeric AS avg_edge
        FROM football_opportunities
    """, fetch='one')
    return row or (0, 0, 0)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _clean_market(m: str) -> str:
    label_map = {
        "value single": "Value Single", "corners_over": "Corners Over",
        "corners_under": "Corners Under", "corners_handicap": "Corners Handicap",
        "cards_over": "Cards Over", "cards_under": "Cards Under",
        "btts": "Both Teams Score", "double_chance": "Double Chance",
        "asian_handicap": "Asian Handicap", "over_2.5": "Over 2.5 Goals",
        "under_2.5": "Under 2.5 Goals", "over_3.5": "Over 3.5 Goals", "1x2": "1X2",
    }
    return label_map.get(str(m).lower().strip(), str(m).replace("_", " ").title())


def _clean_confidence(c) -> tuple:
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
    r = str(result).upper() if result else ""
    s = str(status).upper()
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


def _fmt_ago(ts) -> str:
    if ts is None:
        return "never"
    try:
        from datetime import timezone
        diff = (datetime.now(timezone.utc) - ts) if (hasattr(ts, 'tzinfo') and ts.tzinfo) else (datetime.utcnow() - ts)
    except Exception:
        return "—"
    secs = int(diff.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}min ago"
    return f"{secs // 3600}h ago"


def _next_scan_str(last_ts, interval_min: int) -> str:
    if last_ts is None:
        return "soon"
    try:
        from datetime import timezone
        diff = (datetime.now(timezone.utc) - last_ts) if (hasattr(last_ts, 'tzinfo') and last_ts.tzinfo) else (datetime.utcnow() - last_ts)
    except Exception:
        return "—"
    remaining_sec = max(0, int((interval_min * 60) - diff.total_seconds()))
    if remaining_sec < 60:
        return f"~{remaining_sec}s" if remaining_sec > 0 else "now"
    return f"~{remaining_sec // 60}min"


def _cta_banner():
    st.markdown(f"""
    <div class="cta-banner">
        <h3>🔓 Unlock Full Access</h3>
        <p>See exact selections, odds, stakes &amp; real-time edge across 30+ leagues.<br>
           Join the PGR premium community.</p>
        <a class="pgr-cta" href="{DISCORD_LINK}" target="_blank">Join PGR Premium →</a>
    </div>
    """, unsafe_allow_html=True)


def _fomo_pick_card(home, away, league, market, result=None, status=None, i=0):
    """Show match/league but blur selection+odds."""
    badge = _result_badge(status, result)
    card_cls = _pick_card_class(result)
    market_clean = _clean_market(market)
    st.markdown(f"""
    <div class="{card_cls}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
            <span class="badge badge-new" style="font-size:0.68rem;">#{i+1}</span>
            {badge}
        </div>
        <div class="pick-match">{home} vs {away}</div>
        <div class="pick-meta" style="margin-top:4px;">
            <span>{league}</span>
            <span>{market_clean}</span>
        </div>
        <div style="margin-top:10px;display:flex;align-items:center;gap:10px;">
            <span class="fomo-blur" style="font-size:1.1rem;font-weight:700;color:#00F59D;">
                ██████████ @ x.xx
            </span>
            <span class="lock-pill">🔒 Premium</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
wins, settled, profit_units, pending = load_hero_stats()
hit_rate = (wins / settled * 100) if settled > 0 else 0.0
roi      = (profit_units / settled * 100) if settled > 0 else 0.0

clv_total, clv_positive, avg_clv, _ = load_clv_hero_stats()
clv_hit_rate = (clv_positive / clv_total * 100) if clv_total > 0 else 0.0
total_settled_hero, clv_covered_hero = load_clv_coverage()
live_edges_row = load_live_edge_summary()
live_edges = live_edges_row[0] or 0
live_leagues = live_edges_row[1] or 0
avg_edge   = float(live_edges_row[2] or 0)

st.markdown(f"""
<div class="pgr-hero">
    <div class="pgr-logo-text">PGR Sports Analytics</div>
    <div class="pgr-hero-title">
        AI-Powered <span class="pgr-hero-accent">Value Detection</span>
    </div>
    <div class="pgr-hero-sub">
        Real-time edge scanner across 30+ football leagues — no guesswork, pure data.
    </div>
    <div style="margin-top:1rem;font-size:0.9rem;color:#9BA0B5;">
        <span class="pulse-dot"></span>
        <span style="color:#00F59D;font-weight:700;">{live_edges} live value edges</span>
        &nbsp;·&nbsp; {live_leagues} leagues &nbsp;·&nbsp; avg edge {avg_edge:.1f}%
    </div>
</div>
""", unsafe_allow_html=True)

# KPI row — always visible, builds trust
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    metric_card("All-Time ROI", f"{roi:+.1f}%", kicker=f"{settled} settled picks",
                variant="good" if roi >= 0 else "bad")
with c2:
    metric_card("Hit Rate", f"{hit_rate:.1f}%", kicker="Wins / settled",
                variant="good" if hit_rate >= 45 else "bad")
with c3:
    metric_card("Profit", f"{profit_units:+.1f}u", kicker="Flat 1-unit staking",
                variant="good" if profit_units >= 0 else "bad")
with c4:
    metric_card("Live Picks", str(pending), kicker="Active today", variant="default")
with c5:
    metric_card("CLV Hit Rate",
                f"{clv_hit_rate:.1f}%" if clv_total > 0 else "—",
                kicker=f"{clv_positive} of {clv_total} beat closing line",
                variant="good" if clv_hit_rate >= 50 else ("bad" if clv_total > 0 else "default"))
with c6:
    metric_card("Avg CLV%",
                f"{avg_clv:+.2f}%" if clv_total > 0 else "—",
                kicker="vs closing market price",
                variant="good" if avg_clv >= 0 else ("bad" if clv_total > 0 else "default"))

if clv_total > 0:
    hero_cov_pct   = (clv_covered_hero / total_settled_hero * 100) if total_settled_hero > 0 else 0
    hero_cov_color = "#00F59D" if hero_cov_pct >= 50 else "#FBBF24"
    note = "" if hero_cov_pct >= 50 else ' · <span style="color:#FBBF24;font-size:0.78rem;">⚠ Preliminary — CLV coverage below 50%</span>'
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
        {note}
    </div>
    """, unsafe_allow_html=True)

st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)

# ── Scan status bar ───────────────────────────────────────────────────────────
scan_status = load_scan_status()
if scan_status:
    vs = scan_status["value_singles"]
    co = scan_status["corners"]
    st.markdown(f"""
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px 0;align-items:center;">
        <span style="font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;color:#9BA0B5;margin-right:4px;">Scan status</span>
        <span class="stat-pill">
            💰 Value Singles &nbsp;·&nbsp; <b>Last:</b>&nbsp;<b style="color:#F2F5F8;">{_fmt_ago(vs["last"])}</b>
            &nbsp;·&nbsp; <b>Next:</b>&nbsp;<b style="color:#00F59D;">{_next_scan_str(vs["last"],vs["interval_min"])}</b>
            &nbsp;·&nbsp; <b>Today:</b>&nbsp;<b style="color:#F2F5F8;">{vs["count_today"]}</b>
        </span>
        <span class="stat-pill">
            🔢 Corners &nbsp;·&nbsp; <b>Last:</b>&nbsp;<b style="color:#F2F5F8;">{_fmt_ago(co["last"])}</b>
            &nbsp;·&nbsp; <b>Next:</b>&nbsp;<b style="color:#00F59D;">{_next_scan_str(co["last"],co["interval_min"])}</b>
            &nbsp;·&nbsp; <b>Today:</b>&nbsp;<b style="color:#F2F5F8;">{co["count_today"]}</b>
        </span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px 0;align-items:center;">
        <span style="font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;color:#9BA0B5;margin-right:4px;">Scan status</span>
        <span class="stat-pill" style="color:#9BA0B5;">Engine starting — first scan pending</span>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_today, tab_smart, tab_scanner, tab_track, tab_clv, tab_bt = st.tabs([
    "⚡ Today's Picks",
    "🧠 Smart Value",
    "🔍 Market Scanner",
    "📈 Track Record",
    "🎯 Proof of Edge",
    "🔬 Backtest",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — TODAY'S PICKS
# ─────────────────────────────────────────────────────────────────────────────
with tab_today:
    picks = load_todays_picks()

    today_wins     = sum(1 for p in picks if str(p[9] or "").upper() == "WON")
    today_losses   = sum(1 for p in picks if str(p[9] or "").upper() == "LOST")
    today_pend     = sum(1 for p in picks if str(p[8] or "").upper() == "PENDING")
    today_settled  = today_wins + today_losses
    today_hr       = (today_wins / today_settled * 100) if today_settled > 0 else 0.0

    st.markdown(f"""
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px;">
        <span class="stat-pill"><b style="color:#00F59D;">{today_wins}</b>&nbsp;won today</span>
        <span class="stat-pill"><b style="color:#FF4B6B;">{today_losses}</b>&nbsp;lost</span>
        <span class="stat-pill"><b style="color:#FBBF24;">{today_pend}</b>&nbsp;pending</span>
        {'<span class="stat-pill"><b>Hit rate: ' + f'{today_hr:.0f}%</b></span>' if today_settled > 0 else ''}
    </div>
    """, unsafe_allow_html=True)

    if not picks:
        st.markdown("""
        <div class="empty-state">
            <div class="big">⚡</div>
            <p>No picks generated yet today.<br>Engine scans every 12 minutes — check back soon.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        if is_premium:
            # ── PREMIUM: full picks ──────────────────────────────────────────
            col_a, col_b = st.columns(2)
            for i, p in enumerate(picks):
                home, away, league, market, selection, odds = p[0],p[1],p[2],p[3],p[4],p[5]
                conf, edge, status, result, ko = p[6],p[7],p[8],p[9],p[10]
                fair_odds, model_prob = p[11],p[12]
                conf_lbl, conf_cls = _clean_confidence(conf)
                badge = _result_badge(status, result)
                card_cls = _pick_card_class(result)
                market_clean = _clean_market(market)
                edge_str = f"+{edge:.1f}%" if edge else "—"
                ko_str = str(ko)[:5] if ko else "—"
                fair_str = f"{float(fair_odds):.2f}" if fair_odds else "—"
                model_str = f"{float(model_prob)*100:.0f}%" if model_prob and float(model_prob) <= 1 else (f"{float(model_prob):.0f}%" if model_prob else "—")
                html = f"""
                <div class="{card_cls}">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                        <span style="font-size:0.78rem;color:#9BA0B5;">{league}</span>
                        {badge}
                    </div>
                    <div class="pick-match">{home} vs {away}</div>
                    <div class="pick-selection">{selection}</div>
                    <div class="pick-meta">
                        <span>Odds <b style="color:#F2F5F8;">{float(odds):.2f}</b></span>
                        <span>{market_clean}</span>
                        <span>KO {ko_str}</span>
                        <span class="badge badge-{'high' if conf_cls=='high' else ('medium' if conf_cls=='medium' else 'low')}">{conf_lbl}</span>
                    </div>
                    <div class="pick-meta" style="margin-top:6px;">
                        <span>Edge <b style="color:#00F59D;">{edge_str}</b></span>
                        <span>Fair <b style="color:#F2F5F8;">{fair_str}</b></span>
                        <span>Model <b style="color:#F2F5F8;">{model_str}</b></span>
                    </div>
                </div>"""
                if i % 2 == 0:
                    col_a.markdown(html, unsafe_allow_html=True)
                else:
                    col_b.markdown(html, unsafe_allow_html=True)
        else:
            # ── FREE: FOMO picks ─────────────────────────────────────────────
            PREVIEW_FREE = 2
            col_a, col_b = st.columns(2)
            for i, p in enumerate(picks):
                home, away, league, market, status, result = p[0],p[1],p[2],p[3],p[8],p[9]
                if i % 2 == 0:
                    with col_a:
                        _fomo_pick_card(home, away, league, market, result, status, i)
                else:
                    with col_b:
                        _fomo_pick_card(home, away, league, market, result, status, i)
                if i >= PREVIEW_FREE - 1:
                    break

            remaining = len(picks) - PREVIEW_FREE
            if remaining > 0:
                st.markdown(f"""
                <div style="margin:8px 0;padding:14px 20px;border-radius:10px;
                            border:1px solid #1C2030;background:#101320;
                            text-align:center;color:#9BA0B5;font-size:0.88rem;">
                    🔒 &nbsp; <b style="color:#F2F5F8;">{remaining} more picks</b> available today — selection &amp; odds visible for members only
                </div>
                """, unsafe_allow_html=True)

            _cta_banner()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — SMART PICKS
# ─────────────────────────────────────────────────────────────────────────────
with tab_smart:
    smart = load_smart_picks()

    st.markdown("""
    <div style="padding:14px 20px;border-radius:12px;background:rgba(0,245,157,0.05);
                border:1px solid rgba(0,245,157,0.2);margin-bottom:20px;">
        <div style="font-size:1rem;font-weight:700;color:#00F59D;margin-bottom:6px;">
            🧠 Smart Value — AI Curated
        </div>
        <div style="font-size:0.85rem;color:#C4C9DC;line-height:1.6;">
            One best pick per match, ranked by SmartScore (model confidence × CLV × form).
            These are the highest-conviction opportunities from today's scan.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not smart:
        st.markdown("""
        <div class="empty-state">
            <div class="big">🧠</div>
            <p>Smart Value for today not yet generated.<br>They're published once daily around 09:00 UTC.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        col_a, col_b = st.columns(2)
        for i, row in enumerate(smart):
            home, away, league, market, selection, odds = row[0],row[1],row[2],row[3],row[4],row[5]
            smart_score, confidence, grade = float(row[6] or 0), row[7], row[8]
            conf_icon = "🟢" if confidence == "Strong" else ("🟡" if confidence == "Medium" else "🔴")
            score_color = "#00F59D" if smart_score >= 80 else ("#FBBF24" if smart_score >= 65 else "#9BA0B5")

            if is_premium:
                html = f"""
                <div class="pick-card pick-card-pending">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                        <span style="font-size:0.78rem;color:#9BA0B5;">{league}</span>
                        <span style="font-size:0.82rem;font-weight:700;color:{score_color};">
                            SmartScore {smart_score:.1f} · {grade}
                        </span>
                    </div>
                    <div class="pick-match">{home} vs {away}</div>
                    <div class="pick-selection">{selection}</div>
                    <div class="pick-meta">
                        <span>Odds <b style="color:#F2F5F8;">{float(odds):.2f}</b></span>
                        <span>{_clean_market(market)}</span>
                        <span>{conf_icon} {confidence}</span>
                    </div>
                </div>"""
            else:
                blur_part = '<span class="fomo-blur" style="font-size:1.05rem;font-weight:700;color:#00F59D;">██████ @ x.xx</span>'
                show_full = i < 2
                if show_full:
                    html = f"""
                    <div class="pick-card pick-card-pending">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                            <span style="font-size:0.78rem;color:#9BA0B5;">{league}</span>
                            <span style="font-size:0.82rem;font-weight:700;color:{score_color};">
                                SmartScore {smart_score:.1f}
                            </span>
                        </div>
                        <div class="pick-match">{home} vs {away}</div>
                        <div class="pick-meta" style="margin-top:4px;">
                            <span>{_clean_market(market)}</span>
                            <span>{conf_icon} {confidence}</span>
                        </div>
                        <div style="margin-top:10px;display:flex;align-items:center;gap:10px;">
                            {blur_part}
                            <span class="lock-pill">🔒 Premium</span>
                        </div>
                    </div>"""
                else:
                    html = f"""
                    <div class="fomo-card">
                        <span style="font-size:0.78rem;color:#9BA0B5;">{league} · SmartScore {smart_score:.1f}</span>
                        <div style="margin-top:6px;display:flex;align-items:center;gap:10px;">
                            {blur_part}
                            <span class="lock-pill">🔒 Premium</span>
                        </div>
                    </div>"""

            if i % 2 == 0:
                col_a.markdown(html, unsafe_allow_html=True)
            else:
                col_b.markdown(html, unsafe_allow_html=True)

        if not is_premium:
            _cta_banner()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — MARKET SCANNER
# ─────────────────────────────────────────────────────────────────────────────
with tab_scanner:
    scanner_rows = load_market_scanner()

    if not is_premium:
        # FOMO: show summary + teaser table with blurred details
        league_counts = {}
        for r in scanner_rows:
            lg = r[2]
            league_counts[lg] = league_counts.get(lg, 0) + 1

        st.markdown(f"""
        <div style="padding:20px;border-radius:12px;border:1px solid rgba(0,245,157,0.2);
                    background:rgba(0,245,157,0.04);margin-bottom:20px;text-align:center;">
            <div style="font-size:2rem;font-weight:800;color:#00F59D;">{len(scanner_rows)}</div>
            <div style="font-size:0.9rem;color:#9BA0B5;margin-top:4px;">
                value edges detected today across <b style="color:#F2F5F8;">{len(league_counts)} leagues</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Teaser: league list with edge, but details blurred
        section_title("Top Leagues by Edge Count", "🔍")
        for lg, cnt in sorted(league_counts.items(), key=lambda x: -x[1])[:8]:
            st.markdown(f"""
            <div class="fomo-card" style="margin-bottom:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <span style="color:#F2F5F8;font-weight:600;">{lg}</span>
                        <span style="color:#9BA0B5;font-size:0.82rem;margin-left:8px;">{cnt} edge{'s' if cnt > 1 else ''}</span>
                    </div>
                    <span class="lock-pill">🔒 Selection &amp; odds: Premium</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        _cta_banner()
    else:
        # ── PREMIUM: full scanner table ──────────────────────────────────────
        if not scanner_rows:
            st.markdown("""
            <div class="empty-state">
                <div class="big">🔍</div>
                <p>No scanner results yet today. Engine runs every 12 minutes.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            df = pd.DataFrame(scanner_rows, columns=[
                "Home", "Away", "League", "Market", "Selection", "Odds",
                "Fair Odds", "Model Prob", "Edge %",
                "Best Odds", "Best Book", "Odds by Book",
                "Confidence", "Status", "Date", "KO"
            ])
            df["Market"] = df["Market"].apply(_clean_market)
            df["Edge %"] = df["Edge %"].apply(lambda x: f"+{x:.1f}%" if x else "—")
            df["Odds"] = df["Odds"].apply(lambda x: f"{float(x):.2f}" if x else "—")
            df["Fair Odds"] = df["Fair Odds"].apply(lambda x: f"{float(x):.2f}" if x else "—")
            df["Model Prob"] = df["Model Prob"].apply(
                lambda x: f"{float(x)*100:.0f}%" if x and float(x) <= 1 else (f"{float(x):.0f}%" if x else "—"))
            display_cols = ["League", "Home", "Away", "Market", "Selection", "Odds", "Fair Odds", "Edge %", "Model Prob", "KO"]
            section_title(f"Market Scanner — {len(df)} edges today", "🔍")
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — TRACK RECORD  (always visible — best conversion tool)
# ─────────────────────────────────────────────────────────────────────────────
with tab_track:
    period = st.radio("Period", ["7 days", "30 days", "90 days"],
                      index=1, horizontal=True, label_visibility="collapsed")
    days = {"7 days": 7, "30 days": 30, "90 days": 90}[period]
    perf = load_performance(days)

    if not perf:
        st.markdown("""
        <div class="empty-state">
            <div class="big">📈</div>
            <p>Not enough settled picks yet to show performance.<br>Check back as results come in.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        df = pd.DataFrame(perf, columns=["date", "wins", "settled", "day_units"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df["cumulative_units"] = df["day_units"].cumsum()
        df["hit_rate"] = df.apply(lambda r: (r["wins"] / r["settled"] * 100) if r["settled"] > 0 else None, axis=1)

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
            metric_card("Picks", str(total_settled), kicker="Settled this period", variant="default")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["cumulative_units"],
            mode="lines", fill="tozeroy",
            line=dict(color="#00F59D", width=2.5),
            fillcolor="rgba(0,245,157,0.08)",
            hovertemplate="%{x|%b %d}<br>%{y:+.2f} units<extra></extra>",
        ))
        fig.add_hline(y=0, line_dash="dot", line_color="#1C2030", line_width=1)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9BA0B5", size=12),
            margin=dict(l=10, r=10, t=10, b=10), height=280,
            showlegend=False,
            xaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False),
            yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False, ticksuffix="u"),
        )
        section_title("Equity Curve", "📈")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        bar_colors = ["#00F59D" if v >= 0 else "#FF4B6B" for v in df["day_units"]]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df["date"], y=df["day_units"],
            marker_color=bar_colors,
            hovertemplate="%{x|%b %d}<br>%{y:+.2f}u<extra></extra>",
        ))
        fig2.add_hline(y=0, line_color="#1C2030", line_width=1)
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9BA0B5", size=12),
            margin=dict(l=10, r=10, t=10, b=10), height=200,
            showlegend=False,
            xaxis=dict(gridcolor="#1C2030", showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False, ticksuffix="u"),
        )
        section_title("Daily Units", "📊")
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

        market_data = load_all_time_summary()
        if market_data:
            st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
            section_title("Performance by Market", "🎯")
            mdf = pd.DataFrame(market_data, columns=["Market", "Picks", "Wins", "Units"])
            mdf["Market"] = mdf["Market"].apply(_clean_market)
            mdf["Hit Rate"] = mdf.apply(lambda r: f"{r['Wins']/r['Picks']*100:.0f}%" if r["Picks"] > 0 else "-", axis=1)
            mdf["Units"] = mdf["Units"].apply(lambda x: f"{x:+.1f}u")
            st.dataframe(mdf.drop(columns=["Wins"]), use_container_width=True, hide_index=True)

        if not is_premium:
            st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
            _cta_banner()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — PROOF OF EDGE / CLV  (always visible — transparency = trust)
# ─────────────────────────────────────────────────────────────────────────────
with tab_clv:
    st.markdown("""
    <div style="padding:16px 20px;border-radius:12px;background:rgba(0,245,157,0.05);
                border:1px solid rgba(0,245,157,0.2);margin-bottom:24px;">
        <div style="font-size:1.05rem;font-weight:700;color:#00F59D;margin-bottom:8px;">
            What is Closing Line Value (CLV)?
        </div>
        <div style="font-size:0.88rem;color:#C4C9DC;line-height:1.65;">
            When you place a bet, the odds you get are compared to the odds right before the match starts —
            the <b style="color:#F2F5F8;">closing line</b>. Sharp bookmakers set extremely accurate prices
            as kick-off approaches, absorbing all sharp money.
            <br><br>
            If you consistently get <b style="color:#00F59D;">better odds than the closing price</b>, the market
            agreed with you. That's positive CLV — the clearest, most objective proof a system finds mispriced markets.
            <br><br>
            <span style="color:#9BA0B5;">
                A sustained CLV of +3–5%+ across a large sample is statistically significant evidence of
                genuine edge — independent of short-term win/loss results.
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    total_settled_cov, clv_covered = load_clv_coverage()
    if total_settled_cov > 0:
        coverage_pct = clv_covered / total_settled_cov * 100
        cov_color = "#00F59D" if coverage_pct >= 50 else "#FBBF24"
        cov_label = "Solid CLV sample" if coverage_pct >= 50 else "Preliminary — coverage below 50%"
        st.markdown(f"""
        <div style="padding:8px 16px;border-radius:8px;margin-bottom:20px;
                    background:rgba(0,0,0,0.2);border:1px solid #1C2030;
                    display:flex;align-items:center;gap:12px;font-size:0.82rem;">
            <span style="color:{cov_color};font-weight:700;">{coverage_pct:.0f}% CLV coverage</span>
            <span style="color:#9BA0B5;">{clv_covered} of {total_settled_cov} settled picks have closing line data</span>
            <span style="color:{cov_color};font-size:0.75rem;">· {cov_label}</span>
        </div>
        """, unsafe_allow_html=True)

    clv_period = st.radio("CLV period", ["30 days", "90 days"],
                          index=0, horizontal=True, label_visibility="collapsed")
    clv_days = 30 if clv_period == "30 days" else 90
    clv_rows = load_clv_proof_of_edge(clv_days)

    if not clv_rows:
        st.markdown("""
        <div class="empty-state">
            <div class="big">🎯</div>
            <p>No CLV data yet for this period.<br>CLV is captured automatically as matches approach kick-off.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        clv_df = pd.DataFrame(clv_rows, columns=["clv_pct","match_date","market","league","clv_status"])
        clv_df["clv_pct"] = clv_df["clv_pct"].astype(float)
        clv_df["match_date"] = pd.to_datetime(clv_df["match_date"], errors="coerce")

        total_clv    = len(clv_df)
        pos_clv      = int((clv_df["clv_pct"] > 0).sum())
        avg_clv_p    = float(clv_df["clv_pct"].mean())
        clv_hr_p     = pos_clv / total_clv * 100 if total_clv > 0 else 0.0

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            metric_card("CLV Hit Rate", f"{clv_hr_p:.1f}%", kicker=f"{pos_clv} of {total_clv} beat closing",
                        variant="good" if clv_hr_p >= 50 else "bad")
        with k2:
            metric_card("Avg CLV%", f"{avg_clv_p:+.2f}%", kicker="Mean vs closing line",
                        variant="good" if avg_clv_p >= 0 else "bad")
        with k3:
            best_clv = float(clv_df["clv_pct"].max())
            metric_card("Best CLV", f"{best_clv:+.2f}%", kicker="Top single pick", variant="good")
        with k4:
            metric_card("Picks", str(total_clv), kicker=f"Last {clv_days} days with CLV", variant="default")

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        clv_vals = clv_df["clv_pct"].tolist()
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=clv_vals, nbinsx=30,
            marker_color=["#00F59D" if v > 0 else "#FF4B6B" for v in clv_vals],
            opacity=0.8,
            hovertemplate="CLV: %{x:.1f}%<br>Count: %{y}<extra></extra>",
        ))
        fig_hist.add_vline(x=0, line_dash="dot", line_color="#9BA0B5", line_width=1.5)
        fig_hist.add_vline(x=avg_clv_p, line_dash="dash", line_color="#00F59D", line_width=1.5,
                           annotation_text=f"Avg {avg_clv_p:+.1f}%",
                           annotation_font_color="#00F59D", annotation_position="top right")
        fig_hist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#9BA0B5", size=12),
            margin=dict(l=10, r=10, t=20, b=10), height=250, showlegend=False,
            xaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False, ticksuffix="%", title="CLV%"),
            yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False, title="Picks"),
            bargap=0.05,
        )
        section_title("CLV Distribution", "📊")
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

        clv_time = clv_df.dropna(subset=["match_date"]).copy()
        if not clv_time.empty:
            st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
            section_title(f"CLV Trend — Last {clv_days} Days", "📈")
            clv_daily = (
                clv_time.groupby("match_date")["clv_pct"]
                .mean().reset_index().rename(columns={"clv_pct":"avg_clv"})
                .sort_values("match_date")
            )
            clv_daily["rolling_avg"] = clv_daily["avg_clv"].rolling(window=7, min_periods=1).mean()
            fig_trend = go.Figure()
            bar_clr = ["#00F59D" if v >= 0 else "#FF4B6B" for v in clv_daily["avg_clv"]]
            fig_trend.add_trace(go.Bar(
                x=clv_daily["match_date"], y=clv_daily["avg_clv"],
                marker_color=bar_clr, opacity=0.5, name="Daily avg CLV",
                hovertemplate="%{x|%b %d}<br>%{y:+.2f}%<extra></extra>",
            ))
            fig_trend.add_trace(go.Scatter(
                x=clv_daily["match_date"], y=clv_daily["rolling_avg"],
                mode="lines", line=dict(color="#00F59D", width=2.5), name="7-day rolling avg",
                hovertemplate="%{x|%b %d}<br>Rolling: %{y:+.2f}%<extra></extra>",
            ))
            fig_trend.add_hline(y=0, line_dash="dot", line_color="#1C2030", line_width=1)
            fig_trend.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#9BA0B5", size=12),
                margin=dict(l=10, r=10, t=10, b=10), height=240,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
                xaxis=dict(gridcolor="#1C2030", showgrid=False, zeroline=False),
                yaxis=dict(gridcolor="#1C2030", showgrid=True, zeroline=False, ticksuffix="%"),
            )
            st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
        section_title("CLV by Market", "🎯")
        mkt_grp = (
            clv_df.groupby("market")["clv_pct"]
            .agg(["mean", "count", lambda x: (x > 0).sum()])
            .reset_index()
        )
        mkt_grp.columns = ["Market", "Avg CLV%", "Picks", "Positive"]
        mkt_grp = mkt_grp[mkt_grp["Picks"] >= 3].sort_values("Avg CLV%", ascending=False)
        mkt_grp["Market"]   = mkt_grp["Market"].apply(_clean_market)
        mkt_grp["Hit Rate"] = mkt_grp.apply(lambda r: f"{r['Positive']/r['Picks']*100:.0f}%" if r["Picks"] > 0 else "-", axis=1)
        mkt_grp["Avg CLV%"] = mkt_grp["Avg CLV%"].apply(lambda x: f"{x:+.2f}%")
        if not mkt_grp.empty:
            st.dataframe(mkt_grp.drop(columns=["Positive"]), use_container_width=True, hide_index=True)

        if not is_premium:
            st.markdown('<hr class="pgr-divider">', unsafe_allow_html=True)
            _cta_banner()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — BACKTEST
# ─────────────────────────────────────────────────────────────────────────────
with tab_bt:
    st.markdown("### 🔬 Backtest — Settled Picks Only")
    st.caption("Rent historiskt backtest. 1u flat staking på varje pick. Enbart outcome=won/lost, mode=PROD eller VALUE_OPP. Inga live-picks inblandade.")

    @st.cache_data(ttl=300)
    def load_backtest_data():
        db = DatabaseHelper()
        rows = db.execute("""
            SELECT
                market, league, odds, outcome,
                CASE
                    WHEN odds BETWEEN 1.50 AND 1.69 THEN '1.50\u20131.69'
                    WHEN odds BETWEEN 1.70 AND 1.89 THEN '1.70\u20131.89'
                    WHEN odds BETWEEN 1.90 AND 2.09 THEN '1.90\u20132.09'
                    WHEN odds BETWEEN 2.10 AND 2.49 THEN '2.10\u20132.49'
                    WHEN odds >= 2.50              THEN '2.50+'
                    ELSE '<1.50'
                END as odds_range,
                match_date, mode
            FROM football_opportunities
            WHERE outcome IN ('won','lost')
              AND mode IN ('PROD','VALUE_OPP')
              AND odds > 1.0
              AND market != 'exact_score'
            ORDER BY id ASC
        """, fetch='all') or []
        cols = ["market","league","odds","outcome","odds_range","match_date","mode"]
        df = pd.DataFrame(rows, columns=cols)
        df["odds"] = pd.to_numeric(df["odds"], errors="coerce")
        df["profit"] = df.apply(lambda r: (r["odds"] - 1) if r["outcome"] == "won" else -1.0, axis=1)
        df["win"] = (df["outcome"] == "won").astype(int)
        return df

    bt = load_backtest_data()

    if bt.empty:
        st.info("No settled picks found yet.")
    else:
        # ── Metric helpers ─────────────────────────────────────────────────────
        def bt_stats(df):
            n = len(df)
            if n == 0:
                return {"N": 0, "W": 0, "L": 0, "HR%": 0.0, "Profit": 0.0, "ROI%": 0.0, "AvgOdds": 0.0}
            w = df["win"].sum()
            profit = df["profit"].sum()
            return {
                "N": n,
                "W": int(w),
                "L": int(n - w),
                "HR%": round(100 * w / n, 1),
                "Profit": round(profit, 2),
                "ROI%": round(100 * profit / n, 2),
                "AvgOdds": round(df["odds"].mean(), 2),
            }

        # ── 1. BASELINE ────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 1️⃣ Baseline — All Picks, 1u Flat")
        b = bt_stats(bt)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total Picks", f"{b['N']:,}")
        c2.metric("Wins", f"{b['W']:,}")
        c3.metric("Losses", f"{b['L']:,}")
        c4.metric("Hit Rate", f"{b['HR%']}%")
        c5.metric("Profit (units)", f"{b['Profit']:+.1f}u",
                  delta=f"ROI {b['ROI%']:+.1f}%")
        c6.metric("Avg Odds", f"{b['AvgOdds']:.2f}")

        # ── 2. BY MARKET ───────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 2️⃣ Segmenterat per Marknad")
        mkt_rows = []
        for mkt, grp in bt.groupby("market"):
            s = bt_stats(grp)
            mkt_rows.append({"Market": mkt, **s})
        mdf = pd.DataFrame(mkt_rows).sort_values("Profit", ascending=False)

        col_l, col_r = st.columns([1.2, 1.8])
        with col_l:
            def _color_profit(v):
                color = "#00F59D" if v > 0 else "#FF4B6B" if v < 0 else "#9BA0B5"
                return f"color:{color};font-weight:700"
            def _color_roi(v):
                c = "#00F59D" if v > 0 else "#FF4B6B" if v < 0 else "#9BA0B5"
                return f"color:{c}"
            styled = mdf[["Market","N","W","L","HR%","Profit","ROI%","AvgOdds"]].style\
                .applymap(_color_profit, subset=["Profit"])\
                .applymap(_color_roi, subset=["ROI%"])\
                .format({"HR%":"{:.1f}%","Profit":"{:+.1f}u","ROI%":"{:+.1f}%","AvgOdds":"{:.2f}"})
            st.dataframe(styled, use_container_width=True, hide_index=True)
        with col_r:
            fig_mkt = go.Figure()
            colors_mkt = ["#00F59D" if v > 0 else "#FF4B6B" for v in mdf["Profit"]]
            fig_mkt.add_trace(go.Bar(
                x=mdf["Market"], y=mdf["Profit"],
                marker_color=colors_mkt,
                text=[f"{v:+.1f}u" for v in mdf["Profit"]],
                textposition="outside",
            ))
            fig_mkt.update_layout(
                plot_bgcolor="#0D1117", paper_bgcolor="#0D1117",
                font=dict(color="#9BA0B5", size=12),
                yaxis=dict(gridcolor="#1C2030", zeroline=True, zerolinecolor="#334155"),
                xaxis=dict(gridcolor="#1C2030"),
                margin=dict(t=20, b=10, l=10, r=10),
                height=300,
            )
            st.plotly_chart(fig_mkt, use_container_width=True)

        # ── 3. BY ODDS RANGE ───────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 3️⃣ Segmenterat per Oddsintervall")
        ODDS_ORDER = ["<1.50","1.50–1.69","1.70–1.89","1.90–2.09","2.10–2.49","2.50+"]
        odds_rows = []
        for rng in ODDS_ORDER:
            grp = bt[bt["odds_range"] == rng]
            if grp.empty:
                continue
            s = bt_stats(grp)
            odds_rows.append({"Odds Range": rng, **s})
        odf = pd.DataFrame(odds_rows)

        col_l2, col_r2 = st.columns([1.2, 1.8])
        with col_l2:
            styled_o = odf[["Odds Range","N","W","L","HR%","Profit","ROI%","AvgOdds"]].style\
                .applymap(_color_profit, subset=["Profit"])\
                .applymap(_color_roi, subset=["ROI%"])\
                .format({"HR%":"{:.1f}%","Profit":"{:+.1f}u","ROI%":"{:+.1f}%","AvgOdds":"{:.2f}"})
            st.dataframe(styled_o, use_container_width=True, hide_index=True)
        with col_r2:
            bar_colors_o = ["#00F59D" if v > 0 else "#FF4B6B" for v in odf["Profit"]]
            fig_odds = go.Figure()
            fig_odds.add_trace(go.Bar(
                x=odf["Odds Range"], y=odf["Profit"],
                marker_color=bar_colors_o,
                text=[f"{v:+.1f}u" for v in odf["Profit"]],
                textposition="outside",
            ))
            fig_odds.add_trace(go.Scatter(
                x=odf["Odds Range"], y=odf["HR%"],
                mode="lines+markers+text",
                name="Hit Rate %",
                yaxis="y2",
                line=dict(color="#FBBF24", width=2),
                marker=dict(size=6),
                text=[f"{v:.0f}%" for v in odf["HR%"]],
                textposition="top center",
                textfont=dict(color="#FBBF24", size=10),
            ))
            fig_odds.update_layout(
                plot_bgcolor="#0D1117", paper_bgcolor="#0D1117",
                font=dict(color="#9BA0B5", size=12),
                yaxis=dict(gridcolor="#1C2030", zeroline=True, zerolinecolor="#334155", title="Profit (units)"),
                yaxis2=dict(overlaying="y", side="right", title="Hit Rate %",
                            showgrid=False, range=[0, 100]),
                xaxis=dict(gridcolor="#1C2030"),
                margin=dict(t=20, b=10, l=10, r=40),
                height=310,
                legend=dict(x=0.01, y=0.99, bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_odds, use_container_width=True)

        # ── 4. BY LEAGUE ───────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 4️⃣ Segmenterat per Liga (min 10 picks)")
        lgt_rows = []
        for lge, grp in bt.groupby("league"):
            s = bt_stats(grp)
            if s["N"] < 10:
                continue
            lgt_rows.append({"League": lge, **s})
        ldf = pd.DataFrame(lgt_rows).sort_values("Profit", ascending=False)

        top_n = st.slider("Visa antal ligor", min_value=10, max_value=len(ldf), value=min(25, len(ldf)))
        ldf_show = ldf.head(top_n)

        styled_l = ldf_show[["League","N","W","L","HR%","Profit","ROI%","AvgOdds"]].style\
            .applymap(_color_profit, subset=["Profit"])\
            .applymap(_color_roi, subset=["ROI%"])\
            .format({"HR%":"{:.1f}%","Profit":"{:+.1f}u","ROI%":"{:+.1f}%","AvgOdds":"{:.2f}"})
        st.dataframe(styled_l, use_container_width=True, hide_index=True)

        col_bt1, col_bt2 = st.columns(2)
        with col_bt1:
            top5 = ldf.head(5)
            fig_top = go.Figure(go.Bar(
                x=top5["Profit"], y=top5["League"],
                orientation="h",
                marker_color="#00F59D",
                text=[f"{v:+.1f}u" for v in top5["Profit"]],
                textposition="outside",
            ))
            fig_top.update_layout(
                title="Top 5 ligor (profit)", title_font=dict(color="#9BA0B5", size=13),
                plot_bgcolor="#0D1117", paper_bgcolor="#0D1117",
                font=dict(color="#9BA0B5", size=11),
                yaxis=dict(autorange="reversed"),
                xaxis=dict(gridcolor="#1C2030"),
                margin=dict(t=40, b=10, l=10, r=60), height=230,
            )
            st.plotly_chart(fig_top, use_container_width=True)
        with col_bt2:
            bot5 = ldf.tail(5).sort_values("Profit")
            fig_bot = go.Figure(go.Bar(
                x=bot5["Profit"], y=bot5["League"],
                orientation="h",
                marker_color="#FF4B6B",
                text=[f"{v:+.1f}u" for v in bot5["Profit"]],
                textposition="outside",
            ))
            fig_bot.update_layout(
                title="Botten 5 ligor (förlust)", title_font=dict(color="#9BA0B5", size=13),
                plot_bgcolor="#0D1117", paper_bgcolor="#0D1117",
                font=dict(color="#9BA0B5", size=11),
                yaxis=dict(autorange="reversed"),
                xaxis=dict(gridcolor="#1C2030"),
                margin=dict(t=40, b=10, l=10, r=60), height=230,
            )
            st.plotly_chart(fig_bot, use_container_width=True)

        # ── 5. INSIGHTS ────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 5️⃣ Insikter & Förbättringsförslag")

        # Best/worst odds range
        best_range = odf.loc[odf["Profit"].idxmax(), "Odds Range"] if not odf.empty else "—"
        worst_range = odf.loc[odf["Profit"].idxmin(), "Odds Range"] if not odf.empty else "—"
        best_range_roi = odf.loc[odf["Profit"].idxmax(), "ROI%"] if not odf.empty else 0
        worst_range_roi = odf.loc[odf["Profit"].idxmin(), "ROI%"] if not odf.empty else 0

        # Best/worst markets
        best_mkt = mdf.iloc[0]["Market"] if not mdf.empty else "—"
        worst_mkt = mdf.iloc[-1]["Market"] if not mdf.empty else "—"

        # Positive leagues count
        pos_leagues = (ldf["Profit"] > 0).sum()
        neg_leagues = (ldf["Profit"] <= 0).sum()

        # Value Single odds breakdown
        vs = bt[bt["market"] == "Value Single"]
        vs_by_range = []
        for rng in ODDS_ORDER:
            g = vs[vs["odds_range"] == rng]
            if len(g) >= 5:
                s = bt_stats(g)
                vs_by_range.append(f"**{rng}**: {s['N']} picks, {s['HR%']}% HR, {s['Profit']:+.1f}u ({s['ROI%']:+.1f}% ROI)")

        st.markdown(f"""
<div style="background:#0D1117;border:1px solid #1C2030;border-radius:12px;padding:20px 24px;line-height:2">

**🎯 Sweetspot oddszon: {best_range}** (ROI {best_range_roi:+.1f}%) — fokusera mer volym här.

**⚠️ Giftzon: {worst_range}** (ROI {worst_range_roi:+.1f}%) — undvik eller minska volymen drastiskt i detta intervall.

**✅ Bästa marknaden: {best_mkt}** — klart mest lönsam. Öka caps om möjligt.

**❌ Sämsta marknaden: {worst_mkt}** — negativ EV historiskt. Utvärdera om den ska köras i LEARNING.

**🌍 Ligor:** {pos_leagues} av {pos_leagues + neg_leagues} ligor är lönsamma historiskt. Ligorna i botten bör antingen rensas ur systemet eller flaggas för manuell granskning.

{"**📊 Value Singles per oddszon:**<br>" + "<br>".join(vs_by_range) if vs_by_range else ""}

</div>
""", unsafe_allow_html=True)

        st.markdown("<br>**Rekommenderade åtgärder:**", unsafe_allow_html=True)
        actions = []
        # Poison zone action
        pz = odf[odf["Odds Range"] == worst_range]
        if not pz.empty and pz.iloc[0]["ROI%"] < -2:
            actions.append(f"🚫 **Blockera oddszon {worst_range}** i value_singles_engine — negativt historisk ROI ({pz.iloc[0]['ROI%']:+.1f}%)")
        # Negative leagues
        neg_lge_list = ldf[ldf["Profit"] < -5]["League"].tolist()
        if neg_lge_list:
            actions.append(f"📉 **Nedgradera dessa ligor till LEARNING:** {', '.join(neg_lge_list[:5])}")
        # Markets
        neg_mkt_list = mdf[mdf["Profit"] < -10]["Market"].tolist()
        if neg_mkt_list:
            actions.append(f"🔄 **Flytta till LEARNING:** {', '.join(neg_mkt_list)}")
        # Best leagues
        top_lge_list = ldf.head(5)["League"].tolist()
        actions.append(f"📈 **Öka caps för toppligorna:** {', '.join(top_lge_list[:3])}")

        for a in actions:
            st.markdown(f"- {a}")


# ── footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center;color:#334155;font-size:0.72rem;margin-top:2rem;padding-bottom:1rem;">
    PGR Sports Analytics · Data for informational purposes only · Always gamble responsibly · 18+<br>
    Model scans every ~12 min · Edges vs sharp books (Pinnacle / Betfair) · Last refresh: {datetime.utcnow().strftime("%H:%M UTC")}
</div>
""", unsafe_allow_html=True)
