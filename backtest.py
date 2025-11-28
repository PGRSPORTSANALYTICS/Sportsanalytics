"""
backtest.py

Backtest-motor för PGR Sports Analytics.
- Hämtar historiska bets från PostgreSQL
- Räknar payout + profit/loss per bet
- Ger ROI och hitrate totalt och per marknad

Förutsätter:
- PostgreSQL-URL i env: DATABASE_URL
- Tabeller:
    - football_opportunities
    - sgp_predictions
"""

import os
import math
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime

import psycopg2
import psycopg2.extras


# ---------- Datamodell ----------

@dataclass
class Bet:
    source_table: str       # football_opportunities / sgp_predictions
    market_type: str        # 'exact_score' / 'sgp'
    match_date: date
    description: str        # t.ex. "Panathinaikos 2–1 @12.21"
    odds: float
    stake: float
    outcome: str            # 'WON' / 'LOST' / ev annat
    payout: float
    profit: float           # payout - stake
    league: Optional[str] = None


# ---------- Hjälpfunktioner ----------

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL saknas i environment vars.")
    return psycopg2.connect(db_url)


def compute_payout_profit(stake: float, odds: float, outcome: str) -> Tuple[float, float]:
    """
    Standardmodell:
        WON/won  -> payout = stake * odds, profit = payout - stake
        LOST/lost -> payout = 0,           profit = -stake
    """
    if outcome is None:
        return 0.0, 0.0

    outcome_lower = outcome.lower()
    if outcome_lower in ("won", "win"):
        payout = stake * odds
        profit = payout - stake
    elif outcome_lower in ("lost", "loss"):
        payout = 0.0
        profit = -stake
    else:
        # Push / void / unknown -> ingen vinst, ingen förlust
        payout = 0.0
        profit = 0.0

    return payout, profit


# ---------- SQL-hämtning ----------

def fetch_exact_score_bets(
    conn,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Bet]:
    sql = """
        SELECT
            match_date,
            home_team,
            away_team,
            league,
            market,
            selection,
            odds,
            stake,
            outcome,
            payout,
            profit_loss
        FROM football_opportunities
        WHERE market = 'exact_score'
          AND settled_timestamp IS NOT NULL
    """

    params = []
    if start_date:
        sql += " AND match_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND match_date <= %s"
        params.append(end_date)

    sql += " ORDER BY match_date ASC"

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    bets: List[Bet] = []
    for r in rows:
        odds = float(r["odds"] or 0.0)
        stake = float(r["stake"] or 0.0)

        # Om profit_loss finns: använd den.
        if r["profit_loss"] is not None:
            profit = float(r["profit_loss"])
            payout = profit + stake
        else:
            # fallback till outcome-baserad beräkning
            payout, profit = compute_payout_profit(stake, odds, r["outcome"] or "")

        desc = f"{r['home_team']} vs {r['away_team']} – {r['selection']} @{odds}"
        bets.append(
            Bet(
                source_table="football_opportunities",
                market_type="exact_score",
                match_date=r["match_date"],
                description=desc,
                odds=odds,
                stake=stake,
                outcome=r["outcome"] or "",
                payout=payout,
                profit=profit,
                league=r["league"],
            )
        )

    return bets


def fetch_sgp_bets(
    conn,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Bet]:
    sql = """
        SELECT
            match_date,
            home_team,
            away_team,
            league,
            legs,
            bookmaker_odds,
            stake,
            outcome,
            payout,
            profit_loss
        FROM sgp_predictions
        WHERE settled_timestamp IS NOT NULL
    """

    params = []
    if start_date:
        sql += " AND match_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND match_date <= %s"
        params.append(end_date)

    sql += " ORDER BY match_date ASC"

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    bets: List[Bet] = []
    for r in rows:
        odds = float(r["bookmaker_odds"] or 0.0)
        stake = float(r["stake"] or 0.0)

        if r["profit_loss"] is not None:
            profit = float(r["profit_loss"])
            payout = profit + stake
        else:
            payout, profit = compute_payout_profit(stake, odds, r["outcome"] or "")

        desc = f"{r['home_team']} vs {r['away_team']} – {r['legs']} @{odds}"
        bets.append(
            Bet(
                source_table="sgp_predictions",
                market_type="sgp",
                match_date=r["match_date"],
                description=desc,
                odds=odds,
                stake=stake,
                outcome=r["outcome"] or "",
                payout=payout,
                profit=profit,
                league=r["league"],
            )
        )

    return bets


