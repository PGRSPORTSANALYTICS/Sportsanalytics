"""
snapshot_writer.py — Sharp odds snapshot logger.

Runs every 15 minutes for upcoming picks (next 6h). For each pick, fetches
current odds from sharp + fallback books and INSERTs one row per book per
cycle into pgr_odds_snapshots. This populates the data layer required for
- visible "Movement after detection" graph in modal
- Signal Strength Score (instant_move, books_aligned, time_to_move)
- public CLV proof of work (true intra-day price evolution)

Non-destructive: only writes to pgr_odds_snapshots. Does NOT touch
football_opportunities or any production engine path.
"""

import logging
import time
from typing import List, Dict, Optional

from db_helper import db_helper
from clv_service import (
    CLVService, _sport_key, _market_type, SHARP_BOOKS, PROOF_BOOKS, FALLBACK_BOOKS,
)

logger = logging.getLogger(__name__)

WINDOW_HOURS = 6              # Capture for picks kicking off in next 6h
MIN_INTERVAL_MIN = 12         # Skip if last snapshot for (pick, book) < 12 min ago


class SnapshotWriter:
    def __init__(self, clv_service: Optional[CLVService] = None):
        self.clv = clv_service or CLVService()

    def get_active_picks(self) -> List[Dict]:
        now = int(time.time())
        rows = db_helper.execute("""
            SELECT id, match_id, fixture_id, home_team, away_team, league,
                   market, selection, kickoff_epoch, open_odds, timestamp
            FROM football_opportunities
            WHERE kickoff_epoch IS NOT NULL
              AND kickoff_epoch BETWEEN %s AND %s
              AND open_odds IS NOT NULL
              AND (outcome IS NULL OR outcome = '' OR outcome = 'pending')
            ORDER BY kickoff_epoch ASC
            LIMIT 200
        """, (now - 600, now + WINDOW_HOURS * 3600), fetch='all') or []

        picks = []
        for r in rows:
            picks.append({
                'id': r[0], 'match_id': r[1], 'fixture_id': r[2],
                'home_team': r[3], 'away_team': r[4], 'league': r[5],
                'market': r[6], 'selection': r[7],
                'kickoff_epoch': int(r[8]), 'open_odds': float(r[9]),
                'detected_ts': int(r[10]) if r[10] else None,
            })
        return picks

    def _recently_logged(self, event_id: str, mtype: str, sel: str, book: str) -> bool:
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=MIN_INTERVAL_MIN)
        row = db_helper.execute("""
            SELECT 1 FROM pgr_odds_snapshots
            WHERE event_id=%s AND market_type=%s AND selection=%s
              AND bookmaker=%s AND timestamp_utc > %s
            LIMIT 1
        """, (event_id, mtype, sel, book, cutoff), fetch='one')
        return bool(row)

    def _write_snapshot(self, pick: Dict, mtype: str, sel: str,
                        book: str, odds: float, line: Optional[float] = None):
        from datetime import datetime
        try:
            event_id = f"{pick['fixture_id'] or pick['match_id'] or pick['id']}"
            db_helper.execute("""
                INSERT INTO pgr_odds_snapshots
                  (event_id, sport, league_id, league_name, start_time_utc,
                   home_team, away_team, market_type, selection, line,
                   bookmaker, odds_decimal, timestamp_utc, fixture_id)
                VALUES (%s, 'football', %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, NOW(), %s)
            """, (
                event_id, str(pick.get('league') or ''), pick.get('league') or '',
                datetime.utcfromtimestamp(pick['kickoff_epoch']),
                pick['home_team'], pick['away_team'], mtype, sel, line,
                book, odds, pick.get('fixture_id'),
            ))
        except Exception as e:
            logger.debug("snapshot insert failed pick=%s book=%s: %s",
                         pick['id'], book, e)

    def capture_for_pick(self, pick: Dict) -> int:
        """Fetch current sharp+fallback odds for one pick and write snapshots.
        Returns # of snapshot rows written."""
        if not self.clv.odds_api:
            return 0

        sport = _sport_key(pick.get('league', ''))
        mtype = _market_type(pick['market'], pick['selection'])
        if not sport or not mtype:
            return 0

        try:
            events = self.clv.odds_api.get_live_odds(
                sport, regions=['eu', 'uk'], markets=[mtype]
            )
        except Exception as e:
            logger.debug("snapshot odds fetch failed pick=%s: %s", pick['id'], e)
            return 0
        if not events:
            return 0

        # Find this pick's event in returned data
        event = None
        for ev in events:
            if self.clv._teams_match(ev, pick['home_team'], pick['away_team']):
                event = ev; break
        if not event:
            return 0

        written = 0
        event_id = str(pick.get('fixture_id') or pick.get('match_id') or pick['id'])

        for bk in event.get('bookmakers', []) or []:
            book = (bk.get('key') or '').lower()
            if book not in SHARP_BOOKS:
                continue
            for mk in bk.get('markets', []) or []:
                if mk.get('key') != mtype:
                    continue
                for outcome in mk.get('outcomes', []) or []:
                    name = outcome.get('name', '')
                    price = outcome.get('price')
                    if not price or float(price) < 1.01:
                        continue
                    line = outcome.get('point')
                    sel_key = f"{name}{(' '+str(line)) if line is not None else ''}"
                    if self._recently_logged(event_id, mtype, sel_key, book):
                        continue
                    self._write_snapshot(pick, mtype, sel_key, book,
                                         float(price), line)
                    written += 1
        return written

    def run_cycle(self) -> Dict:
        picks = self.get_active_picks()
        if not picks:
            logger.info("📸 Snapshot writer: no active picks in next %dh", WINDOW_HOURS)
            return {'picks': 0, 'snapshots': 0}

        total_writes = 0
        seen_events = set()
        for p in picks:
            ev_key = f"{p.get('fixture_id') or p.get('match_id')}::{p['market']}"
            if ev_key in seen_events:
                continue
            seen_events.add(ev_key)
            try:
                total_writes += self.capture_for_pick(p)
            except Exception as e:
                logger.debug("snapshot pick=%s err: %s", p['id'], e)

        logger.info("📸 Snapshot writer: %d picks scanned, %d snapshots written",
                    len(picks), total_writes)
        return {'picks': len(picks), 'snapshots': total_writes}


