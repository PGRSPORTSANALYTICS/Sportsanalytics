"""
PGR Seed & Test Script
========================
Seeds sample data into PGR tables for dashboard testing.
Run: python3 pgr_seed_test.py
"""

import json
import random
from datetime import datetime, timezone, timedelta
from db_helper import db_helper

LEAGUES = [
    ('39', 'Premier League'), ('140', 'La Liga'), ('135', 'Serie A'),
    ('78', 'Bundesliga'), ('61', 'Ligue 1'), ('88', 'Eredivisie'),
]
MARKETS = ['moneyline', 'totals', 'btts', 'asian_handicap', 'corners', 'cards']
BOOKMAKERS = ['bet365', 'pinnacle', 'betfair', 'unibet', 'williamhill', 'betway']
TEAMS = [
    ('Arsenal', 'Chelsea'), ('Barcelona', 'Real Madrid'),
    ('Juventus', 'AC Milan'), ('Bayern Munich', 'Dortmund'),
    ('PSG', 'Lyon'), ('Ajax', 'PSV'),
    ('Liverpool', 'Man United'), ('Man City', 'Tottenham'),
    ('Atletico Madrid', 'Sevilla'), ('Inter Milan', 'Napoli'),
    ('RB Leipzig', 'Leverkusen'), ('Marseille', 'Monaco'),
]


def seed():
    print("Seeding PGR test data...")
    now = datetime.now(timezone.utc)
    bet_count = 0
    snap_count = 0

    for i in range(60):
        home, away = random.choice(TEAMS)
        league_id, league_name = random.choice(LEAGUES)
        mkt = random.choice(MARKETS)
        selection = random.choice(['home', 'away', 'over', 'under', 'yes', 'no'])
        line = random.choice([2.5, 1.5, 0.5, -0.5, 1.0, -1.0]) if mkt in ('totals', 'asian_handicap') else None
        event_id = f"seed_{i}_{league_id}"

        start_offset = random.randint(-72, 72)
        start_time = now + timedelta(hours=start_offset)
        is_settled = start_offset < -2

        base_odds = round(random.uniform(1.4, 4.5), 3)
        fair_odds = round(base_odds * random.uniform(0.88, 1.02), 3)
        model_prob = round(1 / fair_odds, 4)
        edge = round(((base_odds / fair_odds) - 1) * 100, 2)
        ev = round((model_prob * (base_odds - 1) - (1 - model_prob)) * 100, 2)
        confidence = round(random.uniform(0.45, 0.95), 3)
        conf_badge = 'HIGH' if confidence > 0.75 else 'MEDIUM' if confidence > 0.55 else 'LOW'

        is_production = random.random() > 0.4
        gating = 'PRODUCTION' if is_production else 'LEARNING_ONLY'

        if is_settled:
            status = 'settled'
            result = 'won' if random.random() < 0.6 else 'lost'
            profit_loss = round(base_odds - 1, 2) if result == 'won' else -1.0
            closing_odds = round(base_odds * random.uniform(0.92, 1.08), 3)
            clv = round(((closing_odds / base_odds) - 1) * 100, 2)
        else:
            status = random.choice(['candidate', 'published', 'placed'])
            result = None
            profit_loss = None
            closing_odds = None
            clv = None

        try:
            row = db_helper.execute("""
                INSERT INTO pgr_bet_lifecycle
                (event_id, home_team, away_team, league_id, league_name, sport,
                 market_type, selection, line, odds_decimal, bookmaker,
                 fair_odds, model_prob, edge_pct, ev_pct,
                 confidence, confidence_badge, status, gating_status,
                 stake_units, start_time_utc, result, profit_loss,
                 closing_odds, clv_pct, created_at,
                 published_at, placed_at, settled_at)
                VALUES (%s,%s,%s,%s,%s,'football',
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        1.0,%s,%s,%s,%s,%s,NOW(),
                        %s,%s,%s)
                RETURNING id
            """, (
                event_id, home, away, league_id, league_name,
                mkt, selection, line, base_odds, random.choice(BOOKMAKERS),
                fair_odds, model_prob, edge, ev,
                confidence, conf_badge, status, gating,
                start_time, result, profit_loss,
                closing_odds, clv,
                now if status in ('published', 'placed', 'settled') else None,
                now if status in ('placed', 'settled') else None,
                now if status == 'settled' else None,
            ), fetch='one')
            bet_id = row[0] if row else None
            bet_count += 1

            if bet_id and clv is not None:
                db_helper.execute("""
                    INSERT INTO pgr_clv_records
                    (bet_lifecycle_id, event_id, market_type, selection,
                     bet_odds, closing_odds, clv_pct, close_window_minutes, close_timestamp_utc)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,5,%s)
                """, (bet_id, event_id, mkt, selection, base_odds, closing_odds, clv, start_time))

            for bk in random.sample(BOOKMAKERS, random.randint(2, 5)):
                bk_odds = round(base_odds * random.uniform(0.92, 1.06), 3)
                snap_ts = start_time - timedelta(hours=random.randint(1, 48))
                db_helper.execute("""
                    INSERT INTO pgr_odds_snapshots
                    (event_id, sport, bookmaker, market_type, selection, line,
                     odds_decimal, timestamp_utc, home_team, away_team,
                     league_id, league_name, start_time_utc)
                    VALUES (%s,'football',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    event_id, bk, mkt, selection, line,
                    bk_odds, snap_ts, home, away, league_id, league_name, start_time,
                ))
                snap_count += 1

            if bet_id:
                db_helper.execute("""
                    INSERT INTO pgr_audit_log
                    (bet_lifecycle_id, action, old_status, new_status, details, timestamp_utc, source)
                    VALUES (%s, 'created', NULL, 'candidate', %s, NOW(), 'seed_script')
                """, (bet_id, json.dumps({'odds': base_odds, 'ev': ev})))

        except Exception as e:
            print(f"  Error seeding bet {i}: {e}")
            continue

    for league_id, league_name in LEAGUES:
        for mkt in MARKETS[:4]:
            db_helper.execute("""
                INSERT INTO pgr_timing_stats
                (sport, league_id, market_type, time_bucket, total_bets, wins, roi_pct, avg_clv, avg_ev)
                VALUES ('football', %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sport, league_id, market_type, time_bucket) DO NOTHING
            """, (
                league_id, mkt, random.choice(['0-1h', '1-3h', '3-6h', '6-12h']),
                random.randint(10, 80), random.randint(5, 50),
                round(random.uniform(-5, 15), 1),
                round(random.uniform(-1, 3), 3),
                round(random.uniform(1, 12), 1),
            ))

    print(f"Done: {bet_count} bets, {snap_count} snapshots seeded")


def test_endpoints():
    import requests
    base = 'http://localhost:8000/api/pgr'
    endpoints = [
        '/health', '/stats', '/bets?limit=5&show_learning=true',
        '/clv', '/discovery', '/timing', '/weekly-report',
    ]
    print("\nTesting API endpoints:")
    for ep in endpoints:
        try:
            r = requests.get(base + ep, timeout=5)
            status = 'OK' if r.status_code == 200 else f'FAIL({r.status_code})'
            print(f"  {ep:45s} {status}")
        except Exception as e:
            print(f"  {ep:45s} ERROR: {e}")


if __name__ == '__main__':
    seed()
    test_endpoints()
