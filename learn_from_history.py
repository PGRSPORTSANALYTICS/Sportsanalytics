"""
learn_from_history.py – FIXED VERSION

Anpassad till din verkliga databas:
- football_opportunities använder edge_percentage (inte ev_percentage)
- sgp_predictions använder ev_percentage
"""

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from datetime import datetime, date
import psycopg2
import psycopg2.extras


def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL saknas i environment vars.")
    return psycopg2.connect(db_url)


@dataclass
class TrainingEvent:
    market_type: str
    match_date: date
    league: Optional[str]
    ev: Optional[float]          # EV/edge in %
    odds: Optional[float]
    stake: float
    profit_loss: float


def fetch_training_events(conn) -> List[TrainingEvent]:
    events: List[TrainingEvent] = []

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

        # ----- EXACT SCORE -----
        sql = """
            SELECT match_date, league, edge_percentage, odds, stake, profit_loss
            FROM football_opportunities
            WHERE settled_timestamp IS NOT NULL
              AND market = 'exact_score'
              AND stake IS NOT NULL
              AND profit_loss IS NOT NULL
        """
        cur.execute(sql)
        for r in cur.fetchall():
            events.append(
                TrainingEvent(
                    market_type="exact_score",
                    match_date=r["match_date"],
                    league=r["league"],
                    ev=float(r["edge_percentage"]) if r["edge_percentage"] else None,
                    odds=float(r["odds"]) if r["odds"] else None,
                    stake=float(r["stake"]),
                    profit_loss=float(r["profit_loss"]),
                )
            )

        # ----- VALUE SINGLES (allt som inte är exact score) -----
        sql = """
            SELECT match_date, league, edge_percentage, odds, stake, profit_loss
            FROM football_opportunities
            WHERE settled_timestamp IS NOT NULL
              AND (market IS NULL OR market != 'exact_score')
              AND stake IS NOT NULL
              AND profit_loss IS NOT NULL
        """
        cur.execute(sql)
        for r in cur.fetchall():
            events.append(
                TrainingEvent(
                    market_type="value_single",
                    match_date=r["match_date"],
                    league=r["league"],
                    ev=float(r["edge_percentage"]) if r["edge_percentage"] else None,
                    odds=float(r["odds"]) if r["odds"] else None,
                    stake=float(r["stake"]),
                    profit_loss=float(r["profit_loss"]),
                )
            )

        # ----- SGP -----
        sql = """
            SELECT match_date, league, ev_percentage, bookmaker_odds, stake, profit_loss
            FROM sgp_predictions
            WHERE settled_timestamp IS NOT NULL
              AND stake IS NOT NULL
              AND profit_loss IS NOT NULL
        """
        cur.execute(sql)
        for r in cur.fetchall():
            events.append(
                TrainingEvent(
                    market_type="sgp",
                    match_date=r["match_date"],
                    league=r["league"],
                    ev=float(r["ev_percentage"]) if r["ev_percentage"] else None,
                    odds=float(r["bookmaker_odds"]) if r["bookmaker_odds"] else None,
                    stake=float(r["stake"]),
                    profit_loss=float(r["profit_loss"]),
                )
            )

    return events


@dataclass
class Policy:
    market_type: str
    min_ev: float
    min_samples: int
    roi_at_threshold: float


def compute_ev_policies(
    events: List[TrainingEvent],
    ev_min=0.0,
    ev_max=40.0,
    bucket_size=5.0,
    min_bucket_samples=15,
) -> Dict[str, Policy]:

    buckets = {}

    def to_bucket(ev):
        if ev is None:
            return None
        if ev < ev_min or ev >= ev_max:
            return None
        return int((ev - ev_min) // bucket_size)

    for e in events:
        idx = to_bucket(e.ev)
        if idx is None:
            continue

        mb = buckets.setdefault(e.market_type, {})
        b = mb.setdefault(idx, {"stake": 0.0, "profit": 0.0, "bets": 0})

        b["stake"] += e.stake
        b["profit"] += e.profit_loss
        b["bets"] += 1

    policies = {}

    for market_type, mb in buckets.items():
        bucket_stats = []

        for idx, stats in sorted(mb.items()):
            if stats["bets"] < min_bucket_samples or stats["stake"] <= 0:
                continue

            ev_low = ev_min + idx * bucket_size
            roi = stats["profit"] / stats["stake"] * 100

            bucket_stats.append((ev_low, roi, stats["bets"]))

        if not bucket_stats:
            policies[market_type] = Policy(
                market_type, min_ev=ev_max, min_samples=0, roi_at_threshold=0
            )
            continue

        chosen = None
        for ev_low, roi, bets in bucket_stats:
            if roi > 0:
                chosen = (ev_low, roi, bets)
                break

        if not chosen:
            chosen = max(bucket_stats, key=lambda x: x[1])

        ev_low, roi, bets = chosen

        policies[market_type] = Policy(
            market_type,
            min_ev=ev_low,
            min_samples=bets,
            roi_at_threshold=roi,
        )

    return policies


def ensure_policy_table(conn):
    sql = """
    CREATE TABLE IF NOT EXISTS betting_policy (
        market_type TEXT PRIMARY KEY,
        min_ev DOUBLE PRECISION NOT NULL,
        min_samples INTEGER NOT NULL,
        roi_at_threshold DOUBLE PRECISION NOT NULL,
        updated_at TIMESTAMP NOT NULL
    );
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def save_policies(conn, policies):
    ensure_policy_table(conn)
    now = datetime.utcnow()

    with conn.cursor() as cur:
        for p in policies.values():
            cur.execute(
                """
                INSERT INTO betting_policy (market_type, min_ev, min_samples, roi_at_threshold, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (market_type)
                DO UPDATE SET
                    min_ev = EXCLUDED.min_ev,
                    min_samples = EXCLUDED.min_samples,
                    roi_at_threshold = EXCLUDED.roi_at_threshold,
                    updated_at = EXCLUDED.updated_at;
            """,
                (p.market_type, p.min_ev, p.min_samples, p.roi_at_threshold, now),
            )

    conn.commit()


def main():
    conn = get_db_connection()
    try:
        print("🔄 Hämtar historiska bets...")
        events = fetch_training_events(conn)
        print(f"   {len(events)} training events hittade.")

        print("🧠 Beräknar EV-policy...")
        policies = compute_ev_policies(events)

        for m, p in policies.items():
            print(
                f"{m}: min_ev={p.min_ev:.2f}  ROI={p.roi_at_threshold:.2f}%  samples={p.min_samples}"
            )

        save_policies(conn, policies)
        print("✅ Policy sparad.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()