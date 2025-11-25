# pgr_dashboard_all_in_one.py
# EN ENDA FIL: PGR-dashboard med tabs & historik

import os
import json
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# ==============================
#  🔌 DB-CONFIG
# ==============================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    try:
        DATABASE_URL = st.secrets.get("DATABASE_URL")
    except Exception:
        pass

if not DATABASE_URL:
    st.error("Saknar DATABASE_URL i Secrets eller Environment. Lägg till den först.")
    st.stop()

engine = create_engine(DATABASE_URL)


# ==============================
#  🧮 HJÄLPFUNKTIONER
# ==============================
@st.cache_data(ttl=60)
def load_bets(days_back: int | None = None, mode: str | None = None) -> pd.DataFrame:
    """
    Läser in alla bets från vyn/tabellen all_bets.
    Försök hålla namnen så här:
      id, created_at, settled_at, sport, product, match, bet_type,
      odds, stake, payout, profit, result, mode, is_parlay, legs
    Allt behöver inte finnas – koden försöker hantera saknade kolumner.
    """
    where_clauses = []
    params: dict = {}

    if days_back is not None:
        since = datetime.utcnow() - timedelta(days=days_back)
        where_clauses.append("created_at >= :since")
        params["since"] = since

    if mode and mode.upper() in ("PROD", "TEST"):
        where_clauses.append("mode = :mode")
        params["mode"] = mode.upper()

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    query = text(f"""
        SELECT *
        FROM all_bets
        {where_sql}
        ORDER BY COALESCE(settled_at, created_at) DESC
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params=params)

    # Tider
    for col in ["created_at", "settled_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    # Profit
    if "profit" not in df.columns:
        if {"payout", "stake"}.issubset(df.columns):
            df["profit"] = df["payout"] - df["stake"]
        else:
            df["profit"] = 0.0

    if "stake" not in df.columns:
        df["stake"] = 1.0

    # Result normalisering
    if "result" in df.columns:
        df["result"] = df["result"].astype(str).str.upper()
    else:
        df["result"] = ""

    return df


def calc_metrics(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"bets": 0, "stake": 0.0, "profit": 0.0, "roi": 0.0, "hit_rate": 0.0}

    stake = float(df["stake"].sum())
    profit = float(df["profit"].sum())
    roi = (profit / stake * 100) if stake > 0 else 0.0

    if "result" in df.columns:
        settled = df[df["result"].isin(["WON", "LOST", "VOID"])]
        if len(settled) > 0:
            wins = (settled["result"] == "WON").sum()
            hit_rate = wins / len(settled) * 100
        else:
            hit_rate = 0.0
    else:
        hit_rate = 0.0

    return {
        "bets": int(len(df)),
        "stake": stake,
        "profit": profit,
        "roi": roi,
        "hit_rate": hit_rate,
    }


def build_cum_roi(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["x", "roi"])

    work = df.sort_values("created_at").copy()
    work["net"] = work["profit"]
    work["cum_profit"] = work["net"].cumsum()
    work["cum_stake"] = work["stake"].cumsum()
    work["roi"] = work.apply(
        lambda r: (r["cum_profit"] / r["cum_stake"]) * 100 if r["cum_stake"] > 0 else 0,
        axis=1,
    )
    work["x"] = work["created_at"]
    return work[["x", "roi"]]


def get_match_text(row: pd.Series) -> str:
    """För historiken: lag-namn / matchnamn."""
    if "match" in row and isinstance(row["match"], str) and row["match"]:
        return row["match"]
    home = row.get("home_team") or row.get("home") or ""
    away = row.get("away_team") or row.get("away") or ""
    if home or away:
        return f"{home} – {away}"
    return row.get("game", "Unknown match")


def get_bet_text(row: pd.Series) -> str:
    """Vilket spel (enkel)."""
    for key in ["bet_type", "market", "prediction", "pick", "bet"]:
        val = row.get(key)
        if isinstance(val, str) and val:
            return val
    return "Unknown bet"


def parse_legs(raw_legs):
    """För parlay: försök få ut legs som lista."""
    if raw_legs is None:
        return []
    if isinstance(raw_legs, list):
        return [str(x) for x in raw_legs if x]
    if isinstance(raw_legs, str):
        # försök JSON först
        try:
            data = json.loads(raw_legs)
            if isinstance(data, list):
                return [str(x) for x in data if x]
        except Exception:
            # fallback: t.ex. "Over 2.5; BTTS; 1X"
            if ";" in raw_legs:
                return [s.strip() for s in raw_legs.split(";") if s.strip()]
            if "|" in raw_legs:
                return [s.strip() for s in raw_legs.split("|") if s.strip()]
            return [raw_legs]
    return [str(raw_legs)]


# ==============================
#  🎨 STREAMLIT UI
# ==============================
st.set_page_config(
    page_title="PGR Sports Analytics – Dashboard",
    page_icon="🧠",
    layout="wide",
)

# Enkel PGR-stil direkt här
PGR_GREEN = "#00F59D"
st.markdown(
    f"""
    <style>
    html, body, [class*="block-container"] {{
        background: radial-gradient(circle at top, #0b1120 0, #05070A 55%);
        color: #F9FAFB;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }}
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    .pgr-card {{
        padding: 1rem 1.1rem;
        border-radius: 16px;
        background: radial-gradient(circle at top left, rgba(0,245,157,0.08) 0, #101320 52%);
        border: 1px solid #1C2030;
        box-shadow: 0 18px 35px rgba(0,0,0,0.7);
    }}
    .pgr-card-label {{
        font-size: 0.75rem;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: #9BA0B5;
        margin-bottom: 0.2rem;
    }}
    .pgr-card-value {{
        font-size: 1.7rem;
        font-weight: 700;
        color: {PGR_GREEN};
    }}
    .pgr-card-sub {{
        font-size: 0.8rem;
        color: #9BA0B5;
        margin-top: 0.15rem;
    }}
    .result-win {{ color: #22c55e; font-weight: 600; }}
    .result-loss {{ color: #ef4444; font-weight: 600; }}
    .result-void {{ color: #eab308; font-weight: 600; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# SIDEBAR
with st.sidebar:
    st.markdown("### 🧠 PGR Sports Analytics")
    st.caption("Green Mean Money-Making Machine")
    st.markdown("---")

    mode_choice = st.radio(
        "Mode",
        options=["PROD", "TEST", "ALL"],
        index=0,
        help="Filtrera på bets-mode om du använder det i din DB.",
    )

    days_back = st.slider(
        "Visa bets från senaste (dagar)",
        min_value=7,
        max_value=365,
        value=90,
        step=7,
    )

mode_filter = None if mode_choice == "ALL" else mode_choice

df = load_bets(days_back=days_back, mode=mode_filter)

if df.empty:
    st.warning("Inga bets hittades för aktuella filter.")
    st.stop()

# matcha produktfält
product_col = "product" if "product" in df.columns else None
if not product_col:
    st.error("Hittar ingen 'product'-kolumn i all_bets. Lägg till den i vyn/tabellen.")
    st.stop()

# ==============================
#  HEADER + GLOBAL ROI
# ==============================
st.markdown(
    """
    <div style="display:flex;flex-direction:column;gap:0.15rem;margin-bottom:0.5rem;">
        <span style="font-size:0.8rem;letter-spacing:0.18em;
                     text-transform:uppercase;color:#9BA0B5;">
            PGR SPORTS ANALYTICS
        </span>
        <span style="font-size:1.6rem;font-weight:700;">
            Performance Dashboard
        </span>
        <span style="font-size:0.85rem;color:#9BA0B5;">
            Total ROI på första sidan · Egen ROI per flik · Historik med alla ben för parlays.
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

metrics_all = calc_metrics(df)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        f"""
        <div class="pgr-card">
            <div class="pgr-card-label">Platform ROI</div>
            <div class="pgr-card-value">{metrics_all['roi']:+.1f}%</div>
            <div class="pgr-card-sub">Alla produkter · {metrics_all['bets']} bets</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f"""
        <div class="pgr-card">
            <div class="pgr-card-label">Total Profit</div>
            <div class="pgr-card-value">{metrics_all['profit']:.0f} kr</div>
            <div class="pgr-card-sub">Payout − stake · {metrics_all['stake']:.0f} kr spelat</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(
        f"""
        <div class="pgr-card">
            <div class="pgr-card-label">Hit Rate</div>
            <div class="pgr-card-value">{metrics_all['hit_rate']:.1f}%</div>
            <div class="pgr-card-sub">Andel vunna bets</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with c4:
    st.markdown(
        f"""
        <div class="pgr-card">
            <div class="pgr-card-label">Mode</div>
            <div class="pgr-card-value">{mode_choice}</div>
            <div class="pgr-card-sub">Filterat läge</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# ==============================
#  TABS: Overview + en per produkt + History
# ==============================
products = sorted(df[product_col].dropna().unique().tolist())
tab_labels = ["Overview"] + products + ["History"]
tabs = st.tabs(tab_labels)

# ---------- OVERVIEW ----------
with tabs[0]:
    st.subheader("Overview – ROI per produkt")

    rows = []
    for prod, g in df.groupby(product_col):
        m = calc_metrics(g)
        rows.append(
            {
                "Product": prod,
                "Bets": m["bets"],
                "Stake": m["stake"],
                "Profit": m["profit"],
                "ROI %": m["roi"],
                "Hit rate %": m["hit_rate"],
            }
        )

    df_prod = pd.DataFrame(rows).sort_values("ROI %", ascending=False)
    st.dataframe(
        df_prod.style.format(
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

    st.markdown("### Cumulative ROI (alla produkter)")

    cum_all = build_cum_roi(df)
    if not cum_all.empty:
        cum_all = cum_all.set_index("x")
        st.line_chart(cum_all["roi"], height=300)
    else:
        st.info("Inte tillräckligt med bets för ROI-graf ännu.")

    st.markdown("### Latest bets (alla produkter)")
    show_cols = []
    for col in ["created_at", "sport", "product", "match", "bet_type", "odds", "stake", "profit", "result"]:
        if col in df.columns:
            show_cols.append(col)
    if not show_cols:
        show_cols = df.columns.tolist()[:8]

    st.dataframe(
        df[show_cols].head(100),
        use_container_width=True,
        hide_index=True,
    )

# ---------- EN FLIK PER PRODUKT ----------
for i, prod in enumerate(products, start=1):
    with tabs[i]:
        st.subheader(f"{prod}")

        df_prod = df[df[product_col] == prod].copy()
        m = calc_metrics(df_prod)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("ROI", f"{m['roi']:+.1f}%")
        c2.metric("Bets", m["bets"])
        c3.metric("Stake", f"{m['stake']:.0f}")
        c4.metric("Profit", f"{m['profit']:.0f}")

        st.markdown("#### Cumulative ROI")

        cum_prod = build_cum_roi(df_prod)
        if not cum_prod.empty:
            st.line_chart(cum_prod.set_index("x")["roi"], height=260)
        else:
            st.info("Inte tillräckligt med bets för ROI-graf på denna produkt ännu.")

        st.markdown("#### Latest bets")
        st.dataframe(
            df_prod.head(100),
            use_container_width=True,
            hide_index=True,
        )

# ---------- HISTORY-FLIK ----------
with tabs[-1]:
    st.subheader("History – alla spel med detaljer")

    # Sortera senaste först
    hist_df = df.sort_values("created_at", ascending=False).copy()

    # Begränsa antal i UI
    max_rows = st.slider("Visa senaste X bets", min_value=20, max_value=300, value=80, step=20)
    hist_df = hist_df.head(max_rows)

    for _, row in hist_df.iterrows():
        match_text = get_match_text(row)
        bet_text = get_bet_text(row)
        odds = row.get("odds", "")
        stake = row.get("stake", 0)
        profit = row.get("profit", 0)
        created = row.get("created_at", "")
        result = row.get("result", "").upper()

        # Result-färg
        if result == "WON":
            rclass = "result-win"
            rlabel = "WIN ✅"
        elif result == "LOST":
            rclass = "result-loss"
            rlabel = "LOSS ❌"
        elif result == "VOID":
            rclass = "result-void"
            rlabel = "VOID ⚪"
        else:
            rclass = ""
            rlabel = result or "PENDING"

        with st.expander(f"{match_text}  ·  {bet_text}"):
            st.markdown(
                f"**Result:** <span class='{rclass}'>{rlabel}</span>",
                unsafe_allow_html=True,
            )
            st.write(f"**Odds:** {odds}")
            st.write(f"**Stake:** {stake}")
            st.write(f"**Profit:** {profit:+.2f}")

            # Parlay-hantering
            is_parlay = row.get("is_parlay", False)
            if isinstance(is_parlay, str):
                is_parlay = is_parlay.lower() in ("true", "t", "1", "yes", "y")

            if is_parlay:
                st.markdown("**Parlay legs:**")
                legs_raw = row.get("legs")
                legs = parse_legs(legs_raw)
                if legs:
                    for leg in legs:
                        st.markdown(f"- {leg}")
                else:
                    st.caption("Inga legs hittades i kolumnen 'legs'.")

            # Tid
            if isinstance(created, pd.Timestamp):
                created_str = created.strftime("%Y-%m-%d %H:%M")
            else:
                created_str = str(created)
            st.caption(f"Placed: {created_str}")