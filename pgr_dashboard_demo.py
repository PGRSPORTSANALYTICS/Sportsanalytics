# pgr_dashboard_demo.py

import random
import pandas as pd
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

# ---- INIT ---- #
st.set_page_config(
    page_title="PGR Sports Analytics – Demo",
    page_icon="🧠",
    layout="wide",
)

inject_pgr_css()

# ---- SIDEBAR ---- #
with st.sidebar:
    st.markdown("### 🧠 PGR Sports Analytics")
    st.caption("Green Mean Money-Making Machine")
    st.markdown("---")
    st.markdown("**Modes**")
    st.checkbox("Football", value=True)
    st.checkbox("College Basketball", value=True)
    st.checkbox("Same Game Parlays", value=True)
    st.markdown("---")
    st.caption("Logged in as: **demo_user**")

# ---- HEADER ---- #
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
        st.toast("Pretending to refresh data… 😉")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("")

# ---- FAKE METRICS (byt till riktiga senare) ---- #
col1, col2, col3, col4 = st.columns(4)

platform_roi = -22.3
singles_roi = 8.4
parlays_roi = -45.0
hit_rate = 61.7

with col1:
    metric_card(
        "Platform Total ROI",
        f"{platform_roi:+.1f}%",
        kicker="All sports · lifetime",
        variant="bad" if platform_roi < 0 else "good",
    )

with col2:
    metric_card(
        "Singles ROI",
        f"{singles_roi:+.1f}%",
        kicker=roi_delta_tag(singles_roi),
        variant="good" if singles_roi >= 0 else "bad",
    )

with col3:
    metric_card(
        "Parlay ROI",
        f"{parlays_roi:+.1f}%",
        kicker=roi_delta_tag(parlays_roi),
        variant="bad" if parlays_roi < 0 else "good",
    )

with col4:
    metric_card(
        "Hit Rate (last 200)",
        f"{hit_rate:.1f}%",
        kicker="All markets",
        variant="good" if hit_rate >= 50 else "bad",
    )

st.markdown("")

# ---- ROI CHART ---- #
random.seed(42)
vals = []
roi = 0.0
for i in range(1, 201):
    roi += random.uniform(-2, 2)
    vals.append({"bet_index": i, "roi": roi})

roi_df = pd.DataFrame(vals)
roi_chart(roi_df, title="Cumulative ROI – all bets")

# ---- LATEST PICKS TABLE ---- #
picks = []
for _ in range(15):
    picks.append(
        {
            "Game": random.choice(
                ["Arsenal – Spurs", "Ajax – Benfica", "Lille – PSG"]
            ),
            "Market": random.choice(
                ["Final Score 2–1", "Over 3.5 goals", "BTTS & Over 2.5"]
            ),
            "Odds": round(random.uniform(1.8, 6.5), 2),
            "EV %": round(random.uniform(-10, 25), 1),
            "Confidence %": round(random.uniform(48, 78), 1),
            "Type": random.choice(["Single", "SGP", "Value Single"]),
        }
    )

picks_df = pd.DataFrame(picks)
picks_table(picks_df, title="Latest engine picks")