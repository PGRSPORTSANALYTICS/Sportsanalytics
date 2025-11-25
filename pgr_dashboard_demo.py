# pgr_dashboard_demo.py

import random
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import streamlit as st

from pgr_theme import inject_pgr_css
from pgr_components import (
    section_title,
    metric_card,
    roi_delta_tag,
    pgr_button,
    roi_chart,
    picks_table,
)
from pgr_notifications import (
    inject_notification_css,
    alert_banner,
    live_match_alert,
    notification_center,
    quick_stats_banner,
    prediction_toast,
)
from pgr_analytics import (
    inject_analytics_css,
    performance_breakdown,
    odds_range_analysis,
    streak_analysis,
    backtest_results,
    strategy_filters,
    insights_panel,
    cumulative_roi_chart,
)
from pgr_match_analysis import (
    inject_match_css,
    match_header,
    prediction_box,
    team_stats_comparison,
    prediction_factors,
    h2h_history,
    team_form,
    injuries_panel,
    odds_movement,
    similar_matches,
)

st.set_page_config(
    page_title="PGR Sports Analytics – Demo",
    page_icon="🧠",
    layout="wide",
)

inject_pgr_css()
inject_notification_css()
inject_analytics_css()
inject_match_css()

with st.sidebar:
    st.markdown("### 🧠 PGR Sports Analytics")
    st.caption("Green Mean Money-Making Machine")
    st.markdown("---")
    
    page = st.radio(
        "Navigation",
        ["Dashboard", "Analytics", "Match Analysis"],
        label_visibility="collapsed",
    )
    
    st.markdown("---")
    st.markdown("**Products**")
    st.checkbox("Exact Score", value=True, key="prod_exact")
    st.checkbox("SGP Parlays", value=True, key="prod_sgp")
    st.checkbox("Women 1X2", value=True, key="prod_women")
    st.checkbox("Value Singles", value=True, key="prod_value")
    st.markdown("---")
    st.caption("Logged in as: **demo_user**")

