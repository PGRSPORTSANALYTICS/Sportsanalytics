"""
multi_backtest_runner.py
------------------------

Kör backtest / performance-analys för ALLA dina system samtidigt,
baserat på historiska bets i databasen.

Antaganden (som du kan ändra i KONFIG-delen nedan):

- Alla bets ligger i EN tabell (t.ex. "bets")
- Kolumner:
    product     - t.ex. 'VALUE_SINGLE', 'EXACT_SCORE', 'SGP', ...
    mode        - t.ex. 'PROD', 'BACKTEST', 'DEMO'
    stake       - decimal/float, insats i SEK
    payout      - decimal/float, utbetalt belopp (inkl. stake vid vinst)
    created_at  - timestamp när betet skapades

För High-End Bets använder vi samma tabell men filtrerar på EV-kolumnen:
    ev_decimal  - t.ex. 0.12 för 12% edge (ändra namn i config om din kolumn heter något annat)

Kör med:
    python multi_backtest_runner.py

Justera DEFAULT_START/END om du vill byta period.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import psycopg2
import psycopg2.extras

# ============================================================
# KONFIGURATION
# ============================================================

# Postgres-anslutning: använder samma DATABASE_URL som du har i Replit
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL saknas. Lägg in din Postgres-URL i Replit Secrets "
        "(key = DATABASE_URL)."
    )

# Namn på din bets-tabell
BETS_TABLE = "bets"  # ändra om din tabell heter något annat

# Kolumnnamn – ändra här om de skiljer sig i din DB
COL_PRODUCT = "product"
COL_MODE = "mode"
COL_STAKE = "stake"
COL_PAYOUT = "payout"
COL_CREATED_AT = "created_at"
COL_EV = "ev_decimal"  # används bara för high-end; ändra till t.ex. "edge" om du har det

# Default-datum för backtestperiod
DEFAULT_START = date(2024, 9, 1)
DEFAULT_END = date(2024, 11, 25)

# Vilket "mode" vi ska analysera – oftast PROD (livebets),
# men du kan sätta BACKTEST om du vill analysera simulerade bets.
TARGET_MODE = "PROD"

# System / produkter som ska köras
# key = label som skrivs ut i terminalen
# value = (product_code, extra_sql_filter)
SYSTEMS: Dict[str, Tuple[str, Optional[str]]] = {
    "Value Singles": ("VALUE_SINGLE", None),
    "Exact Score / Final Score": ("EXACT_SCORE", None),
    "Same Game Parlays": ("SGP", None),
    "Monster SGP": ("MONSTER_SGP", None),
    "Women 1X2": ("WOMEN_1X2", None),
    "College Basketball": ("COLLEGE_BASKETBALL", None),
    # High-End: filtrerar på EV-kolumnen
    "High-End Bets (8%+ EV)": ("VALUE_SINGLE", f"{COL_EV} >= 0.08"),
}

# ============================================================
# Logging
# ============================================================

logger = logging.getLogger("multi_backtest")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = "[MULTI_BACKTEST] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ============================================================
# Datamodell för resultat
# ============================================================


@dataclass
class BacktestResult:
    system_name: str
    product_code: str
    bets: int
    total_stake: float
    profit: float  # payout - stake
    roi_pct: float

    def pretty(self) -> str:
        return (
            f"{self.system_name} ({self.product_code})\n"
            f"   Bets:   {self.bets}\n"
            f"   Stake:  {self.total_stake:,.2f} SEK\n"
            f"   Profit: {self.profit:,.2f} SEK\n"
            f"   ROI:    {self.roi_pct:.2f}%\n"
        )


# ============================================================
# DB-hjälpare
# ============================================================


def get_connection():
    """Skapar en ny Postgres-connection."""
    return psycopg2.connect(DATABASE_URL)


def run_backtest_for_system(
    system_name: str,
    product_code: str,
    start: date,
    end: date,
    extra_filter: Optional[str] = None,
) -> BacktestResult:
    """
    Läser bets för ett system från databasen och räknar ut
    antal bets, total stake, profit och ROI.
    """

    logger.info("=" * 56)
    logger.info(f"→ {system_name} ({product_code})")
    logger.info(f"   Period: {start} → {end}")
    logger.info(f"   Mode:   {TARGET_MODE}")
    if extra_filter:
        logger.info(f"   Extra filter: {extra_filter}")

    query = f"""
        SELECT
            COUNT(*)                              AS bets,
            COALESCE(SUM({COL_STAKE}), 0)        AS total_stake,
            COALESCE(SUM({COL_PAYOUT} - {COL_STAKE}), 0) AS profit
        FROM {BETS_TABLE}
        WHERE {COL_PRODUCT} = %(product)s
          AND {COL_MODE} = %(mode)s
          AND {COL_CREATED_AT} >= %(start)s
          AND {COL_CREATED_AT} < (%(end)s::date + INTERVAL '1 day')
    """

    params = {
        "product": product_code,
        "mode": TARGET_MODE,
        "start": datetime.combine(start, datetime.min.time()),
        "end": datetime.combine(end, datetime.min.time()),
    }

    if extra_filter:
        query += f" AND ({extra_filter})"

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()

    bets = int(row["bets"]) if row["bets"] is not None else 0
    total_stake = float(row["total_stake"]) if row["total_stake"] is not None else 0.0
    profit = float(row["profit"]) if row["profit"] is not None else 0.0

    if total_stake > 0:
        roi_pct = (profit / total_stake) * 100.0
    else:
        roi_pct = 0.0

    logger.info(f"   Bets:   {bets}")
    logger.info(f"   Stake:  {total_stake:,.2f} SEK")
    logger.info(f"   Profit: {profit:,.2f} SEK")
    logger.info(f"   ROI:    {roi_pct:.2f}%")

    return BacktestResult(
        system_name=system_name,
        product_code=product_code,
        bets=bets,
        total_stake=total_stake,
        profit=profit,
        roi_pct=roi_pct,
    )


# ============================================================
# Huvud-funktion
# ============================================================


def main() -> None:
    logger.info("=" * 56)
    logger.info("PGR MULTI-SYSTEM BACKTEST / PERFORMANCE ANALYSIS")
    logger.info("=" * 56)
    logger.info(f"Default period: {DEFAULT_START} → {DEFAULT_END}")
    logger.info(f"Mode: {TARGET_MODE}\n")

    all_results = []

    for system_name, (product_code, extra_filter) in SYSTEMS.items():
        res = run_backtest_for_system(
            system_name=system_name,
            product_code=product_code,
            start=DEFAULT_START,
            end=DEFAULT_END,
            extra_filter=extra_filter,
        )
        all_results.append(res)

    # Sammanfattning
    logger.info("=" * 56)
    logger.info("SUMMARY")
    logger.info("=" * 56)

    total_bets = sum(r.bets for r in all_results)
    total_stake = sum(r.total_stake for r in all_results)
    total_profit = sum(r.profit for r in all_results)
    total_roi = (total_profit / total_stake) * 100.0 if total_stake > 0 else 0.0

    for r in all_results:
        logger.info(r.pretty())

    logger.info("-" * 56)
    logger.info(f"TOTAL BETS:   {total_bets}")
    logger.info(f"TOTAL STAKE:  {total_stake:,.2f} SEK")
    logger.info(f"TOTAL PROFIT: {total_profit:,.2f} SEK")
    logger.info(f"TOTAL ROI:    {total_roi:.2f}%")
    logger.info("-" * 56)


if __name__ == "__main__":
    main()