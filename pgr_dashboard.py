import os
from datetime import datetime
from typing import List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text


def split_bets_by_mode(df: pd.DataFrame):
    """
    Splits raw bets into:
    - prod_bets: real bets (mode='PROD' or null)
    - test_bets: backtests/simulated (mode in ['TEST', 'BACKTEST'])
    """
    if "mode" not in df.columns:
        return df.copy(), df.iloc[0:0].copy()

    mode_col = df["mode"].fillna("PROD").str.upper()

    prod_bets = df[mode_col == "PROD"].copy()
    test_bets = df[mode_col.isin(["TEST", "BACKTEST"])].copy()

    return prod_bets, test_bets


def get_prod_bets(df: pd.DataFrame) -> pd.DataFrame:
    """Get only production bets (mode='PROD' or null)."""
    if "mode" not in df.columns:
        return df.copy()
    mode_col = df["mode"].fillna("PROD").str.upper()
    return df[mode_col == "PROD"].copy()


def get_backtest_bets(df: pd.DataFrame) -> pd.DataFrame:
    """Get only backtest bets (mode='BACKTEST' or 'TEST')."""
    if "mode" not in df.columns:
        return df.iloc[0:0].copy()
    mode_col = df["mode"].fillna("PROD").str.upper()
    return df[mode_col.isin(["TEST", "BACKTEST"])].copy()


def calculate_roi(bets: pd.DataFrame) -> float:
    """Calculate ROI percentage from bets dataframe."""
    summary = compute_roi(bets)
    return summary["roi"]


def calculate_hit_rate(bets: pd.DataFrame) -> float:
    """Calculate hit rate percentage from bets dataframe."""
    summary = compute_roi(bets)
    return summary["hit_rate"]


def calculate_profit(bets: pd.DataFrame) -> float:
    """Calculate total profit from bets dataframe."""
    summary = compute_roi(bets)
    return summary["profit"]


def filter_by_product(bets: pd.DataFrame, product_codes: list) -> pd.DataFrame:
    """Filter bets by product code(s)."""
    if "product" not in bets.columns:
        return bets.iloc[0:0].copy()
    return bets[bets["product"].str.upper().isin([p.upper() for p in product_codes])].copy()


def get_exact_score_bets(prod_bets: pd.DataFrame) -> pd.DataFrame:
    """Get Exact Score / Final Score bets."""
    return filter_by_product(prod_bets, ["EXACT_SCORE", "FINAL_SCORE"])


def get_value_singles(prod_bets: pd.DataFrame) -> pd.DataFrame:
    """Get Value Singles bets."""
    return filter_by_product(prod_bets, ["VALUE_SINGLE", "VALUE_SINGLES", "FOOTBALL_SINGLE"])


def get_sgp_parlays(prod_bets: pd.DataFrame) -> pd.DataFrame:
    """Get SGP Parlay bets."""
    return filter_by_product(prod_bets, ["SGP", "SGP_PARLAY"])


def get_basket_bets(prod_bets: pd.DataFrame) -> pd.DataFrame:
    """Get College Basketball bets."""
    return filter_by_product(prod_bets, ["COLLEGE_BASKET", "BASKET_SINGLE", "BASKET_PARLAY", "NCAAB"])


def get_women_1x2(prod_bets: pd.DataFrame) -> pd.DataFrame:
    """Get Women's 1X2 bets."""
    return filter_by_product(prod_bets, ["WOMEN_1X2", "WOMENS_1X2", "W1X2"])


def weighted_roi(df: pd.DataFrame) -> float:
    """
    Calculate ROI with sample weights.
    Useful for blended PROD/BACKTEST metrics where PROD has higher weight.
    """
    if "weight" not in df.columns:
        df = df.assign(weight=1.0)
    stake = (df["stake"] * df["weight"]).sum()
    profit = ((df["payout"] - df["stake"]) * df["weight"]).sum()
    return 100 * profit / stake if stake > 0 else 0.0


