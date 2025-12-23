import os
from datetime import datetime
from typing import List, Optional, Dict

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from sqlalchemy import create_engine, text

from kelly_engine import KellyEngine, suggest_stake, StakeConfig

# ============ CURRENCY CONFIGURATION ============
# All internal calculations use USD. Display shows USD with SEK equivalent.
USD_TO_SEK = 10.8  # Adjust manually when exchange rate changes

# ============ ROI ANALYTICS MODE ============
# Analytics now run in Unit ROI mode. All picks are evaluated using a flat 1 unit 
# stake for performance tracking. This allows high bet volume without tying results 
# to a specific bankroll size. Real-money stakes (if any) are tracked separately.
ANALYTICS_STAKE_UNITS = 1.0  # Flat 1 unit per bet for analytics
SIMULATED_STARTING_BANKROLL_UNITS = 100.0  # Starting simulated bankroll
DYNAMIC_STAKING_ENABLED = False  # Disabled for analytics layer

# Legacy staking (for real money tracker only)
STAKE_PCT = 0.012  # 1.2% per bet
BASE_UNIT_PCT = 0.01  # 1 unit = 1%
STAKE_UNITS = STAKE_PCT / BASE_UNIT_PCT  # 1.2u


def calculate_profit_units(odds: float, outcome: str) -> float:
    """
    Calculate profit in units for a single bet.
    - Win: (odds - 1) * 1.0 units
    - Loss: -1.0 unit
    - Push/Void: 0.0 units
    """
    outcome_lower = str(outcome).lower().strip()
    if outcome_lower in ('won', 'win', 'w', '1'):
        return (float(odds) - 1.0) * ANALYTICS_STAKE_UNITS
    elif outcome_lower in ('lost', 'loss', 'l', '0'):
        return -ANALYTICS_STAKE_UNITS
    return 0.0


def compute_roi_units(df: pd.DataFrame) -> dict:
    """
    Compute units-based ROI metrics for analytics.
    Every bet = 1 unit stake, profit = (odds-1) for wins, -1 for losses.
    """
    if df.empty:
        return dict(
            units_staked=0.0,
            units_won=0.0,
            roi=0.0,
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            hit_rate=0.0,
            simulated_bankroll=SIMULATED_STARTING_BANKROLL_UNITS,
        )
    
    if "norm_result" not in df.columns:
        df = df.copy()
        if "result" in df.columns:
            df["norm_result"] = df["result"].apply(normalize_result)
        else:
            df["norm_result"] = "PENDING"
    
    settled = df[df["norm_result"].isin(["WON", "LOST", "VOID"])].copy()
    if settled.empty:
        return dict(
            units_staked=float(len(df)) * ANALYTICS_STAKE_UNITS,
            units_won=0.0,
            roi=0.0,
            bets=len(df),
            wins=0,
            losses=0,
            pushes=0,
            hit_rate=0.0,
            simulated_bankroll=SIMULATED_STARTING_BANKROLL_UNITS,
        )
    
    wins = len(settled[settled["norm_result"] == "WON"])
    losses = len(settled[settled["norm_result"] == "LOST"])
    pushes = len(settled[settled["norm_result"] == "VOID"])
    
    if "odds" not in settled.columns:
        settled["odds"] = 2.0
    
    settled["profit_units"] = settled.apply(
        lambda row: calculate_profit_units(row.get("odds", 2.0), row["norm_result"]),
        axis=1
    )
    
    # Exclude VOID bets from stake/ROI calculation - only count WON and LOST
    non_void = settled[settled["norm_result"] != "VOID"]
    units_staked = float(len(non_void)) * ANALYTICS_STAKE_UNITS
    units_won = float(non_void["profit_units"].sum())
    roi = (units_won / units_staked * 100) if units_staked > 0 else 0.0
    
    non_void = settled[settled["norm_result"] != "VOID"]
    hit_rate = (wins / len(non_void) * 100) if len(non_void) > 0 else 0.0
    
    simulated_bankroll = SIMULATED_STARTING_BANKROLL_UNITS + units_won
    
    return dict(
        units_staked=units_staked,
        units_won=units_won,
        roi=roi,
        bets=len(settled),
        wins=wins,
        losses=losses,
        pushes=pushes,
        hit_rate=hit_rate,
        simulated_bankroll=simulated_bankroll,
    )


def format_units(units: float) -> str:
    """Format units for display with + sign for positive values."""
    sign = "+" if units >= 0 else ""
    return f"{sign}{units:.1f} units"


def format_roi(roi: float) -> str:
    """Format ROI for display with + sign for positive values."""
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi:.1f}% ROI"


def get_stake_display(stake_sek: float) -> str:
    """
    Format stake for display - UNITS ONLY (no money references).
    """
    return "1 unit"


def get_stake_display_full(stake_sek: float) -> str:
    """
    Format stake for display - UNITS ONLY (no money references).
    """
    return "1 unit"


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


def get_training_data_stats() -> dict:
    """Get statistics from training_data table for AI model improvement."""
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return {}
        
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN bet_placed = true THEN 1 END) as bets_placed,
                    COUNT(CASE WHEN bet_placed = false THEN 1 END) as predictions_only,
                    COUNT(DISTINCT home_team || ' vs ' || away_team) as unique_matches,
                    COUNT(DISTINCT league) as unique_leagues,
                    COUNT(CASE WHEN analysis_type = 'exact_score_bet' THEN 1 END) as exact_score_bets,
                    COUNT(CASE WHEN analysis_type = 'exact_score_filtered' THEN 1 END) as exact_score_filtered,
                    COUNT(CASE WHEN analysis_type = 'exact_score_skipped' THEN 1 END) as exact_score_skipped,
                    COUNT(CASE WHEN data_source = 'value_singles_engine' THEN 1 END) as value_singles_records,
                    COUNT(CASE WHEN data_source = 'sgp_engine' THEN 1 END) as sgp_records,
                    MIN(created_at) as earliest_record,
                    MAX(created_at) as latest_record
                FROM training_data
            """))
            row = result.fetchone()
            if row:
                return {
                    'total_records': row[0] or 0,
                    'bets_placed': row[1] or 0,
                    'predictions_only': row[2] or 0,
                    'unique_matches': row[3] or 0,
                    'unique_leagues': row[4] or 0,
                    'exact_score_bets': row[5] or 0,
                    'exact_score_filtered': row[6] or 0,
                    'exact_score_skipped': row[7] or 0,
                    'value_singles_records': row[8] or 0,
                    'parlay_records': row[9] or 0,
                    'earliest_record': row[10],
                    'latest_record': row[11]
                }
    except Exception as e:
        st.sidebar.warning(f"AI training data stats unavailable: {e}")
    return {}


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


def get_parlays(prod_bets: pd.DataFrame) -> pd.DataFrame:
    """Get Parlay bets."""
    return filter_by_product(prod_bets, ["SGP", "SGP_PARLAY", "ML_PARLAY", "PARLAY"])


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

st_autorefresh(interval=300000, limit=None, key="dashboard_autorefresh")  # 5 min refresh

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
            selection,
            clv_pct,
            odds_by_bookmaker,
            best_odds_value,
            best_odds_bookmaker
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
    """Compute stake, payout, profit, ROI and hit-rate for a given slice using normalized results.
    
    Note: Database stores values in SEK. We convert to USD for display using USD_TO_SEK rate.
    ROI percentage remains the same regardless of currency.
    """
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
        # Convert SEK to USD
        stake_sek = float(df["stake"].sum())
        return dict(
            stake=stake_sek / USD_TO_SEK,
            payout=0.0,
            profit=0.0,
            roi=0.0,
            bets=len(df),
            wins=0,
            hit_rate=0.0,
        )

    # Exclude VOID bets from stake/ROI calculation - only count WON and LOST
    non_void = settled[settled["norm_result"] != "VOID"]
    total_stake_sek = float(non_void["stake"].sum())
    
    # Only count WON payouts for total payout
    won_mask = non_void["norm_result"] == "WON"
    total_payout_sek = float(non_void.loc[won_mask, "payout"].fillna(0).sum())
    
    profit_sek = total_payout_sek - total_stake_sek
    roi = (profit_sek / total_stake_sek * 100) if total_stake_sek > 0 else 0.0

    # Count wins (only WON, not VOID)
    wins_count = won_mask.sum()
    # Hit rate excludes VOID from denominator
    non_void = settled[settled["norm_result"] != "VOID"]
    hit_rate = (wins_count / len(non_void) * 100) if len(non_void) > 0 else 0.0

    # Return values converted to USD
    return dict(
        stake=total_stake_sek / USD_TO_SEK,
        payout=total_payout_sek / USD_TO_SEK,
        profit=profit_sek / USD_TO_SEK,
        roi=roi,  # ROI is currency-independent
        bets=len(settled),
        wins=int(wins_count),
        hit_rate=hit_rate,
    )


def format_money(x: float) -> str:
    """Format money in USD with SEK equivalent: '1,234 USD (≈ 13,327 SEK)'"""
    sek = x * USD_TO_SEK
    if abs(x) >= 1000:
        return f"{x:,.0f} USD (≈ {sek:,.0f} SEK)"
    else:
        return f"{x:,.2f} USD (≈ {sek:,.0f} SEK)"


def format_money_short(x: float) -> str:
    """Short format for inline use: '1,234 USD'"""
    if abs(x) >= 1000:
        return f"{x:,.0f} USD"
    else:
        return f"{x:,.2f} USD"


def format_money_inline(x: float) -> str:
    """Inline format with both currencies for cards/UI: '1,234 USD (≈13,327 SEK)'"""
    sek = x * USD_TO_SEK
    return f"{x:,.0f} USD (≈{sek:,.0f} SEK)"


def format_pct(x: float) -> str:
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.1f}%"


def product_filter(df: pd.DataFrame, product_codes: List[str]) -> pd.DataFrame:
    return df[df["product"].isin(product_codes)].copy()


# ------------- FREE PREDICTIONS (TEASER) ------------- #

FREE_PICKS_CONFIG = {
    'max_picks': 3,
    'min_ev': 0.06,  # 6% minimum EV
    'preferred_ev': 0.08,  # 8%+ preferred
    'min_odds': 1.80,
    'max_odds': 3.50,
    'product_codes': ['VALUE_SINGLE', 'VALUE_SINGLES', 'FOOTBALL_SINGLE']
}

def get_free_predictions() -> list:
    """
    Select 1-3 free predictions for teaser display.
    Criteria: EV >= 6%, odds 1.80-3.50, sorted by EV descending.
    """
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    query = text("""
        SELECT 
            id, home_team, away_team, selection, market, odds, 
            edge_percentage as ev, confidence, league, match_date,
            odds_by_bookmaker, best_odds_value, best_odds_bookmaker,
            product
        FROM football_opportunities
        WHERE LOWER(status) = 'pending'
          AND edge_percentage >= :min_ev
          AND odds >= :min_odds
          AND odds <= :max_odds
          AND product IN ('VALUE_SINGLE', 'VALUE_SINGLES', 'FOOTBALL_SINGLE')
        ORDER BY edge_percentage DESC
        LIMIT :max_picks
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {
                'min_ev': FREE_PICKS_CONFIG['min_ev'] * 100,  # Config is 0.06 -> 6.0 for DB
                'min_odds': FREE_PICKS_CONFIG['min_odds'],
                'max_odds': FREE_PICKS_CONFIG['max_odds'],
                'max_picks': FREE_PICKS_CONFIG['max_picks']
            })
            rows = result.fetchall()
            columns = result.keys()
            picks = [dict(zip(columns, row)) for row in rows]
            return picks
    except Exception as e:
        print(f"Error fetching free predictions: {e}")
        return []


def generate_why_bullets(pick: dict) -> list:
    """Generate 2 'Why this pick' bullets based on the pick data."""
    bullets = []
    
    ev = float(pick.get('ev', 0) or 0)
    odds = float(pick.get('odds', 0) or 0)
    confidence = float(pick.get('confidence', 0) or 0)
    best_odds = float(pick.get('best_odds_value', odds) or odds)
    
    # Bullet 1: Model probability vs market implied
    if odds > 0:
        implied_prob = 1 / odds * 100
        model_prob = implied_prob + (ev / 100 * implied_prob) if ev > 0 else implied_prob
        bullets.append(f"Model probability {model_prob:.0f}% vs market implied {implied_prob:.0f}%")
    
    # Bullet 2: Best odds above fair price OR confidence level
    if best_odds > odds:
        edge = ((best_odds / odds) - 1) * 100
        bullets.append(f"Best available odds {edge:.1f}% above average market price")
    elif confidence >= 70:
        bullets.append(f"High confidence pick backed by strong historical patterns")
    elif ev >= 8:
        bullets.append(f"Strong edge detected with +{ev:.1f}% expected value")
    else:
        bullets.append(f"Value opportunity identified through statistical modeling")
    
    return bullets[:2]


