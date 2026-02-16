"""
PGR Module 1 — Odds Ingestion + Normalization (Multi-Book)
===========================================================
Ingests odds from The Odds API, normalizes to unified schema,
stores snapshots for CLV tracking, computes market state.

Decimal odds only. Football first, scalable.
"""

import os
import logging
import statistics
import time
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from db_helper import db_helper
from pgr_models import OddsSnapshot, MarketState

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv('THE_ODDS_API_KEY', '')
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = [
    'soccer_epl',
    'soccer_spain_la_liga',
    'soccer_germany_bundesliga',
    'soccer_italy_serie_a',
    'soccer_france_ligue_one',
    'soccer_netherlands_eredivisie',
    'soccer_portugal_primeira_liga',
    'soccer_turkey_super_league',
    'soccer_belgium_first_div',
    'soccer_denmark_superliga',
    'soccer_sweden_allsvenskan',
    'soccer_norway_eliteserien',
    'soccer_finland_veikkausliiga',
    'soccer_austria_bundesliga',
    'soccer_switzerland_superleague',
    'soccer_scotland_premiership',
    'soccer_england_league1',
    'soccer_england_league2',
    'soccer_england_efl_cup',
    'soccer_uefa_champs_league',
    'soccer_uefa_europa_league',
    'soccer_uefa_europa_conference_league',
    'soccer_brazil_campeonato',
    'soccer_argentina_primera_division',
    'soccer_mexico_ligamx',
    'soccer_usa_mls',
    'soccer_japan_j_league',
    'soccer_korea_kleague1',
    'soccer_australia_aleague',
    'soccer_china_superleague',
    'soccer_conmebol_copa_libertadores',
]

MARKET_MAP = {
    'h2h': 'moneyline',
    'spreads': 'asian_handicap',
    'totals': 'totals',
}

STALE_THRESHOLD_MINUTES = 30


def _api_get(endpoint: str, params: Dict = None) -> Optional[Any]:
    if not ODDS_API_KEY:
        logger.warning("THE_ODDS_API_KEY not set")
        return None
    params = params or {}
    params['apiKey'] = ODDS_API_KEY
    try:
        resp = requests.get(f"{ODDS_API_BASE}{endpoint}", params=params, timeout=30)
        remaining = resp.headers.get('x-requests-remaining', '?')
        logger.info(f"Odds API {endpoint}: {resp.status_code} | remaining: {remaining}")
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"Odds API error {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Odds API request failed: {e}")
        return None


def get_available_sports() -> List[Dict]:
    return _api_get("/sports") or []


def _normalize_selection(market_key: str, outcome: Dict, point: float = None) -> Tuple[str, Optional[float]]:
    name = outcome.get('name', '')
    price = outcome.get('price', 0)

    if market_key == 'h2h':
        sel = name.lower().replace(' ', '_')
        if sel not in ('draw',):
            pass
        return name, None

    if market_key == 'totals':
        sel_name = name
        line_val = outcome.get('point', point)
        return sel_name, line_val

    if market_key == 'spreads':
        line_val = outcome.get('point', point)
        return name, line_val

    return name, None


def ingest_sport_odds(sport_key: str, markets: str = 'h2h,totals,spreads',
                      regions: str = 'uk,eu,us,au') -> List[OddsSnapshot]:
    data = _api_get(f"/sports/{sport_key}/odds", {
        'regions': regions,
        'markets': markets,
        'oddsFormat': 'decimal',
    })
    if not data:
        return []

    snapshots = []
    now = datetime.now(timezone.utc)

    for event in data:
        event_id = event.get('id', '')
        sport = event.get('sport_key', sport_key)
        league_title = event.get('sport_title', '')
        home = event.get('home_team', '')
        away = event.get('away_team', '')
        commence = event.get('commence_time', '')

        try:
            start_time = datetime.fromisoformat(commence.replace('Z', '+00:00'))
        except Exception:
            start_time = now

        league_id = sport_key.replace('soccer_', '').replace('_', ' ').title()

        for bookmaker_data in event.get('bookmakers', []):
            bk_name = bookmaker_data.get('key', '')
            bk_title = bookmaker_data.get('title', bk_name)

            for market_data in bookmaker_data.get('markets', []):
                market_key = market_data.get('key', '')
                market_type = MARKET_MAP.get(market_key, market_key)

                for outcome in market_data.get('outcomes', []):
                    price = outcome.get('price', 0)
                    if price <= 1.0:
                        continue

                    sel_name, line_val = _normalize_selection(market_key, outcome)

                    snap = OddsSnapshot(
                        event_id=event_id,
                        sport='football',
                        league_id=league_id,
                        league_name=league_title,
                        start_time_utc=start_time,
                        home_team=home,
                        away_team=away,
                        market_type=market_type,
                        selection=sel_name,
                        line=line_val,
                        bookmaker=bk_title,
                        odds_decimal=round(price, 3),
                        timestamp_utc=now,
                    )
                    snapshots.append(snap)

    return snapshots