def run_backtest(start_date: str, end_date: str, algorithm_fn, load_fixtures_fn, save_bets_fn) -> dict:
    """
    Run backtest on historical fixtures and save results with mode='BACKTEST'.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        algorithm_fn: Function that takes a match and returns bets
        load_fixtures_fn: Function that loads fixtures for date range
        save_bets_fn: Function that saves bets to database
    
    Returns:
        dict with status and count of bets generated
    """
    fixtures = load_fixtures_fn(start_date, end_date)
    total_bets = 0
    
    for match in fixtures:
        bets = algorithm_fn(match)
        if bets:
            save_bets_fn(bets, mode="BACKTEST")
            total_bets += len(bets) if isinstance(bets, list) else 1
    
    return {"status": "done", "bets_generated": total_bets, "matches_processed": len(fixtures)}


def build_training_data(all_bets: pd.DataFrame, backtest_weight: float = 0.3) -> pd.DataFrame:
    """
    Build training dataset combining PROD and BACKTEST data.
    Adds 'source' column to identify origin and 'weight' for sample weighting.
    
    Args:
        all_bets: All bets from database
        backtest_weight: Weight for backtest samples (default 0.3, PROD always 1.0)
    
    Returns:
        DataFrame with 'source' and 'weight' columns for ML training
    """
    prod_bets, backtest_bets = split_bets_by_mode(all_bets)

    prod_bets = prod_bets.assign(source="PROD")
    backtest_bets = backtest_bets.assign(source="BACKTEST")

    train_df = pd.concat([prod_bets, backtest_bets], ignore_index=True)
    
    train_df["weight"] = train_df["source"].map({
        "PROD": 1.0,
        "BACKTEST": backtest_weight,
    })
    
    return train_df


def format_kickoff(date_val) -> str:
    """
    Format match date for display, handling NaT/None/invalid values gracefully.
    Returns formatted string like '25 Nov 20:00' or '25 Nov' for date-only.
    """
    if date_val is None:
        return "TBD"
    
    try:
        if pd.isna(date_val):
            return "TBD"
    except (TypeError, ValueError):
        pass
    
    try:
        if isinstance(date_val, pd.Timestamp):
            if date_val.hour == 0 and date_val.minute == 0:
                return date_val.strftime("%d %b")
            return date_val.strftime("%d %b %H:%M")
        
        from datetime import datetime as dt_module
        if isinstance(date_val, dt_module):
            if date_val.hour == 0 and date_val.minute == 0:
                return date_val.strftime("%d %b")
            return date_val.strftime("%d %b %H:%M")
        
        date_str = str(date_val).strip()
        
        if date_str.upper() in ["NAT", "NONE", "NULL", "", "NATTYPE"]:
            return "TBD"
        
        if 'T' in date_str:
            clean = date_str.replace('Z', '').replace('+00:00', '')
            date_part, time_part = clean.split('T')
            time_short = time_part[:5]
            parsed = dt_module.strptime(f"{date_part} {time_short}", "%Y-%m-%d %H:%M")
            return parsed.strftime("%d %b %H:%M")
        
        import re
        date_only_match = re.match(r'^(\d{4}-\d{2}-\d{2})', date_str)
        if date_only_match:
            date_part = date_only_match.group(1)
            if ' ' in date_str and ':' in date_str:
                try:
                    time_match = re.search(r'(\d{2}:\d{2})', date_str)
                    if time_match:
                        time_part = time_match.group(1)
                        if time_part != "00:00":
                            parsed = dt_module.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
                            return parsed.strftime("%d %b %H:%M")
                except:
                    pass
            parsed = dt_module.strptime(date_part, "%Y-%m-%d")
            return parsed.strftime("%d %b")
        
        parsed = pd.to_datetime(date_val, errors="coerce")
        if pd.isna(parsed):
            return "TBD"
        if parsed.hour == 0 and parsed.minute == 0:
            return parsed.strftime("%d %b")
        return parsed.strftime("%d %b %H:%M")
    except Exception:
        return "TBD"