def render_free_predictions_tab():
    """Render the Free Predictions teaser tab."""
    st.markdown("## Free Predictions")
    st.caption("A sample of our AI-powered predictions. Quality preview of what the full system delivers.")
    
    # Legal disclaimer
    st.markdown("""
    <div style="padding:10px 14px;border-radius:8px;background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.25);margin-bottom:20px;">
        <span style="color:#FBBF24;font-size:12px;">For informational purposes only. Not betting advice. No guarantees.</span>
    </div>
    """, unsafe_allow_html=True)
    
    picks = get_free_predictions()
    
    if not picks:
        st.info("No free predictions available right now. Check back later for quality picks meeting our strict EV criteria.")
        return
    
    st.markdown(f"### Today's Free Picks ({len(picks)})")
    
    for pick in picks:
        ev = float(pick.get('ev', 0) or 0)
        odds = float(pick.get('odds', 0) or 0)
        best_odds = float(pick.get('best_odds_value', odds) or odds)
        home_team = pick.get('home_team', '')
        away_team = pick.get('away_team', '')
        selection = pick.get('selection', '')
        league = pick.get('league', '')
        market = pick.get('market', 'Value Single')
        
        # EV badge color
        if ev >= 10:
            ev_color = "#10B981"  # Green for strong
        elif ev >= 6:
            ev_color = "#F59E0B"  # Amber for solid
        else:
            ev_color = "#6B7280"  # Gray
        
        # Parse odds by bookmaker for top 2
        odds_by_bookmaker = pick.get('odds_by_bookmaker', {})
        if isinstance(odds_by_bookmaker, str):
            try:
                import json
                odds_by_bookmaker = json.loads(odds_by_bookmaker) if odds_by_bookmaker else {}
            except:
                odds_by_bookmaker = {}
        
        # Get best and 2nd best odds
        bookmaker_html = ""
        if odds_by_bookmaker and isinstance(odds_by_bookmaker, dict):
            sorted_books = sorted(odds_by_bookmaker.items(), key=lambda x: float(x[1]) if x[1] else 0, reverse=True)
            best_book = sorted_books[0] if len(sorted_books) > 0 else None
            second_best = sorted_books[1] if len(sorted_books) > 1 else None
            
            bookmaker_html = '<div style="display:flex;gap:8px;margin-top:12px;">'
            if best_book:
                bookmaker_html += f'''
                <div style="padding:8px 14px;border-radius:8px;background:linear-gradient(135deg, rgba(34,197,94,0.3), rgba(16,185,129,0.2));border:1px solid rgba(34,197,94,0.6);">
                    <div style="font-size:9px;color:#22C55E;font-weight:600;">BEST</div>
                    <div style="font-size:11px;color:#E5E7EB;">{best_book[0]}</div>
                    <div style="font-size:18px;font-weight:700;color:#22C55E;">{float(best_book[1]):.2f}</div>
                </div>'''
            if second_best:
                bookmaker_html += f'''
                <div style="padding:8px 14px;border-radius:8px;background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.4);">
                    <div style="font-size:9px;color:#60A5FA;font-weight:600;">2ND</div>
                    <div style="font-size:11px;color:#E5E7EB;">{second_best[0]}</div>
                    <div style="font-size:18px;font-weight:700;color:#60A5FA;">{float(second_best[1]):.2f}</div>
                </div>'''
            bookmaker_html += '</div>'
        elif odds > 0:
            bookmaker_html = f'''
            <div style="display:flex;gap:8px;margin-top:12px;">
                <div style="padding:8px 14px;border-radius:8px;background:linear-gradient(135deg, rgba(34,197,94,0.3), rgba(16,185,129,0.2));border:1px solid rgba(34,197,94,0.6);">
                    <div style="font-size:9px;color:#22C55E;font-weight:600;">ODDS</div>
                    <div style="font-size:18px;font-weight:700;color:#22C55E;">{odds:.2f}</div>
                </div>
            </div>'''
        
        # Generate why bullets
        bullets = generate_why_bullets(pick)
        bullets_html = ""
        for bullet in bullets:
            bullets_html += f'<div style="font-size:12px;color:#9CA3AF;margin-top:4px;">• {bullet}</div>'
        
        # Main card
        st.markdown(f"""
        <div style="padding:18px;margin:12px 0;border-radius:14px;background:radial-gradient(circle at top left, rgba(16,185,129,0.12), rgba(15,23,42,0.95));border:1px solid rgba(16,185,129,0.35);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div style="font-size:12px;color:#9CA3AF;">{league}</div>
                <div style="font-size:12px;padding:4px 10px;border-radius:999px;background:{ev_color}22;color:{ev_color};font-weight:600;">EV +{ev:.1f}%</div>
            </div>
            <div style="font-size:17px;color:#E5E7EB;font-weight:600;margin-bottom:6px;">{home_team} vs {away_team}</div>
            <div style="font-size:15px;color:#6EE7B7;margin-bottom:8px;">{selection}</div>
            {bookmaker_html}
            <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(148,163,184,0.15);">
                <div style="font-size:11px;color:#6B7280;text-transform:uppercase;margin-bottom:6px;">Why this pick</div>
                {bullets_html}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Positioning copy
    st.markdown("""
    <div style="margin-top:24px;padding:16px;border-radius:10px;background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);text-align:center;">
        <div style="font-size:13px;color:#A5B4FC;">This is a sample from PGR Sports Analytics.</div>
        <div style="font-size:12px;color:#9CA3AF;margin-top:4px;">Full access includes more picks, advanced tools, and market comparison.</div>
    </div>
    """, unsafe_allow_html=True)


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
    """Build cumulative profit series for equity curve (converted to USD)."""
    if settled.empty:
        return pd.DataFrame({"when": [], "bank": []})
    s = settled.copy()
    s = s.sort_values(["settled_at", "match_date", "created_at"], na_position="last")
    s["stake"] = s["stake"].astype(float)
    s["profit"] = s["profit"].astype(float)
    settled_ts = pd.to_datetime(s["settled_at"], utc=True, errors="coerce")
    match_ts = pd.to_datetime(s["match_date"], utc=True, errors="coerce")
    s["when"] = settled_ts.fillna(match_ts).dt.tz_localize(None)
    # Convert SEK to USD for display
    s["bank"] = s["profit"].cumsum() / USD_TO_SEK
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
    """Prepare a pretty table with decimal odds (2 decimals). Converts SEK to USD."""
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

    # Convert SEK to USD and format
    for col in ["stake", "payout", "profit"]:
        if col in out.columns:
            out[col] = (out[col].astype(float) / USD_TO_SEK).round(2)

    if "odds" in out.columns:
        out["odds"] = out["odds"].astype(float).round(2)

    # Rename headers (with USD indicator)
    rename_map = {
        "match_date": "Match Date",
        "home_team": "Home",
        "away_team": "Away",
        "product": "Product",
        "stake": "Stake (USD)",
        "odds": "Odds",
        "payout": "Payout (USD)",
        "profit": "Profit (USD)",
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


def get_clv_stats_for_dashboard() -> dict:
    """Fetch CLV stats for dashboard display."""
    try:
        from clv_service import get_clv_stats
        return get_clv_stats()
    except Exception as e:
        return {'avg_clv_all': None, 'avg_clv_last_100': None, 'positive_share': None, 'total_with_clv': 0}


def render_overview(df: pd.DataFrame):
    st.markdown(
        '<div class="pgr-header">PGR Sports Analytics</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="pgr-subtitle">ROI + Units Performance Mode | Flat 1u stake per bet for analytics</div>',
        unsafe_allow_html=True,
    )

    units_summary = compute_roi_units(df)
    money_summary = compute_roi(df)
    clv_stats = get_clv_stats_for_dashboard()

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        metric_card(
            "Total ROI",
            format_roi(units_summary["roi"]),
            f"On {units_summary['units_staked']:.0f} units staked",
        )
    with col2:
        metric_card(
            "Total Profit",
            format_units(units_summary["units_won"]),
            "Based on 1u flat stake per bet",
        )
    with col3:
        metric_card(
            "Hit Rate",
            format_pct(units_summary["hit_rate"]),
            f"{units_summary['wins']}W / {units_summary['losses']}L / {units_summary['pushes']}P",
        )
    with col4:
        clv_value = clv_stats.get('avg_clv_last_100')
        clv_display = f"{clv_value:+.1f}%" if clv_value is not None else "N/A"
        clv_positive = clv_stats.get('positive_share')
        clv_sub = f"{clv_positive:.0f}% positive CLV" if clv_positive is not None else "Collecting closing odds..."
        metric_card(
            "Average CLV",
            clv_display,
            clv_sub,
        )
    with col5:
        metric_card(
            "Bets Tracked",
            f"{units_summary['bets']:,}",
            f"Simulated: {units_summary['simulated_bankroll']:.1f}u",
        )

    with st.expander("Real Money Tracker (Optional)", expanded=False):
        st.caption("Legacy view showing actual USD/SEK stakes - for personal reference only")
        rcol1, rcol2, rcol3 = st.columns(3)
        with rcol1:
            st.metric("Real Profit (USD)", f"${money_summary['profit']:,.0f}")
        with rcol2:
            st.metric("Real Stakes (USD)", f"${money_summary['stake']:,.0f}")
        with rcol3:
            st.metric("Money ROI", f"{money_summary['roi']:+.1f}%")

    st.markdown("### 📅 Daily Units")
    
    try:
        from daily_units_service import get_daily_units
        daily_data = get_daily_units(days_back=14)
        
        if daily_data.get('daily_units'):
            dcol1, dcol2, dcol3 = st.columns(3)
            with dcol1:
                month_units = daily_data['month_summary']['total_units']
                month_sign = "+" if month_units >= 0 else ""
                month_color = "#00F59D" if month_units >= 0 else "#FF4444"
                st.markdown(f"""
                    <div style="text-align: center; padding: 10px;">
                        <div style="font-size: 0.9rem; color: #888;">This Month</div>
                        <div style="font-size: 1.8rem; font-weight: bold; color: {month_color};">{month_sign}{month_units:.1f}u</div>
                    </div>
                """, unsafe_allow_html=True)
            with dcol2:
                if daily_data.get('best_day'):
                    best = daily_data['best_day']
                    st.markdown(f"""
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 0.9rem; color: #888;">Best Day</div>
                            <div style="font-size: 1.4rem; font-weight: bold; color: #00F59D;">+{best['units']:.1f}u</div>
                            <div style="font-size: 0.8rem; color: #666;">{best['date']}</div>
                        </div>
                    """, unsafe_allow_html=True)
            with dcol3:
                if daily_data.get('worst_day'):
                    worst = daily_data['worst_day']
                    st.markdown(f"""
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 0.9rem; color: #888;">Worst Day</div>
                            <div style="font-size: 1.4rem; font-weight: bold; color: #FF4444;">{worst['units']:.1f}u</div>
                            <div style="font-size: 0.8rem; color: #666;">{worst['date']}</div>
                        </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("**Recent Days:**")
            for day in daily_data['daily_units'][:7]:
                units = day['units']
                sign = "+" if units >= 0 else ""
                color = "#00F59D" if units > 0 else ("#FF4444" if units < 0 else "#888888")
                st.markdown(
                    f"<span style='color: #888;'>{day['date']}</span> &nbsp; "
                    f"<span style='color: {color}; font-weight: bold;'>{sign}{units:.2f} units</span> "
                    f"<span style='color: #666;'>({day['bet_count']} bets)</span>",
                    unsafe_allow_html=True
                )
        else:
            st.info("No settled bets yet - daily units will appear once results are in.")
    except Exception as e:
        st.warning(f"Daily units unavailable")

    st.markdown("### 📈 Equity Curve (Units)")

    settled = df[df["profit"].notna()].copy()
    if not settled.empty:
        settled["date"] = pd.to_datetime(settled["match_date"], errors="coerce")
        settled = settled.dropna(subset=["date"])
        settled["date"] = settled["date"].dt.date
        
        if "odds" not in settled.columns:
            settled["odds"] = 2.0
        if "norm_result" not in settled.columns:
            settled["norm_result"] = settled["result"].apply(normalize_result) if "result" in settled.columns else "PENDING"
        
        settled["profit_units"] = settled.apply(
            lambda row: calculate_profit_units(row.get("odds", 2.0), row.get("norm_result", "PENDING")),
            axis=1
        )
        
        curve = (
            settled.groupby("date")["profit_units"]
            .sum()
            .cumsum()
            .reset_index(name="cumulative_units")
        )
        curve["date"] = pd.to_datetime(curve["date"])
        
        fig = px.line(
            curve,
            x="date",
            y="cumulative_units",
            labels={"date": "Date", "cumulative_units": "Cumulative Profit (Units)"},
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
        st.info("No settled bets yet - equity curve will appear once results are in.")

    st.markdown("### 🧩 ROI by Product (Units)")

    if not df.empty:
        prod_settled = df[df["profit"].notna()].copy()
        if not prod_settled.empty:
            agg = (
                prod_settled.groupby("product")
                .apply(lambda x: compute_roi_units(x)["roi"])
                .reset_index(name="ROI")
            )
            agg = agg.sort_values("ROI", ascending=False)
            
            units_agg = (
                prod_settled.groupby("product")
                .apply(lambda x: compute_roi_units(x)["units_won"])
                .reset_index(name="Units")
            )
            agg = agg.merge(units_agg, on="product")
            
            fig = px.bar(
                agg,
                x="product",
                y="ROI",
                labels={"product": "Product", "ROI": "ROI (%)"},
                color="ROI",
                color_continuous_scale=["#FF4444", "#FFAA00", "#00F59D"],
                hover_data={"Units": ":.1f"},
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
            
            st.markdown("**Per-Product Summary (Units)**")
            for _, row in agg.iterrows():
                prod_stats = compute_roi_units(prod_settled[prod_settled["product"] == row["product"]])
                st.markdown(
                    f"**{row['product']}**: {format_roi(prod_stats['roi'])} | "
                    f"{format_units(prod_stats['units_won'])} | "
                    f"{prod_stats['bets']} bets | "
                    f"{prod_stats['hit_rate']:.1f}% hit rate"
                )
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
    
    # AI Training Data Stats
    st.markdown("### 🤖 AI Training Data Collection")
    training_stats = get_training_data_stats()
    if training_stats and training_stats.get('total_records', 0) > 0:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            metric_card(
                "Total Records",
                f"{training_stats['total_records']:,}",
                f"Training data points"
            )
        with col2:
            metric_card(
                "Bets Placed",
                f"{training_stats['bets_placed']:,}",
                "With actual stakes"
            )
        with col3:
            metric_card(
                "Predictions Only",
                f"{training_stats['predictions_only']:,}",
                "AI analysis captured"
            )
        with col4:
            metric_card(
                "Unique Matches",
                f"{training_stats['unique_matches']:,}",
                f"Across {training_stats['unique_leagues']} leagues"
            )
        
        with st.expander("View Data Collection Breakdown"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Value Singles Engine**")
                st.write(f"- Records: {training_stats.get('value_singles_records', 0):,}")
            with col2:
                st.markdown("**Parlay Engine**")
                st.write(f"- Records: {training_stats.get('parlay_records', 0):,}")
    else:
        st.info("AI training data collection starting - stats will appear after next prediction cycle.")
    
    # Learning Track Record Section
    render_learning_track_record()


def render_learning_track_record():
    """Render the Learning Track Record section showing AI prediction performance."""
    from data_collector import get_collector
    
    st.markdown("### 📊 Learning System Track Record")
    
    collector = get_collector()
    summary = collector.get_track_record_summary()
    
    if summary.get('error') or summary.get('settled', 0) == 0:
        st.info("Track record will appear once predictions are settled and verified. Currently collecting data...")
        return
    
    # Top-level KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(
            f"""
            <div style="padding:14px 16px;border-radius:12px;
                background:rgba(0,245,157,0.08);border:1px solid rgba(0,245,157,0.3);">
                <div style="font-size:11px;text-transform:uppercase;color:#00F59D;">Overall Accuracy</div>
                <div style="font-size:28px;font-weight:700;color:#00F59D;">
                    {summary['accuracy_pct']:.1f}%
                </div>
                <div style="font-size:12px;color:#9CA3AF;">
                    {summary['correct']}/{summary['settled']} correct
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with col2:
        st.markdown(
            f"""
            <div style="padding:14px 16px;border-radius:12px;
                background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.3);">
                <div style="font-size:11px;text-transform:uppercase;color:#3B82F6;">Bets Accuracy</div>
                <div style="font-size:28px;font-weight:700;color:#3B82F6;">
                    {summary['bets_accuracy_pct']:.1f}%
                </div>
                <div style="font-size:12px;color:#9CA3AF;">
                    {summary['bets_correct']}/{summary['bets_settled']} bets won
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with col3:
        st.markdown(
            f"""
            <div style="padding:14px 16px;border-radius:12px;
                background:rgba(168,85,247,0.08);border:1px solid rgba(168,85,247,0.3);">
                <div style="font-size:11px;text-transform:uppercase;color:#A855F7;">Predictions Accuracy</div>
                <div style="font-size:28px;font-weight:700;color:#A855F7;">
                    {summary['predictions_accuracy_pct']:.1f}%
                </div>
                <div style="font-size:12px;color:#9CA3AF;">
                    {summary['predictions_correct']}/{summary['predictions_settled']} correct (no bet)
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with col4:
        st.markdown(
            f"""
            <div style="padding:14px 16px;border-radius:12px;
                background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.2);">
                <div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Total Data Points</div>
                <div style="font-size:28px;font-weight:700;color:#FFFFFF;">
                    {summary['total_records']:,}
                </div>
                <div style="font-size:12px;color:#9CA3AF;">
                    {summary['settled']} settled
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    # Expandable sections for detailed breakdown
    with st.expander("📈 Performance by Prediction Type", expanded=False):
        by_type = collector.get_accuracy_by_type()
        if by_type:
            import pandas as pd
            type_df = pd.DataFrame(by_type)
            type_df.columns = ['Type', 'Total', 'Settled', 'Correct', 'Accuracy %', 'Avg Prob %', 'Avg Edge %']
            type_df['Accuracy %'] = type_df['Accuracy %'].apply(lambda x: f"{x:.1f}%")
            type_df['Avg Prob %'] = type_df['Avg Prob %'].apply(lambda x: f"{x*100:.1f}%" if x else "N/A")
            type_df['Avg Edge %'] = type_df['Avg Edge %'].apply(lambda x: f"{x:.1f}%" if x else "N/A")
            st.dataframe(type_df, use_container_width=True, hide_index=True)
        else:
            st.info("No data by type yet.")
    
    with st.expander("🏆 Performance by League", expanded=False):
        by_league = collector.get_accuracy_by_league(min_samples=3)
        if by_league:
            import pandas as pd
            league_df = pd.DataFrame(by_league)
            league_df.columns = ['League', 'Total', 'Settled', 'Correct', 'Accuracy %']
            league_df['Accuracy %'] = league_df['Accuracy %'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(league_df, use_container_width=True, hide_index=True)
        else:
            st.info("Need more settled predictions per league (min 3) to show breakdown.")
    
    # Accuracy Trend Chart
    daily_data = collector.get_daily_accuracy(days=30)
    if daily_data and len(daily_data) >= 2:
        import pandas as pd
        import plotly.graph_objects as go
        
        daily_df = pd.DataFrame(daily_data)
        daily_df['date'] = pd.to_datetime(daily_df['date'])
        
        # Calculate 7-day rolling accuracy
        daily_df['rolling_correct'] = daily_df['correct'].rolling(window=7, min_periods=1).sum()
        daily_df['rolling_settled'] = daily_df['settled'].rolling(window=7, min_periods=1).sum()
        daily_df['rolling_accuracy'] = (daily_df['rolling_correct'] / daily_df['rolling_settled'] * 100).fillna(0)
        
        fig = go.Figure()
        
        # Daily accuracy bars
        fig.add_trace(go.Bar(
            x=daily_df['date'],
            y=daily_df['accuracy_pct'],
            name='Daily Accuracy',
            marker_color='rgba(0,245,157,0.4)',
            hovertemplate='%{x}<br>Accuracy: %{y:.1f}%<extra></extra>'
        ))
        
        # 7-day rolling average line
        fig.add_trace(go.Scatter(
            x=daily_df['date'],
            y=daily_df['rolling_accuracy'],
            mode='lines',
            name='7-Day Average',
            line=dict(color='#00F59D', width=3),
            hovertemplate='%{x}<br>7-Day Avg: %{y:.1f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title='Prediction Accuracy Over Time',
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#FFFFFF",
            xaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Date"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Accuracy %", range=[0, 100]),
            height=300,
            margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Model Calibration Chart
    calibration_data = collector.get_calibration_data(bins=10)
    if calibration_data and len(calibration_data) >= 2:
        with st.expander("🎯 Model Calibration (Predicted vs Actual)", expanded=False):
            import pandas as pd
            import plotly.graph_objects as go
            
            cal_df = pd.DataFrame(calibration_data)
            
            fig = go.Figure()
            
            # Perfect calibration line
            fig.add_trace(go.Scatter(
                x=[0, 100],
                y=[0, 100],
                mode='lines',
                name='Perfect Calibration',
                line=dict(color='rgba(255,255,255,0.3)', dash='dash'),
            ))
            
            # Actual calibration
            fig.add_trace(go.Scatter(
                x=cal_df['predicted_rate'],
                y=cal_df['actual_rate'],
                mode='markers+lines',
                name='Model Calibration',
                marker=dict(size=10, color='#00F59D'),
                line=dict(color='#00F59D', width=2),
                text=cal_df['probability_bin'],
                hovertemplate='Bin: %{text}<br>Predicted: %{x:.1f}%<br>Actual: %{y:.1f}%<extra></extra>'
            ))
            
            fig.update_layout(
                title='Model Calibration: Predicted Probability vs Actual Hit Rate',
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#FFFFFF",
                xaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Predicted Probability %", range=[0, 100]),
                yaxis=dict(gridcolor="rgba(255,255,255,0.1)", title="Actual Hit Rate %", range=[0, 100]),
                height=300,
                margin=dict(l=0, r=0, t=40, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            
            st.plotly_chart(fig, use_container_width=True)
            st.caption("A well-calibrated model follows the diagonal line. Points above = model underestimates, below = overestimates.")


def render_product_tab(
    df: pd.DataFrame,
    product_codes: List[str],
    title: str,
    description: str,
):
    """Render product tab with Parlay-style card layout."""
    data = product_filter(df, product_codes)

    st.markdown(f"## {title}")
    st.caption(description)
    
    # Add odds warning for Exact Score products
    if "EXACT_SCORE" in product_codes or "FINAL_SCORE" in product_codes:
        st.markdown(
            """<div style="padding:8px 12px;border-radius:8px;background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.4);margin-bottom:16px;">
                <span style="color:#FBBF24;">⚠️</span> <span style="color:#E5E7EB;font-size:13px;">Odds may differ from your bookmaker. Our odds are calculated from statistical models.</span>
            </div>""",
            unsafe_allow_html=True
        )

    if data.empty:
        st.info("No bets for this product yet. Once your engine starts saving picks here, this tab will update automatically.")
        return

    for c in ["odds", "stake", "payout"]:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce")
    
    data["profit"] = data["payout"].fillna(0) - data["stake"].fillna(100)
    
    # Use norm_result for filtering (normalized to WON/LOST/PENDING/VOID)
    result_col = "norm_result" if "norm_result" in data.columns else "result"
    data.loc[~data[result_col].isin(["WON", "LOST"]), "profit"] = pd.NA

    active = data[~data[result_col].isin(["WON", "LOST", "VOID"])].copy()
    settled = data[data[result_col].isin(["WON", "LOST"])].copy()

    if not settled.empty:
        units_staked = len(settled)
        won_count = (settled[result_col] == "WON").sum()
        lost_count = (settled[result_col] == "LOST").sum()
        
        won_bets = settled[settled[result_col] == "WON"]
        profit_units = 0.0
        for _, bet in won_bets.iterrows():
            odds = float(bet.get("odds", 2.0) or 2.0)
            profit_units += (odds - 1)
        profit_units -= lost_count
        
        roi = (profit_units / units_staked * 100) if units_staked > 0 else 0.0
        hit_rate = (won_count / len(settled) * 100) if len(settled) > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        with col1:
            roi_color = "#00FFA6" if roi >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(0,255,166,0.06);border:1px solid rgba(0,255,166,0.3);">
                    <div style="font-size:11px;text-transform:uppercase;color:#7EF3C9;">ROI</div>
                    <div style="font-size:26px;font-weight:700;color:{roi_color};">
                        {roi:+.1f}%
                    </div>
                    <div style="font-size:12px;color:#9CA3AF;">
                        On {units_staked} units
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            color = "#00FFA6" if profit_units >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(15,23,42,0.9);border:1px solid rgba(148,163,184,0.4);">
                    <div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Profit</div>
                    <div style="font-size:26px;font-weight:700;color:{color};">
                        {profit_units:+.1f} units
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
        # Only show future matches (after tomorrow) in Upcoming - not past unsettled matches
        upcoming_picks = active[active["match_day"] > tomorrow].copy()
        # Past unsettled matches (awaiting settlement)
        past_unsettled = active[active["match_day"] < today].copy()
        
        def generate_why_bullets(row, ev, model_prob, fair_odds, best_odds, avg_odds, num_bookmakers):
            """Generate 2-3 insight bullets based on pick data. Max 3, structured, no hype."""
            bullets = []
            
            market_implied = 1 / best_odds if best_odds > 1 else 0.5
            model_pct = model_prob * 100 if model_prob else 50
            market_pct = market_implied * 100
            
            if model_prob and model_prob > market_implied + 0.03:
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">📊</span><span>Model probability: {model_pct:.0f}% vs market implied {market_pct:.0f}%</span></div>')
            
            if best_odds > fair_odds * 1.01:
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">💰</span><span>Best price {best_odds:.2f} vs fair odds {fair_odds:.2f}</span></div>')
            
            if num_bookmakers >= 5:
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">🧮</span><span>Edge confirmed across {num_bookmakers} bookmakers</span></div>')
            
            if best_odds > avg_odds * 1.02 and avg_odds > 0:
                pct_above = ((best_odds / avg_odds) - 1) * 100
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">📈</span><span>Best odds {pct_above:.1f}% above market average</span></div>')
            
            product = str(row.get('product', '')).upper()
            if product == 'CORNERS':
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">⚽</span><span>Corner patterns favor this line based on team styles</span></div>')
            elif product == 'CARDS':
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">⚽</span><span>Card frequency supports selection based on referee profile</span></div>')
            
            if ev < 5 and len(bullets) > 1:
                bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">🧠</span><span>Lower edge, tighter margin market</span></div>')
            
            max_bullets = 3 if ev >= 5 else 2
            return bullets[:max_bullets]
        
        def render_bet_cards(bets_df, section_title, section_emoji):
            if section_title:
                st.markdown(f"### {section_emoji} {section_title}")
            if bets_df.empty:
                if section_title:
                    st.caption(f"No {section_title.lower()} available.")
                return
            
            MAJOR_BOOKMAKERS = ['Pinnacle', 'Bet365', 'Betfair', 'Unibet', 'Betway', 'William Hill', 'Ladbrokes', 'Paddy Power', 'Coral', 'Sky Bet', 'BetMGM', 'DraftKings', 'FanDuel', 'Betsson', '1xBet', 'Bovada', 'BetOnline.ag', 'Marathon Bet']
            
            for _, row in bets_df.iterrows():
                ev = row.get("ev", 0.0) or 0.0
                try:
                    ev = float(ev)
                except Exception:
                    ev = 0.0
                
                if ev >= 20:
                    ev_bg = "linear-gradient(135deg, rgba(0,255,166,0.25), rgba(0,255,166,0.15))"
                    ev_border = "rgba(0,255,166,0.9)"
                    ev_color = "#00FFA6"
                    ev_glow = "0 0 12px rgba(0,255,166,0.6)"
                elif ev >= 8:
                    ev_bg = "linear-gradient(135deg, rgba(34,197,94,0.22), rgba(34,197,94,0.12))"
                    ev_border = "rgba(34,197,94,0.85)"
                    ev_color = "#22C55E"
                    ev_glow = "0 0 8px rgba(34,197,94,0.4)"
                elif ev >= 3:
                    ev_bg = "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.08))"
                    ev_border = "rgba(59,130,246,0.75)"
                    ev_color = "#60A5FA"
                    ev_glow = "none"
                else:
                    ev_bg = "rgba(148,163,184,0.10)"
                    ev_border = "rgba(148,163,184,0.5)"
                    ev_color = "#94A3B8"
                    ev_glow = "none"

                raw_match_date = row["match_date"] if "match_date" in row.index else None
                match_str = format_kickoff(raw_match_date)
                
                home_team = str(row.get('home_team', '')).replace('"', '&quot;')
                away_team = str(row.get('away_team', '')).replace('"', '&quot;')
                fixture = f"{home_team} vs {away_team}" if away_team else home_team
                odds_val = float(row.get('odds', 0))
                
                selection = str(row.get('selection', '')).replace('"', '&quot;')
                if not selection or selection.lower() == 'none':
                    selection = ""
                bet_display = selection.replace("Exact Score: ", "").replace("Value Single: ", "") if selection else ""
                
                product = str(row.get('product', '')).upper()
                if product == 'CORNERS':
                    market_badge = '<span style="font-size:10px;padding:3px 10px;border-radius:6px;background:rgba(16,185,129,0.15);color:#10B981;font-weight:600;letter-spacing:0.04em;">CORNERS</span>'
                    if 'corner' not in bet_display.lower():
                        bet_display = f"{bet_display} Corners" if bet_display else "Corners"
                elif product == 'CARDS':
                    market_badge = '<span style="font-size:10px;padding:3px 10px;border-radius:6px;background:rgba(245,158,11,0.15);color:#F59E0B;font-weight:600;letter-spacing:0.04em;">CARDS</span>'
                    if 'card' not in bet_display.lower():
                        bet_display = f"{bet_display} Cards" if bet_display else "Cards"
                else:
                    market_badge = ''
                
                odds_by_bookmaker = row.get('odds_by_bookmaker', {})
                if isinstance(odds_by_bookmaker, str):
                    import json as json_mod
                    try:
                        odds_by_bookmaker = json_mod.loads(odds_by_bookmaker)
                    except:
                        odds_by_bookmaker = {}
                elif not isinstance(odds_by_bookmaker, dict):
                    odds_by_bookmaker = {}
                
                sorted_books = sorted(odds_by_bookmaker.items(), key=lambda x: float(x[1]) if x[1] else 0, reverse=True) if odds_by_bookmaker else []
                best_book = sorted_books[0] if len(sorted_books) > 0 else None
                second_best = sorted_books[1] if len(sorted_books) > 1 else None
                third_best = sorted_books[2] if len(sorted_books) > 2 else None
                
                best_odds = float(best_book[1]) if best_book else odds_val
                avg_odds = sum(float(v) for v in odds_by_bookmaker.values()) / len(odds_by_bookmaker) if odds_by_bookmaker else odds_val
                fair_odds = 1 / (row.get('model_prob', 0.5) or 0.5) if row.get('model_prob') else best_odds * 0.92
                edge_vs_fair = ((best_odds / fair_odds) - 1) * 100 if fair_odds > 0 else ev
                
                odds_section = '<div style="display:flex;gap:8px;margin:12px 0;flex-wrap:wrap;">'
                if best_book:
                    odds_section += f'<div style="padding:8px 14px;border-radius:10px;background:linear-gradient(135deg, rgba(0,255,166,0.25), rgba(34,197,94,0.15));border:2px solid rgba(0,255,166,0.7);box-shadow:0 0 16px rgba(0,255,166,0.3);"><div style="font-size:9px;color:#00FFA6;font-weight:700;letter-spacing:0.08em;">BEST</div><div style="font-size:10px;color:#E5E7EB;margin:2px 0;">{best_book[0]}</div><div style="font-size:20px;font-weight:800;color:#00FFA6;">{float(best_book[1]):.2f}</div></div>'
                else:
                    odds_section += f'<div style="padding:8px 14px;border-radius:10px;background:linear-gradient(135deg, rgba(0,255,166,0.25), rgba(34,197,94,0.15));border:2px solid rgba(0,255,166,0.7);box-shadow:0 0 16px rgba(0,255,166,0.3);"><div style="font-size:9px;color:#00FFA6;font-weight:700;letter-spacing:0.08em;">ODDS</div><div style="font-size:20px;font-weight:800;color:#00FFA6;">{odds_val:.2f}</div></div>'
                if second_best:
                    odds_section += f'<div style="padding:8px 14px;border-radius:10px;background:linear-gradient(135deg, rgba(59,130,246,0.2), rgba(99,102,241,0.1));border:1px solid rgba(59,130,246,0.5);"><div style="font-size:9px;color:#60A5FA;font-weight:600;letter-spacing:0.06em;">2ND</div><div style="font-size:10px;color:#CBD5E1;margin:2px 0;">{second_best[0]}</div><div style="font-size:18px;font-weight:700;color:#60A5FA;">{float(second_best[1]):.2f}</div></div>'
                if third_best:
                    odds_section += f'<div style="padding:8px 14px;border-radius:10px;background:rgba(100,116,139,0.12);border:1px solid rgba(100,116,139,0.35);"><div style="font-size:9px;color:#94A3B8;font-weight:600;letter-spacing:0.06em;">3RD</div><div style="font-size:10px;color:#94A3B8;margin:2px 0;">{third_best[0]}</div><div style="font-size:16px;font-weight:600;color:#94A3B8;">{float(third_best[1]):.2f}</div></div>'
                odds_section += '</div>'
                
                shown = set([best_book[0] if best_book else '', second_best[0] if second_best else '', third_best[0] if third_best else ''])
                major_odds = [(k, float(v)) for k, v in odds_by_bookmaker.items() if k not in shown and any(m.lower() in k.lower() for m in MAJOR_BOOKMAKERS)]
                major_sorted = sorted(major_odds, key=lambda x: x[1], reverse=True)[:5]
                major_html = ""
                if major_sorted:
                    major_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;">'
                    for bk, od in major_sorted:
                        major_html += f'<span style="font-size:10px;color:#9CA3AF;padding:4px 10px;background:rgba(55,65,81,0.35);border-radius:6px;border:1px solid rgba(75,85,99,0.3);">{bk} <span style="color:#CBD5E1;font-weight:600;">{od:.2f}</span></span>'
                    major_html += '</div>'
                
                edge_color = "#00FFA6" if edge_vs_fair >= 5 else "#22C55E" if edge_vs_fair >= 0 else "#F87171"
                model_line = f'<div style="display:flex;gap:16px;font-size:11px;color:#6B7280;margin-top:10px;padding-top:10px;border-top:1px solid rgba(100,116,139,0.2);"><span>Fair <span style="color:#9CA3AF;font-weight:500;">{fair_odds:.2f}</span></span><span>Edge <span style="color:{edge_color};font-weight:600;">{edge_vs_fair:+.1f}%</span></span><span>Avg <span style="color:#9CA3AF;font-weight:500;">{avg_odds:.2f}</span></span></div>'
                
                model_prob = row.get('model_prob', 0.5) or 0.5
                num_bookmakers = len(odds_by_bookmaker)
                why_bullets = generate_why_bullets(row, ev, model_prob, fair_odds, best_odds, avg_odds, num_bookmakers)
                why_glow = "rgba(0,255,166,0.08)" if ev >= 8 else "rgba(59,130,246,0.06)"
                why_bullets_html = ''.join(why_bullets) if why_bullets else '<div style="color:#6B7280;font-size:12px;">No additional insights available</div>'
                why_section = f'''<details style="margin-top:12px;"><summary style="cursor:pointer;font-size:12px;color:#6B7280;padding:6px 0;user-select:none;list-style:none;display:flex;align-items:center;gap:6px;"><span style="color:#9CA3AF;">Why this pick</span><span style="font-size:10px;transition:transform 0.2s;">▾</span></summary><div style="margin-top:8px;padding:12px;border-radius:10px;background:linear-gradient(135deg, rgba(10,18,35,0.95), rgba(20,30,50,0.9));box-shadow:inset 0 0 20px {why_glow};font-size:12px;color:#CBD5E1;display:flex;flex-direction:column;gap:6px;">{why_bullets_html}</div></details>'''
                
                card_html = f'<div style="padding:20px;margin:16px 0;border-radius:16px;background:linear-gradient(145deg, rgba(15,23,42,0.98), rgba(30,41,59,0.95));border:1px solid rgba(0,255,166,0.35);box-shadow:0 8px 32px rgba(0,255,166,0.2), 0 4px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03);"><div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;"><div><div style="font-size:12px;color:#6B7280;margin-bottom:4px;">{match_str}</div><div style="font-size:17px;font-weight:600;color:#E5E7EB;letter-spacing:0.01em;">{fixture}</div></div><div style="padding:6px 12px;border-radius:8px;background:{ev_bg};border:1px solid {ev_border};box-shadow:{ev_glow};"><div style="font-size:10px;color:{ev_color};font-weight:700;letter-spacing:0.1em;">EV</div><div style="font-size:18px;font-weight:800;color:{ev_color};">{ev:+.1f}%</div></div></div><div style="display:flex;align-items:center;gap:10px;margin:12px 0;">{market_badge}<div style="font-size:22px;font-weight:700;color:#F8FAFC;letter-spacing:0.01em;">{bet_display}</div></div>{odds_section}{major_html}{model_line}{why_section}</div>'
                st.markdown(card_html, unsafe_allow_html=True)
                st.code(f"{fixture} | {bet_display} | Odds {best_odds:.2f} | 1 unit", language="text")
        
        # Categorize predictions into 3 sections
        def categorize_picks(df):
            """Split predictions into Match Result, Goals/BTTS, and Cards/Corners"""
            if df.empty:
                return df, df, df
            
            # Check Cards & Corners FIRST - check BOTH product column AND selection text
            # Product column contains 'CARDS' or 'CORNERS' for these bet types
            product_cards_corners = df['product'].str.upper().isin(['CARDS', 'CORNERS']) if 'product' in df.columns else pd.Series([False] * len(df), index=df.index)
            selection_cards_corners = df['selection'].str.contains('Corner|Card', case=False, na=False)
            cards_corners_mask = product_cards_corners | selection_cards_corners
            cards_corners = df[cards_corners_mask]
            
            # Match Result: Home Win, Away Win, Draw (excluding cards/corners)
            match_result_mask = df['selection'].str.contains('Home Win|Away Win|Draw', case=False, na=False) & ~cards_corners_mask
            match_result = df[match_result_mask]
            
            # Goals & BTTS: Over, Under, BTTS (excluding cards/corners)
            goals_btts_mask = df['selection'].str.contains('Over|Under|BTTS|Both Teams', case=False, na=False) & ~cards_corners_mask & ~match_result_mask
            goals_btts = df[goals_btts_mask]
            
            return match_result, goals_btts, cards_corners
        
        def render_categorized_picks(df, day_label):
            """Render picks split into 3 categories"""
            if df.empty:
                st.caption(f"No {day_label.lower()} picks available.")
                return
            
            match_result, goals_btts, cards_corners = categorize_picks(df)
            
            # Section 1: Match Result (1X2)
            if not match_result.empty:
                st.markdown(f"#### 🏆 Match Result ({len(match_result)})")
                render_bet_cards(match_result, "", "")
            
            # Section 2: Goals & BTTS
            if not goals_btts.empty:
                st.markdown(f"#### ⚽ Goals & BTTS ({len(goals_btts)})")
                render_bet_cards(goals_btts, "", "")
            
            # Section 3: Cards & Corners
            if not cards_corners.empty:
                st.markdown(f"#### 🔢 Cards & Corners ({len(cards_corners)})")
                render_bet_cards(cards_corners, "", "")
        
        st.markdown("### 🔥 Today's Picks")
        render_categorized_picks(todays_picks, "today's")
        
        st.markdown("")
        st.markdown("### 📅 Tomorrow's Picks")
        render_categorized_picks(tomorrows_picks, "tomorrow's")
        
        if not upcoming_picks.empty:
            st.markdown("")
            st.markdown("### 🗓️ Upcoming Picks")
            render_categorized_picks(upcoming_picks, "upcoming")
        
        if not past_unsettled.empty:
            st.markdown("")
            st.markdown(f"### ⏳ Awaiting Results ({len(past_unsettled)} bets)")
            st.caption("These matches have finished but results haven't been verified yet.")
            for _, row in past_unsettled.iterrows():
                home_team = str(row.get('home_team', '')).replace('"', '&quot;')
                away_team = str(row.get('away_team', '')).replace('"', '&quot;')
                fixture = f"{home_team} vs {away_team}" if away_team else home_team
                selection = str(row.get('selection', '')).replace('"', '&quot;')
                bet_display = selection.replace("Exact Score: ", "").replace("Value Single: ", "") if selection else ""
                odds_val = float(row.get('odds', 0))
                match_str = format_kickoff(row.get("match_date"))
                st.markdown(
                    f"""<div style="padding:12px;margin:6px 0;border-radius:10px;background:rgba(148,163,184,0.08);border:1px solid rgba(148,163,184,0.3);">
                    <div style="color:#9CA3AF;font-size:14px;">⏳ {fixture} - <span style="color:#E5E7EB;">{bet_display}</span> @ {odds_val:.2f}</div>
                    <div style="font-size:11px;color:#6B7280;">Played: {match_str}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

    st.markdown("---")

    st.markdown("### Performance")
    r1, r2 = st.columns((2, 1))
    with r1:
        roi_df = roi_series(settled)
        if not roi_df.empty:
            st.line_chart(roi_df.set_index("when"), height=220)
        else:
            st.caption("No settled bets yet.")
        st.caption("Cumulative profit (USD)")
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
        
        if "clv_pct" in settled.columns:
            settled["CLV"] = settled["clv_pct"].apply(
                lambda x: f"{x:+.1f}%" if pd.notna(x) else "–"
            )
            cols_hist = [c for c in ["settled", "match", "fixture", "odds", "CLV", "stake", "payout", "profit", "result"] if c in settled.columns and not settled[c].isna().all()]
        else:
            cols_hist = [c for c in ["settled", "match", "fixture", "odds", "stake", "payout", "profit", "result"] if c in settled.columns and not settled[c].isna().all()]
        
        st.dataframe(
            settled.sort_values("settled_at", ascending=False)[cols_hist],
            use_container_width=True,
            hide_index=True,
        )


def render_ml_parlay_tab():
    """Render ML Parlay tab showing moneyline parlays with premium styling."""
    import json
    
    st.markdown("## ML Parlay Engine")
    st.caption("Low/Medium Risk Multi-Match Parlays | 1X2 + DNB Markets")
    
    try:
        from db_helper import db_helper
        
        parlays = db_helper.execute(
            """SELECT parlay_id, match_date, num_legs, legs, parlay_description, 
                      total_odds, combined_ev, confidence_score, stake, 
                      potential_payout, status, outcome, profit_loss, profit_units, mode, created_at
               FROM ml_parlay_predictions 
               ORDER BY created_at DESC 
               LIMIT 200""",
            fetch='all'
        )
        
        if not parlays:
            st.info("No ML Parlays yet. The engine runs every 3 hours and creates parlays when matches meet the filters.")
            return
        
        columns = ['parlay_id', 'match_date', 'num_legs', 'legs', 'parlay_description', 
                   'total_odds', 'combined_ev', 'confidence_score', 'stake',
                   'potential_payout', 'status', 'outcome', 'profit_loss', 'profit_units', 'mode', 'created_at']
        df = pd.DataFrame(parlays, columns=columns)
        
        settled = df[df['status'] == 'settled'].copy()
        pending = df[df['status'] == 'pending'].copy()
        
        won = len(settled[settled['outcome'] == 'won']) if not settled.empty else 0
        lost = len(settled[settled['outcome'] == 'lost']) if not settled.empty else 0
        push = len(settled[settled['outcome'] == 'push']) if not settled.empty else 0
        void = len(settled[settled['outcome'].isin(['void', 'VOID'])]) if not settled.empty else 0
        units_staked = won + lost  # Don't count pushes or voids
        
        profit_units = 0.0
        if not settled.empty:
            settled['total_odds'] = pd.to_numeric(settled['total_odds'], errors='coerce').fillna(2.0)
            for _, bet in settled.iterrows():
                if bet['outcome'] == 'won':
                    odds = float(bet.get('total_odds', 2.0) or 2.0)
                    profit_units += (odds - 1)
                elif bet['outcome'] == 'lost':
                    profit_units -= 1
                # push/void = 0, no change
        
        roi = (profit_units / units_staked * 100) if units_staked > 0 else 0
        hit_rate = (won / units_staked * 100) if units_staked > 0 else 0
        avg_odds = settled['total_odds'].mean() if not settled.empty else 0
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("ROI", f"{roi:+.1f}%")
        with col2:
            st.metric("Profit", f"{profit_units:+.1f}u")
        with col3:
            st.metric("Hit Rate", f"{hit_rate:.0f}%")
        with col4:
            record_str = f"{won}-{lost}"
            if push > 0:
                record_str += f"-{push}P"
            if void > 0:
                record_str += f"-{void}V"
            st.metric("Record", record_str)
        with col5:
            st.metric("Pending", len(pending))
        
        st.markdown("---")
        st.markdown("### Active Parlays")
        
        if pending.empty:
            st.info("No active parlays. Next batch generates when matches meet the filters.")
        else:
            for idx, row in pending.iterrows():
                ev = float(row.get('combined_ev', 0) or 0)
                odds = float(row.get('total_odds', 0) or 0)
                desc = str(row.get('parlay_description', ''))
                num_legs = int(row.get('num_legs', 0) or 0)
                confidence = float(row.get('confidence_score', 0) or 0)
                parlay_id = str(row.get('parlay_id', ''))[:12]
                
                legs_data = row.get('legs', '[]')
                if isinstance(legs_data, str):
                    try:
                        legs_list = json.loads(legs_data)
                    except:
                        legs_list = []
                else:
                    legs_list = legs_data if legs_data else []
                
                ev_tier = "ELITE" if ev >= 50 else "STRONG" if ev >= 20 else "SOLID" if ev >= 10 else "VALUE"
                
                with st.expander(f"{num_legs} LEGS @ {odds:.2f}x | EV +{ev:.1f}% | {ev_tier}", expanded=True):
                    for leg in legs_list:
                        home = leg.get('home_team', 'Home')
                        away = leg.get('away_team', 'Away')
                        league = leg.get('league', '')
                        selection = leg.get('selection', '')
                        leg_odds = float(leg.get('odds', 1.0))
                        edge = float(leg.get('edge_percentage', 0))
                        
                        selection_display = selection.replace('_', ' ').replace('HOME', home).replace('AWAY', away)
                        if 'DNB' in selection:
                            selection_display = selection_display.replace('DNB', '(DNB)')
                        
                        st.markdown(f"**{home} vs {away}** ({league})")
                        st.markdown(f"Pick: {selection_display} @ {leg_odds:.2f} | Edge: +{edge:.1f}%")
                        st.markdown("---")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Total Odds", f"{odds:.2f}x")
                    with c2:
                        st.metric("EV", f"+{ev:.1f}%")
                    with c3:
                        st.metric("Stake", "1 unit")
        
        st.markdown("---")
        st.markdown("### Settled History")
        
        if settled.empty:
            st.info("No settled parlays yet. Results will appear here after verification.")
        else:
            for _, row in settled.head(10).iterrows():
                outcome = row.get('outcome', '')
                ev = float(row.get('combined_ev', 0) or 0)
                odds = float(row.get('total_odds', 0) or 0)
                num_legs = int(row.get('num_legs', 0) or 0)
                match_date = str(row.get('match_date', ''))
                desc = str(row.get('parlay_description', ''))
                
                if outcome == 'won':
                    pl_display = f"+{odds - 1:.2f}u"
                    result_icon = "W"
                else:
                    pl_display = "-1.00u"
                    result_icon = "L"
                
                st.markdown(f"**{result_icon}** | {desc} @ {odds:.2f}x | {pl_display}")
            
    except Exception as e:
        st.error(f"Error loading ML Parlay data: {e}")


def render_daily_card_tab():
    """Render the Daily Betting Card tab with EV-filtered selections."""
    from daily_card_selector import DailyCardSelector
    
    st.markdown("## Today's Betting Card")
    st.caption("AI-curated daily picks based on EV tiers and optimal odds ranges.")
    
    if st.button("Refresh Daily Card", key="refresh_daily_card"):
        st.rerun()
    
    try:
        selector = DailyCardSelector()
        card = selector.generate_daily_card()
        
        if card['error']:
            st.error(f"Error loading data: {card['error']}")
            return
        
        if card['summary'] and card['summary'].get('total_bets', 0) == 0:
            st.info("No official value plays today based on current EV filters. Check back later!")
            return
        
        summary = card['summary']
        st.markdown("### Card Summary")
        cols = st.columns(4)
        with cols[0]:
            st.metric("Total Picks", summary['total_bets'])
        with cols[1]:
            st.metric("Value Singles", summary['value_singles_count'])
        with cols[2]:
            st.metric("Parlay Bets", summary.get('parlay_count', 0))
        with cols[3]:
            st.metric("Basketball", summary['basketball_count'])
        
        st.markdown("---")
        
        if card.get('parlay', []):
            st.markdown("### Parlay Bets")
            for bet in card.get('parlay', []):
                tier_color = "#10B981" if bet['tier'] == 'A' else "#F59E0B" if bet['tier'] == 'B' else "#6B7280"
                ev_color = "#10B981" if bet['ev'] > 0.10 else "#F59E0B" if bet['ev'] > 0.05 else "#9CA3AF"
                st.markdown(f"""
                <div style="padding:16px;margin:10px 0;border-radius:14px;background:radial-gradient(circle at top left, rgba(99,102,241,0.15), rgba(15,23,42,0.96));border:1px solid rgba(99,102,241,0.4);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div style="font-size:11px;padding:3px 8px;border-radius:999px;background:{tier_color}33;color:{tier_color};">TIER {bet['tier']}</div>
                        <div style="font-size:11px;padding:3px 8px;border-radius:999px;background:{ev_color}22;color:{ev_color};">EV +{bet['ev']*100:.1f}%</div>
                    </div>
                    <div style="font-size:13px;color:#9CA3AF;margin-bottom:4px;">{bet['league']}</div>
                    <div style="font-size:16px;color:#E5E7EB;font-weight:600;margin-bottom:6px;">{bet['matchup']}</div>
                    <div style="font-size:14px;color:#A5B4FC;margin-bottom:10px;">{bet['selection']}</div>
                    <div style="display:flex;gap:24px;">
                        <div><span style="font-size:11px;color:#9CA3AF;">ODDS</span><br/><span style="font-size:20px;font-weight:600;color:#6366F1;">{bet['odds']:.2f}x</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        if card['basketball']:
            st.markdown("### Basketball")
            for bet in card['basketball']:
                tier_color = "#10B981" if bet['tier'] == 'A' else "#F59E0B" if bet['tier'] == 'B' else "#6B7280"
                ev_color = "#10B981" if bet['ev'] > 0.10 else "#F59E0B" if bet['ev'] > 0.05 else "#9CA3AF"
                st.markdown(f"""
                <div style="padding:16px;margin:10px 0;border-radius:14px;background:radial-gradient(circle at top left, rgba(249,115,22,0.15), rgba(15,23,42,0.96));border:1px solid rgba(249,115,22,0.4);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div style="font-size:11px;padding:3px 8px;border-radius:999px;background:{tier_color}33;color:{tier_color};">TIER {bet['tier']}</div>
                        <div style="font-size:11px;padding:3px 8px;border-radius:999px;background:{ev_color}22;color:{ev_color};">EV +{bet['ev']*100:.1f}%</div>
                    </div>
                    <div style="font-size:13px;color:#9CA3AF;margin-bottom:4px;">{bet['league']} • {bet['market']}</div>
                    <div style="font-size:16px;color:#E5E7EB;font-weight:600;margin-bottom:6px;">{bet['matchup']}</div>
                    <div style="font-size:14px;color:#FDBA74;margin-bottom:10px;">{bet['selection']}</div>
                    <div style="display:flex;gap:24px;">
                        <div><span style="font-size:11px;color:#9CA3AF;">ODDS</span><br/><span style="font-size:20px;font-weight:600;color:#F97316;">{bet['odds']:.2f}x</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        if card['value_singles']:
            st.markdown("### Value Singles")
            MAJOR_BOOKMAKERS = ['Pinnacle', 'Bet365', 'Betfair', 'Unibet', 'Betway', 'William Hill', 'Ladbrokes', 'Paddy Power', 'Coral', 'Sky Bet', 'BetMGM', 'DraftKings', 'FanDuel', 'Betsson', '1xBet', 'Bovada', 'BetOnline.ag', 'Marathon Bet']
            
            for bet in card['value_singles']:
                tier_color = "#10B981" if bet['tier'] == 'A' else "#F59E0B" if bet['tier'] == 'B' else "#6B7280"
                ev_color = "#10B981" if bet['ev'] > 0.10 else "#F59E0B" if bet['ev'] > 0.05 else "#9CA3AF"
                
                odds_by_bookmaker = bet.get('odds_by_bookmaker', {})
                best_odds_val = bet.get('best_odds_value', bet['odds'])
                
                base_odds = float(bet.get('odds', 0) or 0)
                bookmaker_html = ""
                if odds_by_bookmaker and isinstance(odds_by_bookmaker, dict) and len(odds_by_bookmaker) > 0:
                    sorted_books = sorted(odds_by_bookmaker.items(), key=lambda x: float(x[1]) if x[1] else 0, reverse=True)
                    best_book = sorted_books[0] if len(sorted_books) > 0 else None
                    second_best = sorted_books[1] if len(sorted_books) > 1 else None
                    third_best = sorted_books[2] if len(sorted_books) > 2 else None
                    
                    bookmaker_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;">'
                    if best_book:
                        bookmaker_html += f'<div style="padding:6px 12px;border-radius:8px;background:linear-gradient(135deg, rgba(34,197,94,0.35), rgba(16,185,129,0.25));border:2px solid rgba(34,197,94,0.8);"><div style="font-size:9px;color:#22C55E;font-weight:600;">BEST</div><div style="font-size:11px;color:#E5E7EB;">{best_book[0]}</div><div style="font-size:16px;font-weight:700;color:#22C55E;">{float(best_book[1]):.2f}</div></div>'
                    if second_best:
                        bookmaker_html += f'<div style="padding:6px 12px;border-radius:8px;background:linear-gradient(135deg, rgba(59,130,246,0.3), rgba(99,102,241,0.2));border:2px solid rgba(59,130,246,0.7);"><div style="font-size:9px;color:#60A5FA;font-weight:600;">2ND</div><div style="font-size:11px;color:#E5E7EB;">{second_best[0]}</div><div style="font-size:16px;font-weight:700;color:#60A5FA;">{float(second_best[1]):.2f}</div></div>'
                    if third_best:
                        bookmaker_html += f'<div style="padding:6px 12px;border-radius:8px;background:rgba(148,163,184,0.15);border:1px solid rgba(148,163,184,0.4);"><div style="font-size:9px;color:#94A3B8;font-weight:600;">3RD</div><div style="font-size:11px;color:#CBD5E1;">{third_best[0]}</div><div style="font-size:14px;font-weight:600;color:#94A3B8;">{float(third_best[1]):.2f}</div></div>'
                    bookmaker_html += '</div>'
                    
                    shown = set([best_book[0] if best_book else '', second_best[0] if second_best else '', third_best[0] if third_best else ''])
                    major_odds = [(k, float(v)) for k, v in odds_by_bookmaker.items() if k not in shown and any(m.lower() in k.lower() for m in MAJOR_BOOKMAKERS)]
                    major_sorted = sorted(major_odds, key=lambda x: x[1], reverse=True)[:3]
                    if major_sorted:
                        bookmaker_html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;padding-top:6px;border-top:1px solid rgba(148,163,184,0.2);"><span style="font-size:9px;color:#6B7280;width:100%;">MAJOR:</span>'
                        for bk, od in major_sorted:
                            bookmaker_html += f'<span style="font-size:10px;color:#9CA3AF;padding:2px 6px;background:rgba(55,65,81,0.4);border-radius:4px;">{bk} {od:.2f}</span>'
                        bookmaker_html += '</div>'
                elif base_odds > 0:
                    bookmaker_html = f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;"><div style="padding:6px 12px;border-radius:8px;background:linear-gradient(135deg, rgba(34,197,94,0.35), rgba(16,185,129,0.25));border:2px solid rgba(34,197,94,0.8);"><div style="font-size:9px;color:#22C55E;font-weight:600;">ODDS</div><div style="font-size:16px;font-weight:700;color:#22C55E;">{base_odds:.2f}</div></div><div style="padding:6px 12px;border-radius:8px;background:rgba(55,65,81,0.3);"><div style="font-size:9px;color:#9CA3AF;">Bookmaker comparison not available for this league</div></div></div>'
                
                st.markdown(f"""
                <div style="padding:16px;margin:10px 0;border-radius:14px;background:radial-gradient(circle at top left, rgba(16,185,129,0.15), rgba(15,23,42,0.96));border:1px solid rgba(16,185,129,0.4);">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div style="font-size:11px;padding:3px 8px;border-radius:999px;background:{tier_color}33;color:{tier_color};">TIER {bet['tier']}</div>
                        <div style="font-size:11px;padding:3px 8px;border-radius:999px;background:{ev_color}22;color:{ev_color};">EV +{bet['ev']*100:.1f}%</div>
                    </div>
                    <div style="font-size:13px;color:#9CA3AF;margin-bottom:4px;">{bet['league']} • {bet['market']}</div>
                    <div style="font-size:16px;color:#E5E7EB;font-weight:600;margin-bottom:6px;">{bet['matchup']}</div>
                    <div style="font-size:14px;color:#6EE7B7;margin-bottom:10px;">{bet['selection']}</div>
                    {bookmaker_html}
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### Average Stats")
        stats_cols = st.columns(3)
        with stats_cols[0]:
            if summary.get('parlay_count', 0) > 0:
                st.markdown(f"""
                <div style="padding:12px;border-radius:10px;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.3);">
                    <div style="font-size:12px;color:#9CA3AF;">Parlay Average</div>
                    <div style="font-size:16px;color:#6366F1;">EV: {summary.get('parlay_avg_ev', 0):.1f}% • Odds: {summary.get('parlay_avg_odds', 0):.2f}x</div>
                </div>
                """, unsafe_allow_html=True)
        with stats_cols[1]:
            if summary['basketball_count'] > 0:
                st.markdown(f"""
                <div style="padding:12px;border-radius:10px;background:rgba(249,115,22,0.1);border:1px solid rgba(249,115,22,0.3);">
                    <div style="font-size:12px;color:#9CA3AF;">Basketball Average</div>
                    <div style="font-size:16px;color:#F97316;">EV: {summary['basketball_avg_ev']:.1f}% • Odds: {summary['basketball_avg_odds']:.2f}x</div>
                </div>
                """, unsafe_allow_html=True)
        with stats_cols[2]:
            if summary['value_singles_count'] > 0:
                st.markdown(f"""
                <div style="padding:12px;border-radius:10px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);">
                    <div style="font-size:12px;color:#9CA3AF;">Value Singles Average</div>
                    <div style="font-size:16px;color:#10B981;">EV: {summary['value_singles_avg_ev']:.1f}% • Odds: {summary['value_singles_avg_odds']:.2f}x</div>
                </div>
                """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"Error generating daily card: {e}")


def render_backtest_analysis():
    """Render comprehensive backtest analysis tab with EV, odds, and league breakdowns."""
    from backtest_analyzer import BacktestAnalyzer
    
    st.markdown("## Historical Performance Analysis")
    st.caption("Data-driven analysis of what actually works based on all settled bets.")
    
    try:
        analyzer = BacktestAnalyzer()
        
        if analyzer.load_error:
            st.warning(f"Could not load backtest data: {analyzer.load_error}")
            return
        
        stats = analyzer.get_summary_stats()
        
        if not stats:
            st.info("No settled bets available for analysis yet. Place some bets and wait for results!")
            return
        
        st.markdown("### Summary by Product")
        cols = st.columns(len(stats))
        for i, (product, data) in enumerate(stats.items()):
            with cols[i]:
                product_name = product.replace('_', ' ').title()
                roi_color = "#10B981" if data['roi'] > 0 else "#EF4444"
                st.markdown(f"""
                <div style="padding:16px;border-radius:12px;background:linear-gradient(135deg, rgba(30,41,59,0.9), rgba(15,23,42,0.95));border:1px solid rgba(99,102,241,0.3);">
                    <div style="font-size:14px;color:#9CA3AF;margin-bottom:8px;">{product_name}</div>
                    <div style="font-size:28px;font-weight:600;color:{roi_color};">{data['roi']:+.1f}%</div>
                    <div style="font-size:12px;color:#6B7280;margin-top:4px;">
                        {data['wins']}/{data['total_bets']} wins ({data['hit_rate']:.1f}% HR)
                    </div>
                    <div style="font-size:12px;color:#6B7280;">
                        {data['total_profit']:+,.0f} SEK profit
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### EV Threshold Analysis")
            st.caption("Which EV ranges generate the best returns?")
            ev_df = analyzer.analyze_ev_thresholds()
            if not ev_df.empty:
                st.dataframe(ev_df, use_container_width=True, hide_index=True)
                
                best_ev = ev_df.iloc[0]['EV Range']
                best_roi = ev_df.iloc[0]['ROI']
                st.success(f"Best performer: **{best_ev}** EV range with **{best_roi}** ROI")
        
        with col2:
            st.markdown("### Odds Range Analysis")
            st.caption("Which odds ranges are most profitable?")
            odds_df = analyzer.analyze_odds_ranges()
            if not odds_df.empty:
                st.dataframe(odds_df, use_container_width=True, hide_index=True)
                
                best_odds = odds_df.iloc[0]['Odds Range']
                best_roi = odds_df.iloc[0]['ROI']
                st.success(f"Best performer: **{best_odds}** odds with **{best_roi}** ROI")
        
        st.markdown("---")
        
        col3, col4 = st.columns(2)
        
        with col3:
            st.markdown("### League Performance")
            st.caption("Which leagues predict best?")
            league_df = analyzer.analyze_by_league()
            if not league_df.empty:
                st.dataframe(league_df, use_container_width=True, hide_index=True)
        
        with col4:
            st.markdown("### Basketball Market Analysis")
            st.caption("Which basketball markets are most accurate?")
            market_df = analyzer.analyze_by_market()
            if not market_df.empty:
                st.dataframe(market_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        col5, col6 = st.columns(2)
        
        with col5:
            st.markdown("### Parlay Odds Deep Dive")
            st.caption("Fine-grained parlay odds analysis")
            sgp_odds_df = analyzer.get_sgp_odds_analysis()
            if not sgp_odds_df.empty:
                st.dataframe(sgp_odds_df, use_container_width=True, hide_index=True)
        
        with col6:
            st.markdown("### Basketball Confidence Levels")
            st.caption("How confidence correlates with accuracy")
            conf_df = analyzer.analyze_confidence_thresholds()
            if not conf_df.empty:
                st.dataframe(conf_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("### Key Insights")
        
        insights = []
        
        if not odds_df.empty:
            profitable_odds = odds_df[odds_df['ROI'].str.contains(r'\+')]
            if not profitable_odds.empty:
                ranges = profitable_odds['Odds Range'].tolist()
                insights.append(f"Profitable odds ranges: **{', '.join(ranges)}**")
        
        if not ev_df.empty:
            best_ev_row = ev_df.iloc[0]
            insights.append(f"Optimal EV threshold: **{best_ev_row['EV Range']}** ({best_ev_row['ROI']} ROI)")
        
        if not league_df.empty:
            profitable_leagues = league_df[league_df['ROI'].str.contains(r'\+')]
            if not profitable_leagues.empty:
                top_leagues = profitable_leagues.head(3)['League'].tolist()
                insights.append(f"Top performing leagues: **{', '.join(top_leagues)}**")
        
        if insights:
            for insight in insights:
                st.markdown(f"- {insight}")
        else:
            st.info("More data needed for actionable insights.")
            
    except Exception as e:
        st.error(f"Error loading backtest analysis: {e}")
        import traceback
        st.code(traceback.format_exc())


def render_basketball_tab(df: pd.DataFrame):
    """Render College Basketball tab with Parlay-style card layout."""
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
        units_staked = len(settled_data)
        won_count = (settled_data["result"].isin(["WON", "WIN"])).sum()
        lost_count = len(settled_data) - won_count
        
        won_bets = settled_data[settled_data["result"].isin(["WON", "WIN"])]
        profit_units = 0.0
        for _, bet in won_bets.iterrows():
            odds = float(bet.get("odds", 2.0) or 2.0)
            profit_units += (odds - 1)
        profit_units -= lost_count
        
        roi = (profit_units / units_staked * 100) if units_staked > 0 else 0.0
        hit_rate = (won_count / len(settled_data) * 100) if len(settled_data) > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        with col1:
            roi_color = "#00FFA6" if roi >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(0,255,166,0.06);border:1px solid rgba(0,255,166,0.3);">
                    <div style="font-size:11px;text-transform:uppercase;color:#7EF3C9;">ROI</div>
                    <div style="font-size:26px;font-weight:700;color:{roi_color};">
                        {roi:+.1f}%
                    </div>
                    <div style="font-size:12px;color:#9CA3AF;">
                        On {units_staked} units
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            color = "#00FFA6" if profit_units >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(15,23,42,0.9);border:1px solid rgba(148,163,184,0.4);">
                    <div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Profit</div>
                    <div style="font-size:26px;font-weight:700;color:{color};">
                        {profit_units:+.1f} units
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
            
            if ev >= 20:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(0,255,166,0.25), rgba(0,255,166,0.15))", "rgba(0,255,166,0.9)", "#00FFA6", "0 0 12px rgba(0,255,166,0.6)"
            elif ev >= 8:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(34,197,94,0.22), rgba(34,197,94,0.12))", "rgba(34,197,94,0.85)", "#22C55E", "0 0 8px rgba(34,197,94,0.4)"
            elif ev >= 3:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.08))", "rgba(59,130,246,0.75)", "#60A5FA", "none"
            else:
                ev_bg, ev_border, ev_color, ev_glow = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.5)", "#94A3B8", "none"

            match_str = format_kickoff(row.get("match_date"))
            home_team = str(row.get('home_team', '')).replace('"', '&quot;')
            away_team = str(row.get('away_team', '')).replace('"', '&quot;')
            match_name = f"{home_team} vs {away_team}" if away_team else home_team
            odds_val = float(row.get('odds', 0))
            selection = str(row.get('selection', '')).replace('"', '&quot;')
            if not selection or selection.lower() == 'none':
                selection = "Home Win"
            pick_display = selection

            bball_bullets = []
            implied_prob = 1 / odds_val if odds_val > 1 else 0.5
            if ev >= 5:
                bball_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">📊</span><span>Model edge: +{ev:.1f}% above market price</span></div>')
            if odds_val >= 1.6 and odds_val <= 2.5:
                bball_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">💰</span><span>Optimal odds range for +EV basketball</span></div>')
            if implied_prob < 0.6:
                bball_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">🧠</span><span>Market undervaluing outcome at {implied_prob*100:.0f}% implied</span></div>')
            bball_max = 3 if ev >= 5 else 2
            bball_bullets = bball_bullets[:bball_max]
            bball_why_html = ''.join(bball_bullets) if bball_bullets else '<div style="color:#6B7280;font-size:12px;">Edge identified via line analysis</div>'
            bball_glow = "rgba(0,255,166,0.08)" if ev >= 8 else "rgba(59,130,246,0.06)"
            bball_why_section = f'''<details style="margin-top:12px;"><summary style="cursor:pointer;font-size:12px;color:#6B7280;padding:6px 0;user-select:none;list-style:none;display:flex;align-items:center;gap:6px;"><span style="color:#9CA3AF;">Why this pick</span><span style="font-size:10px;">▾</span></summary><div style="margin-top:8px;padding:12px;border-radius:10px;background:linear-gradient(135deg, rgba(10,18,35,0.95), rgba(20,30,50,0.9));box-shadow:inset 0 0 20px {bball_glow};font-size:12px;color:#CBD5E1;display:flex;flex-direction:column;gap:6px;">{bball_why_html}</div></details>'''

            card_html = f'<div style="padding:20px;margin:16px 0;border-radius:16px;background:linear-gradient(145deg, rgba(15,23,42,0.98), rgba(30,41,59,0.95));border:1px solid rgba(0,255,166,0.35);box-shadow:0 8px 32px rgba(0,255,166,0.2), 0 4px 16px rgba(0,0,0,0.4);"><div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;"><div><div style="font-size:12px;color:#6B7280;margin-bottom:4px;">{match_str}</div><div style="font-size:17px;font-weight:600;color:#E5E7EB;">🏀 {match_name}</div></div><div style="padding:6px 12px;border-radius:8px;background:{ev_bg};border:1px solid {ev_border};box-shadow:{ev_glow};"><div style="font-size:10px;color:{ev_color};font-weight:700;letter-spacing:0.1em;">EV</div><div style="font-size:18px;font-weight:800;color:{ev_color};">{ev:+.1f}%</div></div></div><div style="font-size:22px;font-weight:700;color:#F8FAFC;margin:12px 0;">{pick_display}</div><div style="display:flex;gap:8px;"><div style="padding:8px 14px;border-radius:10px;background:linear-gradient(135deg, rgba(0,255,166,0.25), rgba(34,197,94,0.15));border:2px solid rgba(0,255,166,0.7);box-shadow:0 0 16px rgba(0,255,166,0.3);"><div style="font-size:9px;color:#00FFA6;font-weight:700;">ODDS</div><div style="font-size:20px;font-weight:800;color:#00FFA6;">{odds_val:.2f}</div></div></div>{bball_why_section}</div>'
            st.markdown(card_html, unsafe_allow_html=True)
            st.code(f"{match_name} | {pick_display} | Odds {odds_val:.2f} | 1 unit", language="text")

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
            
            if ev >= 20:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(0,255,166,0.25), rgba(0,255,166,0.15))", "rgba(0,255,166,0.9)", "#00FFA6", "0 0 12px rgba(0,255,166,0.6)"
            elif ev >= 8:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(34,197,94,0.22), rgba(34,197,94,0.12))", "rgba(34,197,94,0.85)", "#22C55E", "0 0 8px rgba(34,197,94,0.4)"
            else:
                ev_bg, ev_border, ev_color, ev_glow = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.5)", "#94A3B8", "none"

            match_str = format_kickoff(row.get("match_date"))
            home_team = str(row.get('home_team', '')).replace('"', '&quot;')
            away_team = str(row.get('away_team', '')).replace('"', '&quot;')
            match_name = f"{home_team} vs {away_team}" if away_team else home_team
            odds_val = float(row.get('odds', 0))
            selection = str(row.get('selection', '')).replace('"', '&quot;')
            if not selection or selection.lower() == 'none':
                selection = "Parlay"
            pick_display = selection

            parlay_bullets = []
            if ev >= 5:
                parlay_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">📊</span><span>Combined EV: +{ev:.1f}% across all legs</span></div>')
            if odds_val >= 2.5:
                parlay_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">💰</span><span>Parlay odds {odds_val:.2f}x in target range</span></div>')
            parlay_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">🧮</span><span>Individual legs meet minimum edge threshold</span></div>')
            parlay_max = 3 if ev >= 5 else 2
            parlay_bullets = parlay_bullets[:parlay_max]
            parlay_why_html = ''.join(parlay_bullets)
            parlay_glow = "rgba(0,255,166,0.08)" if ev >= 8 else "rgba(59,130,246,0.06)"
            parlay_why_section = f'''<details style="margin-top:12px;"><summary style="cursor:pointer;font-size:12px;color:#6B7280;padding:6px 0;user-select:none;list-style:none;display:flex;align-items:center;gap:6px;"><span style="color:#9CA3AF;">Why this pick</span><span style="font-size:10px;">▾</span></summary><div style="margin-top:8px;padding:12px;border-radius:10px;background:linear-gradient(135deg, rgba(10,18,35,0.95), rgba(20,30,50,0.9));box-shadow:inset 0 0 20px {parlay_glow};font-size:12px;color:#CBD5E1;display:flex;flex-direction:column;gap:6px;">{parlay_why_html}</div></details>'''

            card_html = f'<div style="padding:20px;margin:16px 0;border-radius:16px;background:linear-gradient(145deg, rgba(15,23,42,0.98), rgba(30,41,59,0.95));border:1px solid rgba(0,255,166,0.35);box-shadow:0 8px 32px rgba(0,255,166,0.2), 0 4px 16px rgba(0,0,0,0.4);"><div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;"><div><div style="font-size:12px;color:#6B7280;margin-bottom:4px;">{match_str}</div><div style="font-size:17px;font-weight:600;color:#E5E7EB;">🏀 {match_name}</div></div><div style="padding:6px 12px;border-radius:8px;background:{ev_bg};border:1px solid {ev_border};box-shadow:{ev_glow};"><div style="font-size:10px;color:{ev_color};font-weight:700;letter-spacing:0.1em;">EV</div><div style="font-size:18px;font-weight:800;color:{ev_color};">{ev:+.1f}%</div></div></div><div style="font-size:22px;font-weight:700;color:#F8FAFC;margin:12px 0;">{pick_display}</div><div style="display:flex;gap:8px;"><div style="padding:8px 14px;border-radius:10px;background:linear-gradient(135deg, rgba(0,255,166,0.25), rgba(34,197,94,0.15));border:2px solid rgba(0,255,166,0.7);box-shadow:0 0 16px rgba(0,255,166,0.3);"><div style="font-size:9px;color:#00FFA6;font-weight:700;">ODDS</div><div style="font-size:20px;font-weight:800;color:#00FFA6;">{odds_val:.2f}</div></div></div>{parlay_why_section}</div>'
            st.markdown(card_html, unsafe_allow_html=True)
            st.code(f"{match_name} | {pick_display} | Odds {odds_val:.2f} | 1 unit", language="text")

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
            st.markdown(f"**{len(singles_settled)} settled** | ROI: {s_summary['roi']:.1f}% | Profit: {s_summary['profit']:.0f} USD (≈{s_summary['profit'] * USD_TO_SEK:.0f} SEK)")
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
            st.markdown(f"**{len(parlays_settled)} settled** | ROI: {p_summary['roi']:.1f}% | Profit: {p_summary['profit']:.0f} USD (≈{p_summary['profit'] * USD_TO_SEK:.0f} SEK)")
            parlays_settled["fixture"] = parlays_settled.apply(as_fixture, axis=1)
            cols = [c for c in ["fixture", "odds", "result", "profit"] if c in parlays_settled.columns]
            if cols:
                st.dataframe(parlays_settled[cols].head(15), use_container_width=True, hide_index=True)


def render_parlays_tab():
    """Specialized Parlays tab with beautiful card layout."""
    st.markdown("## Multi-Match Parlays")
    st.caption("High-edge parlays built from approved L1/L2 single bets across multiple matches.")

    db_url = get_db_url()
    engine = create_engine(db_url)
    
    from datetime import datetime as dt_module, timedelta as td_module
    today = dt_module.utcnow().date()
    
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
        ORDER BY match_date DESC, id DESC
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if df.empty:
        st.info("No parlays in the database yet.")
        return

    # Split active vs settled - check BOTH result and outcome columns
    # Settled = has result (WON/LOSS/VOID) OR has outcome (won/loss/win/lost/void)
    outcome_settled = df["outcome"].isin(["won", "win", "loss", "lost", "WON", "WIN", "LOSS", "LOST", "void", "VOID"])
    result_settled = df["result"].isin(["WON", "WIN", "LOSS", "LOST", "VOID", "void"])
    settled_mask = outcome_settled | result_settled
    
    # Only show today's and future unsettled parlays as "active"
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    today_mask = df["match_date"].dt.date >= today
    
    active_bets = df[~settled_mask & today_mask].drop_duplicates(subset=['home_team', 'away_team', 'parlay_description']).copy()
    settled_bets = df[settled_mask].copy()
    
    # Past unsettled parlays (matches already played but not yet verified)
    past_unsettled = df[~settled_mask & ~today_mask].copy()

    # ROI / PROFIT / HIT RATE for settled (UNITS MODE) - EXCLUDE VOIDs
    if not settled_bets.empty:
        # Filter out VOIDs from stats calculations
        void_mask = settled_bets["result"].isin(["VOID", "void"]) | settled_bets["outcome"].isin(["void", "VOID"])
        non_void_bets = settled_bets[~void_mask]
        void_count = void_mask.sum()
        
        won_mask = non_void_bets["result"].isin(["WON", "WIN"]) | non_void_bets["outcome"].isin(["won", "win", "WON", "WIN"])
        won_count = won_mask.sum()
        lost_count = len(non_void_bets) - won_count
        units_staked = len(non_void_bets)  # Only count non-void bets
        
        profit_units = 0.0
        for idx, bet in non_void_bets.iterrows():
            is_won = bet["result"] in ["WON", "WIN"] or bet["outcome"] in ["won", "win", "WON", "WIN"]
            if is_won:
                odds = float(bet.get("odds", 2.0) or 2.0)
                profit_units += (odds - 1)
            else:
                profit_units -= 1
        
        roi = (profit_units / units_staked * 100) if units_staked > 0 else 0.0
        hit_rate = (won_count / len(non_void_bets) * 100) if len(non_void_bets) > 0 else 0.0

        col1, col2, col3 = st.columns(3)
        with col1:
            roi_color = "#00FFA6" if roi >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(0,255,166,0.06);border:1px solid rgba(0,255,166,0.3);">
                    <div style="font-size:11px;text-transform:uppercase;color:#7EF3C9;">ROI</div>
                    <div style="font-size:26px;font-weight:700;color:{roi_color};">
                        {roi:+.1f}%
                    </div>
                    <div style="font-size:12px;color:#9CA3AF;">
                        On {units_staked} units
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col2:
            color = "#00FFA6" if profit_units >= 0 else "#F97373"
            st.markdown(
                f"""
                <div style="padding:14px 16px;border-radius:12px;
                    background:rgba(15,23,42,0.9);border:1px solid rgba(148,163,184,0.4);">
                    <div style="font-size:11px;text-transform:uppercase;color:#9CA3AF;">Profit</div>
                    <div style="font-size:26px;font-weight:700;color:{color};">
                        {profit_units:+.1f} units
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
                        {won_count}/{len(non_void_bets)} won{f' ({void_count} void)' if void_count > 0 else ''}
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
            
            if ev >= 20:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(0,255,166,0.25), rgba(0,255,166,0.15))", "rgba(0,255,166,0.9)", "#00FFA6", "0 0 12px rgba(0,255,166,0.6)"
            elif ev >= 8:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(34,197,94,0.22), rgba(34,197,94,0.12))", "rgba(34,197,94,0.85)", "#22C55E", "0 0 8px rgba(34,197,94,0.4)"
            elif ev >= 3:
                ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.08))", "rgba(59,130,246,0.75)", "#60A5FA", "none"
            else:
                ev_bg, ev_border, ev_color, ev_glow = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.5)", "#94A3B8", "none"

            parlay_desc = str(row.get("parlay_description", "") or "")
            
            if "|" in parlay_desc:
                legs_list = [p.strip() for p in parlay_desc.split("|") if p.strip()]
            elif "+" in parlay_desc:
                legs_list = [p.strip() for p in parlay_desc.split("+") if p.strip()]
            else:
                legs_list = [parlay_desc] if parlay_desc else []
            
            legs_html = "".join([f"<div style='margin:3px 0;font-size:13px;color:#CBD5E1;'>• {p}</div>" for p in legs_list]) if legs_list else ""

            match_str = format_kickoff(row.get("match_date"))
            home_team = str(row.get('home_team', '')).replace('"', '&quot;')
            away_team = str(row.get('away_team', '')).replace('"', '&quot;')
            odds_val = float(row.get('odds', 0))
            num_legs = len(legs_list)

            mm_bullets = []
            if ev >= 10:
                mm_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">📊</span><span>Combined EV: +{ev:.1f}% exceeds threshold</span></div>')
            if num_legs >= 2:
                mm_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">🧮</span><span>{num_legs} legs selected from L1/L2 approved singles</span></div>')
            if odds_val >= 3.0:
                mm_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">💰</span><span>Combined odds {odds_val:.2f}x in target range</span></div>')
            else:
                mm_bullets.append(f'<div style="display:flex;align-items:center;gap:8px;"><span style="font-size:12px;opacity:0.7;">⚽</span><span>Cross-match diversification reduces correlation</span></div>')
            mm_max = 3 if ev >= 5 else 2
            mm_bullets = mm_bullets[:mm_max]
            mm_why_html = ''.join(mm_bullets) if mm_bullets else '<div style="color:#6B7280;font-size:12px;">Built from approved value singles</div>'
            mm_glow = "rgba(0,255,166,0.08)" if ev >= 8 else "rgba(59,130,246,0.06)"
            mm_why_section = f'''<details style="margin-top:12px;"><summary style="cursor:pointer;font-size:12px;color:#6B7280;padding:6px 0;user-select:none;list-style:none;display:flex;align-items:center;gap:6px;"><span style="color:#9CA3AF;">Why this pick</span><span style="font-size:10px;">▾</span></summary><div style="margin-top:8px;padding:12px;border-radius:10px;background:linear-gradient(135deg, rgba(10,18,35,0.95), rgba(20,30,50,0.9));box-shadow:inset 0 0 20px {mm_glow};font-size:12px;color:#CBD5E1;display:flex;flex-direction:column;gap:6px;">{mm_why_html}</div></details>'''

            card_html = f'<div style="padding:20px;margin:16px 0;border-radius:16px;background:linear-gradient(145deg, rgba(15,23,42,0.98), rgba(30,41,59,0.95));border:1px solid rgba(0,255,166,0.35);box-shadow:0 8px 32px rgba(0,255,166,0.2), 0 4px 16px rgba(0,0,0,0.4);"><div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;"><div><div style="font-size:12px;color:#6B7280;margin-bottom:4px;">{match_str}</div><div style="font-size:17px;font-weight:600;color:#E5E7EB;">{home_team} vs {away_team}</div></div><div style="padding:6px 12px;border-radius:8px;background:{ev_bg};border:1px solid {ev_border};box-shadow:{ev_glow};"><div style="font-size:10px;color:{ev_color};font-weight:700;letter-spacing:0.1em;">EV</div><div style="font-size:18px;font-weight:800;color:{ev_color};">{ev:+.1f}%</div></div></div><div style="margin:12px 0;"><span style="font-size:10px;padding:3px 10px;border-radius:6px;background:rgba(168,85,247,0.15);color:#A855F7;font-weight:600;letter-spacing:0.04em;">{num_legs}-LEG PARLAY</span></div><div style="margin:8px 0;">{legs_html}</div><div style="display:flex;gap:8px;margin-top:12px;"><div style="padding:8px 14px;border-radius:10px;background:linear-gradient(135deg, rgba(0,255,166,0.25), rgba(34,197,94,0.15));border:2px solid rgba(0,255,166,0.7);box-shadow:0 0 16px rgba(0,255,166,0.3);"><div style="font-size:9px;color:#00FFA6;font-weight:700;">COMBINED</div><div style="font-size:20px;font-weight:800;color:#00FFA6;">{odds_val:.2f}</div></div></div>{mm_why_section}</div>'
            st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Parlay history")

    history_df = df.sort_values("match_date", ascending=False).head(100)
    display_cols = [c for c in ["match_date", "home_team", "away_team", "parlay_description", "odds", "stake", "ev", "result", "payout"] if c in history_df.columns]
    st.dataframe(
        history_df[display_cols],
        use_container_width=True,
        hide_index=True,
    )


# ------------- PROPS & SPECIALS TAB ------------- #

@st.cache_data(ttl=120, show_spinner="Loading props bets...")
def load_props_bets() -> pd.DataFrame:
    """Load Cards, Corners, and Shots bets from football_opportunities table."""
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        query = text("""
            SELECT 
                id, match_id, home_team, away_team, league, market, selection,
                odds, edge_percentage as ev, confidence, trust_level,
                match_date, kickoff_time, status, result, profit_loss,
                mode, raw_ev, boosted_ev, weighted_ev,
                profile_boost_score, market_weight, outcome
            FROM football_opportunities
            WHERE market IN ('Cards', 'Corners', 'Shots')
            ORDER BY match_date DESC, id DESC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        for col in ["odds", "ev", "confidence", "profit_loss", "raw_ev", "boosted_ev", "weighted_ev"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        if "match_date" in df.columns:
            df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
        
        return df
    except Exception as e:
        st.warning(f"Could not load props bets: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner="Loading bookmaker odds...")
def load_bookmaker_odds() -> pd.DataFrame:
    """Load bookmaker odds comparison data from football_opportunities table."""
    try:
        db_url = get_db_url()
        engine = create_engine(db_url)
        
        from datetime import datetime, timedelta
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        
        query = text("""
            SELECT 
                id, match_id, home_team, away_team, league, market, selection,
                odds, edge_percentage as ev, confidence, model_prob,
                match_date, kickoff_time,
                odds_by_bookmaker, best_odds_value, best_odds_bookmaker, avg_odds, fair_odds
            FROM football_opportunities
            WHERE match_date >= :today AND match_date <= :tomorrow
            AND mode != 'TEST'
            AND market IN ('Value Single', 'over_under', 'btts', '1x2')
            ORDER BY edge_percentage DESC NULLS LAST
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"today": str(today), "tomorrow": str(tomorrow)})
        
        for col in ["odds", "ev", "confidence", "model_prob", "best_odds_value", "avg_odds", "fair_odds"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        if "match_date" in df.columns:
            df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
        
        return df
    except Exception as e:
        st.warning(f"Could not load bookmaker odds: {e}")
        return pd.DataFrame()


def render_bookmaker_odds_card(row: pd.Series):
    """Render a single bookmaker odds comparison card."""
    import json as json_module
    import math
    
    def safe_float(val, default=0.0):
        """Safely convert to float, handling NaN and None."""
        if val is None:
            return default
        try:
            f = float(val)
            return default if math.isnan(f) else f
        except (ValueError, TypeError):
            return default
    
    def safe_str(val, default=''):
        """Safely convert to string, handling NaN and None."""
        if val is None:
            return default
        if isinstance(val, float) and math.isnan(val):
            return default
        s = str(val)
        return default if s.lower() in ['nan', 'none', ''] else s
    
    home_team = safe_str(row.get('home_team', '')).replace('"', '&quot;')
    away_team = safe_str(row.get('away_team', '')).replace('"', '&quot;')
    fixture = f"{home_team} vs {away_team}"
    
    selection = safe_str(row.get('selection', ''))
    market = safe_str(row.get('market', ''))
    current_odds = safe_float(row.get('odds', 0))
    best_odds = safe_float(row.get('best_odds_value', 0))
    best_bookmaker = safe_str(row.get('best_odds_bookmaker', ''))
    avg_odds = safe_float(row.get('avg_odds', 0))
    fair_odds = safe_float(row.get('fair_odds', 0))
    ev = safe_float(row.get('ev', 0))
    
    odds_by_bookmaker = row.get('odds_by_bookmaker', {})
    if isinstance(odds_by_bookmaker, str):
        try:
            odds_by_bookmaker = json_module.loads(odds_by_bookmaker)
        except:
            odds_by_bookmaker = {}
    elif not isinstance(odds_by_bookmaker, dict):
        odds_by_bookmaker = {}
    
    if ev >= 20:
        ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(0,255,166,0.25), rgba(0,255,166,0.15))", "rgba(0,255,166,0.9)", "#00FFA6", "0 0 12px rgba(0,255,166,0.6)"
    elif ev >= 8:
        ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(34,197,94,0.22), rgba(34,197,94,0.12))", "rgba(34,197,94,0.85)", "#22C55E", "0 0 8px rgba(34,197,94,0.4)"
    elif ev >= 3:
        ev_bg, ev_border, ev_color, ev_glow = "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.08))", "rgba(59,130,246,0.75)", "#60A5FA", "none"
    else:
        ev_bg, ev_border, ev_color, ev_glow = "rgba(148,163,184,0.10)", "rgba(148,163,184,0.5)", "#94A3B8", "none"
    
    MAJOR_BOOKMAKERS = [
        'Pinnacle', 'Bet365', 'Betfair', 'Unibet', 'Betway', 'William Hill',
        'Ladbrokes', 'Paddy Power', 'Coral', 'Sky Bet', 'BetMGM', 'DraftKings',
        'FanDuel', 'Betsson', '1xBet', 'Bovada', 'BetOnline.ag', 'Marathon Bet'
    ]
    
    sorted_bookmakers = sorted(odds_by_bookmaker.items(), key=lambda x: float(x[1]) if x[1] else 0, reverse=True) if odds_by_bookmaker else []
    
    best_book = sorted_bookmakers[0] if len(sorted_bookmakers) > 0 else None
    second_best_book = sorted_bookmakers[1] if len(sorted_bookmakers) > 1 else None
    third_best_book = sorted_bookmakers[2] if len(sorted_bookmakers) > 2 else None
    
    major_odds = {}
    for book_name, book_odds in odds_by_bookmaker.items():
        for major in MAJOR_BOOKMAKERS:
            if major.lower() in book_name.lower():
                major_odds[book_name] = float(book_odds) if book_odds else 0
                break
    
    bookmaker_html = ""
    
    if best_book:
        bookmaker_html += f'<div style="display:inline-block;padding:8px 14px;margin:4px;border-radius:10px;background:linear-gradient(135deg, rgba(0,255,166,0.25), rgba(0,200,130,0.15));border:2px solid rgba(0,255,166,0.7);box-shadow:0 0 10px rgba(0,255,166,0.3);"><div style="font-size:10px;color:#00FFA6;font-weight:600;text-transform:uppercase;">BEST</div><div style="font-size:12px;color:#E5E7EB;margin-top:2px;">{best_book[0]}</div><div style="font-size:20px;font-weight:700;color:#00FFA6;">{float(best_book[1]):.2f}</div></div>'
    
    if second_best_book:
        bookmaker_html += f'<div style="display:inline-block;padding:8px 14px;margin:4px;border-radius:10px;background:linear-gradient(135deg, rgba(59,130,246,0.3), rgba(99,102,241,0.2));border:2px solid rgba(59,130,246,0.7);"><div style="font-size:10px;color:#60A5FA;font-weight:600;text-transform:uppercase;">2ND</div><div style="font-size:12px;color:#E5E7EB;margin-top:2px;">{second_best_book[0]}</div><div style="font-size:20px;font-weight:700;color:#60A5FA;">{float(second_best_book[1]):.2f}</div></div>'
    
    if third_best_book:
        bookmaker_html += f'<div style="display:inline-block;padding:8px 14px;margin:4px;border-radius:10px;background:rgba(148,163,184,0.15);border:1px solid rgba(148,163,184,0.4);"><div style="font-size:10px;color:#94A3B8;font-weight:600;text-transform:uppercase;">3RD</div><div style="font-size:12px;color:#CBD5E1;margin-top:2px;">{third_best_book[0]}</div><div style="font-size:18px;font-weight:600;color:#94A3B8;">{float(third_best_book[1]):.2f}</div></div>'
    
    shown_books = set([best_book[0] if best_book else '', second_best_book[0] if second_best_book else '', third_best_book[0] if third_best_book else ''])
    major_sorted = sorted([(k, v) for k, v in major_odds.items() if k not in shown_books], key=lambda x: x[1], reverse=True)[:4]
    
    if major_sorted:
        bookmaker_html += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid rgba(148,163,184,0.2);">'
        bookmaker_html += '<div style="width:100%;font-size:10px;color:#6B7280;margin-bottom:4px;">MAJOR BOOKMAKERS:</div>'
        for book_name, book_odds in major_sorted:
            bookmaker_html += f'<div style="display:inline-block;padding:6px 10px;border-radius:8px;background:rgba(55,65,81,0.4);border:1px solid rgba(75,85,99,0.5);"><div style="font-size:11px;color:#9CA3AF;">{book_name}</div><div style="font-size:15px;font-weight:600;color:#E5E7EB;">{book_odds:.2f}</div></div>'
        bookmaker_html += '</div>'
    
    fair_vs_best = ""
    if fair_odds > 0 and best_odds > 0:
        edge_vs_fair = ((best_odds / fair_odds) - 1) * 100
        edge_color = "#22C55E" if edge_vs_fair >= 0 else "#EF4444"
        fair_vs_best = f'<div style="margin-top:8px;padding:8px;background:rgba(99,102,241,0.1);border-radius:8px;border:1px solid rgba(99,102,241,0.3);"><div style="display:flex;justify-content:space-between;align-items:center;"><div><span style="font-size:11px;color:#9CA3AF;">Model Fair Odds:</span><span style="font-size:14px;color:#A5B4FC;font-weight:500;margin-left:6px;">{fair_odds:.2f}</span></div><div><span style="font-size:11px;color:#9CA3AF;">Edge vs Fair:</span><span style="font-size:14px;color:{edge_color};font-weight:600;margin-left:6px;">{edge_vs_fair:+.1f}%</span></div><div><span style="font-size:11px;color:#9CA3AF;">Avg Odds:</span><span style="font-size:14px;color:#E5E7EB;margin-left:6px;">{avg_odds:.2f}</span></div></div></div>'
    
    bookmaker_section = ""
    if bookmaker_html:
        bookmaker_section = f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{bookmaker_html}</div>'
    
    comparing_count = len(odds_by_bookmaker) if odds_by_bookmaker else 0
    card_html = f'<div style="padding:20px;margin:16px 0;border-radius:16px;background:linear-gradient(145deg, rgba(15,23,42,0.98), rgba(30,41,59,0.95));border:1px solid rgba(0,255,166,0.35);box-shadow:0 8px 32px rgba(0,255,166,0.2), 0 4px 16px rgba(0,0,0,0.4);"><div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;"><div><div style="font-size:17px;font-weight:600;color:#E5E7EB;">{fixture}</div><div style="display:flex;align-items:center;gap:8px;margin-top:6px;"><div style="font-size:22px;font-weight:700;color:#F8FAFC;">{selection}</div></div></div><div style="padding:6px 12px;border-radius:8px;background:{ev_bg};border:1px solid {ev_border};box-shadow:{ev_glow};"><div style="font-size:10px;color:{ev_color};font-weight:700;letter-spacing:0.1em;">EV</div><div style="font-size:18px;font-weight:800;color:{ev_color};">{ev:+.1f}%</div></div></div><div style="font-size:11px;color:#6B7280;margin-bottom:10px;">{comparing_count} bookmakers compared</div>{bookmaker_section}{fair_vs_best}</div>'
    st.markdown(card_html, unsafe_allow_html=True)


def render_bookmaker_odds_section():
    """Render the bookmaker odds comparison section."""
    st.markdown("## Bookmaker Odds Comparison")
    st.caption("Compare odds across bookmakers to find the best value. Green = above fair odds, Red = below fair odds.")
    
    odds_df = load_bookmaker_odds()
    
    if odds_df.empty:
        st.info("No bookmaker odds data available for today's picks yet. Odds are collected when predictions are generated.")
        return
    
    has_odds_data = odds_df['odds_by_bookmaker'].apply(
        lambda x: bool(x) if isinstance(x, dict) else (
            bool(x) if x and str(x) not in ['{}', 'None', 'null', ''] else False
        )
    ).any()
    
    if not has_odds_data:
        st.info("Bookmaker odds comparison data is being collected. Check back after the next prediction run.")
        return
    
    import json as json_module
    
    def count_bookmakers(x):
        if isinstance(x, dict):
            return len(x)
        if isinstance(x, str) and x not in ['{}', 'None', 'null', '']:
            try:
                parsed = json_module.loads(x)
                return len(parsed) if isinstance(parsed, dict) else 0
            except:
                return 0
        return 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        avg_books = odds_df['odds_by_bookmaker'].apply(count_bookmakers).mean()
        st.metric("Avg Bookmakers", f"{avg_books:.1f}")
    with col2:
        st.metric("Total Selections", len(odds_df))
    with col3:
        with_best = odds_df['best_odds_bookmaker'].notna().sum()
        st.metric("With Best Odds", with_best)
    
    st.markdown("---")
    
    for _, row in odds_df.iterrows():
        render_bookmaker_odds_card(row)


def compute_props_roi(df: pd.DataFrame) -> dict:
    """Compute ROI metrics for props bets."""
    if df.empty:
        return {"bets": 0, "wins": 0, "losses": 0, "pending": 0, "needs_verification": 0, "units_won": 0.0, "roi": 0.0, "hit_rate": 0.0}
    
    result_col = df["result"].fillna("").str.lower() if "result" in df.columns else pd.Series([""] * len(df))
    status_col = df["status"].fillna("").str.lower() if "status" in df.columns else pd.Series([""] * len(df))
    
    wins = result_col.str.contains("won|win", na=False).sum()
    losses = result_col.str.contains("lost|loss", na=False).sum()
    voids = result_col.str.contains("void", na=False).sum()
    
    needs_verification = status_col.str.contains("needs_verification|needs verification", na=False).sum()
    if "outcome" in df.columns:
        outcome_col = df["outcome"].fillna("").str.lower()
        needs_verification = max(needs_verification, outcome_col.str.contains("needs_verification|needs verification", na=False).sum())
    
    pending = len(df) - wins - losses - voids
    
    settled = wins + losses
    if settled == 0:
        return {"bets": len(df), "wins": 0, "losses": 0, "pending": pending, "needs_verification": needs_verification, "units_won": 0.0, "roi": 0.0, "hit_rate": 0.0}
    
    if "profit_loss" in df.columns:
        units_won = df["profit_loss"].fillna(0).sum()
    else:
        units_won = 0.0
        for _, row in df.iterrows():
            res = str(row.get("result", "")).lower()
            odds = float(row.get("odds", 2.0) or 2.0)
            if "won" in res or "win" in res:
                units_won += (odds - 1)
            elif "lost" in res or "loss" in res:
                units_won -= 1
    
    roi = (units_won / settled * 100) if settled > 0 else 0.0
    hit_rate = (wins / settled * 100) if settled > 0 else 0.0
    
    return {"bets": len(df), "wins": wins, "losses": losses, "pending": pending, "needs_verification": needs_verification, "units_won": units_won, "roi": roi, "hit_rate": hit_rate}


def render_props_tab():
    """Render the Props & Specials tab with Corners, Cards, and Shots predictions."""
    st.markdown("## Props & Specials")
    st.caption("Advanced markets: Corners, Cards, and Team Shots predictions using Monte Carlo simulation.")
    
    props_df = load_props_bets()
    
    if not props_df.empty:
        needs_verif_count = 0
        if "outcome" in props_df.columns:
            needs_verif_count = props_df["outcome"].fillna("").str.contains("needs_verification", na=False).sum()
        
        if needs_verif_count > 0:
            st.warning(f"{needs_verif_count} bets need manual verification. Corner/Card statistics require match statistics API which has reached its daily limit. Results will be verified when API access is restored.")
        
        st.markdown("### Performance Summary")
        
        corners_df = props_df[props_df["market"] == "Corners"]
        cards_df = props_df[props_df["market"] == "Cards"]
        shots_df = props_df[props_df["market"] == "Shots"]
        
        corners_stats = compute_props_roi(corners_df)
        cards_stats = compute_props_roi(cards_df)
        shots_stats = compute_props_roi(shots_df)
        total_stats = compute_props_roi(props_df)
        
        cols = st.columns(4)
        stats_data = [
            ("Corners", corners_stats, "#10B981"),
            ("Cards", cards_stats, "#F59E0B"),
            ("Shots", shots_stats, "#6366F1"),
            ("Total Props", total_stats, "#00FFC2"),
        ]
        
        for i, (name, stats, color) in enumerate(stats_data):
            with cols[i]:
                roi_color = color if stats["roi"] >= 0 else "#EF4444"
                st.markdown(f"""
                <div style="padding:16px;border-radius:12px;background:linear-gradient(135deg, {color}22, rgba(15,23,42,0.95));border:1px solid {color}55;">
                    <div style="font-size:15px;font-weight:600;color:{color};margin-bottom:8px;">{name}</div>
                    <div style="font-size:24px;font-weight:700;color:{roi_color};">{stats['roi']:+.1f}%</div>
                    <div style="font-size:12px;color:#9CA3AF;">ROI</div>
                    <div style="display:flex;gap:12px;margin-top:8px;">
                        <div><span style="color:#10B981;font-weight:600;">{stats['wins']}</span><span style="color:#6B7280;"> W</span></div>
                        <div><span style="color:#EF4444;font-weight:600;">{stats['losses']}</span><span style="color:#6B7280;"> L</span></div>
                        <div><span style="color:#F59E0B;font-weight:600;">{stats['pending']}</span><span style="color:#6B7280;"> P</span></div>
                    </div>
                    <div style="font-size:11px;color:#9CA3AF;margin-top:4px;">
                        {stats['units_won']:+.2f} units | {stats['hit_rate']:.0f}% hit
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### Recent Props Bets")
        
        market_filter = st.selectbox("Filter by market:", ["All", "Corners", "Cards", "Shots"])
        if market_filter != "All":
            display_df = props_df[props_df["market"] == market_filter].copy()
        else:
            display_df = props_df.copy()
        
        display_cols = ["match_date", "home_team", "away_team", "market", "selection", "odds", "trust_level", "result", "profit_loss"]
        display_cols = [c for c in display_cols if c in display_df.columns]
        
        st.dataframe(
            display_df[display_cols].head(100),
            use_container_width=True,
            hide_index=True,
        )
        
        st.markdown("---")
    
    try:
        from corners_engine import CornersEngine, run_corners_cycle
        from cards_engine import CardsEngine, run_cards_cycle
        from shots_engine import ShotsEngine, run_shots_cycle
        from unified_ev_filter import get_filter_stats, PRODUCT_FILTER_CONFIGS
        
        st.markdown("### Engine Configuration")
        
        props_config = {
            "CORNERS_MATCH": {"max_day": 6, "markets": ["Over/Under 8.5, 9.5, 10.5, 11.5 Corners"]},
            "CORNERS_TEAM": {"max_day": 4, "markets": ["Home/Away Team Corners Over X"]},
            "CORNERS_HANDICAP": {"max_day": 6, "markets": ["Corner Handicaps -2.5, -1.5, +0.5"]},
            "CARDS_MATCH": {"max_day": 6, "markets": ["Total Cards Over/Under, Booking Points"]},
            "CARDS_TEAM": {"max_day": 4, "markets": ["Home/Away Team Cards Over X"]},
            "SHOTS_TEAM": {"max_day": 6, "markets": ["Team Shots Over, SOT Over"]},
        }
        
        cols = st.columns(3)
        for i, (product, config) in enumerate(props_config.items()):
            with cols[i % 3]:
                filter_cfg = PRODUCT_FILTER_CONFIGS.get(product, {})
                l1_ev = getattr(filter_cfg, 'l1_min_ev', 0.05) * 100
                l2_ev = getattr(filter_cfg, 'l2_min_ev', 0.02) * 100
                
                st.markdown(f"""
                <div style="padding:12px;border-radius:10px;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.3);margin-bottom:10px;">
                    <div style="font-size:14px;font-weight:600;color:#A5B4FC;">{product.replace('_', ' ')}</div>
                    <div style="font-size:11px;color:#9CA3AF;">Max: {config['max_day']}/day</div>
                    <div style="font-size:11px;color:#9CA3AF;">L1: EV≥{l1_ev:.0f}% | L2: EV≥{l2_ev:.0f}%</div>
                    <div style="font-size:10px;color:#6B7280;margin-top:4px;">{config['markets'][0]}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### Trust Tier Filter Summary")
        
        tier_info = [
            ("L1 HIGH TRUST", "#10B981", "EV ≥ 5%, Confidence ≥ 55%, Sim Approved"),
            ("L2 MEDIUM TRUST", "#F59E0B", "EV ≥ 2%, Confidence ≥ 52%, Sim Approved"),
            ("L3 SOFT VALUE", "#6B7280", "EV ≥ 0%, Confidence ≥ 50%"),
        ]
        
        cols = st.columns(3)
        for i, (tier, color, desc) in enumerate(tier_info):
            with cols[i]:
                st.markdown(f"""
                <div style="padding:12px;border-radius:10px;background:{color}22;border:1px solid {color}55;">
                    <div style="font-size:13px;font-weight:600;color:{color};">{tier}</div>
                    <div style="font-size:10px;color:#9CA3AF;">{desc}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### Recent Props Predictions")
        st.info("Props predictions are generated by the Combined Sports Engine. "
                "Check the Daily Card tab for today's picks, sorted by trust tier and EV.")
        
        st.markdown("### Engine Status")
        status_cols = st.columns(3)
        
        with status_cols[0]:
            st.markdown("""
            <div style="padding:16px;border-radius:12px;background:linear-gradient(135deg, rgba(16,185,129,0.15), rgba(15,23,42,0.95));border:1px solid rgba(16,185,129,0.3);">
                <div style="font-size:20px;margin-bottom:8px;">🔢</div>
                <div style="font-size:16px;font-weight:600;color:#10B981;">Corners v3.0</div>
                <div style="font-size:12px;color:#9CA3AF;">Pace • Wing Play • Referee • Weather</div>
                <div style="font-size:11px;color:#6EE7B7;margin-top:8px;">✅ Active</div>
            </div>
            """, unsafe_allow_html=True)
        
        with status_cols[1]:
            st.markdown("""
            <div style="padding:16px;border-radius:12px;background:linear-gradient(135deg, rgba(245,158,11,0.15), rgba(15,23,42,0.95));border:1px solid rgba(245,158,11,0.3);">
                <div style="font-size:20px;margin-bottom:8px;">🟨</div>
                <div style="font-size:16px;font-weight:600;color:#F59E0B;">Cards v2.0</div>
                <div style="font-size:12px;color:#9CA3AF;">Referee • Rivalry • Formation • Tempo</div>
                <div style="font-size:11px;color:#FCD34D;margin-top:8px;">✅ Active</div>
            </div>
            """, unsafe_allow_html=True)
        
        with status_cols[2]:
            st.markdown("""
            <div style="padding:16px;border-radius:12px;background:linear-gradient(135deg, rgba(99,102,241,0.15), rgba(15,23,42,0.95));border:1px solid rgba(99,102,241,0.3);">
                <div style="font-size:20px;margin-bottom:8px;">🎯</div>
                <div style="font-size:16px;font-weight:600;color:#6366F1;">Shots v1.0</div>
                <div style="font-size:12px;color:#9CA3AF;">Attack Power • Defence • xG • Tempo</div>
                <div style="font-size:11px;color:#A5B4FC;margin-top:8px;">✅ Active</div>
            </div>
            """, unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"Error loading Props tab: {e}")


# ------------- KELLY STAKE CALCULATOR ------------- #

def render_kelly_calculator():
    """Render the Kelly Criterion stake calculator."""
    st.markdown("""
    <div style="text-align:center;padding:20px 0;">
        <h2 style="color:#10B981;margin-bottom:5px;">Stake Calculator</h2>
        <p style="color:#9CA3AF;font-size:14px;">Kelly Criterion-based bankroll management</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### Input Parameters")
        
        bankroll = st.number_input(
            "Bankroll (SEK)",
            min_value=100.0,
            max_value=1000000.0,
            value=10000.0,
            step=1000.0,
            help="Your total betting bankroll"
        )
        
        odds = st.number_input(
            "Decimal Odds",
            min_value=1.01,
            max_value=100.0,
            value=2.00,
            step=0.05,
            help="The decimal odds offered by the bookmaker"
        )
        
        model_prob = st.slider(
            "Win Probability (%)",
            min_value=1,
            max_value=99,
            value=55,
            help="Your estimated probability of winning"
        ) / 100.0
        
        market_type = st.selectbox(
            "Market Type",
            options=["single", "parlay", "sgp"],
            index=0,
            help="Single bet or accumulator"
        )
        
        risk_profile = st.selectbox(
            "Risk Profile",
            options=["conservative", "balanced", "aggressive"],
            index=1,
            help="Conservative (10% Kelly), Balanced (25% Kelly), Aggressive (50% Kelly)"
        )
        
        unit_value = st.number_input(
            "Unit Value (SEK)",
            min_value=10.0,
            max_value=10000.0,
            value=100.0,
            step=10.0,
            help="How much 1 unit is worth"
        )
    
    with col2:
        st.markdown("### Recommendation")
        
        cfg = StakeConfig(unit_value_sek=unit_value)
        result = suggest_stake(
            bankroll=bankroll,
            odds_decimal=odds,
            model_prob=model_prob,
            market_type=market_type,
            risk_profile=risk_profile,
            cfg=cfg
        )
        
        implied_prob = 1 / odds
        edge_pct = (model_prob - implied_prob) * 100
        ev_pct = result.get('ev', 0) * 100
        
        if result.get('ok', False):
            stake_units = result.get('stake_units', 0)
            stake_amount = result.get('stake_amount', 0)
            potential_win = stake_amount * (odds - 1)
            
            st.markdown(f"""
            <div style="background:linear-gradient(135deg, rgba(16,185,129,0.2), rgba(15,23,42,0.95));
                        border:2px solid #10B981;border-radius:16px;padding:24px;margin-bottom:16px;">
                <div style="text-align:center;">
                    <div style="font-size:14px;color:#9CA3AF;margin-bottom:8px;">RECOMMENDED STAKE</div>
                    <div style="font-size:48px;font-weight:700;color:#10B981;">{stake_units:.2f}u</div>
                    <div style="font-size:20px;color:#6EE7B7;">{stake_amount:,.0f} SEK</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Edge", f"{edge_pct:.1f}%")
            with m2:
                st.metric("EV", f"{ev_pct:.1f}%")
            with m3:
                st.metric("Potential Win", f"{potential_win:,.0f} SEK")
            
            st.markdown(f"""
            <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:16px;margin-top:16px;">
                <div style="font-size:12px;color:#9CA3AF;margin-bottom:8px;">CALCULATION DETAILS</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">
                    <div><span style="color:#6B7280;">Implied Prob:</span> <span style="color:#E5E7EB;">{implied_prob*100:.1f}%</span></div>
                    <div><span style="color:#6B7280;">Model Prob:</span> <span style="color:#E5E7EB;">{model_prob*100:.1f}%</span></div>
                    <div><span style="color:#6B7280;">Full Kelly:</span> <span style="color:#E5E7EB;">{result.get('kelly_full_fraction', 0)*100:.2f}%</span></div>
                    <div><span style="color:#6B7280;">Fractional Kelly:</span> <span style="color:#E5E7EB;">{result.get('kelly_fractional_fraction', 0)*100:.2f}%</span></div>
                    <div><span style="color:#6B7280;">Risk Profile:</span> <span style="color:#E5E7EB;">{risk_profile.title()}</span></div>
                    <div><span style="color:#6B7280;">Market Type:</span> <span style="color:#E5E7EB;">{market_type.upper()}</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            reason = result.get('reason', 'unknown')
            st.markdown(f"""
            <div style="background:linear-gradient(135deg, rgba(239,68,68,0.2), rgba(15,23,42,0.95));
                        border:2px solid #EF4444;border-radius:16px;padding:24px;text-align:center;">
                <div style="font-size:32px;margin-bottom:8px;">⚠️</div>
                <div style="font-size:18px;font-weight:600;color:#EF4444;">No Bet Recommended</div>
                <div style="font-size:14px;color:#FCA5A5;margin-top:8px;">{reason.replace('_', ' ').title()}</div>
                <div style="font-size:13px;color:#9CA3AF;margin-top:12px;">
                    Edge: {edge_pct:.1f}% | EV: {ev_pct:.1f}%
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("### Kelly Criterion Explained")
    with st.expander("How it works"):
        st.markdown("""
        **Kelly Criterion** calculates the optimal bet size to maximize long-term growth while minimizing risk of ruin.
        
        **Formula:** f* = (bp - q) / b
        - f* = fraction of bankroll to bet
        - b = decimal odds - 1
        - p = probability of winning
        - q = probability of losing (1 - p)
        
        **Risk Profiles:**
        - **Conservative (10%)**: Slower growth, lower variance
        - **Balanced (25%)**: Good balance of growth and safety
        - **Aggressive (50%)**: Faster growth, higher volatility
        
        **Caps Applied:**
        - Max 2% of bankroll per bet
        - Max 2 units per bet
        - Parlays use reduced sizing due to higher variance
        """)


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
    free_tab, daily_card_tab, overview_tab, singles_tab, odds_compare_tab, props_tab, parlays_tab, ml_parlay_tab, basket_tab, kelly_tab, backtest_tab = st.tabs(
        [
            "Free Picks",
            "Daily Card",
            "Overview",
            "Value Singles",
            "Odds Compare",
            "Props & Specials",
            "Parlays",
            "ML Parlay",
            "College Basketball",
            "Stake Calculator",
            "Backtests",
        ]
    )

    with free_tab:
        render_free_predictions_tab()

    with daily_card_tab:
        render_daily_card_tab()

    with overview_tab:
        render_overview(prod_bets)

    with singles_tab:
        render_product_tab(
            prod_bets,
            product_codes=["VALUE_SINGLE", "VALUE_SINGLES", "FOOTBALL_SINGLE", "CORNERS", "CARDS"],  # EXACT_SCORE removed
            title="Value Singles",
            description="High-edge single bets across 1X2, over/under, BTTS, corners and cards.",
        )

    with odds_compare_tab:
        render_bookmaker_odds_section()

    with props_tab:
        render_props_tab()

    with parlays_tab:
        render_parlays_tab()

    with ml_parlay_tab:
        render_ml_parlay_tab()

    with basket_tab:
        render_basketball_tab(prod_bets)

    with kelly_tab:
        render_kelly_calculator()

    with backtest_tab:
        render_backtest_analysis()


if __name__ == "__main__":
    main()