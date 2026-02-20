import json
import streamlit as st
import pandas as pd
from datetime import datetime

from smart_picks_filter import get_smart_picks_from_db, SMART_PICKS_ODDS_MIN, SMART_PICKS_ODDS_MAX
from db_helper import DatabaseHelper


def render_smart_picks_tab():
    st.markdown("""
    <style>
        .sp-header {
            text-align: center;
            padding: 20px 0 10px 0;
        }
        .sp-title {
            font-size: 1.8rem;
            font-weight: 700;
            color: #E5E7EB;
            margin-bottom: 4px;
        }
        .sp-subtitle {
            font-size: 0.9rem;
            color: #6B7280;
        }
        .sp-stats-row {
            display: flex;
            gap: 12px;
            margin: 16px 0 24px 0;
            flex-wrap: wrap;
        }
        .sp-stat {
            flex: 1;
            min-width: 120px;
            padding: 14px;
            border-radius: 10px;
            text-align: center;
        }
        .sp-stat-value {
            font-size: 1.5rem;
            font-weight: 700;
        }
        .sp-stat-label {
            font-size: 0.7rem;
            color: #6B7280;
            text-transform: uppercase;
            margin-top: 4px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="sp-header">
        <div class="sp-title">Smart Picks</div>
        <div class="sp-subtitle">Clean, conflict-free picks. One best pick per match. No opposing bets.</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:10px 14px;border-radius:8px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.25);margin-bottom:20px;">
        <span style="color:#FBBF24;font-size:12px;">For informational purposes only. Not betting advice. No guarantees of profit.</span>
    </div>
    """, unsafe_allow_html=True)

    picks = get_smart_picks_from_db()

    db = DatabaseHelper()

    today_rows = db.execute("""
        SELECT result, COUNT(*) as cnt,
               ROUND(SUM(CASE 
                   WHEN UPPER(result) = 'WON' THEN odds - 1
                   WHEN UPPER(result) = 'LOST' THEN -1
                   ELSE 0
               END)::numeric, 2) as profit
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND UPPER(status) = 'SETTLED'
          AND UPPER(result) IN ('WON', 'LOST')
          AND match_date = CURRENT_DATE::text
        GROUP BY result
    """, fetch='all')

    today_pending = db.execute("""
        SELECT COUNT(*) FROM football_opportunities
        WHERE mode = 'PROD' AND UPPER(status) = 'PENDING'
          AND match_date = CURRENT_DATE::text
    """, fetch='one')

    today_wins = 0
    today_losses = 0
    today_profit = 0.0
    for row in (today_rows or []):
        r = str(row[0]).upper()
        cnt = int(row[1])
        profit = float(row[2]) if row[2] else 0
        if r == 'WON':
            today_wins = cnt
        elif r == 'LOST':
            today_losses = cnt
        today_profit += profit

    today_settled = today_wins + today_losses
    today_hit = (today_wins / today_settled * 100) if today_settled > 0 else 0
    today_pending_cnt = int(today_pending[0]) if today_pending else 0
    today_profit_color = "#10B981" if today_profit >= 0 else "#EF4444"
    today_profit_sign = "+" if today_profit >= 0 else ""

    if not picks:
        st.info("No Smart Picks available right now. The engine runs every hour — check back soon.")

    st.markdown(f"""
    <div style="font-size:0.85rem;color:#9CA3AF;margin-bottom:6px;">Today's Results</div>
    <div class="sp-stats-row">
        <div class="sp-stat" style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);">
            <div class="sp-stat-value" style="color:#22C55E;">{today_wins}</div>
            <div class="sp-stat-label">Wins</div>
        </div>
        <div class="sp-stat" style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);">
            <div class="sp-stat-value" style="color:#EF4444;">{today_losses}</div>
            <div class="sp-stat-label">Losses</div>
        </div>
        <div class="sp-stat" style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);">
            <div class="sp-stat-value" style="color:#3B82F6;">{today_hit:.1f}%</div>
            <div class="sp-stat-label">Hit Rate</div>
        </div>
        <div class="sp-stat" style="background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.3);">
            <div class="sp-stat-value" style="color:{today_profit_color};">{today_profit_sign}{today_profit:.1f}u</div>
            <div class="sp-stat-label">Profit</div>
        </div>
        <div class="sp-stat" style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);">
            <div class="sp-stat-value" style="color:#F59E0B;">{today_pending_cnt}</div>
            <div class="sp-stat-label">Pending</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not picks:
        return

    core_picks = [p for p in picks if SMART_PICKS_ODDS_MIN <= float(p.get('odds', 0)) <= SMART_PICKS_ODDS_MAX]
    high_value_picks = [p for p in picks if float(p.get('odds', 0)) < SMART_PICKS_ODDS_MIN or float(p.get('odds', 0)) > SMART_PICKS_ODDS_MAX]

    avg_ev = sum(float(p.get('edge_percentage', 0)) for p in picks) / len(picks) if picks else 0
    avg_odds = sum(float(p.get('odds', 0)) for p in picks) / len(picks) if picks else 0
    high_trust = sum(1 for p in picks if p.get('trust_level') == 'L1_HIGH_TRUST')

    st.markdown(f"""
    <div class="sp-stats-row">
        <div class="sp-stat" style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);">
            <div class="sp-stat-value" style="color:#10B981;">{len(picks)}</div>
            <div class="sp-stat-label">Total Picks</div>
        </div>
        <div class="sp-stat" style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);">
            <div class="sp-stat-value" style="color:#3B82F6;">{len(core_picks)}</div>
            <div class="sp-stat-label">Core Range (1.70-2.10)</div>
        </div>
        <div class="sp-stat" style="background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.3);">
            <div class="sp-stat-value" style="color:#A855F7;">+{avg_ev:.1f}%</div>
            <div class="sp-stat-label">Avg EV</div>
        </div>
        <div class="sp-stat" style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);">
            <div class="sp-stat-value" style="color:#F59E0B;">{avg_odds:.2f}</div>
            <div class="sp-stat-label">Avg Odds</div>
        </div>
        <div class="sp-stat" style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);">
            <div class="sp-stat-value" style="color:#22C55E;">{high_trust}</div>
            <div class="sp-stat-label">High Trust</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if core_picks:
        st.markdown("### Core Picks")
        st.caption(f"Odds {SMART_PICKS_ODDS_MIN:.2f} – {SMART_PICKS_ODDS_MAX:.2f} | Best balance of value and probability")
        for pick in core_picks:
            _render_smart_pick_card(pick, badge_type="core")

    if high_value_picks:
        st.markdown("### High Value Picks")
        st.caption("Outside core odds range but strong edge detected")
        for pick in high_value_picks:
            _render_smart_pick_card(pick, badge_type="value")

    st.markdown("---")
    _render_picks_table(picks)