def normalize_result(raw_result: Optional[str]) -> str:
    """
    Normalize all possible result variants to: WON, LOST, PENDING, VOID.
    Supports English and Swedish terminology.
    """
    if raw_result is None:
        return "PENDING"

    s = str(raw_result).strip().lower()

    win_keywords = [
        "won", "win", "wins", "winner",
        "vinst", "vunnit", "vinna", "green",
        "success"
    ]

    loss_keywords = [
        "lost", "loss", "förlust",
        "förlorat", "red"
    ]

    void_keywords = [
        "void", "push", "refunded",
        "money back", "pushed", "voided",
        "tie", "draw", "oavgjort"
    ]

    if any(k in s for k in win_keywords):
        return "WON"
    if any(k in s for k in loss_keywords):
        return "LOST"
    if any(k in s for k in void_keywords):
        return "VOID"

    if s in ["pending", "open", "not settled", "running", "live", ""]:
        return "PENDING"

    return "PENDING"


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
def load_all_bets_from_db() -> pd.DataFrame:
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
            norm_result,
            mode,
            created_at,
            settled_at,
            home_team,
            away_team,
            match_date,
            legs,
            parlay_description,
            ev,
            selection
        FROM normalized_bets
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

    for col in ["created_at", "settled_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    
    if "match_date" in df.columns:
        def convert_match_date(val):
            if pd.isna(val) or val is None:
                return pd.NaT
            s = str(val).strip()
            if not s or s.upper() in ['NAT', 'NONE', 'NULL']:
                return pd.NaT
            try:
                return pd.to_datetime(s, utc=True)
            except:
                try:
                    return pd.to_datetime(s)
                except:
                    return pd.NaT
        df["match_date"] = df["match_date"].apply(convert_match_date)

    # profit only for settled bets (WON, LOST, VOID) - norm_result comes from database view
    df["profit"] = None
    settled_mask = df["norm_result"].isin(["WON", "LOST", "VOID"])
    
    # Calculate profit: WON gets payout - stake, LOST gets -stake, VOID gets 0
    df.loc[settled_mask & (df["norm_result"] == "WON"), "profit"] = (
        df.loc[settled_mask & (df["norm_result"] == "WON"), "payout"].fillna(0) - 
        df.loc[settled_mask & (df["norm_result"] == "WON"), "stake"]
    )
    df.loc[settled_mask & (df["norm_result"] == "LOST"), "profit"] = (
        -df.loc[settled_mask & (df["norm_result"] == "LOST"), "stake"]
    )
    df.loc[settled_mask & (df["norm_result"] == "VOID"), "profit"] = 0.0

    return df


# ------------- METRICS HELPERS ------------- #

def compute_roi(df: pd.DataFrame) -> dict:
    """Compute stake, payout, profit, ROI and hit-rate for a given slice using normalized results."""
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

    # Ensure norm_result exists
    if "norm_result" not in df.columns:
        df = df.copy()
        df["norm_result"] = df["result"].apply(normalize_result)

    # settled only (WON, LOST, VOID)
    settled = df[df["norm_result"].isin(["WON", "LOST", "VOID"])].copy()
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
    
    # Only count WON payouts for total payout
    won_mask = settled["norm_result"] == "WON"
    total_payout = float(settled.loc[won_mask, "payout"].fillna(0).sum())
    
    profit = total_payout - total_stake
    roi = (profit / total_stake * 100) if total_stake > 0 else 0.0

    # Count wins (only WON, not VOID)
    wins_count = won_mask.sum()
    # Hit rate excludes VOID from denominator
    non_void = settled[settled["norm_result"] != "VOID"]
    hit_rate = (wins_count / len(non_void) * 100) if len(non_void) > 0 else 0.0

    return dict(
        stake=total_stake,
        payout=total_payout,
        profit=profit,
        roi=roi,
        bets=len(settled),
        wins=int(wins_count),
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
        settled["date"] = pd.to_datetime(settled["settled_at"], errors="coerce")
        settled.loc[settled["date"].isna(), "date"] = pd.to_datetime(settled.loc[settled["date"].isna(), "match_date"], errors="coerce")
        settled = settled.dropna(subset=["date"])
        settled["date"] = settled["date"].dt.date
        
        curve = (
            settled.groupby("date")["profit"]
            .sum()
            .cumsum()
            .reset_index(name="cumulative_profit")
        )
        curve["date"] = pd.to_datetime(curve["date"])
        
        fig = px.line(
            curve,
            x="date",
            y="cumulative_profit",
            labels={"date": "Date", "cumulative_profit": "Cumulative Profit (SEK)"},
        )
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#FFFFFF",
            xaxis=dict(
                tickformat="%b %d",
                gridcolor="rgba(255,255,255,0.1)",
            ),
            yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
            height=300,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        fig.update_traces(line_color="#00F59D", line_width=3)
        st.plotly_chart(fig, use_container_width=True)
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
            
            fig = px.bar(
                agg,
                x="product",
                y="ROI",
                labels={"product": "Product", "ROI": "ROI (%)"},
                color="ROI",
                color_continuous_scale=["#FF4444", "#FFAA00", "#00F59D"],
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#FFFFFF",
                xaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                showlegend=False,
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True)
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
    """Render product tab with SGP-style card layout."""
    data = product_filter(df, product_codes)

    st.markdown(f"## {title}")
    st.caption(description)

    if data.empty:
        st.info("No bets for this product yet. Once your engine starts saving picks here, this tab will update automatically.")
        return

    for c in ["odds", "stake", "payout"]:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce")
    
    data["profit"] = data["payout"].fillna(0) - data["stake"].fillna(100)
    data.loc[~data["result"].isin(["WON", "LOST", "WIN", "LOSS"]), "profit"] = pd.NA

    active = data[~data["result"].isin(["WON", "LOST", "WIN", "LOSS", "VOID"])].copy()
    settled = data[data["result"].isin(["WON", "LOST", "WIN", "LOSS"])].copy()

    if not settled.empty:
        total_staked = settled["stake"].sum()
        total_return = settled["payout"].fillna(0).sum()
        profit = total_return - total_staked
        roi = (profit / total_staked * 100) if total_staked > 0 else 0.0
        won_count = (settled["result"].isin(["WON", "WIN"])).sum()
        hit_rate = (won_count / len(settled) * 100) if len(settled) > 0 else 0.0

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
                        All settled bets
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
                        {won_count}/{len(settled)} won
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    if active.empty:
        st.info("No active bets right now.")
    else:
        from datetime import datetime, timedelta
        import pytz
        
        now_utc = datetime.now(pytz.UTC)
        today = now_utc.date()
        tomorrow = today + timedelta(days=1)
        
        def parse_match_date(val):
            if pd.isna(val) or val is None or str(val).strip() == '':
                return pd.NaT
            s = str(val).strip()
            if len(s) == 10 and '-' in s:
                s = s + "T00:00:00Z"
            try:
                return pd.to_datetime(s, utc=True)
            except:
                return pd.NaT
        
        active["match_date_parsed"] = active["match_date"].apply(parse_match_date)
        active["match_day"] = active["match_date_parsed"].dt.date
        
        todays_picks = active[active["match_day"] == today].copy()
        tomorrows_picks = active[active["match_day"] == tomorrow].copy()
        upcoming_picks = active[(active["match_day"] != today) & (active["match_day"] != tomorrow)].copy()
        
        def render_bet_cards(bets_df, section_title, section_emoji):
            st.markdown(f"### {section_emoji} {section_title}")
            if bets_df.empty:
                st.caption(f"No {section_title.lower()} available.")
                return
            
            for _, row in bets_df.iterrows():
                ev = row.get("ev", 0.0) or 0.0
                try:
                    ev = float(ev)
                except Exception:
                    ev = 0.0

                if ev >= 15:
                    ev_bg, ev_border = "rgba(34,197,94,0.18)", "rgba(34,197,94,0.8)"
                elif ev >= 8:
                    ev_bg, ev_border = "rgba(250,204,21,0.14)", "rgba(250,204,21,0.9)"
                elif ev >= 3:
                    ev_bg, ev_border = "rgba(59,130,246,0.14)", "rgba(59,130,246,0.7)"
                else:
                    ev_bg, ev_border = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.6)"

                raw_match_date = row["match_date"] if "match_date" in row.index else None
                match_str = format_kickoff(raw_match_date)
                
                home_team = str(row.get('home_team', '')).replace('"', '&quot;')
                away_team = str(row.get('away_team', '')).replace('"', '&quot;')
                fixture = f"{home_team} vs {away_team}" if away_team else home_team
                odds_val = float(row.get('odds', 0))
                stake_val = float(row.get('stake', 100))
                
                selection = str(row.get('selection', '')).replace('"', '&quot;')
                if not selection or selection.lower() == 'none':
                    selection = ""
                bet_display = selection.replace("Exact Score: ", "").replace("Value Single: ", "") if selection else ""

                card_html = f"""<div style="padding:18px;margin:10px 0;border-radius:16px;background:radial-gradient(circle at top left, rgba(0,255,166,0.14), rgba(15,23,42,0.96));border:1px solid rgba(0,255,166,0.35);box-shadow:0 0 20px rgba(0,255,166,0.25);">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
<div style="font-size:18px;font-weight:600;color:#E5E7EB;">⚽ {fixture}</div>
<div style="font-size:11px;padding:4px 9px;border-radius:999px;background:{ev_bg};border:1px solid {ev_border};color:#E5E7EB;text-transform:uppercase;letter-spacing:0.06em;">EV {ev:+.1f}%</div>
</div>
<div style="font-size:12px;color:#9CA3AF;margin-bottom:6px;">Kickoff: {match_str}</div>
<div style="font-size:22px;font-weight:700;color:#00FFA6;margin:8px 0;letter-spacing:0.02em;">{bet_display}</div>
<div style="display:flex;gap:18px;align-items:baseline;margin-top:4px;">
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Odds</div><div style="font-size:20px;font-weight:600;color:#00FFA6;">{odds_val:.2f}</div></div>
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Stake</div><div style="font-size:18px;font-weight:500;color:#E5E7EB;">{stake_val:.0f} kr</div></div>
</div>
</div>"""
                st.markdown(card_html, unsafe_allow_html=True)
                st.code(f"{fixture} | {bet_display} | Odds {odds_val:.2f} | Stake {stake_val:.0f} kr", language="text")
        
        render_bet_cards(todays_picks, "Today's Picks", "🔥")
        st.markdown("")
        render_bet_cards(tomorrows_picks, "Tomorrow's Picks", "📅")
        
        if not upcoming_picks.empty:
            st.markdown("")
            render_bet_cards(upcoming_picks, "Upcoming Picks", "🗓️")

    st.markdown("---")

    st.markdown("### Performance")
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

    st.markdown("---")
    st.markdown("### Bet History")
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
        
        cols_hist = [c for c in ["settled", "match", "fixture", "odds", "stake", "payout", "profit", "result"] if c in settled.columns and not settled[c].isna().all()]
        st.dataframe(
            settled.sort_values("settled_at", ascending=False)[cols_hist],
            use_container_width=True,
            hide_index=True,
        )


def render_basketball_tab(df: pd.DataFrame):
    """Render College Basketball tab with SGP-style card layout."""
    st.markdown("## College Basketball")
    st.caption("NCAAB value singles and parlays from your basketball engine.")

    singles = product_filter(df, ["BASKET_SINGLE"])
    parlays = product_filter(df, ["BASKET_PARLAY"])
    all_data = product_filter(df, ["BASKET_SINGLE", "BASKET_PARLAY"])

    if all_data.empty:
        st.info("No basketball bets yet. Once your engine starts saving picks here, this tab will update automatically.")
        return

    for c in ["odds", "stake", "payout"]:
        if c in all_data.columns:
            all_data[c] = pd.to_numeric(all_data[c], errors="coerce")
        if c in singles.columns:
            singles[c] = pd.to_numeric(singles[c], errors="coerce")
        if c in parlays.columns:
            parlays[c] = pd.to_numeric(parlays[c], errors="coerce")

    for df_item in [all_data, singles, parlays]:
        df_item["profit"] = df_item["payout"].fillna(0) - df_item["stake"].fillna(100)
        df_item.loc[~df_item["result"].isin(["WON", "LOST", "WIN", "LOSS"]), "profit"] = pd.NA
    
    settled_data = all_data[all_data["result"].isin(["WON", "LOST", "WIN", "LOSS"])].copy()
    active_data = all_data[~all_data["result"].isin(["WON", "LOST", "WIN", "LOSS", "VOID"])].copy()

    if not settled_data.empty:
        total_staked = settled_data["stake"].sum()
        total_return = settled_data["payout"].fillna(0).sum()
        profit = total_return - total_staked
        roi = (profit / total_staked * 100) if total_staked > 0 else 0.0
        won_count = (settled_data["result"].isin(["WON", "WIN"])).sum()
        hit_rate = (won_count / len(settled_data) * 100) if len(settled_data) > 0 else 0.0

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
                        All settled bets
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
                        {won_count}/{len(settled_data)} won
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    singles_active = singles[~singles["result"].isin(["WON", "LOST", "WIN", "LOSS", "VOID"])].copy()
    parlays_active = parlays[~parlays["result"].isin(["WON", "LOST", "WIN", "LOSS", "VOID"])].copy()

    st.markdown("### 🎯 Active Singles")
    if singles_active.empty:
        st.info("No active singles right now.")
    else:
        for _, row in singles_active.iterrows():
            ev = row.get("ev", 0.0) or 0.0
            try:
                ev = float(ev)
            except Exception:
                ev = 0.0

            if ev >= 15:
                ev_bg, ev_border = "rgba(34,197,94,0.18)", "rgba(34,197,94,0.8)"
            elif ev >= 8:
                ev_bg, ev_border = "rgba(250,204,21,0.14)", "rgba(250,204,21,0.9)"
            elif ev >= 3:
                ev_bg, ev_border = "rgba(59,130,246,0.14)", "rgba(59,130,246,0.7)"
            else:
                ev_bg, ev_border = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.6)"

            match_str = format_kickoff(row.get("match_date"))
            
            home_team = str(row.get('home_team', '')).replace('"', '&quot;')
            away_team = str(row.get('away_team', '')).replace('"', '&quot;')
            match_name = f"{home_team} vs {away_team}" if away_team else home_team
            odds_val = float(row.get('odds', 0))
            stake_val = float(row.get('stake', 100))
            
            selection = str(row.get('selection', '')).replace('"', '&quot;')
            if not selection or selection.lower() == 'none':
                selection = "Home Win"
            pick_display = selection

            card_html = f"""<div style="padding:18px;margin:10px 0;border-radius:16px;background:radial-gradient(circle at top left, rgba(59,130,246,0.14), rgba(15,23,42,0.96));border:1px solid rgba(59,130,246,0.35);box-shadow:0 0 20px rgba(59,130,246,0.25);">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
<div style="font-size:18px;font-weight:600;color:#E5E7EB;">🏀 {match_name}</div>
<div style="font-size:11px;padding:4px 9px;border-radius:999px;background:{ev_bg};border:1px solid {ev_border};color:#E5E7EB;text-transform:uppercase;letter-spacing:0.06em;">EV {ev:+.1f}%</div>
</div>
<div style="font-size:12px;color:#9CA3AF;margin-bottom:6px;">Kickoff: {match_str}</div>
<div style="font-size:22px;font-weight:700;color:#3B82F6;margin:8px 0;letter-spacing:0.02em;">📍 {pick_display}</div>
<div style="display:flex;gap:18px;align-items:baseline;margin-top:4px;">
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Odds</div><div style="font-size:20px;font-weight:600;color:#3B82F6;">{odds_val:.2f}</div></div>
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Stake</div><div style="font-size:18px;font-weight:500;color:#E5E7EB;">{stake_val:.0f} kr</div></div>
</div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)
            st.code(f"{match_name} | {pick_display} | Odds {odds_val:.2f}", language="text")

    st.markdown("---")

    st.markdown("### 🎲 Active Parlays")
    if parlays_active.empty:
        st.info("No active parlays right now.")
    else:
        for _, row in parlays_active.iterrows():
            ev = row.get("ev", 0.0) or 0.0
            try:
                ev = float(ev)
            except Exception:
                ev = 0.0

            if ev >= 15:
                ev_bg, ev_border = "rgba(34,197,94,0.18)", "rgba(34,197,94,0.8)"
            elif ev >= 8:
                ev_bg, ev_border = "rgba(250,204,21,0.14)", "rgba(250,204,21,0.9)"
            else:
                ev_bg, ev_border = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.6)"

            match_str = format_kickoff(row.get("match_date"))
            
            home_team = str(row.get('home_team', '')).replace('"', '&quot;')
            away_team = str(row.get('away_team', '')).replace('"', '&quot;')
            match_name = f"{home_team} vs {away_team}" if away_team else home_team
            odds_val = float(row.get('odds', 0))
            stake_val = float(row.get('stake', 100))
            
            selection = str(row.get('selection', '')).replace('"', '&quot;')
            if not selection or selection.lower() == 'none':
                selection = "Parlay"
            pick_display = selection

            card_html = f"""<div style="padding:18px;margin:10px 0;border-radius:16px;background:radial-gradient(circle at top left, rgba(168,85,247,0.14), rgba(15,23,42,0.96));border:1px solid rgba(168,85,247,0.35);box-shadow:0 0 20px rgba(168,85,247,0.25);">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