def store_snapshots(snapshots: List[OddsSnapshot]) -> int:
    if not snapshots:
        return 0

    stored = 0
    batch = []
    for s in snapshots:
        batch.append((
            s.event_id, s.sport, s.league_id, s.league_name,
            s.start_time_utc, s.home_team, s.away_team,
            s.market_type, s.selection, s.line,
            s.bookmaker, s.odds_decimal, s.timestamp_utc, s.fixture_id,
        ))

    chunk_size = 200
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i:i+chunk_size]
        placeholders = ','.join(['(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'] * len(chunk))
        flat = [v for row in chunk for v in row]
        try:
            db_helper.execute(f"""
                INSERT INTO pgr_odds_snapshots
                (event_id, sport, league_id, league_name, start_time_utc,
                 home_team, away_team, market_type, selection, line,
                 bookmaker, odds_decimal, timestamp_utc, fixture_id)
                VALUES {placeholders}
            """, tuple(flat))
            stored += len(chunk)
        except Exception as e:
            logger.error(f"Store snapshots error: {e}")

    logger.info(f"Stored {stored}/{len(snapshots)} odds snapshots")
    return stored


def compute_market_state(event_id: str) -> List[MarketState]:
    rows = db_helper.execute("""
        SELECT DISTINCT ON (market_type, selection, line, bookmaker)
            market_type, selection, line, bookmaker, odds_decimal, timestamp_utc
        FROM pgr_odds_snapshots
        WHERE event_id = %s
        ORDER BY market_type, selection, line, bookmaker, timestamp_utc DESC
    """, (event_id,), fetch='all') or []

    groups: Dict[str, List] = {}
    for r in rows:
        mkt = r[0]
        sel = r[1]
        line_val = r[2]
        key = f"{mkt}|{sel}|{line_val}"
        if key not in groups:
            groups[key] = []
        groups[key].append({
            'bookmaker': r[3],
            'odds': float(r[4]),
            'ts': r[5],
        })

    now = datetime.now(timezone.utc)
    states = []

    for key, entries in groups.items():
        parts = key.split('|')
        mkt, sel = parts[0], parts[1]
        line_val = float(parts[2]) if parts[2] != 'None' else None

        prices = {e['bookmaker']: e['odds'] for e in entries}
        odds_vals = list(prices.values())

        if not odds_vals:
            continue

        best_price = max(odds_vals)
        best_bk = [bk for bk, o in prices.items() if o == best_price][0]
        avg_price = statistics.mean(odds_vals)
        median_price = statistics.median(odds_vals)
        disp = statistics.stdev(odds_vals) if len(odds_vals) > 1 else 0

        stale_books = []
        for e in entries:
            if hasattr(e['ts'], 'timestamp'):
                age_min = (now - e['ts'].replace(tzinfo=timezone.utc)).total_seconds() / 60
                if age_min > STALE_THRESHOLD_MINUTES:
                    stale_books.append(e['bookmaker'])

        state = MarketState(
            event_id=event_id,
            market_type=mkt,
            selection=sel,
            line=line_val,
            best_price=round(best_price, 3),
            best_bookmaker=best_bk,
            market_avg=round(avg_price, 3),
            market_median=round(median_price, 3),
            dispersion=round(disp, 4),
            book_count=len(prices),
            prices=prices,
            timestamp_utc=now,
            is_stale=len(stale_books) > 0,
            stale_books=stale_books,
        )
        states.append(state)

    return states


def persist_market_states(states: List[MarketState]) -> int:
    saved = 0
    for s in states:
        try:
            import json
            db_helper.execute("""
                INSERT INTO pgr_market_state
                (event_id, market_type, selection, line, best_price, best_bookmaker,
                 market_avg, market_median, dispersion, book_count, prices,
                 is_stale, stale_books, timestamp_utc)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_id, market_type, selection, line)
                DO UPDATE SET
                    best_price = EXCLUDED.best_price,
                    best_bookmaker = EXCLUDED.best_bookmaker,
                    market_avg = EXCLUDED.market_avg,
                    market_median = EXCLUDED.market_median,
                    dispersion = EXCLUDED.dispersion,
                    book_count = EXCLUDED.book_count,
                    prices = EXCLUDED.prices,
                    is_stale = EXCLUDED.is_stale,
                    stale_books = EXCLUDED.stale_books,
                    timestamp_utc = EXCLUDED.timestamp_utc
            """, (
                s.event_id, s.market_type, s.selection, s.line,
                s.best_price, s.best_bookmaker,
                s.market_avg, s.market_median, s.dispersion, s.book_count,
                json.dumps(s.prices), s.is_stale, s.stale_books, s.timestamp_utc,
            ))
            saved += 1
        except Exception as e:
            logger.error(f"Persist market state error: {e}")
    return saved


