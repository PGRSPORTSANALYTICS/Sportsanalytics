# pgr_match_analysis.py
"""
PGR Detailed Match Analysis Views
In-depth match breakdown, team stats, H2H, and prediction factors
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import streamlit as st

from pgr_theme import PGR_COLORS
from pgr_components import section_title


def inject_match_css():
    """Inject CSS for match analysis components"""
    st.markdown(
        f"""
        <style>
        .pgr-match-header {{
            background: linear-gradient(135deg, {PGR_COLORS["bg_alt"]} 0%, {PGR_COLORS["bg"]} 100%);
            border: 1px solid {PGR_COLORS["border"]};
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        
        .pgr-match-teams {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}
        
        .pgr-team {{
            text-align: center;
            flex: 1;
        }}
        
        .pgr-team-name {{
            font-size: 1.25rem;
            font-weight: 700;
            color: {PGR_COLORS["text"]};
            margin-bottom: 0.25rem;
        }}
        
        .pgr-team-meta {{
            font-size: 0.75rem;
            color: {PGR_COLORS["muted"]};
        }}
        
        .pgr-match-vs {{
            font-size: 1rem;
            color: {PGR_COLORS["muted"]};
            padding: 0 1rem;
        }}
        
        .pgr-match-info {{
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            font-size: 0.8rem;
            color: {PGR_COLORS["muted"]};
        }}
        
        .pgr-prediction-box {{
            background: {PGR_COLORS["bg_alt"]};
            border: 2px solid {PGR_COLORS["accent"]};
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
            margin-bottom: 1rem;
        }}
        
        .pgr-prediction-score {{
            font-size: 2.5rem;
            font-weight: 800;
            color: {PGR_COLORS["accent"]};
            margin: 0.5rem 0;
        }}
        
        .pgr-prediction-label {{
            font-size: 0.8rem;
            color: {PGR_COLORS["muted"]};
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .pgr-prediction-odds {{
            font-size: 1.25rem;
            font-weight: 600;
            color: {PGR_COLORS["text"]};
        }}
        
        .pgr-stat-bar {{
            display: flex;
            align-items: center;
            margin: 0.75rem 0;
        }}
        
        .pgr-stat-bar-label {{
            width: 100px;
            font-size: 0.8rem;
            color: {PGR_COLORS["muted"]};
            text-align: right;
            padding-right: 1rem;
        }}
        
        .pgr-stat-bar-value {{
            width: 50px;
            font-size: 0.85rem;
            font-weight: 600;
            color: {PGR_COLORS["text"]};
        }}
        
        .pgr-stat-bar-track {{
            flex: 1;
            height: 8px;
            background: {PGR_COLORS["border"]};
            border-radius: 4px;
            overflow: hidden;
            display: flex;
        }}
        
        .pgr-stat-bar-home {{
            background: {PGR_COLORS["accent"]};
            height: 100%;
        }}
        
        .pgr-stat-bar-away {{
            background: {PGR_COLORS["warning"]};
            height: 100%;
        }}
        
        .pgr-factor-card {{
            background: {PGR_COLORS["bg_alt"]};
            border: 1px solid {PGR_COLORS["border"]};
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 0.75rem;
        }}
        
        .pgr-factor-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }}
        
        .pgr-factor-name {{
            font-weight: 600;
            color: {PGR_COLORS["text"]};
            font-size: 0.9rem;
        }}
        
        .pgr-factor-weight {{
            font-size: 0.75rem;
            color: {PGR_COLORS["muted"]};
        }}
        
        .pgr-factor-bar {{
            height: 6px;
            background: {PGR_COLORS["border"]};
            border-radius: 3px;
            overflow: hidden;
        }}
        
        .pgr-factor-fill {{
            height: 100%;
            border-radius: 3px;
        }}
        
        .pgr-h2h-match {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem;
            border-bottom: 1px solid {PGR_COLORS["border"]};
        }}
        
        .pgr-h2h-match:last-child {{
            border-bottom: none;
        }}
        
        .pgr-h2h-score {{
            font-weight: 700;
            color: {PGR_COLORS["accent"]};
            font-size: 1rem;
            min-width: 60px;
            text-align: center;
        }}
        
        .pgr-h2h-teams {{
            flex: 1;
            padding: 0 1rem;
        }}
        
        .pgr-h2h-date {{
            font-size: 0.75rem;
            color: {PGR_COLORS["muted"]};
        }}
        
        .pgr-form-dot {{
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            font-weight: 700;
            margin: 0 2px;
        }}
        
        .pgr-form-dot.W {{
            background: {PGR_COLORS["accent"]};
            color: {PGR_COLORS["bg"]};
        }}
        
        .pgr-form-dot.D {{
            background: {PGR_COLORS["warning"]};
            color: {PGR_COLORS["bg"]};
        }}
        
        .pgr-form-dot.L {{
            background: {PGR_COLORS["danger"]};
            color: white;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def match_header(
    home_team: str,
    away_team: str,
    league: str,
    match_date: str,
    kickoff: str = "",
    venue: str = "",
):
    """Display match header with teams and info"""
    st.markdown(
        f"""
        <div class="pgr-match-header">
            <div class="pgr-match-teams">
                <div class="pgr-team">
                    <div class="pgr-team-name">{home_team}</div>
                    <div class="pgr-team-meta">Home</div>
                </div>
                <div class="pgr-match-vs">VS</div>
                <div class="pgr-team">
                    <div class="pgr-team-name">{away_team}</div>
                    <div class="pgr-team-meta">Away</div>
                </div>
            </div>
            <div class="pgr-match-info">
                <span>🏆 {league}</span>
                <span>📅 {match_date}</span>
                {"<span>⏰ " + kickoff + "</span>" if kickoff else ""}
                {"<span>🏟️ " + venue + "</span>" if venue else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def prediction_box(
    prediction: str,
    odds: float,
    ev: float,
    confidence: float,
    product: str = "Exact Score",
):
    """Display the main prediction box"""
    ev_color = PGR_COLORS["accent"] if ev >= 0 else PGR_COLORS["danger"]
    
    st.markdown(
        f"""
        <div class="pgr-prediction-box">
            <div class="pgr-prediction-label">{product} Prediction</div>
            <div class="pgr-prediction-score">{prediction}</div>
            <div class="pgr-prediction-odds">@ {odds:.2f}</div>
            <div style="margin-top: 1rem; display: flex; justify-content: center; gap: 2rem;">
                <div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: {ev_color};">{ev:+.1f}%</div>
                    <div style="font-size: 0.7rem; color: {PGR_COLORS["muted"]};">Expected Value</div>
                </div>
                <div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: {PGR_COLORS["text"]};">{confidence:.0f}%</div>
                    <div style="font-size: 0.7rem; color: {PGR_COLORS["muted"]};">Confidence</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def team_comparison_bar(
    label: str,
    home_value: float,
    away_value: float,
    format_str: str = "{:.1f}",
):
    """Display a comparison bar between two teams"""
    total = home_value + away_value if (home_value + away_value) > 0 else 1
    home_pct = (home_value / total) * 100
    away_pct = (away_value / total) * 100
    
    st.markdown(
        f"""
        <div class="pgr-stat-bar">
            <div class="pgr-stat-bar-value" style="text-align: right;">{format_str.format(home_value)}</div>
            <div class="pgr-stat-bar-track">
                <div class="pgr-stat-bar-home" style="width: {home_pct}%;"></div>
                <div class="pgr-stat-bar-away" style="width: {away_pct}%;"></div>
            </div>
            <div class="pgr-stat-bar-value">{format_str.format(away_value)}</div>
        </div>
        <div style="text-align: center; font-size: 0.75rem; color: {PGR_COLORS["muted"]}; margin-top: -0.5rem; margin-bottom: 0.5rem;">{label}</div>
        """,
        unsafe_allow_html=True,
    )


def team_stats_comparison(
    stats: Dict[str, Dict[str, float]],
):
    """
    Display team stats comparison
    
    stats format:
    {
        "xG": {"home": 1.8, "away": 1.2},
        "Shots": {"home": 15, "away": 10},
        ...
    }
    """
    section_title("Team Stats Comparison", icon="📊")
    
    for stat_name, values in stats.items():
        team_comparison_bar(
            stat_name,
            values.get("home", 0),
            values.get("away", 0),
        )


def prediction_factors(factors: List[Dict]):
    """
    Display prediction factors breakdown
    
    factors format:
    [
        {"name": "Team Form", "score": 75, "weight": 20, "insight": "Home team on 4-match win streak"},
        {"name": "H2H History", "score": 60, "weight": 15, "insight": "3 of last 5 ended 2-1"},
        ...
    ]
    """
    section_title("Prediction Factors", icon="🧮")
    
    for factor in factors:
        score = factor.get("score", 50)
        
        if score >= 70:
            color = PGR_COLORS["accent"]
        elif score >= 40:
            color = PGR_COLORS["warning"]
        else:
            color = PGR_COLORS["danger"]
        
        st.markdown(
            f"""
            <div class="pgr-factor-card">
                <div class="pgr-factor-header">
                    <span class="pgr-factor-name">{factor.get("name", "")}</span>
                    <span class="pgr-factor-weight">{factor.get("weight", 0)}% weight</span>
                </div>
                <div class="pgr-factor-bar">
                    <div class="pgr-factor-fill" style="width: {score}%; background: {color};"></div>
                </div>
                <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]}; margin-top: 0.5rem;">
                    {factor.get("insight", "")}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def h2h_history(matches: List[Dict]):
    """
    Display head-to-head history
    
    matches format:
    [
        {"date": "2024-10-15", "home": "Arsenal", "away": "Chelsea", "score": "2-1", "competition": "Premier League"},
        ...
    ]
    """
    section_title("Head-to-Head History", icon="⚔️")
    
    if not matches:
        st.caption("No H2H data available")
        return
    
    st.markdown('<div class="pgr-analytics-card">', unsafe_allow_html=True)
    
    for match in matches[:5]:
        st.markdown(
            f"""
            <div class="pgr-h2h-match">
                <div class="pgr-h2h-date">{match.get("date", "")}</div>
                <div class="pgr-h2h-teams">{match.get("home", "")} vs {match.get("away", "")}</div>
                <div class="pgr-h2h-score">{match.get("score", "")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    st.markdown('</div>', unsafe_allow_html=True)


def team_form(form_string: str, team_name: str):
    """Display team's recent form (W/D/L)"""
    dots = ""
    for char in form_string.upper()[:5]:
        if char in ['W', 'D', 'L']:
            dots += f'<span class="pgr-form-dot {char}">{char}</span>'
    
    st.markdown(
        f"""
        <div style="margin-bottom: 0.75rem;">
            <div style="font-size: 0.8rem; color: {PGR_COLORS["muted"]}; margin-bottom: 0.25rem;">{team_name} Form</div>
            <div>{dots}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def injuries_panel(injuries: Dict[str, List[str]]):
    """
    Display injuries for both teams
    
    injuries format:
    {
        "home": ["Player A (Knee)", "Player B (Illness)"],
        "away": ["Player C (Suspended)"]
    }
    """
    section_title("Injuries & Suspensions", icon="🏥")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**Home Team**")
        home_injuries = injuries.get("home", [])
        if home_injuries:
            for inj in home_injuries:
                st.markdown(f"- {inj}")
        else:
            st.caption("No reported injuries")
    
    with col2:
        st.markdown(f"**Away Team**")
        away_injuries = injuries.get("away", [])
        if away_injuries:
            for inj in away_injuries:
                st.markdown(f"- {inj}")
        else:
            st.caption("No reported injuries")


def odds_movement(
    opening: float,
    current: float,
    peak: float,
    low: float,
):
    """Display odds movement chart/info"""
    section_title("Odds Movement", icon="📉")
    
    movement = ((current - opening) / opening) * 100 if opening > 0 else 0
    movement_color = PGR_COLORS["accent"] if movement < 0 else PGR_COLORS["danger"]
    direction = "↓" if movement < 0 else "↑"
    
    cols = st.columns(4)
    
    with cols[0]:
        st.metric("Opening", f"{opening:.2f}")
    
    with cols[1]:
        st.metric("Current", f"{current:.2f}")
    
    with cols[2]:
        st.metric("Peak", f"{peak:.2f}")
    
    with cols[3]:
        st.metric("Low", f"{low:.2f}")
    
    st.markdown(
        f"""
        <div style="text-align: center; margin-top: 0.5rem;">
            <span style="color: {movement_color}; font-weight: 600;">
                {direction} {abs(movement):.1f}% from open
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def similar_matches(matches: List[Dict]):
    """
    Display similar historical matches
    
    matches format:
    [
        {"match": "Team A vs Team B", "score": "2-1", "similarity": 85, "date": "2024-08-20"},
        ...
    ]
    """
    section_title("Similar Historical Matches", icon="🔍")
    
    if not matches:
        st.caption("No similar matches found")
        return
    
    for match in matches[:5]:
        similarity = match.get("similarity", 0)
        
        st.markdown(
            f"""
            <div class="pgr-factor-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 600; color: {PGR_COLORS["text"]};">{match.get("match", "")}</div>
                        <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">{match.get("date", "")}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.25rem; font-weight: 700; color: {PGR_COLORS["accent"]};">{match.get("score", "")}</div>
                        <div style="font-size: 0.7rem; color: {PGR_COLORS["muted"]};">{similarity}% similar</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