def _render_smart_pick_card(pick: dict, badge_type: str = "core"):
    home = pick.get('home_team', '')
    away = pick.get('away_team', '')
    selection = pick.get('selection', '')
    league = pick.get('league', '')
    odds = float(pick.get('odds', 0))
    ev = float(pick.get('edge_percentage', 0))
    conf = int(pick.get('confidence', 0))
    trust = pick.get('trust_level', '')
    kickoff = pick.get('kickoff_utc', '')
    score = float(pick.get('_smart_score', 0))

    kickoff_display = kickoff[:16].replace('T', ' ') if kickoff else 'TBD'

    if ev >= 15:
        ev_color = "#10B981"
    elif ev >= 8:
        ev_color = "#3B82F6"
    else:
        ev_color = "#F59E0B"

    if badge_type == "core":
        border_color = "rgba(16,185,129,0.4)"
        bg_gradient = "radial-gradient(circle at top left, rgba(16,185,129,0.1), rgba(15,23,42,0.95))"
        badge_html = '<span style="padding:3px 10px;border-radius:999px;background:rgba(16,185,129,0.2);color:#10B981;font-size:10px;font-weight:600;">CORE</span>'
    else:
        border_color = "rgba(168,85,247,0.4)"
        bg_gradient = "radial-gradient(circle at top left, rgba(168,85,247,0.1), rgba(15,23,42,0.95))"
        badge_html = '<span style="padding:3px 10px;border-radius:999px;background:rgba(168,85,247,0.2);color:#A855F7;font-size:10px;font-weight:600;">VALUE</span>'

    trust_badge = ""
    if trust == 'L1_HIGH_TRUST':
        trust_badge = '<span style="padding:3px 8px;border-radius:999px;background:rgba(34,197,94,0.15);color:#22C55E;font-size:10px;font-weight:600;margin-left:6px;">HIGH TRUST</span>'
    elif trust == 'L2_MEDIUM_TRUST':
        trust_badge = '<span style="padding:3px 8px;border-radius:999px;background:rgba(245,158,11,0.15);color:#F59E0B;font-size:10px;font-weight:600;margin-left:6px;">MEDIUM</span>'

    odds_by_bookmaker = pick.get('odds_by_bookmaker', {})
    if isinstance(odds_by_bookmaker, str):
        try:
            odds_by_bookmaker = json.loads(odds_by_bookmaker) if odds_by_bookmaker else {}
        except:
            odds_by_bookmaker = {}

    bookmaker_html = ""
    if odds_by_bookmaker and isinstance(odds_by_bookmaker, dict):
        sorted_books = sorted(odds_by_bookmaker.items(), key=lambda x: float(x[1]) if x[1] else 0, reverse=True)[:3]
        bookmaker_html = '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">'
        for i, (book, book_odds) in enumerate(sorted_books):
            if i == 0:
                bookmaker_html += f'''
                <div style="padding:6px 12px;border-radius:8px;background:linear-gradient(135deg, rgba(34,197,94,0.3), rgba(16,185,129,0.2));border:1px solid rgba(34,197,94,0.5);">
                    <div style="font-size:8px;color:#22C55E;font-weight:600;text-transform:uppercase;">Best</div>
                    <div style="font-size:16px;font-weight:700;color:#22C55E;">{float(book_odds):.2f}</div>
                    <div style="font-size:9px;color:#6B7280;">{book}</div>
                </div>'''
            else:
                bookmaker_html += f'''
                <div style="padding:6px 12px;border-radius:8px;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);">
                    <div style="font-size:8px;color:#60A5FA;font-weight:600;text-transform:uppercase;">#{i+1}</div>
                    <div style="font-size:16px;font-weight:700;color:#60A5FA;">{float(book_odds):.2f}</div>
                    <div style="font-size:9px;color:#6B7280;">{book}</div>
                </div>'''
        bookmaker_html += '</div>'

    st.markdown(f"""
    <div style="padding:18px;margin:10px 0;border-radius:14px;background:{bg_gradient};border:1px solid {border_color};">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:12px;color:#9CA3AF;">{league}</span>
                {badge_html}
                {trust_badge}
            </div>
            <div style="font-size:12px;padding:4px 10px;border-radius:999px;background:{ev_color}22;color:{ev_color};font-weight:600;">EV +{ev:.1f}%</div>
        </div>
        <div style="font-size:17px;color:#E5E7EB;font-weight:600;margin-bottom:4px;">{home} vs {away}</div>
        <div style="font-size:15px;color:#6EE7B7;font-weight:600;margin-bottom:4px;">{selection}</div>
        <div style="display:flex;gap:16px;align-items:center;margin-top:8px;">
            <div style="font-size:12px;color:#9CA3AF;">Odds: <span style="color:#E5E7EB;font-weight:600;">{odds:.2f}</span></div>
            <div style="font-size:12px;color:#9CA3AF;">Confidence: <span style="color:#E5E7EB;font-weight:600;">{conf}%</span></div>
            <div style="font-size:12px;color:#9CA3AF;">Kickoff: <span style="color:#E5E7EB;font-weight:600;">{kickoff_display} UTC</span></div>
        </div>
        {bookmaker_html}
    </div>
    """, unsafe_allow_html=True)