def run_ingestion_cycle(sport_keys: List[str] = None, markets: str = 'h2h,totals,spreads') -> Dict:
    if sport_keys is None:
        sport_keys = SPORT_KEYS

    total_snapshots = 0
    total_states = 0
    events_seen = set()

    for sport_key in sport_keys:
        try:
            snapshots = ingest_sport_odds(sport_key, markets=markets)
            if snapshots:
                stored = store_snapshots(snapshots)
                total_snapshots += stored

                for s in snapshots:
                    events_seen.add(s.event_id)

            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Ingestion error for {sport_key}: {e}")

    for event_id in events_seen:
        try:
            states = compute_market_state(event_id)
            saved = persist_market_states(states)
            total_states += saved
        except Exception as e:
            logger.error(f"Market state error for {event_id}: {e}")

    result = {
        'sports_processed': len(sport_keys),
        'snapshots_stored': total_snapshots,
        'events_processed': len(events_seen),
        'market_states_computed': total_states,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"Ingestion cycle: {result}")
    return result


def get_latest_market_state(event_id: str) -> List[Dict]:
    rows = db_helper.execute("""
        SELECT event_id, market_type, selection, line,
               best_price, best_bookmaker, market_avg, market_median,
               dispersion, book_count, prices, is_stale, stale_books, timestamp_utc
        FROM pgr_market_state
        WHERE event_id = %s
        ORDER BY market_type, selection
    """, (event_id,), fetch='all') or []

    results = []
    for r in rows:
        import json
        prices = r[10] if isinstance(r[10], dict) else json.loads(r[10]) if r[10] else {}
        stale = r[12] if isinstance(r[12], list) else []
        results.append({
            'event_id': r[0], 'market_type': r[1], 'selection': r[2], 'line': r[3],
            'best_price': float(r[4]), 'best_bookmaker': r[5],
            'market_avg': float(r[6]), 'market_median': float(r[7]),
            'dispersion': float(r[8]), 'book_count': r[9],
            'prices': prices, 'is_stale': r[11], 'stale_books': stale,
            'timestamp_utc': r[13].isoformat() if r[13] else None,
        })
    return results


def get_odds_history(event_id: str, market_type: str = None, selection: str = None) -> List[Dict]:
    query = """
        SELECT bookmaker, odds_decimal, timestamp_utc, market_type, selection, line
        FROM pgr_odds_snapshots
        WHERE event_id = %s
    """
    params = [event_id]
    if market_type:
        query += " AND market_type = %s"
        params.append(market_type)
    if selection:
        query += " AND selection = %s"
        params.append(selection)
    query += " ORDER BY timestamp_utc ASC"

    rows = db_helper.execute(query, tuple(params), fetch='all') or []
    return [
        {
            'bookmaker': r[0], 'odds_decimal': float(r[1]),
            'timestamp_utc': r[2].isoformat() if r[2] else None,
            'market_type': r[3], 'selection': r[4], 'line': r[5],
        }
        for r in rows
    ]


def get_upcoming_events(hours_ahead: int = 48) -> List[Dict]:
    rows = db_helper.execute("""
        SELECT DISTINCT ON (event_id)
            event_id, home_team, away_team, league_id, league_name,
            start_time_utc, sport
        FROM pgr_odds_snapshots
        WHERE start_time_utc > NOW()
        AND start_time_utc < NOW() + INTERVAL '%s hours'
        ORDER BY event_id, timestamp_utc DESC
    """, (hours_ahead,), fetch='all') or []

    return [
        {
            'event_id': r[0], 'home_team': r[1], 'away_team': r[2],
            'league_id': r[3], 'league_name': r[4],
            'start_time_utc': r[5].isoformat() if r[5] else None,
            'sport': r[6],
        }
        for r in rows
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_ingestion_cycle(sport_keys=SPORT_KEYS[:3], markets='h2h,totals')
    print(f"Ingestion result: {result}")
