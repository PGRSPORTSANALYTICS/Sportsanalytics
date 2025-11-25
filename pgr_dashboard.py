import os
from datetime import datetime
from typing import List

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


# ------------- CONFIG & THEME ------------- #

st.set_page_config(
    page_title="PGR Sports Analytics – Performance Dashboard",
    page_icon="📊",
    layout="wide",
)

PGR_PRIMARY = "#00FFC2"
PGR_DARK_BG = "#050A10"
PGR_CARD_BG = "#0D141F"
PGR_TEXT_MUTED = "#9BA3B5"


def inject_pgr_global_background():
    st.markdown("""
    <style>
    .stApp {
        background: radial-gradient(circle at 20% 20%, rgba(0,255,166,0.08) 0%, rgba(0,0,0,1) 60%),
                    radial-gradient(circle at 80% 80%, rgba(0,255,166,0.05) 0%, rgba(0,0,0,1) 70%),
                    #000;
        background-attachment: fixed;
        color: #d7fff3 !important;
        font-family: 'Inter', sans-serif !important;
    }
    @keyframes floatDust {
        0% { transform: translateY(0px) translateX(0px); opacity: .2; }
        50% { transform: translateY(-20px) translateX(10px); opacity: .5; }
        100% { transform: translateY(0px) translateX(0px); opacity: .2; }
    }
    .neon-dust {
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        pointer-events: none;
        z-index: -1;
        background-image:
          radial-gradient(circle, rgba(0,255,166,0.18) 2px, transparent 3px),
          radial-gradient(circle, rgba(0,255,166,0.12) 1.6px, transparent 3px),
          radial-gradient(circle, rgba(0,255,166,0.06) 2px, transparent 2.8px);
        background-size: 120px 120px, 90px 90px, 160px 160px;
        animation: floatDust 8s infinite ease-in-out;
        opacity: 0.10;
    }
    .neon-grid::before {
        content: "";
        position: fixed;
        bottom: -10vh;
        left: 0;
        width: 100vw;
        height: 60vh;
        background:
          linear-gradient(transparent, rgba(0,255,166,0.08)),
          repeating-linear-gradient(
             to right,
             rgba(0,255,166,0.10) 0px,
             rgba(0,255,166,0.10) 1px,
             transparent 1px,
             transparent 40px
          ),
          repeating-linear-gradient(
             to top,
             rgba(0,255,166,0.10) 0px,
             rgba(0,255,166,0.10) 1px,
             transparent 1px,
             transparent 40px
          );
        background-blend-mode: overlay;
        pointer-events: none;
        z-index: -2;
    }
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: rgba(255,255,255,0.04); }
    ::-webkit-scrollbar-thumb { background: rgba(0,255,166,0.45); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0,255,166,0.80); }
    h1, h2, h3, h4, h5 {
        color: #aaffea !important;
        text-shadow: 0 0 12px rgba(0,255,166,0.35), 0 0 24px rgba(0,255,166,0.15);
    }
    .block-container { padding-top: 1.8rem; }
    </style>
    <div class="neon-dust"></div>
    <div class="neon-grid"></div>
    """, unsafe_allow_html=True)