# ---------- Aggregation ----------

def aggregate_metrics(bets: List[Bet]) -> Dict:
    total_stake = sum(b.stake for b in bets)
    total_profit = sum(b.profit for b in bets)
    won = sum(1 for b in bets if b.outcome.lower() in ("won", "win"))
    lost = sum(1 for b in bets if b.outcome.lower() in ("lost", "loss"))

    n_bets = len(bets)
    roi = (total_profit / total_stake * 100) if total_stake > 0 else 0.0
    hitrate = (won / n_bets * 100) if n_bets > 0 else 0.0

    # Per marknadstyp (exact_score, sgp, osv)
    by_market: Dict[str, Dict] = {}
    for b in bets:
        m = b.market_type
        bucket = by_market.setdefault(
            m,
            {"bets": 0, "stake": 0.0, "profit": 0.0, "won": 0, "lost": 0},
        )
        bucket["bets"] += 1
        bucket["stake"] += b.stake
        bucket["profit"] += b.profit
        if b.outcome.lower() in ("won", "win"):
            bucket["won"] += 1
        elif b.outcome.lower() in ("lost", "loss"):
            bucket["lost"] += 1

    # räkna ROI/hitrate per market
    for m, bucket in by_market.items():
        if bucket["stake"] > 0:
            bucket["roi"] = bucket["profit"] / bucket["stake"] * 100
        else:
            bucket["roi"] = 0.0
        if bucket["bets"] > 0:
            bucket["hitrate"] = bucket["won"] / bucket["bets"] * 100
        else:
            bucket["hitrate"] = 0.0

    return {
        "total_bets": n_bets,
        "total_stake": total_stake,
        "total_profit": total_profit,
        "roi_percentage": roi,
        "hitrate_percentage": hitrate,
        "won": won,
        "lost": lost,
        "by_market": by_market,
    }


# ---------- CLI / entrypoint ----------

def run_backtest(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> None:
    """
    Kör en full backtest över Exact Score + SGP.

    start_date / end_date i formatet 'YYYY-MM-DD' (valfritt).
    Om inget anges: backtestar allt som finns i databasen.
    """
    start_d: Optional[date] = (
        datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    )
    end_d: Optional[date] = (
        datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    )

    conn = get_db_connection()
    try:
        exact_bets = fetch_exact_score_bets(conn, start_d, end_d)
        sgp_bets = fetch_sgp_bets(conn, start_d, end_d)

        all_bets: List[Bet] = exact_bets + sgp_bets

        metrics = aggregate_metrics(all_bets)

        print("====== PGR Sports Analytics – Backtest ======")
        if start_d or end_d:
            print(f"Period: {start_d or 'ALL'} → {end_d or 'ALL'}")
        print(f"Antal bets: {metrics['total_bets']}")
        print(f"Total stake: {metrics['total_stake']:.2f}")
        print(f"Total profit: {metrics['total_profit']:.2f}")
        print(f"ROI: {metrics['roi_percentage']:.2f}%")
        print(f"Hitrate: {metrics['hitrate_percentage']:.2f}%")
        print(f"Won: {metrics['won']}  Lost: {metrics['lost']}")
        print()

        print("---- Per market ----")
        for m, bucket in metrics["by_market"].items():
            print(f"[{m}]")
            print(f"  Bets:   {bucket['bets']}")
            print(f"  Stake:  {bucket['stake']:.2f}")
            print(f"  Profit: {bucket['profit']:.2f}")
            print(f"  ROI:    {bucket['roi']:.2f}%")
            print(f"  Hitrate:{bucket['hitrate']:.2f}%")
            print()
    finally:
        conn.close()


if __name__ == "__main__":
    # Du kan sätta BACKTEST_START_DATE / BACKTEST_END_DATE i env,
    # eller bara köra utan för att backtesta allt.
    s = os.getenv("BACKTEST_START_DATE")
    e = os.getenv("BACKTEST_END_DATE")
    run_backtest(start_date=s, end_date=e)