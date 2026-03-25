"""
📊 CLV SERVICE v2 - Closing Line Value Tracking
================================================
Correct CLV formula: CLV% = (open_odds / close_odds - 1) * 100

Positive CLV = close_odds < open_odds = you got better price than closing line.
Negative CLV = close_odds > open_odds = market moved against your bet.

Worker window: 0–8 hours before kickoff (candidates).
Capture target: as close to 60 min before kickoff as possible.
Fallback: accept any capture within the 8h window.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_helper import db_helper
from real_odds_api import RealOddsAPI

logger = logging.getLogger(__name__)

# ── Window settings ──────────────────────────────────────────────
CANDIDATE_WINDOW_HOURS = 8          # Look for picks kicking off within next 8 h
CLOSE_AFTER_KICKOFF_MIN = 5         # Allow capture up to 5 min AFTER kickoff
TARGET_MINUTES_BEFORE = 60          # Ideal capture point (60 min before KO)
DRIFT_REJECT_PCT = 0.50             # Reject if odds moved >50% (data error)

SHARP_BOOKS = ['pinnacle', 'bet365', 'matchbook', 'betfair', 'betfair_ex_eu', 'nordicbet', 'unibet']

SHARP_PRIORITY = ['pinnacle', 'bet365', 'matchbook', 'betfair', 'betfair_ex_eu']

LEAGUE_TO_SPORT_KEY: Dict[str, str] = {
    'Premier League': 'soccer_epl',
    'La Liga': 'soccer_spain_la_liga',
    'Serie A': 'soccer_italy_serie_a',
    'Bundesliga': 'soccer_germany_bundesliga',
    'Ligue 1': 'soccer_france_ligue_one',
    'Champions League': 'soccer_uefa_champs_league',
    'Europa League': 'soccer_uefa_europa_league',
    'Conference League': 'soccer_uefa_europa_conference_league',
    'Eredivisie': 'soccer_netherlands_eredivisie',
    'Primeira Liga': 'soccer_portugal_primeira_liga',
    'Portuguese Primeira': 'soccer_portugal_primeira_liga',
    'Belgian First Division': 'soccer_belgium_first_div',
    'English Championship': 'soccer_efl_champ',
    'English League One': 'soccer_england_league1',
    'English League Two': 'soccer_england_league2',
    'Scottish Premiership': 'soccer_spl',
    'Turkish Super Lig': 'soccer_turkey_super_league',
    'Swiss Super League': 'soccer_switzerland_superleague',
    'Danish Superliga': 'soccer_denmark_superliga',
    'Superliga': 'soccer_denmark_superliga',
    'Norwegian Eliteserien': 'soccer_norway_eliteserien',
    'Swedish Allsvenskan': 'soccer_sweden_allsvenskan',
    'Greek Super League': 'soccer_greece_super_league',
    'Austrian Bundesliga': 'soccer_austria_bundesliga',
    'MLS': 'soccer_usa_mls',
    'Liga MX': 'soccer_mexico_ligamx',
    'Brazilian Serie A': 'soccer_brazil_serie_a',
    'Brasileirao': 'soccer_brazil_serie_a',
    'Argentine Primera': 'soccer_argentina_primera_division',
    'J1 League': 'soccer_japan_j_league',
    'K League 1': 'soccer_korea_kleague1',
    'A-League': 'soccer_australia_aleague',
    'Australian A-League': 'soccer_australia_aleague',
    'Eerste Divisie': 'soccer_netherlands_eredivisie',
    'Bundesliga 2': 'soccer_germany_bundesliga2',
    '2. Bundesliga': 'soccer_germany_bundesliga2',
    'Ligue 2': 'soccer_france_ligue_two',
    'La Liga 2': 'soccer_spain_segunda_division',
    'Segunda División': 'soccer_spain_segunda_division',
    'Serie B': 'soccer_italy_serie_b',
    'Championship': 'soccer_efl_champ',
    'League One': 'soccer_england_league1',
    'League Two': 'soccer_england_league2',
    'Czech Liga': 'soccer_czech_republic_first_league',
    'Polish Ekstraklasa': 'soccer_poland_ekstraklasa',
}

UNSUPPORTED_MARKETS = {
    'corners', 'cards', 'shots', 'fouls', 'offsides',
    'throw-ins', 'player props', 'player_props', 'props',
    'exact score', 'exact_score',
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> int:
    return int(time.time())


def _clv_pct(open_odds: float, close_odds: float) -> float:
    """
    CLV% = (open_odds / close_odds - 1) * 100

    Positive  → close_odds shortened after your bet  → you got better price ✅
    Negative  → close_odds lengthened                → market moved against you ❌
    """
    if close_odds <= 1.0:
        raise ValueError(f"Invalid close_odds: {close_odds}")
    return (open_odds / close_odds - 1.0) * 100.0


def _clv_status(clv: float) -> str:
    if clv > 0:
        return 'pos'
    if clv < 0:
        return 'neg'
    return 'na'


def _sport_key(league: str) -> Optional[str]:
    direct = LEAGUE_TO_SPORT_KEY.get(league)
    if direct:
        return direct
    lower = league.lower()
    for key, val in LEAGUE_TO_SPORT_KEY.items():
        if key.lower() in lower or lower in key.lower():
            return val
    return None


def _is_supported(market: str) -> bool:
    m = market.lower()
    return not any(u in m for u in UNSUPPORTED_MARKETS)


def _market_type(market: str, selection: str = '') -> Optional[str]:
    """Determine Odds API market type from market name AND selection text.

    The DB stores market as 'Value Single' for all value-single picks, so we
    must inspect the selection text to find the correct market endpoint.
    """
    if not _is_supported(market):
        return None
    # Combine both fields for matching — selection text is more specific
    combined = (market + ' ' + selection).lower()
    if 'over' in combined or 'under' in combined:
        return 'totals'
    if 'btts' in combined or 'both teams' in combined:
        return 'h2h'   # Pinnacle/sharp books include BTTS inside h2h response
    if ('ah' in combined or 'asian' in combined or 'handicap' in combined
            or re.search(r'[+-]\d+(\.\d+)?\s*(ah|\(ah\))', combined)):
        return 'spreads'
    if 'home win' in combined or 'away win' in combined or 'draw' in combined:
        return 'h2h'
    if 'double chance' in combined:
        return 'h2h'
    return 'h2h'


def _extract_line(text: str) -> Optional[float]:
    match = re.search(r'(\d+\.?\d*)', text)
    return float(match.group(1)) if match else None


# ─────────────────────────────────────────────────────────────────────────────
# Main service
# ─────────────────────────────────────────────────────────────────────────────

class CLVService:
    """Closing Line Value tracking service."""

    def __init__(self):
        try:
            self.odds_api = RealOddsAPI()
            logger.info("✅ CLVService initialised with RealOddsAPI")
        except Exception as exc:
            logger.warning("⚠️  CLVService: RealOddsAPI init failed: %s", exc)
            self.odds_api = None

    # ── Candidate selection ───────────────────────────────────────────────────

    def get_candidates(self) -> List[Dict]:
        """
        Return picks that:
        - are 'pending'
        - have open_odds and kickoff_epoch
        - lack close_odds
        - kickoff is within the next 8 hours (or up to 5 min past kickoff)
        """
        now = _now()
        window_start = now - (CLOSE_AFTER_KICKOFF_MIN * 60)
        window_end = now + (CANDIDATE_WINDOW_HOURS * 3600)

        try:
            rows = db_helper.execute("""
                SELECT id, match_id, home_team, away_team, league,
                       market, selection, open_odds, kickoff_epoch, kickoff_utc,
                       best_odds_bookmaker
                FROM football_opportunities
                WHERE status       = 'pending'
                  AND close_odds   IS NULL
                  AND open_odds    IS NOT NULL
                  AND kickoff_epoch IS NOT NULL
                  AND kickoff_epoch >= %s
                  AND kickoff_epoch <= %s
                ORDER BY kickoff_epoch ASC
            """, (window_start, window_end), fetch='all') or []

            candidates = []
            for row in rows:
                rec = {
                    'id':                  row[0],
                    'match_id':            row[1],
                    'home_team':           row[2],
                    'away_team':           row[3],
                    'league':              row[4],
                    'market':              row[5],
                    'selection':           row[6],
                    'open_odds':           float(row[7]),
                    'kickoff_epoch':       int(row[8]),
                    'kickoff_utc':         row[9],
                    'seconds_to_ko':       int(row[8]) - now,
                    'open_source_book':    row[10] or 'unknown',
                }
                candidates.append(rec)

            if candidates:
                logger.info("📊 CLV: %d candidate(s) in 0–8h window", len(candidates))
            return candidates

        except Exception as exc:
            logger.error("❌ CLV: get_candidates error: %s", exc)
            return []

    # ── Closing-odds fetch ────────────────────────────────────────────────────

    def fetch_closing_odds(self, bet: Dict) -> Optional[Dict]:
        """
        Fetch live odds for the bet's match/market.

        Returns dict with keys:
            odds (float), bookmaker (str), ts (int),
            api_market_type (str), matched_outcome (str)
        or None if unavailable.
        """
        if not self.odds_api:
            return None

        market = bet.get('market', '')
        selection = bet.get('selection', '')
        if not _is_supported(market):
            logger.debug("CLV: unsupported market '%s' for %s vs %s",
                         market, bet['home_team'], bet['away_team'])
            return None

        sport = _sport_key(bet.get('league', ''))
        if not sport:
            logger.debug("CLV: no sport_key for league '%s'", bet.get('league'))
            return None

        mtype = _market_type(market, selection)
        if not mtype:
            return None

        try:
            odds_data = self.odds_api.get_live_odds(
                sport, regions=['eu', 'uk'], markets=[mtype]
            )
        except Exception as exc:
            logger.error("CLV: odds API error: %s", exc)
            return None

        if not odds_data:
            return None

        open_odds = bet.get('open_odds', 0)

        for event in odds_data:
            if not self._teams_match(event, bet['home_team'], bet['away_team']):
                continue

            result = self._best_odds_for_selection(
                event, market, bet['selection'], bet['home_team'], bet['away_team']
            )
            if result is None:
                continue

            close_odds, bookmaker, matched_outcome = result

            if open_odds and open_odds > 1.0:
                drift = abs(close_odds - open_odds) / open_odds
                if drift > DRIFT_REJECT_PCT:
                    logger.warning(
                        "CLV: ⚠️ DRIFT REJECT  bet=%d  %s vs %s | "
                        "open=%.2f close=%.2f drift=%.0f%%",
                        bet['id'], bet['home_team'], bet['away_team'],
                        open_odds, close_odds, drift * 100
                    )
                    return None

            return {
                'odds':             close_odds,
                'bookmaker':        bookmaker,
                'ts':               _now(),
                'api_market_type':  mtype,
                'matched_outcome':  matched_outcome,
            }

        return None

    def _teams_match(self, event: Dict, home: str, away: str) -> bool:
        eh = event.get('home_team', '').lower()
        ea = event.get('away_team', '').lower()
        h, a = home.lower(), away.lower()
        if eh == h and ea == a:
            return True
        h_words = set(h.split())
        a_words = set(a.split())
        return (
            bool(h_words & set(eh.split()))
            and bool(a_words & set(ea.split()))
        )

    def _best_odds_for_selection(
        self, event: Dict, market: str, selection: str, home: str, away: str
    ) -> Optional[tuple]:
        """
        Sharp-average approach: collect closing odds from all available sharp books
        (Pinnacle, Bet365, Matchbook, Betfair) and return their average.
        Falls back to any available book if no sharp books match.

        Returns (avg_odds, source_label, matched_outcome_name)
        """
        bookmakers = event.get('bookmakers', [])
        sel_lower = selection.lower()
        mkt_lower = market.lower()

        sharp_hits: List[tuple] = []
        fallback_hit: Optional[tuple] = None

        for bk in bookmakers:
            bk_key = bk.get('key', '').lower()
            bk_title = bk.get('title', bk.get('key', 'unknown'))
            is_sharp = bk_key in SHARP_PRIORITY

            for mkt_obj in bk.get('markets', []):
                for outcome in mkt_obj.get('outcomes', []):
                    name = outcome.get('name', '').lower()
                    price = outcome.get('price')
                    if not price:
                        continue
                    if self._sel_matches(sel_lower, name, home, away, mkt_lower):
                        entry = (float(price), bk_title, outcome.get('name', name))
                        if is_sharp:
                            sharp_hits.append(entry)
                        elif fallback_hit is None:
                            fallback_hit = entry

        if sharp_hits:
            avg_odds = sum(h[0] for h in sharp_hits) / len(sharp_hits)
            book_names = sorted({h[1] for h in sharp_hits}, key=lambda b: SHARP_PRIORITY.index(b.lower()) if b.lower() in SHARP_PRIORITY else 99)
            source_label = f"sharp_avg({','.join(book_names)};n={len(sharp_hits)})"
            matched_out = sharp_hits[0][2]
            return (round(avg_odds, 4), source_label, matched_out)

        if fallback_hit:
            return fallback_hit

        return None

    def _sel_matches(self, sel: str, outcome: str, home: str, away: str, market: str) -> bool:
        h, a = home.lower(), away.lower()
        if sel == outcome:
            return True
        if ('home' in sel or h in sel) and (h in outcome or outcome == h):
            return True
        if ('away' in sel or a in sel) and (a in outcome or outcome == a):
            return True
        if 'draw' in sel and 'draw' in outcome:
            return True
        for side in ('over', 'under'):
            if side in sel and side in outcome:
                sl = _extract_line(sel)
                ol = _extract_line(outcome)
                if sl is not None and ol is not None and abs(sl - ol) < 0.01:
                    return True
        if ('btts' in sel or 'both teams' in sel):
            if 'yes' in sel and 'yes' in outcome:
                return True
            if 'no' in sel and 'no' in outcome:
                return True
        return False

    # ── DB update ────────────────────────────────────────────────────────────

    def save_clv(self, bet: Dict, close_result: Dict) -> bool:
        """Persist close_odds, close_ts, clv_pct, clv_status, clv_source_book.
        Also emits the full debug block for this CLV calculation.
        """
        bet_id    = bet['id']
        open_odds = bet['open_odds']
        close_odds  = close_result['odds']
        close_ts    = close_result['ts']
        close_book  = close_result['bookmaker']
        api_mtype   = close_result.get('api_market_type', '?')
        matched_out = close_result.get('matched_outcome', '?')
        open_book   = bet.get('open_source_book', 'unknown')
        ko_epoch    = bet.get('kickoff_epoch', 0)
        ko_utc      = bet.get('kickoff_utc', '?')
        db_market   = bet.get('market', '?')
        db_sel      = bet.get('selection', '?')

        try:
            clv = _clv_pct(open_odds, close_odds)
            status = _clv_status(clv)
        except ValueError as exc:
            logger.warning("CLV calc error for bet %d: %s", bet_id, exc)
            return False

        mins_to_ko_at_close = round((ko_epoch - close_ts) / 60) if ko_epoch else None

        # ── Full debug block (always emitted at INFO level) ──────────────────
        book_match  = (open_book.lower() == close_book.lower())
        mtype_label = f"{db_market}  →  API:{api_mtype}"
        logger.info(
            "╔═ CLV DEBUG  bet=%d ═══════════════════════════════════════════",
            bet_id
        )
        logger.info("║  Match       : %s vs %s  (%s)", bet['home_team'], bet['away_team'], bet.get('league', '?'))
        logger.info("║  match_id    : %s", bet.get('match_id', '?'))
        logger.info("║  DB market   : %s", db_market)
        logger.info("║  Selection   : %s", db_sel)
        logger.info("║  API mtype   : %s  (mapped from DB market)", api_mtype)
        logger.info("║  Matched out : %s  (outcome string in API response)", matched_out)

        mkt_ok = (
            ('over' in db_market.lower() and 'over' in matched_out.lower())
            or ('under' in db_market.lower() and 'under' in matched_out.lower())
            or ('btts' in db_market.lower() and ('yes' in matched_out.lower() or 'no' in matched_out.lower()))
            or api_mtype == 'h2h'
        )
        if not mkt_ok:
            logger.warning(
                "║  ⚠️  MARKET MISMATCH  DB market='%s'  matched='%s'",
                db_market, matched_out
            )

        logger.info("║  open_odds   : %.3f  [%s]", open_odds, open_book)
        logger.info("║  close_odds  : %.3f  [%s]", close_odds, close_book)
        if book_match:
            logger.info("║  Bookmaker   : ✅ SAME (%s)", close_book)
        else:
            logger.warning(
                "║  ⚠️  BOOK MISMATCH  open=[%s]  close=[%s]",
                open_book, close_book
            )
        logger.info("║  kickoff     : %s", ko_utc)
        if mins_to_ko_at_close is not None:
            logger.info("║  mins to KO  : %+d min  (%s before kickoff)",
                        mins_to_ko_at_close,
                        f"{mins_to_ko_at_close}min" if mins_to_ko_at_close >= 0 else "AFTER kickoff")
        logger.info("║  CLV%%        : %+.2f%%  [%s]", clv, status)
        logger.info(
            "╚══════════════════════════════════════════════════════════════"
        )

        try:
            db_helper.execute("""
                UPDATE football_opportunities
                SET close_odds      = %s,
                    close_ts        = %s,
                    clv_pct         = %s,
                    clv_status      = %s,
                    clv_source_book = %s
                WHERE id = %s
            """, (close_odds, close_ts, clv, status, close_book, bet_id))
            return True

        except Exception as exc:
            logger.error("❌ CLV: DB update error for bet %d: %s", bet_id, exc)
            return False

    def mark_clv_na(self, bet_id: int, reason: str) -> None:
        """Mark a bet as CLV=na (could not capture closing odds)."""
        try:
            db_helper.execute("""
                UPDATE football_opportunities
                SET clv_status = 'na'
                WHERE id = %s AND close_odds IS NULL
            """, (bet_id,))
            logger.debug("CLV: bet %d marked na — %s", bet_id, reason)
        except Exception:
            pass

    # ── Main cycle ───────────────────────────────────────────────────────────

    def run_cycle(self) -> Dict[str, Any]:
        """
        Main CLV update cycle (runs every 5 min via scheduler).

        Returns health stats:
            candidates, updated, failed, na, avg_clv, timestamp
        """
        stats: Dict[str, Any] = {
            'candidates': 0,
            'updated':    0,
            'failed':     0,
            'na':         0,
            'avg_clv':    None,
            'timestamp':  datetime.now(timezone.utc).isoformat(),
        }

        candidates = self.get_candidates()
        stats['candidates'] = len(candidates)

        if not candidates:
            logger.info("📊 CLV cycle: 0 candidates in 0–8h window — nothing to do")
            return stats

        CAPTURE_WINDOW_MIN  = 120   # Do not finalise close_odds more than 2h before kickoff
        CAPTURE_WINDOW_PAST = -5    # Allow up to 5 min after kickoff

        clv_vals: List[float] = []
        now = _now()

        for bet in candidates:
            bet_id    = bet['id']
            open_odds = bet['open_odds']
            mins_to_ko = bet['seconds_to_ko'] // 60

            if mins_to_ko > CAPTURE_WINDOW_MIN:
                # Too early — will be captured in a future cycle closer to kickoff
                logger.debug(
                    "CLV: skipping bet %d (%s vs %s) — %d min to KO, waiting for <%d min window",
                    bet_id, bet['home_team'], bet['away_team'], mins_to_ko, CAPTURE_WINDOW_MIN
                )
                continue

            close_result = self.fetch_closing_odds(bet)

            if close_result:
                ok = self.save_clv(bet, close_result)
                if ok:
                    stats['updated'] += 1
                    try:
                        clv_vals.append(_clv_pct(open_odds, close_result['odds']))
                    except ValueError:
                        pass
                else:
                    stats['failed'] += 1
            else:
                # Log what we attempted so it's traceable
                db_market = bet.get('market', '?')
                db_sel = bet.get('selection', '')
                mtype = _market_type(db_market, db_sel) or 'unsupported'
                sport = _sport_key(bet.get('league', '')) or 'no_sport_key'
                logger.info(
                    "CLV: ⚪ NO ODDS  bet=%d  %s vs %s | "
                    "market='%s' → api_type='%s' | sport='%s' | "
                    "open_book=[%s] | %+d min to KO",
                    bet_id, bet['home_team'], bet['away_team'],
                    db_market, mtype, sport,
                    bet.get('open_source_book', 'unknown'),
                    mins_to_ko
                )
                if mins_to_ko < CAPTURE_WINDOW_PAST:
                    self.mark_clv_na(bet_id, "no odds data found after kickoff")
                    stats['na'] += 1
                else:
                    stats['failed'] += 1

        if clv_vals:
            stats['avg_clv'] = round(sum(clv_vals) / len(clv_vals), 2)

        logger.info(
            "📊 CLV cycle done — candidates=%d updated=%d failed=%d na=%d avg_clv=%s",
            stats['candidates'], stats['updated'], stats['failed'], stats['na'],
            f"{stats['avg_clv']:+.2f}%" if stats['avg_clv'] is not None else "—"
        )
        return stats


# ─────────────────────────────────────────────────────────────────────────────
# Statistics for dashboard
# ─────────────────────────────────────────────────────────────────────────────

def get_clv_stats() -> Dict[str, Any]:
    """
    Aggregated CLV statistics for the dashboard.

    Returns:
        avg_clv        float | None
        avg_clv_30d    float | None   (last 30 days)
        positive_rate  float | None   (0–100 %)
        coverage_pct   float | None   (0–100 %)
        sample_n       int
        total_picks    int
        sample_ok      bool           (N >= 200 and coverage >= 30 %)
        breakdown      list[dict]     per-status counts
        recent_20      list[dict]     last 20 bets with all CLV fields
    """
    stats: Dict[str, Any] = {
        'avg_clv':       None,
        'avg_clv_30d':   None,
        'positive_rate': None,
        'coverage_pct':  None,
        'sample_n':      0,
        'total_picks':   0,
        'sample_ok':     False,
        'breakdown':     [],
        'recent_20':     [],
    }

    try:
        # Overall counts
        row = db_helper.execute("""
            SELECT
                COUNT(*)                                            AS total,
                COUNT(*) FILTER (WHERE close_odds IS NOT NULL)     AS with_clv,
                AVG(clv_pct) FILTER (WHERE close_odds IS NOT NULL
                                       AND clv_pct BETWEEN -50 AND 50) AS avg_clv,
                COUNT(*) FILTER (WHERE clv_status = 'pos')         AS pos_count,
                COUNT(*) FILTER (WHERE clv_status = 'neg')         AS neg_count
            FROM football_opportunities
            WHERE match_id NOT LIKE 'seed_%%'
        """, fetch='one')

        if row:
            total, with_clv = int(row[0] or 0), int(row[1] or 0)
            stats['total_picks'] = total
            stats['sample_n']    = with_clv
            stats['avg_clv']     = round(float(row[2]), 2) if row[2] else None

            if with_clv > 0:
                pos, neg = int(row[3] or 0), int(row[4] or 0)
                stats['positive_rate'] = round(pos / with_clv * 100, 1)
                stats['breakdown'] = [
                    {'status': 'pos', 'count': pos},
                    {'status': 'neg', 'count': neg},
                    {'status': 'na',  'count': with_clv - pos - neg},
                ]

            if total > 0:
                stats['coverage_pct'] = round(with_clv / total * 100, 1)

            stats['sample_ok'] = (
                with_clv >= 200
                and stats['coverage_pct'] is not None
                and stats['coverage_pct'] >= 30
            )

        # Last 30 days
        row_30 = db_helper.execute("""
            SELECT AVG(clv_pct)
            FROM football_opportunities
            WHERE close_odds IS NOT NULL
              AND clv_pct BETWEEN -50 AND 50
              AND open_ts >= EXTRACT(EPOCH FROM NOW() - INTERVAL '30 days')::BIGINT
              AND match_id NOT LIKE 'seed_%%'
        """, fetch='one')
        if row_30 and row_30[0]:
            stats['avg_clv_30d'] = round(float(row_30[0]), 2)

        # Recent 20 bets debug view
        rows_20 = db_helper.execute("""
            SELECT
                id, home_team, away_team, league, market, selection,
                open_odds, open_ts,
                close_odds, close_ts,
                clv_pct, clv_status, clv_source_book,
                kickoff_epoch
            FROM football_opportunities
            WHERE close_odds IS NOT NULL
              AND match_id NOT LIKE 'seed_%%'
            ORDER BY close_ts DESC NULLS LAST
            LIMIT 20
        """, fetch='all') or []

        recent = []
        for r in rows_20:
            (rid, home, away, league, market, selection,
             open_odds, open_ts, close_odds, close_ts,
             clv_pct, clv_status, clv_source_book,
             kickoff_epoch) = r

            time_to_ko_at_close = None
            if close_ts and kickoff_epoch:
                time_to_ko_at_close = round((kickoff_epoch - close_ts) / 60, 1)

            recent.append({
                'id':                  rid,
                'home_team':           home,
                'away_team':           away,
                'league':              league,
                'market':              market,
                'selection':           selection,
                'open_odds':           float(open_odds) if open_odds else None,
                'open_ts':             open_ts,
                'close_odds':          float(close_odds) if close_odds else None,
                'close_ts':            close_ts,
                'clv_pct':             float(clv_pct) if clv_pct else None,
                'clv_status':          clv_status,
                'clv_source_book':     clv_source_book,
                'time_to_ko_at_close': time_to_ko_at_close,
            })
        stats['recent_20'] = recent

    except Exception as exc:
        logger.error("❌ get_clv_stats error: %s", exc)

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Public convenience functions
# ─────────────────────────────────────────────────────────────────────────────

def run_clv_update_cycle() -> Dict[str, Any]:
    """Convenience wrapper — called by combined_sports_runner."""
    svc = CLVService()
    return svc.run_cycle()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    print("🧪 CLV Service v2 — manual test run")
    stats = run_clv_update_cycle()
    print(f"\nCycle stats: {stats}")
    print("\n📊 Dashboard stats:")
    ds = get_clv_stats()
    for k, v in ds.items():
        if k not in ('recent_20', 'breakdown'):
            print(f"  {k}: {v}")
    print(f"  breakdown: {ds['breakdown']}")
    print(f"  recent_20: {len(ds['recent_20'])} records")