if page == "Dashboard":
    col_logo, col_title, col_right = st.columns([0.3, 1.4, 0.8])

    with col_title:
        st.markdown(
            """
            <div style="display:flex;flex-direction:column;gap:0.15rem;">
                <span style="font-size:0.75rem;letter-spacing:0.18em;
                             text-transform:uppercase;color:#9BA0B5;">
                    PGR SPORTS ANALYTICS
                </span>
                <span style="font-size:1.7rem;font-weight:700;">
                    Daily Edge Dashboard
                </span>
                <span style="font-size:0.85rem;color:#9BA0B5;">
                    Live tracking of ROI, hit-rate and value picks across all engines.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_right:
        st.markdown("<div style='text-align:right;'>", unsafe_allow_html=True)
        if pgr_button("Refresh Data", primary=True, key="refresh"):
            st.toast("Refreshing live data...", icon="🔄")
            prediction_toast("Arsenal vs Chelsea", "2-1", 8.50, 12.3)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("")
    
    live_match_alert("Arsenal", "Chelsea", "1-0", 34, "Saka goal 34'")
    
    alert_banner(
        "3 New Predictions Available",
        "Premier League & La Liga matches added",
        variant="info",
    )

    sample_notifications = [
        {"type": "prediction", "text": "New pick: Arsenal 2-1 Chelsea @ 8.50", "time": "10:30", "unread": True},
        {"type": "result", "text": "WIN: Liverpool 3-1 Man United @ 11.00", "time": "09:15", "unread": True},
        {"type": "alert", "text": "High EV opportunity: Barcelona vs Real Madrid", "time": "08:45", "unread": False},
        {"type": "prediction", "text": "SGP: Over 2.5 + BTTS @ 2.85", "time": "Yesterday", "unread": False},
    ]
    notification_center(sample_notifications)
    
    st.markdown("")

    quick_stats_banner(pending_bets=7, live_matches=2, new_picks_today=5)
    
    st.markdown("")

    col1, col2, col3, col4 = st.columns(4)

    platform_roi = 14.7
    exact_roi = 28.4
    sgp_roi = -12.5
    hit_rate = 18.3

    with col1:
        metric_card(
            "Platform Total ROI",
            f"{platform_roi:+.1f}%",
            kicker="All products · PROD mode",
            variant="good" if platform_roi >= 0 else "bad",
        )

    with col2:
        metric_card(
            "Exact Score ROI",
            f"{exact_roi:+.1f}%",
            kicker=roi_delta_tag(exact_roi),
            variant="good" if exact_roi >= 0 else "bad",
        )

    with col3:
        metric_card(
            "SGP ROI",
            f"{sgp_roi:+.1f}%",
            kicker=roi_delta_tag(sgp_roi),
            variant="bad" if sgp_roi < 0 else "good",
        )

    with col4:
        metric_card(
            "Hit Rate",
            f"{hit_rate:.1f}%",
            kicker="Target: 15-25%",
            variant="good" if hit_rate >= 15 else "bad",
        )

    st.markdown("")

    random.seed(42)
    vals = []
    roi = 0.0
    for i in range(1, 201):
        win = random.random() < 0.18
        if win:
            roi += random.uniform(5, 12)
        else:
            roi -= 1
        vals.append({"bet_index": i, "roi": roi})

    roi_df = pd.DataFrame(vals)
    roi_chart(roi_df, title="Cumulative ROI – PROD Bets")

    matches = [
        ("Arsenal vs Chelsea", "Premier League"),
        ("Liverpool vs Man City", "Premier League"),
        ("Tottenham vs Man United", "Premier League"),
        ("Barcelona vs Real Madrid", "La Liga"),
        ("Atletico vs Sevilla", "La Liga"),
        ("PSG vs Lyon", "Ligue 1"),
        ("Marseille vs Monaco", "Ligue 1"),
        ("Bayern vs Dortmund", "Bundesliga"),
        ("Leipzig vs Leverkusen", "Bundesliga"),
        ("Inter vs AC Milan", "Serie A"),
        ("Juventus vs Napoli", "Serie A"),
        ("Roma vs Lazio", "Serie A"),
    ]
    
    predictions = ["2-1", "1-0", "2-0", "1-1", "3-1", "2-2", "3-0", "1-2"]
    products = ["Exact Score", "Exact Score", "SGP", "Women 1X2"]
    
    picks = []
    for i, (match, league) in enumerate(matches):
        picks.append(
            {
                "Match": match,
                "League": league,
                "Prediction": predictions[i % len(predictions)],
                "Odds": round(6.0 + i * 0.8, 2),
                "EV %": round(5 + i * 1.5, 1),
                "Product": products[i % len(products)],
            }
        )

    picks_df = pd.DataFrame(picks)
    picks_table(picks_df, title="Today's Predictions")

elif page == "Analytics":
    st.markdown(
        """
        <div style="margin-bottom: 1.5rem;">
            <span style="font-size:1.5rem;font-weight:700;">Advanced Analytics</span>
            <span style="font-size:0.85rem;color:#9BA0B5;margin-left:1rem;">
                Strategy backtesting & performance insights
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3 = st.tabs(["Performance", "Backtesting", "Insights"])
    
    with tab1:
        random.seed(123)
        perf_data = []
        for _ in range(150):
            product = random.choice(["Exact Score", "SGP", "Women 1X2", "Value Singles"])
            odds = round(random.uniform(3, 15), 2)
            won = random.random() < (0.20 if product == "Exact Score" else 0.35)
            stake = 100
            profit = (odds - 1) * stake if won else -stake
            perf_data.append({
                "product": product,
                "odds": odds,
                "won": won,
                "stake": stake,
                "profit": profit,
                "date": datetime.now() - timedelta(days=random.randint(0, 60)),
            })
        
        perf_df = pd.DataFrame(perf_data)
        
        col1, col2 = st.columns(2)
        
        with col1:
            performance_breakdown(perf_df, group_by="product", title="Performance by Product")
        
        with col2:
            odds_range_analysis(perf_df)
        
        st.markdown("")
        streak_analysis(perf_df)
    
    with tab2:
        st.markdown("#### Configure Backtest Strategy")
        
        filters = strategy_filters()
        
        st.markdown("---")
        
        if st.button("Run Backtest", type="primary"):
            with st.spinner("Running backtest simulation..."):
                import time
                time.sleep(1)
            
            backtest_results(
                total_bets=287,
                wins=52,
                roi=18.4,
                profit=5280,
                avg_odds=9.2,
                period=f"Backtest with EV>{filters['min_ev']}%, Odds {filters['min_odds']}-{filters['max_odds']}",
            )
    
    with tab3:
        sample_insights = [
            {"type": "good", "text": "Premier League: +32% ROI"},
            {"type": "good", "text": "Odds 8-12x performing best"},
            {"type": "warning", "text": "SGP needs higher EV filter"},
            {"type": "bad", "text": "Bundesliga underperforming"},
            {"type": "good", "text": "Weekend matches +15% vs weekday"},
        ]
        insights_panel(sample_insights)
        
        st.markdown("")
        
        perf_df_sorted = perf_df.sort_values('date').copy()
        perf_df_sorted['date'] = perf_df_sorted['date'].dt.strftime('%Y-%m-%d')
        cumulative_roi_chart(perf_df_sorted)

elif page == "Match Analysis":
    st.markdown(
        """
        <div style="margin-bottom: 1.5rem;">
            <span style="font-size:1.5rem;font-weight:700;">Match Analysis</span>
            <span style="font-size:0.85rem;color:#9BA0B5;margin-left:1rem;">
                Detailed breakdown of upcoming predictions
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    sample_matches = [
        "Arsenal vs Chelsea (Premier League)",
        "Barcelona vs Real Madrid (La Liga)",
        "PSG vs Lyon (Ligue 1)",
        "Bayern vs Dortmund (Bundesliga)",
    ]
    
    selected_match = st.selectbox("Select Match", sample_matches)
    
    st.markdown("")
    
    if "Arsenal" in selected_match:
        match_header(
            home_team="Arsenal",
            away_team="Chelsea",
            league="Premier League",
            match_date="Nov 26, 2025",
            kickoff="20:00 CET",
            venue="Emirates Stadium",
        )
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            prediction_box(
                prediction="2-1",
                odds=8.50,
                ev=12.3,
                confidence=68,
                product="Exact Score",
            )
        
        with col2:
            team_form("WWDWL", "Arsenal")
            team_form("WLDWL", "Chelsea")
        
        st.markdown("")
        
        col1, col2 = st.columns(2)
        
        with col1:
            team_stats_comparison({
                "xG (Last 5)": {"home": 2.1, "away": 1.6},
                "Goals/Game": {"home": 2.4, "away": 1.8},
                "Clean Sheets": {"home": 3, "away": 2},
                "Shots/Game": {"home": 16.2, "away": 12.8},
            })
        
        with col2:
            prediction_factors([
                {"name": "Team Form", "score": 78, "weight": 25, "insight": "Arsenal on strong home form, 4W in last 5"},
                {"name": "H2H History", "score": 65, "weight": 20, "insight": "3 of last 5 H2H ended 2-1 or 1-2"},
                {"name": "xG Analysis", "score": 72, "weight": 30, "insight": "Arsenal xG 2.1 vs Chelsea 1.6 defensive issues"},
                {"name": "Odds Value", "score": 85, "weight": 25, "insight": "Model: 11.7% vs Market: 10.5%"},
            ])
        
        st.markdown("")
        
        col1, col2 = st.columns(2)
        
        with col1:
            h2h_history([
                {"date": "2025-04-23", "home": "Chelsea", "away": "Arsenal", "score": "1-2"},
                {"date": "2024-10-15", "home": "Arsenal", "away": "Chelsea", "score": "2-1"},
                {"date": "2024-05-05", "home": "Chelsea", "away": "Arsenal", "score": "2-2"},
                {"date": "2024-01-20", "home": "Arsenal", "away": "Chelsea", "score": "3-1"},
                {"date": "2023-10-08", "home": "Chelsea", "away": "Arsenal", "score": "0-1"},
            ])
        
        with col2:
            injuries_panel({
                "home": ["Timber (ACL)", "Zinchenko (Calf)"],
                "away": ["Reece James (Hamstring)", "Fofana (Knee)"],
            })
        
        st.markdown("")
        
        odds_movement(
            opening=9.00,
            current=8.50,
            peak=9.50,
            low=8.20,
        )
        
        st.markdown("")
        
        similar_matches([
            {"match": "Arsenal vs Man United", "score": "2-1", "similarity": 87, "date": "2024-12-01"},
            {"match": "Liverpool vs Chelsea", "score": "2-1", "similarity": 82, "date": "2024-10-27"},
            {"match": "Arsenal vs Tottenham", "score": "2-1", "similarity": 79, "date": "2024-09-15"},
        ])
    
    else:
        st.info("Select 'Arsenal vs Chelsea' to see the full demo analysis")
