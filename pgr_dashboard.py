# pgr_dashboard.py – PGR LIVE DASHBOARD MED TABS

import os
from datetime import datetime, timedelta

import pandas as pd
import sqlalchemy
import streamlit as st

from pgr_theme import inject_pgr_css
from pgr_components import (
    section_title,
    metric_card,
    roi_delta_tag,
    roi_chart,
    picks_table,
)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    try:
        if "DATABASE_URL" in st.secrets:
            DATABASE_URL = st.secrets["DATABASE_URL"]
    except Exception:
        pass

if not DATABASE_URL:
    st.error("DATABASE_URL saknas i secrets / environment.")
    st.stop()

engine = sqlalchemy.create_engine(DATABASE_URL)


@st.cache_data(ttl=60)
def load_all_bets(mode: str | None = None) -> pd.DataFrame:
    where = ""
    params = {}

    if mode and mode.upper() in ("PROD", "TEST"):
        where = "WHERE mode = %(mode)s"
        params["mode"] = mode.upper()

    query = f"""
        SELECT
            id,
            product,
            stake,
            odds,
            payout,
            result,
            mode,
            created_at,
            settled_at
        FROM all_bets
        {where}
        ORDER BY COALESCE(settled_at, created_at)
    """

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params if params else None)

    if df.empty:
        df["created_at"] = pd.to_datetime([])
        df["settled_at"] = pd.to_datetime([])
        df["profit"] = []
        return df

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    if "settled_at" in df.columns:
        df["settled_at"] = pd.to_datetime(df["settled_at"], errors="coerce", utc=True)

    df["created_at"] = df["created_at"].dt.tz_localize(None)
    if "settled_at" in df.columns:
        df["settled_at"] = df["settled_at"].dt.tz_localize(None)

    min_date = pd.Timestamp("2020-01-01")
    max_date = pd.Timestamp("2030-12-31")
    df = df[(df["created_at"] >= min_date) & (df["created_at"] <= max_date) | df["created_at"].isna()]

    df["profit"] = df["payout"] - df["stake"]

    return df


def compute_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "bets": 0,
            "stake": 0.0,
            "profit": 0.0,
            "roi": 0.0,
            "hit_rate": 0.0,
        }

    bets = len(df)
    stake = df["stake"].sum()
    profit = df["profit"].sum()
    roi = (profit / stake) * 100 if stake > 0 else 0.0

    settled = df[df["result"].isin(["WON", "LOST", "VOID"])]
    if settled.empty:
        hit_rate = 0.0
    else:
        wins = (settled["result"] == "WON").sum()
        hit_rate = wins / len(settled) * 100

    return {
        "bets": bets,
        "stake": float(stake),
        "profit": float(profit),
        "roi": float(roi),
        "hit_rate": float(hit_rate),
    }


def build_cumulative_roi_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["created_at", "roi"])

    df_sorted = df.sort_values("created_at").copy()
    df_sorted["net"] = df_sorted["payout"] - df_sorted["stake"]

    df_sorted["cum_profit"] = df_sorted["net"].cumsum()
    df_sorted["cum_stake"] = df_sorted["stake"].cumsum()
    df_sorted["roi"] = df_sorted.apply(
        lambda r: (r["cum_profit"] / r["cum_stake"]) * 100 if r["cum_stake"] > 0 else 0,
        axis=1,
    )

    return df_sorted[["created_at", "roi"]]


st.set_page_config(
    page_title="PGR Sports Analytics – Dashboard",
    page_icon="🧠",
    layout="wide",
)

inject_pgr_css()

with st.sidebar:
    st.markdown("### 🧠 PGR Sports Analytics")
    st.caption("Green Mean Money-Making Machine")
    st.markdown("---")

    mode_choice = st.radio(
        "Data mode",
        options=["PROD", "TEST", "ALL"],
        index=0,
        help="PROD = riktiga bets, TEST = experiment, ALL = allt blandat.",
    )

    days_back = st.slider(
        "Period (dagar tillbaka)",
        min_value=7,
        max_value=365,
        value=90,
        step=7,
    )

mode = None if mode_choice == "ALL" else mode_choice
df_all = load_all_bets(mode=mode)

end_date = datetime.utcnow()
start_date = end_date - timedelta(days=days_back)

df_all = df_all[
    (df_all["created_at"] >= start_date) & (df_all["created_at"] <= end_date)
].copy()

if df_all.empty:
    st.warning("Inga bets hittades för nuvarande filter.")
    st.stop()

def calculate_roi(df: pd.DataFrame):
    """Calculate ROI, stake, profit, count for a dataframe."""
    if df.empty:
        return 0.0, 0.0, 0.0, 0
    stake = df["stake"].sum()
    profit = df["profit"].sum()
    roi = (profit / stake) * 100 if stake > 0 else 0.0
    count = len(df)
    return roi, stake, profit, count


football_df = df_all[df_all["product"].isin(["EXACT_SCORE", "VALUE_SINGLE"])].copy()
sgp_df = df_all[df_all["product"] == "SGP"].copy()
women_df = df_all[df_all["product"] == "WOMEN_1X2"].copy()
basket_df = df_all[df_all["product"].isin(["BASKET_SINGLE", "BASKET_PARLAY"])].copy()

st.markdown(
    """
    <div style="display:flex;flex-direction:column;gap:0.2rem;">
        <span style="font-size:0.8rem;letter-spacing:0.18em;
                     text-transform:uppercase;color:#9BA0B5;">
            PGR SPORTS ANALYTICS
        </span>
        <span style="font-size:1.7rem;font-weight:700;">
            Performance & ROI Dashboard
        </span>
        <span style="font-size:0.85rem;color:#9BA0B5;">
            Live ROI, profit and hit-rate across all engines
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")

tab1, tab2, tab3, tab4 = st.tabs(["Football", "SGP", "Women's 1X2", "College Basket"])

with tab1:
    st.subheader("Football – Single Bets & Exact Score")
    roi, stake, profit, count = calculate_roi(football_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("ROI", f"{roi:,.1f}%")
    col2.metric("Total stake", f"{stake:,.0f}")
    col3.metric("Net profit", f"{profit:,.0f}")
    st.dataframe(football_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Same Game Parlays (SGP)")
    roi, stake, profit, count = calculate_roi(sgp_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("ROI", f"{roi:,.1f}%")
    col2.metric("Total stake", f"{stake:,.0f}")
    col3.metric("Net profit", f"{profit:,.0f}")
    st.dataframe(sgp_df, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Women's Football 1X2")
    roi, stake, profit, count = calculate_roi(women_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("ROI", f"{roi:,.1f}%")
    col2.metric("Total stake", f"{stake:,.0f}")
    col3.metric("Net profit", f"{profit:,.0f}")
    st.dataframe(women_df, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("College Basketball – Singles & Parlays")
    roi, stake, profit, count = calculate_roi(basket_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("ROI", f"{roi:,.1f}%")
    col2.metric("Total stake", f"{stake:,.0f}")
    col3.metric("Net profit", f"{profit:,.0f}")
    st.dataframe(basket_df, use_container_width=True, hide_index=True)