def _render_picks_table(picks: list):
    st.markdown("### All Smart Picks — Table View")
    rows = []
    for p in picks:
        odds_by_bookmaker = p.get('odds_by_bookmaker', {})
        if isinstance(odds_by_bookmaker, str):
            try:
                odds_by_bookmaker = json.loads(odds_by_bookmaker)
            except:
                odds_by_bookmaker = {}
        best_book = ''
        if isinstance(odds_by_bookmaker, dict) and odds_by_bookmaker:
            top = max(odds_by_bookmaker, key=lambda k: float(odds_by_bookmaker[k]) if odds_by_bookmaker[k] else 0)
            best_book = f"{top} @ {float(odds_by_bookmaker[top]):.2f}"

        kickoff = p.get('kickoff_utc', '')
        kickoff_display = kickoff[:16].replace('T', ' ') if kickoff else 'TBD'

        rows.append({
            'Match': f"{p.get('home_team', '')} vs {p.get('away_team', '')}",
            'Market': p.get('selection', ''),
            'Odds': f"{float(p.get('odds', 0)):.2f}",
            'EV': f"+{float(p.get('edge_percentage', 0)):.1f}%",
            'Conf': f"{int(p.get('confidence', 0))}%",
            'League': p.get('league', ''),
            'Kickoff (UTC)': kickoff_display,
            'Best Book': best_book,
            'Trust': p.get('trust_level', '').replace('L1_HIGH_TRUST', 'High').replace('L2_MEDIUM_TRUST', 'Medium').replace('L3_SOFT_VALUE', 'Soft'),
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
