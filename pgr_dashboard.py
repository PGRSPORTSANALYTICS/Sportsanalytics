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

PRODUCT_TABS = {
    "Overview": None,
    "Final Score": ["EXACT_SCORE", "FINAL_SCORE"],
    "Value Singles": ["VALUE_SINGLE", "SINGLE_VALUE", "VALUE_SINGLE_FOOTBALL"],
    "SGP": ["SGP", "SAME_GAME_PARLAY"],
    "Basket (NCAAB)": ["BASKET_NCAAB", "NCAAB"],
    "Women 1X2": ["WOMEN_1X2", "WOMEN_3WAY"],
}

known_codes = {code for codes in PRODUCT_TABS.values() if codes for code in codes}
other_codes = sorted(set(df_all["product"].unique()) - known_codes)
if other_codes:
    PRODUCT_TABS["Other"] = other_codes

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
            Live ROI, profit and hit-rate across all engines · mode-filter & produkt-tabs.
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")

tab_labels = list(PRODUCT_TABS.keys())
tabs = st.tabs(tab_labels)

with tabs[0]:
    section_title("Overview – Platform", icon="📊")

    m = compute_metrics(df_all)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card(
            "Platform ROI",
            f"{m['roi']:+.1f}%",
            kicker=f"Stake: {m['stake']:.0f} kr · Bets: {m['bets']}",
            variant="good" if m["roi"] >= 0 else "bad",
        )
    with c2:
        metric_card(
            "Total Profit",
            f"{m['profit']:.0f} kr",
            kicker="Payout − Stake",
            variant="good" if m["profit"] >= 0 else "bad",
        )
    with c3:
        metric_card(
            "Hit Rate",
            f"{m['hit_rate']:.1f}%",
            kicker="WON / (WON + LOST + VOID)",
        )
    with c4:
        metric_card(
            "Mode",
            mode_choice,
            kicker="Data mode filter i sidebar.",
        )

    section_title("ROI per produkt", icon="📦")

    rows = []
    for prod_code, group in df_all.groupby("product"):
        mm = compute_metrics(group)
        rows.append(
            {
                "Product code": prod_code,
                "Bets": mm["bets"],
                "Stake": mm["stake"],
                "Profit": mm["profit"],
                "ROI %": mm["roi"],
                "Hit rate %": mm["hit_rate"],
            }
        )
    df_products = pd.DataFrame(rows).sort_values("ROI %", ascending=False)

    st.dataframe(
        df_products.style.format(
            {
                "Stake": "{:,.0f} kr",
                "Profit": "{:,.0f} kr",
                "ROI %": "{:,.1f} %",
                "Hit rate %": "{:,.1f} %",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    cum_df = build_cumulative_roi_df(df_all)
    if not cum_df.empty:
        roi_chart(
            cum_df.rename(columns={"created_at": "bet_index"}),
            x_col="bet_index",
            y_col="roi",
            title="Cumulative ROI – All products",
        )

    picks_table(df_all.sort_values("created_at", ascending=False), title="Latest bets – All products")

for idx, (tab_name, codes) in enumerate(PRODUCT_TABS.items()):
    if tab_name == "Overview":
        continue

    tab_index = tab_labels.index(tab_name)
    with tabs[tab_index]:
        if codes is None:
            df_sub = df_all.copy()
        else:
            df_sub = df_all[df_all["product"].isin(codes)].copy()

        section_title(tab_name, icon="🎯")

        if df_sub.empty:
            st.info(f"Inga bets hittades för {tab_name} med nuvarande filter.")
            continue

        mp = compute_metrics(df_sub)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card(
                f"{tab_name} ROI",
                f"{mp['roi']:+.1f}%",
                kicker=roi_delta_tag(mp["roi"]),
                variant="good" if mp["roi"] >= 0 else "bad",
            )
        with c2:
            metric_card(
                "Profit",
                f"{mp['profit']:.0f} kr",
                kicker=f"Stake: {mp['stake']:.0f} kr",
                variant="good" if mp["profit"] >= 0 else "bad",
            )
        with c3:
            metric_card(
                "Hit Rate",
                f"{mp['hit_rate']:.1f}%",
                kicker=f"Bets: {mp['bets']}",
            )
        with c4:
            metric_card(
                "Share of platform stake",
                f"{(mp['stake'] / df_all['stake'].sum())*100:,.1f}%" if df_all["stake"].sum() > 0 else "0.0%",
                kicker="Av total stake i filtret.",
            )

        cum_prod_df = build_cumulative_roi_df(df_sub)
        if not cum_prod_df.empty:
            roi_chart(
                cum_prod_df.rename(columns={"created_at": "bet_index"}),
                x_col="bet_index",
                y_col="roi",
                title=f"Cumulative ROI – {tab_name}",
            )

        picks_table(
            df_sub.sort_values("created_at", ascending=False),
            title=f"Latest bets – {tab_name}",
        )
