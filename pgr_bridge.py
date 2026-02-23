"""
PGR Bridge — Connects Existing Engine to PGR Analytics
========================================================
Syncs football_opportunities → pgr_bet_lifecycle
Runs odds ingestion for snapshot collection
Computes CLV on settled bets
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from db_helper import db_helper

logger = logging.getLogger(__name__)

MARKET_MAP = {
    'Value Single': 'moneyline',
    'HOME_WIN': 'moneyline',
    'AWAY_WIN': 'moneyline',
    'DRAW': 'moneyline',
    'FT_OVER_2_5': 'totals',
    'FT_UNDER_2_5': 'totals',
    'FT_OVER_3_5': 'totals',
    'FT_UNDER_3_5': 'totals',
    'BTTS_YES': 'btts',
    'BTTS_NO': 'btts',
    'Corners': 'corners',
    'Cards': 'cards',
    'exact_score': 'exact_score',
    'DOUBLE_CHANCE': 'double_chance',
}

LEAGUE_ID_MAP = {
    'Premier League': '39',
    'La Liga': '140',
    'Serie A': '135',
    'Bundesliga': '78',
    'Ligue 1': '61',
    'Eredivisie': '88',
    'Primeira Liga': '94',
    'Champions League': '2',
    'Europa League': '3',
    'English Championship': '40',
    'English League One': '41',
    'English League Two': '42',
    'Scottish Premiership': '179',
    'Belgian First Division': '144',
    'Turkish Super Lig': '203',
    'Swiss Super League': '207',
    'Austrian Bundesliga': '218',
    'Danish Superliga': '119',
    'Norwegian Eliteserien': '103',
    'Swedish Allsvenskan': '113',
    'Greek Super League': '197',
    'Czech First League': '345',
    'Polish Ekstraklasa': '106',
    'MLS': '253',
    'A-League': '188',
    'J1 League': '98',
    'K League 1': '292',
    'Brazilian Serie A': '71',
    'Argentine Primera': '128',
    'Liga MX': '262',
    'Saudi Pro League': '307',
    'Conference League': '848',
    'Copa Libertadores': '13',
}


def _normalize_market(raw_market: str, selection: str = '') -> str:
    if raw_market in MARKET_MAP:
        return MARKET_MAP[raw_market]
    raw_lower = raw_market.lower()
    if 'corner' in raw_lower:
        return 'corners'
    if 'card' in raw_lower:
        return 'cards'
    if 'over' in raw_lower or 'under' in raw_lower:
        return 'totals'
    if 'btts' in raw_lower:
        return 'btts'
    if 'double_chance' in raw_lower or 'double chance' in raw_lower:
        return 'double_chance'
    if 'draw_no_bet' in raw_lower:
        return 'draw_no_bet'
    return 'moneyline'


def _get_league_id(league_name: str) -> str:
    if league_name in LEAGUE_ID_MAP:
        return LEAGUE_ID_MAP[league_name]
    for name, lid in LEAGUE_ID_MAP.items():
        if name.lower() in league_name.lower() or league_name.lower() in name.lower():
            return lid
    return league_name[:20]


def _parse_analysis(analysis_str: str) -> Dict:
    if not analysis_str:
        return {}
    try:
        if isinstance(analysis_str, dict):
            return analysis_str
        return json.loads(analysis_str)
    except:
        return {}


def sync_new_bets(hours_back: int = 6) -> Dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    cutoff_epoch = int(cutoff.timestamp())
    cutoff_str = cutoff.isoformat()

    rows = db_helper.execute("""
        SELECT id, home_team, away_team, league, market, selection, odds,
               edge_percentage, confidence, analysis, match_date,
               status, model_prob, calibrated_prob, trust_level,
               fair_odds, best_odds_value, best_odds_bookmaker,
               kickoff_utc, fixture_id, ev_sim, sim_probability,
               mode, bet_placed
        FROM football_opportunities
        WHERE created_at_utc >= %s
        OR (created_at_utc IS NULL AND timestamp >= %s)
        ORDER BY id DESC
    """, (cutoff_str, cutoff_epoch), fetch='all') or []

    synced = 0
    skipped = 0
    errors = 0

    for r in rows:
        fo_id = r[0]
        home = r[1]
        away = r[2]
        league = r[3] or ''
        raw_market = r[4] or ''
        selection = r[5] or ''
        odds = float(r[6]) if r[6] else 0
        edge = float(r[7]) if r[7] else 0
        confidence_raw = float(r[8]) if r[8] else 0
        analysis = _parse_analysis(r[9])
        match_date = r[10]
        status = r[11]
        model_prob = float(r[12]) if r[12] else 0
        calibrated_prob = float(r[13]) if r[13] else model_prob
        trust_level = r[14] or ''
        fair_odds_val = float(r[15]) if r[15] else 0
        best_odds = float(r[16]) if r[16] else odds
        best_bookmaker = r[17] or 'unknown'
        kickoff_utc = r[18]
        fixture_id = r[19]
        ev_sim = float(r[20]) if r[20] else 0
        sim_prob = float(r[21]) if r[21] else model_prob
        mode = r[22] or ''
        bet_placed = r[23]

        market_type = _normalize_market(raw_market, selection)
        league_id = _get_league_id(league)

        event_id = f"fo_{fo_id}"
        if fixture_id:
            event_id = str(fixture_id)

        existing = db_helper.execute("""
            SELECT id FROM pgr_bet_lifecycle
            WHERE event_id = %s AND market_type = %s AND selection = %s
            AND bookmaker = %s
        """, (event_id, market_type, selection, best_bookmaker), fetch='one')

        if existing:
            skipped += 1
            continue

        if not model_prob and not sim_prob:
            model_prob = analysis.get('p_model', 0) or analysis.get('sim_probability', 0)
        if not model_prob:
            model_prob = 0.5

        if not fair_odds_val and model_prob > 0:
            fair_odds_val = round(1 / model_prob, 3)

        edge_pct = edge
        if not edge_pct and odds > 1 and fair_odds_val > 1:
            edge_pct = round(((odds / fair_odds_val) - 1) * 100, 2)

        ev_pct = ev_sim * 100 if ev_sim and ev_sim < 1 else ev_sim if ev_sim else edge_pct
        if not ev_pct:
            ev_pct = edge_pct

        confidence = confidence_raw / 100 if confidence_raw > 1 else confidence_raw
        conf_badge = 'HIGH' if confidence > 0.75 else 'MEDIUM' if confidence > 0.55 else 'LOW'

        is_production = mode not in ('LEARNING', 'TEST') and bet_placed
        gating_status = 'PRODUCTION' if is_production else 'LEARNING_ONLY'

        pgr_status = 'candidate'
        if bet_placed and status == 'pending':
            pgr_status = 'placed'
        elif status in ('won', 'lost', 'settled', 'void'):
            pgr_status = 'settled'

        start_time = kickoff_utc
        if not start_time and match_date:
            try:
                start_time = datetime.strptime(str(match_date)[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except:
                start_time = None

        line = None
        if 'over' in selection.lower() or 'under' in selection.lower():
            for val in ['3.5', '2.5', '1.5', '0.5']:
                if val in selection or val in raw_market:
                    line = float(val)
                    break

        tags = []
        if trust_level:
            tags.append(trust_level)
        if mode:
            tags.append(mode)

        try:
            row = db_helper.execute("""
                INSERT INTO pgr_bet_lifecycle
                (event_id, home_team, away_team, league_id, league_name, sport,
                 market_type, selection, line, odds_decimal, bookmaker,
                 fair_odds, model_prob, edge_pct, ev_pct,
                 confidence, confidence_badge, status, gating_status,
                 stake_units, start_time_utc, tags, notes,
                 created_at)
                VALUES (%s,%s,%s,%s,%s,'football',
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        1.0,%s,%s,%s,NOW())
                RETURNING id
            """, (
                event_id, home, away, league_id, league,
                market_type, selection, line, best_odds, best_bookmaker,
                fair_odds_val, model_prob, edge_pct, ev_pct,
                confidence, conf_badge, pgr_status, gating_status,
                start_time, tags, f"Synced from fo#{fo_id}",
            ), fetch='one')

            if row:
                db_helper.execute("""
                    INSERT INTO pgr_audit_log
                    (bet_lifecycle_id, action, old_status, new_status, details, timestamp_utc, source)
                    VALUES (%s, 'synced_from_engine', NULL, %s, %s, NOW(), 'pgr_bridge')
                """, (row[0], pgr_status, json.dumps({'fo_id': fo_id, 'odds': best_odds, 'ev': ev_pct})))
                synced += 1

        except Exception as e:
            logger.error(f"Sync bet fo#{fo_id} error: {e}")
            errors += 1

    logger.info(f"PGR Bridge sync: {synced} synced, {skipped} skipped, {errors} errors")
    return {'synced': synced, 'skipped': skipped, 'errors': errors}


def sync_settled_results(hours_back: int = 24) -> Dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    cutoff_epoch = int(cutoff.timestamp())
    cutoff_str = cutoff.isoformat()

    rows = db_helper.execute("""
        SELECT id, home_team, away_team, league, market, selection,
               odds, result, profit_loss, close_odds, clv_pct,
               fixture_id, status
        FROM football_opportunities
        WHERE status IN ('won', 'lost')
        AND (settled_timestamp >= %s
             OR updated_at >= %s)
    """, (cutoff_epoch, cutoff_str), fetch='all') or []

    settled = 0
    for r in rows:
        fo_id = r[0]
        result = r[7] or ''
        profit_loss = float(r[8]) if r[8] else 0
        close_odds = float(r[9]) if r[9] else None
        clv = float(r[10]) if r[10] else None
        fixture_id = r[11]
        fo_status = r[12]

        event_id = str(fixture_id) if fixture_id else f"fo_{fo_id}"
        selection = r[5] or ''
        raw_market = r[4] or ''
        market_type = _normalize_market(raw_market, selection)

        pgr_bet = db_helper.execute("""
            SELECT id, status FROM pgr_bet_lifecycle
            WHERE event_id = %s AND market_type = %s AND selection = %s
            AND status != 'settled'
            LIMIT 1
        """, (event_id, market_type, selection), fetch='one')

        if not pgr_bet:
            continue

        bet_id = pgr_bet[0]
        old_status = pgr_bet[1]

        try:
            db_helper.execute("""
                UPDATE pgr_bet_lifecycle
                SET status = 'settled', result = %s, profit_loss = %s,
                    closing_odds = %s, clv_pct = %s, settled_at = NOW()
                WHERE id = %s
            """, (result, profit_loss, close_odds, clv, bet_id))

            db_helper.execute("""
                INSERT INTO pgr_audit_log
                (bet_lifecycle_id, action, old_status, new_status, details, timestamp_utc, source)
                VALUES (%s, 'settled_from_engine', %s, 'settled', %s, NOW(), 'pgr_bridge')
            """, (bet_id, old_status, json.dumps({
                'result': result, 'profit_loss': profit_loss,
                'closing_odds': close_odds, 'clv': clv, 'fo_id': fo_id,
            })))

            if close_odds and close_odds > 1:
                odds_val = float(db_helper.execute(
                    "SELECT odds_decimal FROM pgr_bet_lifecycle WHERE id = %s",
                    (bet_id,), fetch='one'
                )[0])
                if odds_val > 1:
                    computed_clv = round(((close_odds / odds_val) - 1) * 100, 3)
                    db_helper.execute("""
                        INSERT INTO pgr_clv_records
                        (bet_lifecycle_id, event_id, market_type, selection,
                         bet_odds, closing_odds, clv_pct, close_window_minutes, close_timestamp_utc)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,5,NOW())
                    """, (bet_id, event_id, market_type, selection, odds_val, close_odds, computed_clv))

            settled += 1
        except Exception as e:
            logger.error(f"Settle PGR bet {bet_id} error: {e}")

    logger.info(f"PGR Bridge settled: {settled} bets")
    return {'settled': settled}


def run_odds_ingestion_safe() -> Dict:
    try:
        from pgr_odds_ingestion import run_ingestion_cycle, SPORT_KEYS
        result = run_ingestion_cycle(sport_keys=SPORT_KEYS[:3])
        logger.info(f"PGR odds ingestion: {result.get('total_snapshots', 0)} snapshots")
        return result
    except Exception as e:
        logger.error(f"PGR odds ingestion error: {e}")
        return {'error': str(e)}


def run_full_pgr_cycle() -> Dict:
    logger.info("PGR Bridge: Starting full PGR cycle...")
    results = {}

    try:
        results['ingestion'] = run_odds_ingestion_safe()
    except Exception as e:
        results['ingestion'] = {'error': str(e)}

    try:
        results['sync_bets'] = sync_new_bets(hours_back=4)
    except Exception as e:
        results['sync_bets'] = {'error': str(e)}

    try:
        results['sync_results'] = sync_settled_results(hours_back=12)
    except Exception as e:
        results['sync_results'] = {'error': str(e)}

    logger.info(f"PGR Bridge cycle complete: {results}")
    return results