<div style="font-size:18px;font-weight:600;color:#E5E7EB;">🏀 {match_name}</div>
<div style="font-size:11px;padding:4px 9px;border-radius:999px;background:{ev_bg};border:1px solid {ev_border};color:#E5E7EB;text-transform:uppercase;letter-spacing:0.06em;">EV {ev:+.1f}%</div>
</div>
<div style="font-size:12px;color:#9CA3AF;margin-bottom:6px;">Kickoff: {match_str}</div>
<div style="font-size:22px;font-weight:700;color:#A855F7;margin:8px 0;letter-spacing:0.02em;">📍 {pick_display}</div>
<div style="display:flex;gap:18px;align-items:baseline;margin-top:4px;">
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Odds</div><div style="font-size:20px;font-weight:600;color:#A855F7;">{odds_val:.2f}</div></div>
<div><div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Stake</div><div style="font-size:18px;font-weight:500;color:#E5E7EB;">{stake_val:.0f} kr</div></div>
</div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)
            st.code(f"{match_name} | {pick_display} | Odds {odds_val:.2f}", language="text")

    st.markdown("---")
    st.markdown("### Bet History")

    singles_settled = singles[singles["result"].isin(["WON", "LOST", "WIN", "LOSS"])].copy()
    parlays_settled = parlays[parlays["result"].isin(["WON", "LOST", "WIN", "LOSS"])].copy()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Singles")
        if singles_settled.empty:
            st.caption("No settled singles yet.")
        else:
            s_summary = compute_roi(singles)
            st.markdown(f"**{len(singles_settled)} settled** | ROI: {s_summary['roi']:.1f}% | Profit: {s_summary['profit']:.0f} kr")
            singles_settled["fixture"] = singles_settled.apply(as_fixture, axis=1)
            cols = [c for c in ["fixture", "odds", "result", "profit"] if c in singles_settled.columns]
            if cols:
                st.dataframe(singles_settled[cols].head(15), use_container_width=True, hide_index=True)

    with col2:
        st.markdown("##### Parlays")
        if parlays_settled.empty:
            st.caption("No settled parlays yet.")
        else:
            p_summary = compute_roi(parlays)
            st.markdown(f"**{len(parlays_settled)} settled** | ROI: {p_summary['roi']:.1f}% | Profit: {p_summary['profit']:.0f} kr")
            parlays_settled["fixture"] = parlays_settled.apply(as_fixture, axis=1)
            cols = [c for c in ["fixture", "odds", "result", "profit"] if c in parlays_settled.columns]
            if cols:
                st.dataframe(parlays_settled[cols].head(15), use_container_width=True, hide_index=True)


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
            match_str = format_kickoff(row.get("match_date"))

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
        all_bets = load_all_bets_from_db()
    except Exception as e:
        st.error(
            "Could not load data from the database. "
            "Check your DATABASE_URL and that the `all_bets` view exists."
        )
        st.exception(e)
        return

    with st.expander("Debug: last 20 raw bets"):
        st.dataframe(
            all_bets[["created_at", "match_date", "product", "home_team", "away_team", "result", "mode", "stake", "odds"]]
            .head(20),
            use_container_width=True,
        )

    # Split PROD vs BACKTEST data
    prod_bets, backtest_bets = split_bets_by_mode(all_bets)

    # Tabs for different products
    overview_tab, exact_tab, singles_tab, sgp_tab, women_tab, basket_tab, backtest_tab = st.tabs(
        [
            "Overview",
            "Exact Score",
            "Value Singles",
            "SGP Parlays",
            "Women's 1X2",
            "College Basketball",
            "Backtests",
        ]
    )

    with overview_tab:
        render_overview(prod_bets)

    with exact_tab:
        render_product_tab(
            prod_bets,
            product_codes=["EXACT_SCORE", "FINAL_SCORE"],
            title="Exact Score / Final Score",
            description="All correct-score bets generated by your main football engine.",
        )

    with singles_tab:
        render_product_tab(
            prod_bets,
            product_codes=["VALUE_SINGLE", "VALUE_SINGLES", "FOOTBALL_SINGLE"],
            title="Value Singles",
            description="High-edge single bets across 1X2, over/under, BTTS, corners and more.",
        )

    with sgp_tab:
        render_sgp_parlays_tab()

    with women_tab:
        render_product_tab(
            prod_bets,
            product_codes=["WOMEN_1X2", "WOMENS_1X2", "W1X2"],
            title="Women’s 1X2",
            description="Match-winner bets in women’s football – a softer market with big edges.",
        )

    with basket_tab:
        render_basketball_tab(prod_bets)

    with backtest_tab:
        st.subheader("Backtest Results (Not Included in Live ROI)")
        if backtest_bets.empty:
            st.info("No backtest bets found. All current data is PROD.")
        else:
            # Calculate backtest metrics
            backtest_settled = backtest_bets[backtest_bets["result"].isin(["WON", "LOST", "WIN", "LOSS"])].copy()
            if not backtest_settled.empty:
                bt_roi = compute_roi(backtest_settled)
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Backtest ROI", f"{bt_roi['roi']:.1f}%")
                with col2:
                    st.metric("Backtest Profit", f"{bt_roi['profit']:.0f} kr")
                with col3:
                    won = len(backtest_settled[backtest_settled["result"].isin(["WON", "WIN"])])
                    hit_rate = (won / len(backtest_settled) * 100) if len(backtest_settled) > 0 else 0
                    st.metric("Backtest Hit Rate", f"{hit_rate:.1f}%")
            
            display_cols = [c for c in ["match_date", "home_team", "away_team", "product", "selection", "stake", "odds", "payout", "result", "mode"] if c in backtest_df.columns]
            st.dataframe(
                backtest_bets[display_cols].sort_values("match_date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()