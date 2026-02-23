import json
import streamlit as st
import pandas as pd
from datetime import datetime

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
        <div class="sp-subtitle">Curated AI selections. One best pick per match. SmartScore ranked.</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:10px 14px;border-radius:8px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.25);margin-bottom:20px;">
        <span style="color:#FBBF24;font-size:12px;">Curated AI selections for recreational players. No staking advice.</span>
    </div>
    """, unsafe_allow_html=True)

    db = DatabaseHelper()

    today = datetime.now().strftime("%Y-%m-%d")
    picks = db.execute("""
        SELECT home_team, away_team, league, market, selection, odds,
               smart_score, confidence, model_grade
        FROM smart_picks
        WHERE pick_date = %s
        ORDER BY smart_score DESC
    """, (today,), fetch='all')

    today_rows = db.execute("""
        SELECT result, COUNT(*) as cnt
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
    for row in (today_rows or []):
        r = str(row[0]).upper()
        cnt = int(row[1])
        if r == 'WON':
            today_wins = cnt
        elif r == 'LOST':
            today_losses = cnt

    today_settled = today_wins + today_losses
    today_hit = (today_wins / today_settled * 100) if today_settled > 0 else 0
    today_pending_cnt = int(today_pending[0]) if today_pending else 0

    if not picks:
        st.info("No Smart Picks available for today. The engine runs daily at 10:00 — check back then.")

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
        <div class="sp-stat" style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);">
            <div class="sp-stat-value" style="color:#F59E0B;">{today_pending_cnt}</div>
            <div class="sp-stat-label">Pending</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not picks:
        return

    st.markdown(f"""
    <div class="sp-stats-row">
        <div class="sp-stat" style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);">
            <div class="sp-stat-value" style="color:#10B981;">{len(picks)}</div>
            <div class="sp-stat-label">Smart Picks</div>
        </div>
        <div class="sp-stat" style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);">
            <div class="sp-stat-value" style="color:#3B82F6;">{sum(1 for p in picks if p[7] == 'Strong')}</div>
            <div class="sp-stat-label">Strong Confidence</div>
        </div>
        <div class="sp-stat" style="background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.3);">
            <div class="sp-stat-value" style="color:#A855F7;">{sum(1 for p in picks if p[8] == 'A')}</div>
            <div class="sp-stat-label">Grade A</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    for i, pick in enumerate(picks, 1):
        home_team, away_team, league, market, selection, odds, smart_score, confidence, model_grade = pick

        if confidence == "Strong":
            border_color = "rgba(16,185,129,0.4)"
            bg_gradient = "radial-gradient(circle at top left, rgba(16,185,129,0.1), rgba(15,23,42,0.95))"
            conf_color = "#10B981"
        elif confidence == "Medium":
            border_color = "rgba(59,130,246,0.4)"
            bg_gradient = "radial-gradient(circle at top left, rgba(59,130,246,0.1), rgba(15,23,42,0.95))"
            conf_color = "#3B82F6"
        else:
            border_color = "rgba(245,158,11,0.4)"
            bg_gradient = "radial-gradient(circle at top left, rgba(245,158,11,0.1), rgba(15,23,42,0.95))"
            conf_color = "#F59E0B"

        grade_color = "#10B981" if model_grade == "A" else "#3B82F6" if model_grade == "B" else "#F59E0B"

        st.markdown(f"""
        <div style="padding:18px;margin:10px 0;border-radius:14px;background:{bg_gradient};border:1px solid {border_color};">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <div style="display:flex;align-items:center;gap:8px;">
                    <span style="font-size:12px;color:#9CA3AF;">{league}</span>
                    <span style="padding:3px 10px;border-radius:999px;background:{conf_color}22;color:{conf_color};font-size:10px;font-weight:600;">{confidence}</span>
                    <span style="padding:3px 10px;border-radius:999px;background:{grade_color}22;color:{grade_color};font-size:10px;font-weight:600;">Grade {model_grade}</span>
                </div>
                <div style="font-size:12px;color:#6B7280;">#{i}</div>
            </div>
            <div style="font-size:17px;color:#E5E7EB;font-weight:600;margin-bottom:4px;">{home_team} vs {away_team}</div>
            <div style="font-size:15px;color:#6EE7B7;font-weight:600;margin-bottom:4px;">{selection}</div>
            <div style="display:flex;gap:16px;align-items:center;margin-top:8px;">
                <div style="font-size:12px;color:#9CA3AF;">Odds: <span style="color:#E5E7EB;font-weight:600;">{float(odds):.2f}</span></div>
                <div style="font-size:12px;color:#9CA3AF;">Market: <span style="color:#E5E7EB;font-weight:600;">{market}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    _render_picks_table(picks)


def _render_picks_table(picks: list):
    st.markdown("### All Smart Picks — Table View")
    rows = []
    for p in picks:
        home_team, away_team, league, market, selection, odds, smart_score, confidence, model_grade = p
        rows.append({
            'Match': f"{home_team} vs {away_team}",
            'Selection': selection,
            'Odds': f"{float(odds):.2f}",
            'Confidence': confidence,
            'Grade': model_grade,
            'League': league,
            'Market': market,
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