# ── Signal Strength Score ────────────────────────────────────────────────────

def _classify_selection(pick_market: str, pick_sel: str, home: str, away: str):
    """
    Map a pick's selection → snapshot resolver.
      ('h2h_single', team_or_'Draw')      → match snapshot.selection == team
      ('dc',         (leg1, leg2))        → derive DC odds = 1/(1/leg1 + 1/leg2)
      ('totals',     ('Over'|'Under', line_str))
      (None, None)                        → unsupported (BTTS etc)
    """
    import re
    sel = (pick_sel or '').strip().lower()
    market = (pick_market or '').strip().lower()
    if 'btts' in sel or 'both teams' in sel or 'btts' in market:
        return None, None
    m = re.search(r'(over|under)\s*(\d+\.?\d*)', sel)
    if m:
        return 'totals', (m.group(1).capitalize(), m.group(2))
    if sel in ('home or draw', '1x'):  return 'dc', (home, 'Draw')
    if sel in ('draw or away', 'x2'):  return 'dc', ('Draw', away)
    if sel in ('home or away', '12'):  return 'dc', (home, away)
    if 'home' in sel: return 'h2h_single', home
    if 'away' in sel: return 'h2h_single', away
    if 'draw' in sel: return 'h2h_single', 'Draw'
    return None, None