CUSTOM_CSS = f"""
<style>
    .stApp {{
        background: radial-gradient(circle at top, #0b1724 0, #02050A 55%, #000000 100%);
        color: white;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
                     "Segoe UI", sans-serif;
    }}
    .pgr-header {{
        font-size: 2.2rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {PGR_PRIMARY};
    }}
    .pgr-subtitle {{
        font-size: 0.9rem;
        color: {PGR_TEXT_MUTED};
    }}
    .pgr-card {{
        padding: 1.1rem 1.25rem;
        border-radius: 0.9rem;
        background: linear-gradient(135deg, #0A111C 0%, #05070C 100%);
        border: 1px solid rgba(255, 255, 255, 0.04);
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.5);
    }}
    .pgr-metric-label {{
        font-size: 0.75rem;
        color: {PGR_TEXT_MUTED};
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 0.32rem;
    }}
    .pgr-metric-value {{
        font-size: 1.4rem;
        font-weight: 650;
    }}
    .pgr-badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.12rem 0.55rem;
        border-radius: 999px;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        border: 1px solid rgba(255,255,255,0.08);
        background: radial-gradient(circle at top, rgba(0,255,194,0.12),
                                    transparent 60%);
        color: {PGR_PRIMARY};
    }}
    .pgr-table thead tr th {{
        background: #050A10 !important;
        color: #E5EAF5 !important;
        border-bottom: 1px solid rgba(255,255,255,0.08);
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.11em;
    }}
    .pgr-table tbody tr td {{
        font-size: 0.84rem;
        color: #D6DEEC;
    }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ------------- DATABASE CONNECTION ------------- #

def get_db_url() -> str:
    """Try a few common env vars for the Postgres connection string."""
    candidates = [
        "DATABASE_URL",
        "POSTGRES_URL",
        "PGDATABASE_URL",
        "SUPABASE_DB_URL",
    ]
    for key in candidates:
        url = os.getenv(key)
        if url:
            return url
    raise RuntimeError(
        "No database URL found. Please set DATABASE_URL (or POSTGRES_URL) "
        "in your Replit / Railway environment."
    )


@st.cache_data(ttl=120, show_spinner="Loading bets from database…")
def load_all_bets() -> pd.DataFrame:
    """
    Load all bets from the `all_bets` view.
    We do NOT filter on mode here so that active / test bets also show up.
    ROI is still only based on settled bets (where profit is not null).
    """
    db_url = get_db_url()
    engine = create_engine(db_url)

    query = text(
        """
        SELECT
            id,
            product,
            stake,
            odds,
            payout,
            result,
            mode,
            created_at,
            settled_at,
            home_team,
            away_team,
            match_date,
            legs,
            parlay_description
        FROM all_bets
        ORDER BY created_at DESC
        """
    )

    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if df.empty:
        st.info("No parlays in the database yet.")
        return df

    # Find any columns that look like "legs" / selections
    leg_cols = [
        c for c in df.columns
        if c.lower() in ("leg_summary", "bet_legs", "markets", "selections", "description")
        or c.lower().startswith("leg_")
        or c.lower().endswith("_legs")
    ]

    # numeric cleanup
    for col in ["stake", "odds", "payout"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["created_at", "settled_at", "match_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # profit only for settled bets
    df["profit"] = None
    settled_mask = df["result"].isin(
        ["WIN", "WON", "LOSS", "LOST", "VOID", "CANCELLED"]
    ) & df["payout"].notna()
    df.loc[settled_mask, "profit"] = (
        df.loc[settled_mask, "payout"] - df.loc[settled_mask, "stake"]
    )

    return df


# ------------- METRICS HELPERS ------------- #

def compute_roi(df: pd.DataFrame) -> dict:
    """Compute stake, payout, profit, ROI and hit-rate for a given slice."""
    if df.empty:
        return dict(
            stake=0.0,
            payout=0.0,
            profit=0.0,
            roi=0.0,
            bets=0,
            wins=0,
            hit_rate=0.0,
        )

    # settled only
    settled = df[df["profit"].notna()].copy()
    if settled.empty:
        return dict(
            stake=float(df["stake"].sum()),
            payout=0.0,
            profit=0.0,
            roi=0.0,
            bets=len(df),
            wins=0,
            hit_rate=0.0,
        )

    total_stake = float(settled["stake"].sum())
    total_payout = float(settled["payout"].sum())
    profit = total_payout - total_stake
    roi = (profit / total_stake * 100) if total_stake > 0 else 0.0

    wins = settled["profit"] > 0
    hit_rate = (wins.sum() / len(settled) * 100) if len(settled) > 0 else 0.0

    return dict(
        stake=total_stake,
        payout=total_payout,
        profit=profit,
        roi=roi,
        bets=len(settled),
        wins=int(wins.sum()),
        hit_rate=hit_rate,
    )


def format_money(x: float) -> str:
    return f"{x:,.0f} kr" if abs(x) >= 1000 else f"{x:,.2f} kr"


def format_pct(x: float) -> str:
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.1f}%"


def product_filter(df: pd.DataFrame, product_codes: List[str]) -> pd.DataFrame:
    return df[df["product"].isin(product_codes)].copy()


def as_fixture(r):
    ht = str(r.get("home_team", "")).strip()
    at = str(r.get("away_team", "")).strip()
    return f"{ht} – {at}".strip(" –")


def build_legs_display(row, leg_cols):
    """Build legs text from available leg columns."""
    legs_parts = []
    for col in leg_cols:
        val = row.get(col)
        if val is None:
            continue
        val_str = str(val).strip()
        if not val_str or val_str.lower() == 'none':
            continue
        legs_parts.append(val_str)
    
    legs_text = " | ".join(legs_parts)
    legs_html = "<br>".join([f"• {p}" for p in legs_parts]) if legs_parts else ""
    return legs_text, legs_html


def roi_series(settled: pd.DataFrame):
    if settled.empty:
        return pd.DataFrame({"when": [], "bank": []})
    s = settled.copy()
    s = s.sort_values(["settled_at", "match_date", "created_at"], na_position="last")
    s["stake"] = s["stake"].astype(float)
    s["profit"] = s["profit"].astype(float)
    settled_ts = pd.to_datetime(s["settled_at"], utc=True, errors="coerce")
    match_ts = pd.to_datetime(s["match_date"], utc=True, errors="coerce")
    s["when"] = settled_ts.fillna(match_ts).dt.tz_localize(None)
    s["bank"] = s["profit"].cumsum()
    return s[["when", "bank"]]


def rolling_hit_rate(settled: pd.DataFrame, window=50):
    if settled.empty:
        return pd.DataFrame({"when": [], "roll": []})
    s = settled.copy()
    s["when"] = pd.to_datetime(s["settled_at"], utc=True, errors="coerce").dt.tz_localize(None)
    s = s.sort_values("when")
    s["hit"] = (s["profit"] > 0).astype(int)
    s["roll"] = s["hit"].rolling(window, min_periods=1).mean() * 100
    return s[["when", "roll"]]


def style_bet_table(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare a pretty table with decimal odds (2 decimals)."""
    if df.empty:
        return df

    display_cols = [
        "match_date",
        "home_team",
        "away_team",
        "product",
        "stake",
        "odds",
        "payout",
        "profit",
        "result",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    out = df[display_cols].copy()

    # dates
    for col in ["match_date"]:
        if col in out.columns:
            out[col] = out[col].dt.strftime("%Y-%m-%d")

    # numeric formatting
    for col in ["stake", "payout", "profit"]:
        if col in out.columns:
            out[col] = out[col].astype(float).round(2)

    if "odds" in out.columns:
        out["odds"] = out["odds"].astype(float).round(2)

    # Rename headers
    rename_map = {
        "match_date": "Match Date",
        "home_team": "Home",
        "away_team": "Away",
        "product": "Product",
        "stake": "Stake",
        "odds": "Odds",
        "payout": "Payout",
        "profit": "Profit",
        "result": "Result",
    }
    out = out.rename(columns=rename_map)

    return out


# ------------- UI COMPONENTS ------------- #

def metric_card(label: str, value: str, sublabel: str = ""):
    st.markdown(
        f"""
        <div class="pgr-card">
            <div class="pgr-metric-label">{label}</div>
            <div class="pgr-metric-value">{value}</div>
            <div class="pgr-subtitle">{sublabel}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview(df: pd.DataFrame):
    st.markdown(
        '<div class="pgr-header">PGR Sports Analytics</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="pgr-subtitle">Live performance across all products – football, SGP, women’s 1X2 and college basketball.</div>',
        unsafe_allow_html=True,
    )

    summary = compute_roi(df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card(
            "Total ROI",
            format_pct(summary["roi"]),
            f"On {format_money(summary['stake'])} staked",
        )
    with col2:
        metric_card(
            "Total Profit",
            format_money(summary["profit"]),
            "All settled bets",
        )
    with col3:
        metric_card(
            "Hit Rate",
            format_pct(summary["hit_rate"]),
            f"{summary['wins']} wins out of {summary['bets']} bets",
        )
    with col4:
        metric_card(
            "Bets Tracked",
            f"{len(df):,}",
            "Including pending bets",
        )

    st.markdown("### 📈 Equity Curve (Cumulative Profit)")

    settled = df[df["profit"].notna()].copy()
    if not settled.empty:
        settled["date"] = settled["settled_at"].fillna(pd.to_datetime(settled["match_date"], errors="coerce"))
        settled["date"] = pd.to_datetime(settled["date"], errors="coerce").dt.date
        curve = (
            settled.groupby("date")["profit"]
            .sum()
            .cumsum()
            .reset_index(name="cumulative_profit")
        )
        curve = curve.set_index("date")
        st.line_chart(curve, height=260)
    else:
        st.info("No settled bets yet – equity curve will appear once results are in.")

    st.markdown("### 🧩 ROI by Product")

    if not df.empty:
        prod_settled = df[df["profit"].notna()].copy()
        if not prod_settled.empty:
            agg = (
                prod_settled.groupby("product")
                .apply(lambda x: compute_roi(x)["roi"])
                .reset_index(name="ROI")
            )
            agg = agg.sort_values("ROI", ascending=False)
            agg = agg.set_index("product")
            st.bar_chart(agg, height=260)
        else:
            st.info("Waiting for settled bets before we can show per-product ROI.")
    else:
        st.info("No bets found in the database yet.")

    st.markdown("### 🕒 Latest 50 Bets")
    latest = df.sort_values("created_at", ascending=False).head(50)
    table = style_bet_table(latest)
    st.dataframe(
        table,
        use_container_width=True,
        height=380,
        column_config=None,
    )


def render_product_tab(
    df: pd.DataFrame,
    product_codes: List[str],
    title: str,
    description: str,
):
    data = product_filter(df, product_codes)

    st.markdown(
        f"#### {title} <span class='pgr-badge'>live</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="pgr-subtitle">{description}</div>', unsafe_allow_html=True)

    if data.empty:
        st.info("No bets for this product yet. Once your engine starts saving picks here, this tab will update automatically.")
        return

    for c in ["odds", "stake", "payout", "profit"]:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce")

    active = data[data["profit"].isna()].copy()
    settled = data[data["profit"].notna()].copy()

    st.markdown("##### Active Bets")
    if active.empty:
        st.caption("No active bets for this product right now.")
    else:
        if "match_date" in active.columns:
            dt = pd.to_datetime(active["match_date"], errors="coerce")
            if hasattr(dt.dt, 'tz') and dt.dt.tz is not None:
                dt = dt.dt.tz_localize(None)
            active["kickoff"] = dt.dt.strftime("%d %b %H:%M").fillna("")
        active["fixture"] = active.apply(as_fixture, axis=1)
        
        # Add legs display for SGP products
        if "parlay_description" in active.columns:
            active["legs"] = active["parlay_description"].apply(
                lambda x: str(x) if x and str(x).lower() != 'none' else ""
            )
        
        cols_active = [c for c in ["kickoff", "fixture", "legs", "odds", "stake", "mode"] if c in active.columns and not active[c].isna().all()]
        st.dataframe(
            active[cols_active].sort_values("kickoff" if "kickoff" in cols_active else cols_active[0]),
            use_container_width=True,
            hide_index=True,
        )

    summary = compute_roi(data)

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card(
            "ROI",
            format_pct(summary["roi"]),
            f"On {format_money(summary['stake'])} staked",
        )
    with c2:
        metric_card(
            "Profit",
            format_money(summary["profit"]),
            "All settled bets",
        )
    with c3:
        metric_card(
            "Hit Rate",
            format_pct(summary["hit_rate"]),
            f"{summary['bets']} settled",
        )

    st.markdown("##### Performance")
    r1, r2 = st.columns((2, 1))
    with r1:
        roi_df = roi_series(settled)
        if not roi_df.empty:
            st.line_chart(roi_df.set_index("when"), height=220)
        else:
            st.caption("No settled bets yet.")
        st.caption("Cumulative profit (kr)")
    with r2:
        hit_df = rolling_hit_rate(settled)
        if not hit_df.empty:
            st.line_chart(hit_df, x="when", y="roll", height=220)
        else:
            st.caption("No data yet.")
        st.caption("Rolling hit rate (last 50)")

    st.markdown("##### History")
    if settled.empty:
        st.caption("No settled bets yet.")
    else:
        if "settled_at" in settled.columns:
            dt_settled = pd.to_datetime(settled["settled_at"], errors="coerce")
            if hasattr(dt_settled.dt, 'tz') and dt_settled.dt.tz is not None:
                dt_settled = dt_settled.dt.tz_localize(None)
            settled["settled"] = dt_settled.dt.strftime("%d %b %H:%M").fillna("")
        if "match_date" in settled.columns:
            dt_match = pd.to_datetime(settled["match_date"], errors="coerce")
            if hasattr(dt_match.dt, 'tz') and dt_match.dt.tz is not None:
                dt_match = dt_match.dt.tz_localize(None)
            settled["match"] = dt_match.dt.strftime("%d %b %H:%M").fillna("")
        settled["fixture"] = settled.apply(as_fixture, axis=1)
        
        # Add legs display for SGP products
        if "parlay_description" in settled.columns:
            settled["legs"] = settled["parlay_description"].apply(
                lambda x: str(x) if x and str(x).lower() != 'none' else ""
            )
        
        cols_hist = [c for c in ["settled", "match", "fixture", "legs", "odds", "stake", "payout", "profit", "result"] if c in settled.columns and not settled[c].isna().all()]
        st.dataframe(
            settled.sort_values("settled_at", ascending=False)[cols_hist],
            use_container_width=True,
            hide_index=True,
        )


def render_basketball_tab(df: pd.DataFrame):
    """Render College Basketball tab with separate sections for singles and parlays."""
    st.markdown(
        "#### College Basketball <span class='pgr-badge'>live</span>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="pgr-subtitle">NCAAB value singles and parlays from your basketball engine.</div>', unsafe_allow_html=True)

    singles = product_filter(df, ["BASKET_SINGLE"])
    parlays = product_filter(df, ["BASKET_PARLAY"])
    all_data = product_filter(df, ["BASKET_SINGLE", "BASKET_PARLAY"])

    if all_data.empty:
        st.info("No basketball bets yet. Once your engine starts saving picks here, this tab will update automatically.")
        return

    for c in ["odds", "stake", "payout", "profit"]:
        if c in all_data.columns:
            all_data[c] = pd.to_numeric(all_data[c], errors="coerce")
        if c in singles.columns:
            singles[c] = pd.to_numeric(singles[c], errors="coerce")
        if c in parlays.columns:
            parlays[c] = pd.to_numeric(parlays[c], errors="coerce")

    summary = compute_roi(all_data)
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("ROI", format_pct(summary["roi"]), f"On {format_money(summary['stake'])} staked")
    with c2:
        metric_card("Profit", format_money(summary["profit"]), "All settled bets")
    with c3:
        metric_card("Hit Rate", format_pct(summary["hit_rate"]), f"{summary['bets']} settled")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 🎯 Singles")
        if singles.empty:
            st.caption("No singles yet.")
        else:
            singles_settled = singles[singles["profit"].notna()].copy()
            singles_active = singles[singles["profit"].isna()].copy()
            
            if not singles_settled.empty:
                s_summary = compute_roi(singles)
                st.markdown(f"**{len(singles_settled)} settled** | ROI: {s_summary['roi']:.1f}% | Profit: {s_summary['profit']:.0f} kr")
            
            if not singles_active.empty:
                st.caption(f"🔴 {len(singles_active)} active")
            
            singles_settled["fixture"] = singles_settled.apply(as_fixture, axis=1)
            cols = [c for c in ["fixture", "odds", "result", "profit"] if c in singles_settled.columns]
            if cols and not singles_settled.empty:
                st.dataframe(singles_settled[cols].head(10), use_container_width=True, hide_index=True)

    with col2:
        st.markdown("##### 🎲 Parlays")
        if parlays.empty:
            st.caption("No parlays yet.")
        else:
            parlays_settled = parlays[parlays["profit"].notna()].copy()
            parlays_active = parlays[parlays["profit"].isna()].copy()
            
            if not parlays_settled.empty:
                p_summary = compute_roi(parlays)
                st.markdown(f"**{len(parlays_settled)} settled** | ROI: {p_summary['roi']:.1f}% | Profit: {p_summary['profit']:.0f} kr")
            
            if not parlays_active.empty:
                st.caption(f"🔴 {len(parlays_active)} active")
            
            parlays_settled["fixture"] = parlays_settled.apply(as_fixture, axis=1)
            cols = [c for c in ["fixture", "odds", "result", "profit"] if c in parlays_settled.columns]
            if cols and not parlays_settled.empty:
                st.dataframe(parlays_settled[cols].head(10), use_container_width=True, hide_index=True)


def render_sgp_parlays_tab():
    """Specialized SGP Parlays tab with beautiful card layout."""
    st.markdown("## Same Game Parlays")
    st.caption("High-edge correlated parlays built within a single match.")

    db_url = get_db_url()
    engine = create_engine(db_url)
    
    query = text("""
        SELECT
            id,
            home_team,
            away_team,
            legs,
            parlay_description,
            bookmaker_odds as odds,
            stake,
            ev_percentage as ev,
            result,
            outcome,
            match_date,
            payout,
            profit_loss
        FROM sgp_predictions
        WHERE mode = 'PROD'
        ORDER BY match_date ASC, id ASC
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if df.empty:
        st.info("No parlays in the database yet.")
        return

    # Split active vs settled - check BOTH result and outcome columns
    # Settled = has result (WON/LOSS) OR has outcome (won/loss)
    outcome_settled = df["outcome"].isin(["won", "loss", "WON", "LOSS"])
    result_settled = df["result"].isin(["WON", "WIN", "LOSS", "LOST"])
    settled_mask = outcome_settled | result_settled
    
    active_bets = df[~settled_mask].copy()
    settled_bets = df[settled_mask].copy()

    # ROI / PROFIT / HIT RATE for settled
    if not settled_bets.empty:
        total_staked = settled_bets["stake"].sum()

        if "payout" in settled_bets.columns:
            total_return = settled_bets["payout"].fillna(0).sum()
        else:
            # Check both result and outcome for wins
            won_mask = settled_bets["result"].isin(["WON", "WIN"]) | settled_bets["outcome"].isin(["won", "WON"])
            total_return = (settled_bets["stake"] * settled_bets["odds"] * won_mask.astype(float)).sum()

        profit = total_return - total_staked
        roi = (profit / total_staked * 100) if total_staked > 0 else 0.0
        won_count = (settled_bets["result"].isin(["WON", "WIN"]) | settled_bets["outcome"].isin(["won", "WON"])).sum()
        hit_rate = (won_count / len(settled_bets) * 100) if len(settled_bets) > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(0,255,166,0.06);border:1px solid rgba(0,255,166,0.3);">
                    <div style="font-size:11px;text-transform:uppercase;color:#7EF3C9;">ROI</div>
                    <div style="font-size:26px;font-weight:700;color:#00FFA6;">
                        {roi:+.1f}%
                    </div>
                    <div style="font-size:12px;color:#9CA3AF;">
                        On {total_staked:.0f} kr staked
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            color = "#00FFA6" if profit >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(15,23,42,0.9);border:1px solid rgba(148,163,184,0.4);">
                    <div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Profit</div>
                    <div style="font-size:26px;font-weight:700;color:{color};">
                        {profit:+.0f} kr
                    </div>
                    <div style="font-size:12px;color:#9CA3AF;">
                        All settled parlays
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(15,23,42,0.9);border:1px solid rgba(148,163,184,0.4);">
                    <div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Hit rate</div>
                    <div style="font-size:26px;font-weight:700;color:#E5E7EB;">
                        {hit_rate:.1f}%
                    </div>
                    <div style="font-size:12px;color:#9CA3AF;">
                        Won / settled parlays
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ACTIVE PARLAYS
    st.markdown("### Active Parlays (Ready to bet)")

    if active_bets.empty:
        st.info("No active parlays right now.")
    else:
        for _, row in active_bets.iterrows():
            ev = row.get("ev", 0.0) or 0.0
            try:
                ev = float(ev)
            except Exception:
                ev = 0.0

            # EV-badge color
            if ev >= 15:
                ev_bg = "rgba(34,197,94,0.18)"
                ev_border = "rgba(34,197,94,0.8)"
            elif ev >= 8:
                ev_bg = "rgba(250,204,21,0.14)"
                ev_border = "rgba(250,204,21,0.9)"
            elif ev >= 3:
                ev_bg = "rgba(59,130,246,0.14)"
                ev_border = "rgba(59,130,246,0.7)"
            else:
                ev_bg = "rgba(148,163,184,0.10)"
                ev_border = "rgba(148,163,184,0.6)"

            # Build legs text from whatever columns we found
            leg_cols = ["parlay_description", "legs", "leg_summary", "bet_legs", "markets", "selections", "description"]
            legs_parts = []
            for col in leg_cols:
                val = row.get(col)
                if val is None:
                    continue
                val_str = str(val).strip()
                if not val_str or val_str.lower() == 'none':
                    continue
                legs_parts.append(val_str)
                break  # Use first non-empty column found

            legs_text = legs_parts[0] if legs_parts else ""
            legs_list = [p.strip() for p in legs_text.split(",") if p.strip()]
            legs_html = "".join([f"<div style='margin:2px 0;'>• {p}</div>" for p in legs_list]) if legs_list else "<i>No leg details stored</i>"

            # Format match date
            match_dt = pd.to_datetime(row.get("match_date"), errors="coerce")
            match_str = match_dt.strftime("%d %b %H:%M") if pd.notna(match_dt) else str(row.get("match_date", ""))

            home_team = str(row.get('home_team', '')).replace('"', '&quot;')
            away_team = str(row.get('away_team', '')).replace('"', '&quot;')
            odds_val = float(row.get('odds', 0))
            stake_val = float(row.get('stake', 0))

            card_html = f"""<div style="padding:18px;margin:10px 0;border-radius:16px;background:radial-gradient(circle at top left, rgba(0,255,166,0.14), rgba(15,23,42,0.96));border:1px solid rgba(0,255,166,0.35);box-shadow:0 0 20px rgba(0,255,166,0.25);">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
<div style="font-size:18px;font-weight:600;color:#E5E7EB;">{home_team} – {away_team}</div>
<div style="font-size:11px;padding:4px 9px;border-radius:999px;background:{ev_bg};border:1px solid {ev_border};color:#E5E7EB;text-transform:uppercase;letter-spacing:0.06em;">EV {ev:+.1f}%</div>
</div>
<div style="font-size:12px;color:#9CA3AF;margin-bottom:6px;">Kickoff: {match_str}</div>
<div style="font-size:13px;color:#CBD5F5;margin-bottom:8px;">
<span style="font-weight:600;color:#E5E7EB;">SGP legs:</span>
{legs_html}
</div>
<div style="display:flex;gap:18px;align-items:baseline;margin-top:4px;">
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Odds</div><div style="font-size:20px;font-weight:600;color:#00FFA6;">{odds_val:.2f}</div></div>
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Stake</div><div style="font-size:18px;font-weight:500;color:#E5E7EB;">{stake_val:.0f} kr</div></div>
</div>
</div>"""

            st.markdown(card_html, unsafe_allow_html=True)

            bet_string = f"{home_team} – {away_team} | SGP: {legs_text} | Odds {odds_val:.2f} | Stake {stake_val:.0f} kr"
            st.code(bet_string, language="text")

    st.markdown("---")
    st.markdown("### Parlay history")

    history_df = df.sort_values("match_date", ascending=False).head(100)
    display_cols = [c for c in ["match_date", "home_team", "away_team", "parlay_description", "odds", "stake", "ev", "result", "payout"] if c in history_df.columns]
    st.dataframe(
        history_df[display_cols],
        use_container_width=True,
        hide_index=True,
    )


# ------------- MAIN APP ------------- #

def main():
    inject_pgr_global_background()

    try:
        df = load_all_bets()
    except Exception as e:
        st.error(
            "Could not load data from the database. "
            "Check your DATABASE_URL and that the `all_bets` view exists."
        )
        st.exception(e)
        return

    with st.expander("Debug: last 20 raw bets"):
        st.dataframe(
            df[["created_at", "match_date", "product", "home_team", "away_team", "result", "mode", "stake", "odds"]]
            .head(20),
            use_container_width=True,
        )

    # Tabs for different products
    overview_tab, exact_tab, singles_tab, sgp_tab, women_tab, basket_tab = st.tabs(
        [
            "Overview",
            "Exact Score",
            "Value Singles",
            "SGP Parlays",
            "Women’s 1X2",
            "College Basketball",
        ]
    )

    with overview_tab:
        render_overview(df)

    with exact_tab:
        render_product_tab(
            df,
            product_codes=["EXACT_SCORE", "FINAL_SCORE"],
            title="Exact Score / Final Score",
            description="All correct-score bets generated by your main football engine.",
        )

    with singles_tab:
        render_product_tab(
            df,
            product_codes=["VALUE_SINGLE", "VALUE_SINGLES", "FOOTBALL_SINGLE"],
            title="Value Singles",
            description="High-edge single bets across 1X2, over/under, BTTS, corners and more.",
        )

    with sgp_tab:
        render_sgp_parlays_tab()

    with women_tab:
        render_product_tab(
            df,
            product_codes=["WOMEN_1X2", "WOMENS_1X2", "W1X2"],
            title="Women’s 1X2",
            description="Match-winner bets in women’s football – a softer market with big edges.",
        )

    with basket_tab:
        render_basketball_tab(df)


if __name__ == "__main__":
    main()