def compute_signal_strength(pick_id: int) -> Optional[Dict]:
    """
    Compute a 0–100 signal strength score for a pick from snapshots + open_odds.
    Components:
      - instant_move: line moved >=1.5% within first 30 min after detection
      - move_size:    abs % drift open → latest sharp avg
      - books_aligned: # of sharp books moving in same direction / total
      - time_to_move:  mins until first significant (>=1%) sharp shift
    """
    pick = db_helper.execute("""
        SELECT id, home_team, away_team, market, selection, league,
               open_odds, timestamp, kickoff_epoch, fixture_id, match_id
        FROM football_opportunities WHERE id=%s
    """, (pick_id,), fetch='one')
    if not pick:
        return None

    open_odds   = float(pick[6]) if pick[6] else None
    detected_ts = int(pick[7]) if pick[7] else None
    if not open_odds or not detected_ts:
        return None

    home, away  = pick[1], pick[2]
    event_id    = str(pick[9] or pick[10] or pick[0])
    kind, params = _classify_selection(pick[3], pick[4], home, away)
    if kind is None:
        return {'score': None, 'has_data': False,
                'reason': f'snapshot mapping not supported for selection: {pick[4]}'}
    mtype = _market_type(pick[3], pick[4])

    raw = db_helper.execute("""
        SELECT bookmaker, selection, odds_decimal,
               EXTRACT(EPOCH FROM timestamp_utc)::bigint AS ts
        FROM pgr_odds_snapshots
        WHERE event_id=%s AND market_type=%s
          AND bookmaker = ANY(%s)
          AND EXTRACT(EPOCH FROM timestamp_utc) >= %s
        ORDER BY timestamp_utc ASC
    """, (event_id, mtype, list(SHARP_BOOKS), detected_ts), fetch='all') or []
    if not raw:
        return {'score': None, 'has_data': False,
                'reason': 'no snapshots captured yet for this pick'}

    # Group by (book, ts) so we can derive multi-leg pick-side odds at each tick
    from collections import defaultdict
    grouped = defaultdict(dict)
    for bk, sel_s, od, ts in raw:
        grouped[(bk.lower(), int(ts))][sel_s] = float(od)

    series = defaultdict(list)   # book -> [(ts, derived_odds)]
    for (bk, ts), legs in grouped.items():
        derived = None
        if kind == 'h2h_single':
            target = (params or '').lower()
            for k, v in legs.items():
                if k.lower() == target:
                    derived = v; break
        elif kind == 'dc':
            l1, l2 = params
            o1 = next((v for k, v in legs.items() if k.lower() == l1.lower()), None)
            o2 = next((v for k, v in legs.items() if k.lower() == l2.lower()), None)
            if o1 and o2 and o1 > 1 and o2 > 1:
                derived = round(1.0 / (1.0 / o1 + 1.0 / o2), 4)
        elif kind == 'totals':
            side, line = params
            for k, v in legs.items():
                kl = k.lower()
                if side.lower() in kl and line in k:
                    derived = v; break
        if derived is not None:
            series[bk].append((ts, derived))

    if not series:
        return {'score': None, 'has_data': False,
                'reason': f'snapshot legs incomplete for {kind} pick'}

    # Build snaps + by_book from derived series
    snaps = []
    by_book = {}
    for bk, pts in series.items():
        pts.sort()
        for ts, v in pts:
            snaps.append((bk, v, ts))
        by_book[bk] = {'first':  {'odds': pts[0][1],  'ts': pts[0][0]},
                       'latest': {'odds': pts[-1][1], 'ts': pts[-1][0]}}
    snaps.sort(key=lambda x: x[2])

    # Latest sharp avg (PROOF books only if any, else fallback)
    proof_latest = [r['latest']['odds'] for k, r in by_book.items() if k in PROOF_BOOKS]
    latest_avg = (sum(proof_latest) / len(proof_latest)) if proof_latest else \
                 (sum(r['latest']['odds'] for r in by_book.values()) / len(by_book))

    move_pct = (latest_avg / open_odds - 1.0) * 100   # negative = price shortened
    abs_move = abs(move_pct)

    # Books aligned: count books moving in same direction as overall move
    direction = -1 if move_pct < 0 else (1 if move_pct > 0 else 0)
    aligned, total = 0, 0
    for r in by_book.values():
        if r['first'] and r['latest']:
            d = (r['latest']['odds'] - r['first']['odds'])
            total += 1
            if direction != 0 and ((d < 0 and direction < 0) or (d > 0 and direction > 0)):
                aligned += 1

    # Time-to-move: minutes from detection to first significant (>1%) sharp shift
    time_to_move_min = None
    for bk, od, ts in snaps:
        diff = (float(od) - open_odds) / open_odds
        if abs(diff) >= 0.01:
            time_to_move_min = max(0, int((int(ts) - detected_ts) / 60))
            break

    instant_move = (time_to_move_min is not None and time_to_move_min <= 30
                    and abs_move >= 1.5)

    # Score (0–100)
    s_size = min(50, abs_move * 5)                    # 10% move = 50 pts
    s_align = (aligned / total * 25) if total > 0 else 0
    s_instant = 15 if instant_move else 0
    s_speed = 0
    if time_to_move_min is not None:
        if time_to_move_min <= 5:    s_speed = 10
        elif time_to_move_min <= 15: s_speed = 7
        elif time_to_move_min <= 30: s_speed = 4
    score = int(round(s_size + s_align + s_instant + s_speed))

    return {
        'score': score,
        'has_data': True,
        'instant_move': instant_move,
        'move_size_pct': round(move_pct, 2),
        'books_aligned': aligned,
        'books_total': total,
        'time_to_move_min': time_to_move_min,
        'snapshot_count': len(snaps),
        'sharp_books_seen': sorted(by_book.keys()),
    }


# ── Public scheduler hook ────────────────────────────────────────────────────

_writer = None
def run_snapshot_cycle():
    global _writer
    if _writer is None:
        _writer = SnapshotWriter()
    try:
        return _writer.run_cycle()
    except Exception as e:
        logger.error("❌ snapshot cycle error: %s", e)
        return {'picks': 0, 'snapshots': 0, 'error': str(e)}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    res = run_snapshot_cycle()
    print(f"Result: {res}")
