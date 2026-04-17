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
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from db_helper import db_helper
from real_odds_api import RealOddsAPI
from proof_poster import post_clv_proof

logger = logging.getLogger(__name__)

def _get_af_client():
    """Lazy-import API-Football client to avoid circular imports."""
    try:
        from api_football_client import APIFootballClient
        return APIFootballClient()
    except Exception:
        return None

# ── Window settings ──────────────────────────────────────────────
CANDIDATE_WINDOW_HOURS = 12         # Look for picks kicking off within next 12 h
CLOSE_AFTER_KICKOFF_MIN = 90        # Allow capture up to 90 min AFTER kickoff
TARGET_MINUTES_BEFORE = 60          # Ideal capture point (60 min before KO)
DRIFT_REJECT_PCT = 0.50             # Reject if odds moved >50% (data error)

# Sharp books hierarchy:
# Tier 1 (gold): Pinnacle, Betfair Exchange — highest limits, accept winners, move fast
# Tier 2 (sharp): Matchbook — peer-to-peer exchange, strong signal, same-line proof quality
# Tier 3 (semi-sharp): Bet365, NordicBet, Unibet — good secondary, lower limits
SHARP_BOOKS = ['pinnacle', 'betfair', 'betfair_ex_eu', 'matchbook', 'bet365', 'nordicbet', 'unibet']

# Matchbook borttagen ur priority — stängde börsen 2019, opålitlig som ensam källa
# Tier 1 (gold — direct proof): Pinnacle, Betfair Exchange
# Tier 2 (sharp): Bet365 — high volume, good liquidity
# Tier 3 (semi-sharp — secondary confirmation): NordicBet, Unibet — accept winners in EU,
#         can confirm exact lines when T1/T2 have moved off
SHARP_PRIORITY = ['pinnacle', 'betfair', 'betfair_ex_eu', 'bet365', 'nordicbet', 'unibet']

LEAGUE_TO_SPORT_KEY: Dict[str, str] = {
    # England
    'Premier League': 'soccer_epl',
    'English Championship': 'soccer_efl_champ',
    'Championship': 'soccer_efl_champ',
    'English League One': 'soccer_england_league1',
    'League One': 'soccer_england_league1',
    'English League Two': 'soccer_england_league2',
    'League Two': 'soccer_england_league2',
    'Scottish Premiership': 'soccer_spl',
    # Spain
    'La Liga': 'soccer_spain_la_liga',
    'La Liga 2': 'soccer_spain_segunda_division',
    'Segunda División': 'soccer_spain_segunda_division',
    'Spanish Segunda Division': 'soccer_spain_segunda_division',
    # Italy
    'Serie A': 'soccer_italy_serie_a',
    'Serie B': 'soccer_italy_serie_b',
    'Italian Serie B': 'soccer_italy_serie_b',
    # Germany
    'Bundesliga': 'soccer_germany_bundesliga',
    'Bundesliga 2': 'soccer_germany_bundesliga2',
    '2. Bundesliga': 'soccer_germany_bundesliga2',
    'German 2. Bundesliga': 'soccer_germany_bundesliga2',
    # France
    'Ligue 1': 'soccer_france_ligue_one',
    'Ligue 2': 'soccer_france_ligue_two',
    'French Ligue 2': 'soccer_france_ligue_two',
    # Europe
    'Champions League': 'soccer_uefa_champs_league',
    'Europa League': 'soccer_uefa_europa_league',
    'Conference League': 'soccer_uefa_europa_conference_league',
    # Netherlands
    'Eredivisie': 'soccer_netherlands_eredivisie',
    'Eerste Divisie': 'soccer_netherlands_eredivisie',
    # Portugal
    'Primeira Liga': 'soccer_portugal_primeira_liga',
    'Portuguese Primeira Liga': 'soccer_portugal_primeira_liga',
    'Portuguese Primeira': 'soccer_portugal_primeira_liga',
    'Primeira Liga Portugal': 'soccer_portugal_primeira_liga',
    'Segunda Liga': 'soccer_portugal_segunda_liga',
    # Belgium
    'Belgian First Division': 'soccer_belgium_first_div',
    'Belgian Pro League': 'soccer_belgium_first_div',
    # Turkey
    'Turkish Super Lig': 'soccer_turkey_super_league',
    'Turkish Super League': 'soccer_turkey_super_league',
    # Scandinavia
    'Swiss Super League': 'soccer_switzerland_superleague',
    'Danish Superliga': 'soccer_denmark_superliga',
    'Superliga': 'soccer_denmark_superliga',
    'Norwegian Eliteserien': 'soccer_norway_eliteserien',
    'Swedish Allsvenskan': 'soccer_sweden_allsvenskan',
    # Other Europe
    'Greek Super League': 'soccer_greece_super_league',
    'Austrian Bundesliga': 'soccer_austria_bundesliga',
    'Czech Liga': 'soccer_czech_republic_first_league',
    'Czech First League': 'soccer_czech_republic_first_league',
    'Polish Ekstraklasa': 'soccer_poland_ekstraklasa',
    # Americas
    'MLS': 'soccer_usa_mls',
    'Liga MX': 'soccer_mexico_ligamx',
    'Brazilian Serie A': 'soccer_brazil_serie_a',
    'Brasileirao': 'soccer_brazil_serie_a',
    'Argentine Primera': 'soccer_argentina_primera_division',
    # CONMEBOL
    'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
    'Copa Sudamericana': 'soccer_conmebol_copa_sudamericana',
    # Asia / Oceania
    'J1 League': 'soccer_japan_j_league',
    'K League 1': 'soccer_korea_kleague1',
    'A-League': 'soccer_australia_aleague',
    'Australian A-League': 'soccer_australia_aleague',
}

UNSUPPORTED_MARKETS = {
    'shots', 'fouls', 'offsides',
    'throw-ins', 'player props', 'player_props', 'props',
    'exact score', 'exact_score',
}
# Corners and Cards: no Odds API support — handled via API-Football fallback (_try_af_clv)
AF_ONLY_MARKETS = {'corners', 'cards'}


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


DC_PATTERNS = [
    'home or draw', 'draw or home',
    'draw or away', 'away or draw',
    'home or away', 'away or home',
    'double chance',
]


def _is_double_chance(market: str, selection: str) -> bool:
    combined = (market + ' ' + selection).lower()
    return any(p in combined for p in DC_PATTERNS)


def _dc_type(selection: str) -> str:
    """Return '1X', 'X2', or '12' for a double-chance selection."""
    s = selection.lower()
    has_home = 'home' in s
    has_draw = 'draw' in s
    has_away = 'away' in s
    if has_home and has_draw:
        return '1X'
    if has_draw and has_away:
        return 'X2'
    if has_home and has_away:
        return '12'
    return 'UNKNOWN'


def _market_type(market: str, selection: str = '') -> Optional[str]:
    """Determine Odds API market type from market name AND selection text.

    The DB stores market as 'Value Single' for all value-single picks, so we
    must inspect the selection text to find the correct market endpoint.
    """
    if not _is_supported(market):
        return None
    # Corners/Cards: Odds API has no endpoint — route to API-Football fallback
    if any(af in market.lower() for af in AF_ONLY_MARKETS):
        return None
    combined = (market + ' ' + selection).lower()

    # Double Chance — must be checked BEFORE generic 'draw'/'home'/'away' checks
    if _is_double_chance(market, selection):
        return 'h2h'   # We fetch h2h and compute DC odds from legs (see _compute_dc_odds)

    if 'over' in combined or 'under' in combined:
        return 'totals'

    # BTTS — The Odds API does not reliably expose this market; skip CLV tracking
    if 'btts' in combined or 'both teams' in combined:
        return None

    if ('ah' in combined or 'asian' in combined or 'handicap' in combined
            or re.search(r'[+-]\d+(\.\d+)?\s*(ah|\(ah\))', combined)):
        return 'spreads'

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
            # Also include picks where close_odds was captured early (>30 min before KO)
            # so we can refresh with the true closing line in the final 30-minute window.
            refresh_cutoff = now - (30 * 60)   # 30 min ago
            rows = db_helper.execute("""
                SELECT id, match_id, home_team, away_team, league,
                       market, selection, open_odds, kickoff_epoch, kickoff_utc,
                       best_odds_bookmaker, fixture_id
                FROM football_opportunities
                WHERE status IN ('pending', 'won', 'lost', 'settled')
                  AND open_odds    IS NOT NULL
                  AND kickoff_epoch IS NOT NULL
                  AND kickoff_epoch >= %s
                  AND kickoff_epoch <= %s
                  AND (
                    close_odds IS NULL
                    OR (close_ts IS NOT NULL AND close_ts < kickoff_epoch - 1800
                        AND kickoff_epoch > %s)
                  )
                ORDER BY kickoff_epoch ASC
            """, (window_start, window_end, refresh_cutoff), fetch='all') or []

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
                    'fixture_id':          row[11],
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
        Fetch closing odds for CLV calculation.

        Priority:
          1. Historical endpoint (kickoff snapshot from Pinnacle/Betfair)
             — used when we're within 30 min of KO or match has already kicked off.
             Gives the TRUE closing line regardless of when CLV service runs.
          2. Live endpoint (real-time sharp average)
             — used pre-match when historical snapshot may not yet be final.

        Returns dict with keys:
            odds (float), bookmaker (str), ts (int),
            api_market_type (str), matched_outcome (str)
        or None if unavailable.
        """
        if not self.odds_api:
            return None

        market    = bet.get('market', '')
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
            combined = (market + ' ' + selection).lower()
            if 'btts' in combined or 'both teams' in combined:
                logger.debug(
                    "CLV: BTTS market skipped (Odds API has no BTTS endpoint) — bet=%d %s vs %s",
                    bet.get('id', '?'), bet['home_team'], bet['away_team']
                )
            else:
                logger.debug("CLV: unsupported market type '%s' sel='%s'", market, selection)
            return None

        # ── 1. Historical snapshot (primary — true closing line) ──────────────
        # Use when within 30 min of KO or after KO (historical gives final odds).
        now       = _now()
        ko_epoch  = bet.get('kickoff_epoch', 0)
        mins_to_ko = (ko_epoch - now) // 60 if ko_epoch else 9999

        if ko_epoch and mins_to_ko <= 30:
            hist = self.fetch_historical_closing_odds(bet)
            if hist:
                logger.info(
                    "CLV: ✅ historical close  bet=%d %s vs %s | %.2f [%s]",
                    bet['id'], bet['home_team'], bet['away_team'],
                    hist['odds'], hist['bookmaker']
                )
                return hist
            logger.debug(
                "CLV: historical returned None for bet=%d — falling back to live",
                bet['id']
            )

        # ── 2. Live endpoint (fallback / pre-match real-time) ─────────────────
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

    def fetch_historical_closing_odds(self, bet: Dict) -> Optional[Dict]:
        """
        Fetch CLOSING odds using The Odds API historical endpoint.

        Uses a frozen snapshot at kickoff time — much more reliable than live endpoint
        because it captures where Pinnacle/Betfair actually closed, regardless of when
        the CLV service happens to run.

        Snapshot timestamp: kickoff_epoch (true closing line = last pre-match odds).
        Falls back to (kickoff - 60min) if kickoff snapshot has no data.

        Returns same format as fetch_closing_odds: {odds, bookmaker, ts, ...} or None.
        """
        if not self.odds_api:
            return None

        ko_epoch = bet.get('kickoff_epoch', 0)
        if not ko_epoch:
            return None

        market = bet.get('market', '')
        if not _is_supported(market):
            return None

        sport = _sport_key(bet.get('league', ''))
        if not sport:
            return None

        mtype = _market_type(market, bet.get('selection', ''))
        if not mtype:
            return None

        api_key = self.odds_api.api_key if hasattr(self.odds_api, 'api_key') else os.getenv('THE_ODDS_API_KEY', '')
        if not api_key:
            return None

        # Try kickoff time first, then 60 min before KO as fallback
        for ts_offset in [0, -3600]:
            snap_ts  = ko_epoch + ts_offset
            snap_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(snap_ts))

            try:
                resp = requests.get(
                    f'https://api.the-odds-api.com/v4/historical/sports/{sport}/odds',
                    params={
                        'apiKey':      api_key,
                        'date':        snap_iso,
                        'regions':     'eu,uk',
                        'markets':     mtype,
                        'bookmakers':  'pinnacle,betfair_ex_eu,betfair,bet365,nordicbet,unibet',
                        'oddsFormat':  'decimal',
                    },
                    timeout=12,
                )
            except Exception as exc:
                logger.debug("CLV historical: request error: %s", exc)
                continue

            if resp.status_code != 200:
                logger.debug("CLV historical: HTTP %d for %s", resp.status_code, sport)
                continue

            payload = resp.json()
            events  = payload.get('data', [])
            if not events:
                continue

            for event in events:
                if not self._teams_match(event, bet['home_team'], bet['away_team']):
                    continue

                result = self._best_odds_for_selection(
                    event, market, bet['selection'], bet['home_team'], bet['away_team']
                )
                if result is None:
                    continue

                close_odds, bookmaker, matched_outcome = result
                open_odds = bet.get('open_odds', 0)

                if open_odds and open_odds > 1.0:
                    drift = abs(close_odds - open_odds) / open_odds
                    if drift > DRIFT_REJECT_PCT:
                        logger.warning(
                            "CLV historical: DRIFT REJECT bet=%d open=%.2f close=%.2f drift=%.0f%%",
                            bet['id'], open_odds, close_odds, drift * 100
                        )
                        continue

                logger.info(
                    "CLV historical ✅ bet=%d %s vs %s | %s %.2f→%.2f [%s] snap=%s",
                    bet['id'], bet['home_team'], bet['away_team'],
                    market, open_odds, close_odds, bookmaker, snap_iso
                )
                return {
                    'odds':            close_odds,
                    'bookmaker':       f"hist:{bookmaker}",
                    'ts':              _now(),
                    'api_market_type': mtype,
                    'matched_outcome': matched_outcome,
                }

        return None

    def _teams_match(self, event: Dict, home: str, away: str) -> bool:
        from difflib import SequenceMatcher

        def _norm(s: str) -> str:
            return (s.lower()
                    .replace('fc ', '').replace(' fc', '')
                    .replace('afc ', '').replace(' afc', '')
                    .replace('sc ', '').replace(' sc', '')
                    .replace('ö', 'o').replace('ü', 'u').replace('ä', 'a')
                    .replace('ø', 'o').replace('å', 'a').replace('é', 'e')
                    .replace('-', ' ').strip())

        def _sim(a: str, b: str) -> float:
            return SequenceMatcher(None, _norm(a), _norm(b)).ratio()

        def _word_overlap(a: str, b: str) -> bool:
            wa = set(_norm(a).split())
            wb = set(_norm(b).split())
            common = wa & wb
            # At least 1 meaningful word (len>2) must overlap
            return any(len(w) > 2 for w in common)

        eh = event.get('home_team', '')
        ea = event.get('away_team', '')
        # Exact match
        if eh.lower() == home.lower() and ea.lower() == away.lower():
            return True
        # Fuzzy: both teams must score >= 0.75 similarity
        h_score = _sim(home, eh)
        a_score = _sim(away, ea)
        if h_score >= 0.75 and a_score >= 0.75:
            return True
        # Word-overlap fallback (catches "Man Utd" vs "Manchester United")
        if _word_overlap(home, eh) and _word_overlap(away, ea):
            return True
        return False

    def _compute_dc_odds(
        self, bookmakers: List, selection: str, home: str, away: str
    ) -> Optional[tuple]:
        """
        Compute Double Chance closing odds from h2h legs using no-vig probability.

        For 'Home or Draw' (1X): P(DC) = P(home) + P(draw)
        For 'Draw or Away' (X2): P(DC) = P(draw) + P(away)
        For 'Home or Away' (12): P(DC) = P(home) + P(away)

        Returns (dc_odds, source_label, matched_outcome_name) or None.
        """
        dc = _dc_type(selection)
        if dc == 'UNKNOWN':
            return None

        h_lower = home.lower()
        a_lower = away.lower()

        sharp_hits: List[tuple] = []
        fallback_hit: Optional[tuple] = None

        for bk in bookmakers:
            bk_key   = bk.get('key', '').lower()
            bk_title = bk.get('title', bk.get('key', 'unknown'))
            is_sharp = bk_key in SHARP_PRIORITY

            home_price = draw_price = away_price = None

            for mkt_obj in bk.get('markets', []):
                if mkt_obj.get('key') != 'h2h':
                    continue
                for outcome in mkt_obj.get('outcomes', []):
                    name  = outcome.get('name', '').lower()
                    price = outcome.get('price')
                    if not price:
                        continue
                    if 'draw' in name:
                        draw_price = float(price)
                    elif name == h_lower or h_lower in name:
                        home_price = float(price)
                    elif name == a_lower or a_lower in name:
                        away_price = float(price)

            if home_price and draw_price and away_price:
                raw   = [1.0 / home_price, 1.0 / draw_price, 1.0 / away_price]
                total = sum(raw)
                p_h, p_d, p_a = [p / total for p in raw]

                if dc == '1X':
                    p_dc = p_h + p_d
                elif dc == 'X2':
                    p_dc = p_d + p_a
                else:  # 12
                    p_dc = p_h + p_a

                if p_dc > 0:
                    dc_odds = round(1.0 / p_dc, 4)
                    entry   = (dc_odds, bk_title, f"DC_{dc}(computed)")
                    if is_sharp:
                        sharp_hits.append(entry)
                    elif fallback_hit is None:
                        fallback_hit = entry

        if sharp_hits:
            avg = sum(h[0] for h in sharp_hits) / len(sharp_hits)
            names = sorted(
                {h[1] for h in sharp_hits},
                key=lambda b: SHARP_PRIORITY.index(b.lower()) if b.lower() in SHARP_PRIORITY else 99
            )
            book_label = ' + '.join(names[:2]) + (' ...' if len(names) > 2 else '')
            return (round(avg, 4), f"vs {book_label} (DC)", f"DC_{dc}")

        if fallback_hit:
            odds, book_title, matched_out = fallback_hit
            return (odds, f"~{book_title} (soft)", matched_out)

        return None

    def _best_odds_for_selection(
        self, event: Dict, market: str, selection: str, home: str, away: str
    ) -> Optional[tuple]:
        """
        Sharp-average approach: collect closing odds from all available sharp books
        (Pinnacle, Bet365, Matchbook, Betfair) and return their average.
        Falls back to any available book if no sharp books match.

        Special handling:
        - Double Chance selections → computed from h2h legs via _compute_dc_odds
        - Totals → uses outcome 'point' field for line matching (not name regex)

        Returns (avg_odds, source_label, matched_outcome_name)
        """
        bookmakers = event.get('bookmakers', [])

        # ── Double Chance: compute from h2h legs, don't do direct outcome match ──
        if _is_double_chance(market, selection):
            return self._compute_dc_odds(bookmakers, selection, home, away)

        sel_lower = selection.lower()
        mkt_lower = market.lower()
        is_totals = 'over' in sel_lower or 'under' in sel_lower
        target_line = _extract_line(sel_lower) if is_totals else None

        sharp_hits: List[tuple] = []
        fallback_hit: Optional[tuple] = None
        # For nearest-line fallback: track best sharp candidate per book
        # (book_title -> (price, line, outcome_name))
        sharp_nearest: dict = {}
        # For interpolation: track closest line BELOW and ABOVE target per book
        # (book_title -> (price, line, outcome_name))
        sharp_below: dict = {}
        sharp_above: dict = {}

        for bk in bookmakers:
            bk_key   = bk.get('key', '').lower()
            bk_title = bk.get('title', bk.get('key', 'unknown'))
            is_sharp = bk_key in SHARP_PRIORITY

            for mkt_obj in bk.get('markets', []):
                for outcome in mkt_obj.get('outcomes', []):
                    name  = outcome.get('name', '').lower()
                    price = outcome.get('price')
                    if not price:
                        continue

                    # For totals: match using the 'point' field, not the name
                    if is_totals:
                        point = outcome.get('point')
                        if point is None:
                            continue
                        side_match = ('over' in sel_lower and 'over' in name) or \
                                     ('under' in sel_lower and 'under' in name)
                        if not side_match:
                            continue

                        point_f = float(point)
                        line_diff = abs(point_f - target_line) if target_line is not None else 0

                        if target_line is not None and line_diff > 0.01:
                            # Not an exact match — store as nearest-line candidate for sharp books
                            if is_sharp and line_diff <= 0.75:
                                prev = sharp_nearest.get(bk_title)
                                prev_diff = abs(prev[1] - target_line) if prev else 999
                                if line_diff < prev_diff:
                                    sharp_nearest[bk_title] = (float(price), point_f, outcome.get('name', name))
                                # Also track for interpolation: separate below/above buckets
                                entry_t = (float(price), point_f, outcome.get('name', name))
                                if point_f < target_line:
                                    prev_b = sharp_below.get(bk_title)
                                    if prev_b is None or (target_line - point_f) < (target_line - prev_b[1]):
                                        sharp_below[bk_title] = entry_t
                                else:
                                    prev_a = sharp_above.get(bk_title)
                                    if prev_a is None or (point_f - target_line) < (prev_a[1] - target_line):
                                        sharp_above[bk_title] = entry_t
                            continue
                        # Exact totals match confirmed
                    else:
                        if not self._sel_matches(sel_lower, name, home, away, mkt_lower):
                            continue

                    entry = (float(price), bk_title, outcome.get('name', name))
                    if is_sharp:
                        sharp_hits.append(entry)
                    elif fallback_hit is None:
                        fallback_hit = entry

        if sharp_hits:
            avg_odds  = sum(h[0] for h in sharp_hits) / len(sharp_hits)
            book_names = sorted(
                {h[1] for h in sharp_hits},
                key=lambda b: SHARP_PRIORITY.index(b.lower()) if b.lower() in SHARP_PRIORITY else 99
            )
            book_label = ' + '.join(book_names[:2]) + (' ...' if len(book_names) > 2 else '')
            source_label = f"vs {book_label}"
            matched_out  = sharp_hits[0][2]
            return (round(avg_odds, 4), source_label, matched_out)

        # ── Interpolation: derive fair odds for exact target line from two adjacent sharp lines ──
        # Uses linear interpolation of implied probability between the closest line below
        # and above the target. Tags as "(interp L↔H)" — credible same-line-equivalent proof.
        # Only runs for totals when no exact sharp match found.
        if not sharp_hits and is_totals and target_line is not None and sharp_below and sharp_above:
            # Find best sharp book that has BOTH sides (sorted by SHARP_PRIORITY)
            both_books = sorted(
                [bk for bk in sharp_below if bk in sharp_above],
                key=lambda b: SHARP_PRIORITY.index(b.lower()) if b.lower() in SHARP_PRIORITY else 99
            )
            if both_books:
                interp_results = []
                for bk in both_books:
                    lo_odds, lo_line, _ = sharp_below[bk]
                    hi_odds, hi_line, _ = sharp_above[bk]
                    span = hi_line - lo_line
                    if span < 0.01:
                        continue
                    # Linear interpolation of implied probability
                    p_lo = 1.0 / lo_odds
                    p_hi = 1.0 / hi_odds
                    # Weight: target closer to lo_line → more weight on lo_line's prob
                    w_lo = (hi_line - target_line) / span
                    w_hi = (target_line - lo_line) / span
                    p_interp = w_lo * p_lo + w_hi * p_hi
                    if p_interp <= 0:
                        continue
                    fair_odds = round(1.0 / p_interp, 4)
                    lo_str = f"{lo_line:.2f}".rstrip('0').rstrip('.')
                    hi_str = f"{hi_line:.2f}".rstrip('0').rstrip('.')
                    interp_results.append((fair_odds, bk, f"interp_{lo_str}_{hi_str}",
                                           lo_line, hi_line, lo_odds, hi_odds))

                if interp_results:
                    avg_odds   = sum(r[0] for r in interp_results) / len(interp_results)
                    book_names = [r[1] for r in interp_results]
                    lo_str     = f"{interp_results[0][3]:.2f}".rstrip('0').rstrip('.')
                    hi_str     = f"{interp_results[0][4]:.2f}".rstrip('0').rstrip('.')
                    lo_o       = f"{interp_results[0][5]:.2f}"
                    hi_o       = f"{interp_results[0][6]:.2f}"
                    book_label = ' + '.join(book_names[:2]) + (' ...' if len(book_names) > 2 else '')
                    # Format includes odds so proof embed can show derivation:
                    # "vs Pinnacle (interp 3.25@1.91↔3.75@2.55)"
                    source_label = f"vs {book_label} (interp {lo_str}@{lo_o}↔{hi_str}@{hi_o})"
                    matched_out  = interp_results[0][2]
                    logger.info(
                        "CLV: interpolated odds %.4f for line %.2f between %.2f@%.2f↔%.2f@%.2f — books=%s",
                        avg_odds, target_line,
                        interp_results[0][3], interp_results[0][5],
                        interp_results[0][4], interp_results[0][6],
                        book_names
                    )
                    return (round(avg_odds, 4), source_label, matched_out)

        # ── Nearest-line fallback: use Pinnacle/sharp book's closest line ────────
        # Triggered when sharp books offer totals but on a different line (e.g. 2.75 vs 2.5).
        # Marked as "approx_CLV" — directionally valid, not a direct comparison.
        if sharp_nearest and is_totals:
            sorted_books = sorted(
                sharp_nearest.items(),
                key=lambda kv: SHARP_PRIORITY.index(kv[0].lower()) if kv[0].lower() in SHARP_PRIORITY else 99
            )
            approx_hits = [(price, title, out_name, line)
                           for title, (price, line, out_name) in sorted_books]
            avg_odds = sum(h[0] for h in approx_hits) / len(approx_hits)
            book_names = [h[1] for h in approx_hits]
            actual_line = approx_hits[0][3]
            book_label  = ' + '.join(book_names[:2]) + (' ...' if len(book_names) > 2 else '')
            bet_line_str = f"{target_line:.2f}".rstrip('0').rstrip('.') if target_line else '?'
            act_line_str = f"{actual_line:.2f}".rstrip('0').rstrip('.')
            source_label = f"vs {book_label} (line moved {bet_line_str} → {act_line_str})"
            matched_out  = approx_hits[0][2]
            logger.info(
                "CLV: approx line — bet=%.2f nearest sharp=%.2f books=%s",
                target_line or 0, actual_line, book_names
            )
            return (round(avg_odds, 4), source_label, matched_out)

        if fallback_hit:
            odds, book_title, matched_out = fallback_hit
            logger.info(
                "CLV: soft source — no sharp book found, using %s (bronze)",
                book_title
            )
            return (odds, f"~{book_title} (soft)", matched_out)

        return None

    def _sel_matches(self, sel: str, outcome: str, home: str, away: str, market: str) -> bool:
        """
        Strict outcome matching for h2h (1X2) markets only.
        Totals and Double Chance are handled separately — do NOT call this for them.
        """
        h, a = home.lower(), away.lower()

        # Exact match
        if sel == outcome:
            return True

        # Home win: sel must reference home side and outcome must be home team name
        if ('home win' in sel or sel == h) and (outcome == h or h in outcome):
            return True

        # Away win: sel must reference away side and outcome must be away team name
        if ('away win' in sel or sel == a) and (outcome == a or a in outcome):
            return True

        # Draw: only pure draw selections (not double chance)
        if sel == 'draw' and outcome == 'draw':
            return True

        # Home team name directly in selection (e.g. sel = "manchester city")
        if sel == h and (outcome == h or h in outcome):
            return True

        # Away team name directly in selection
        if sel == a and (outcome == a or a in outcome):
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
            # 3-tier CLV: bronze sources (~book (soft)) are not sharp proof
            if close_book and '(soft)' in close_book:
                status = 'soft'
            # Line-moved captures compare odds across different markets
            # (e.g. Over 2.5 vs Over 2.0) — directional only, not sharp proof.
            if close_book and '(line moved' in close_book:
                status = 'soft'
        except ValueError as exc:
            logger.warning("CLV calc error for bet %d: %s", bet_id, exc)
            return False

        # Steam flag: positive CLV > 3% = "early" (we were ahead of market move)
        #             negative CLV < -3% = "late" (missed the move, market already moved)
        if clv > 3.0:
            steam_flag = 'early'
        elif clv < -3.0:
            steam_flag = 'late'
        else:
            steam_flag = 'neutral'

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
            # Only post to Discord on FIRST capture — check if close_odds already set
            already_captured = db_helper.execute(
                "SELECT close_ts FROM football_opportunities WHERE id = %s",
                (bet_id,), fetch='one'
            )
            first_capture = not (already_captured and already_captured[0])

            db_helper.execute("""
                UPDATE football_opportunities
                SET close_odds      = %s,
                    close_ts        = %s,
                    clv_pct         = %s,
                    clv_status      = %s,
                    clv_source_book = %s,
                    steam_flag      = %s
                WHERE id = %s
            """, (close_odds, close_ts, clv, status, close_book, steam_flag, bet_id))

            if not first_capture:
                logger.debug(
                    "CLV: bet=%d already captured — skip Discord post", bet_id
                )
            else:
                # Post proof-of-work to Discord (fire-and-forget, never blocks)
                try:
                    post_clv_proof(bet, close_odds, clv, close_book,
                                   mins_to_close=mins_to_ko_at_close)
                except Exception as _pe:
                    logger.debug("proof_poster non-fatal: %s", _pe)

                # Per-pick CLV capture — posts ALL picks to DISCORD_RESULTS_WEBHOOK (no threshold)
                try:
                    from proof_poster import post_clv_capture
                    post_clv_capture(bet, close_odds, clv, close_book,
                                     mins_to_close=mins_to_ko_at_close)
                except Exception as _ce:
                    logger.debug("clv_capture non-fatal: %s", _ce)

            # 🔔 Push notification for significant CLV moves — first alert only
            if steam_flag in ('early', 'late'):
                try:
                    # Only fire if not already pushed for this pick
                    _push_row = db_helper.execute(
                        "SELECT push_sent FROM football_opportunities WHERE id=%s",
                        (bet_id,)
                    )
                    _already_pushed = _push_row and _push_row[0][0]
                    if not _already_pushed:
                        import threading
                        from push_service import PushService
                        match_str = f"{bet.get('home_team', '?')} vs {bet.get('away_team', '?')}"
                        sel = bet.get('selection', bet.get('market', '?'))
                        clv_sign = f"+{clv:.1f}" if clv >= 0 else f"{clv:.1f}"
                        if steam_flag == 'early':
                            title = "⚡ CLV Confirmed"
                            body  = (
                                f"{match_str}\n"
                                f"{sel} — {clv_sign}% vs close\n"
                                f"Market moved our way"
                            )
                        else:
                            title = "⚠️ Early Drop Alert"
                            body  = (
                                f"{match_str}\n"
                                f"{sel} — {clv_sign}% CLV\n"
                                f"Odds drifted against entry"
                            )
                        def _fire_clv(t=title, b=body, bid=bet_id):
                            try:
                                result = PushService().send_to_all(t, b, url="/")
                                if result.get('sent', 0) > 0:
                                    db_helper.execute(
                                        "UPDATE football_opportunities SET push_sent=TRUE WHERE id=%s",
                                        (bid,)
                                    )
                            except Exception as _e:
                                logger.debug("CLV push non-fatal: %s", _e)
                        threading.Thread(target=_fire_clv, daemon=True).start()
                except Exception as _pe:
                    logger.debug("CLV push setup non-fatal: %s", _pe)

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

    # ── API-Football fallback (BTTS + unsupported-sport leagues) ─────────────

    def _try_af_clv(self, bet: Dict, stats: Dict) -> bool:
        """
        API-Football fallback for BTTS, Corners, Cards, and leagues not in Odds API.
        Uses fixture_id directly if available (avoids extra team-name search API call).
        Returns True if CLV was captured and saved.
        """
        db_market = bet.get('market', '')
        db_sel    = bet.get('selection', '')
        home      = bet['home_team']
        away      = bet['away_team']
        open_odds = bet['open_odds']

        af = _get_af_client()
        if not af:
            return False

        # Derive match_date string from kickoff_utc or kickoff_epoch
        match_date = bet.get('kickoff_utc') or ''
        if not match_date:
            ko = bet.get('kickoff_epoch')
            if ko:
                match_date = datetime.fromtimestamp(ko, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if not match_date:
            return False

        try:
            # Use stored fixture_id directly if available (faster, no extra API call)
            stored_fid = bet.get('fixture_id')
            if stored_fid:
                fixture_id = int(stored_fid)
                logger.debug("CLV(AF-fb): using stored fixture_id=%d for bet=%d", fixture_id, bet['id'])
            else:
                fixture = af.get_fixture_by_teams_and_date(home, away, match_date)
                if not fixture:
                    return False
                fixture_id = fixture.get('fixture', {}).get('id')
                if not fixture_id:
                    return False

            odds_data = af.get_fixture_odds(fixture_id, bypass_cache=True)
            if not odds_data:
                return False

            market_odds = odds_data.get('markets', {})
            if not market_odds:
                return False

            close_odds = _match_api_football_odds(db_market, db_sel, home, away, market_odds)
            if not close_odds or close_odds <= 1.0:
                return False

            # Drift guard
            if open_odds > 1.0:
                drift = abs(close_odds - open_odds) / open_odds
                if drift > DRIFT_REJECT_PCT:
                    logger.debug(
                        "CLV(AF-fb): drift reject bet=%d open=%.2f close=%.2f drift=%.0f%%",
                        bet['id'], open_odds, close_odds, drift * 100
                    )
                    return False

            close_result = {
                'odds':            close_odds,
                'bookmaker':       'api_football',
                'ts':              _now(),
                'api_market_type': 'af_fallback',
                'matched_outcome': db_sel,
            }
            ok = self.save_clv(bet, close_result)
            if ok:
                stats['updated'] += 1
                logger.info(
                    "CLV(AF-fb): ✅ bet=%d  %s vs %s  %s  open=%.2f close=%.2f",
                    bet['id'], home, away, db_sel, open_odds, close_odds
                )
            return ok

        except Exception as exc:
            logger.debug("CLV(AF-fb): error bet=%d: %s", bet.get('id', '?'), exc)
            return False

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
            'skipped':    0,    # unsupported market/league — not an error
            'na':         0,
            'avg_clv':    None,
            'timestamp':  datetime.now(timezone.utc).isoformat(),
        }

        candidates = self.get_candidates()
        stats['candidates'] = len(candidates)

        if not candidates:
            logger.info("📊 CLV cycle: 0 candidates in 0–12h window — nothing to do")
            return stats

        CAPTURE_WINDOW_MIN  = CANDIDATE_WINDOW_HOURS * 60   # mirror candidate window
        CAPTURE_WINDOW_PAST = -CLOSE_AFTER_KICKOFF_MIN      # mirror post-kickoff window

        clv_vals: List[float] = []
        now = _now()

        for bet in candidates:
            bet_id    = bet['id']
            open_odds = bet['open_odds']
            mins_to_ko = bet['seconds_to_ko'] // 60

            if mins_to_ko > CAPTURE_WINDOW_MIN:
                logger.info(
                    "CLV: ⏳ TOO EARLY  bet=%d  %s vs %s  (%d min to KO, window <%d min)",
                    bet_id, bet['home_team'], bet['away_team'], mins_to_ko, CAPTURE_WINDOW_MIN
                )
                continue

            # Pre-check: skip unsupported markets immediately (not a failure)
            db_market = bet.get('market', '?')
            db_sel    = bet.get('selection', '')
            if not _is_supported(db_market):
                logger.debug(
                    "CLV: ⏭️ SKIP  bet=%d  %s vs %s | market='%s' unsupported",
                    bet_id, bet['home_team'], bet['away_team'], db_market
                )
                stats['skipped'] += 1
                continue

            mtype = _market_type(db_market, db_sel)
            sport = _sport_key(bet.get('league', ''))
            if not mtype or not sport:
                # Fallback: try API-Football for BTTS + unsupported-sport leagues
                af_ok = self._try_af_clv(bet, stats)
                if not af_ok:
                    logger.info(
                        "CLV: ⏭️ SKIP  bet=%d  %s vs %s | market='%s' → api_type='%s' | league='%s' sport='%s'",
                        bet_id, bet['home_team'], bet['away_team'],
                        db_market, mtype or 'none', bet.get('league', '?'), sport or 'not_mapped'
                    )
                    stats['skipped'] += 1
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
                logger.info(
                    "CLV: ⚪ NO MATCH  bet=%d  %s vs %s | "
                    "market='%s' → api_type='%s' | sport='%s' | %+d min to KO",
                    bet_id, bet['home_team'], bet['away_team'],
                    db_market, mtype, sport, mins_to_ko
                )
                if mins_to_ko < CAPTURE_WINDOW_PAST:
                    self.mark_clv_na(bet_id, "no match found in API after kickoff")
                    stats['na'] += 1
                else:
                    stats['failed'] += 1

        if clv_vals:
            stats['avg_clv'] = round(sum(clv_vals) / len(clv_vals), 2)

        logger.info(
            "📊 CLV cycle done — candidates=%d updated=%d skipped=%d failed=%d na=%d avg_clv=%s",
            stats['candidates'], stats['updated'], stats['skipped'],
            stats['failed'], stats['na'],
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
                COUNT(*) FILTER (WHERE close_odds IS NOT NULL
                                   AND clv_status != 'soft')       AS with_clv,
                AVG(clv_pct) FILTER (WHERE close_odds IS NOT NULL
                                       AND clv_status != 'soft'
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

        # Last 30 days (sharp + approx only — exclude soft_CLV bronze)
        row_30 = db_helper.execute("""
            SELECT AVG(clv_pct)
            FROM football_opportunities
            WHERE close_odds IS NOT NULL
              AND clv_status != 'soft'
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


def sweep_missed_clv(lookback_hours: int = 48) -> int:
    """
    Retroactive sweep: finds picks from last `lookback_hours` that still
    have close_odds IS NULL and kickoff has already passed by >90 min.
    Tries API-Football for each one.

    Called hourly from combined_sports_runner.
    Returns number of picks updated.
    """
    now = _now()
    cutoff_open   = now - (lookback_hours * 3600)
    cutoff_kickoff = now - (90 * 60)   # must have kicked off >90 min ago

    try:
        rows = db_helper.execute("""
            SELECT id, match_id, home_team, away_team, league,
                   market, selection, open_odds, kickoff_epoch, kickoff_utc,
                   best_odds_bookmaker, fixture_id
            FROM football_opportunities
            WHERE status          = 'pending'
              AND close_odds      IS NULL
              AND clv_status      IS NULL
              AND open_odds       IS NOT NULL
              AND kickoff_epoch   IS NOT NULL
              AND open_ts         >= %s
              AND kickoff_epoch   <= %s
            ORDER BY kickoff_epoch DESC
        """, (cutoff_open, cutoff_kickoff), fetch='all') or []
    except Exception as exc:
        logger.error("sweep_missed_clv: DB fetch error: %s", exc)
        return 0

    if not rows:
        logger.info("sweep_missed_clv: no missed picks found (window %dh)", lookback_hours)
        return 0

    logger.info("sweep_missed_clv: %d pick(s) to retry via API-Football", len(rows))
    svc = CLVService()
    updated = 0
    dummy_stats: Dict[str, Any] = {'updated': 0}

    for row in rows:
        bet = {
            'id':               row[0],
            'match_id':         row[1],
            'home_team':        row[2],
            'away_team':        row[3],
            'league':           row[4],
            'market':           row[5],
            'selection':        row[6],
            'open_odds':        float(row[7]),
            'kickoff_epoch':    int(row[8]),
            'kickoff_utc':      row[9],
            'seconds_to_ko':    int(row[8]) - now,
            'open_source_book': row[10] or 'unknown',
            'fixture_id':       row[11],
        }
        if not _is_supported(bet['market']):
            continue
        ok = svc._try_af_clv(bet, dummy_stats)
        if ok:
            updated += 1

    logger.info("sweep_missed_clv: updated %d/%d pick(s)", updated, len(rows))
    return updated


def capture_from_api_football(home_team: str, away_team: str,
                               market_odds: Dict[str, float],
                               kickoff_epoch: Optional[int] = None,
                               match_date: Optional[str] = None) -> int:
    """
    Secondary CLV source: capture closing odds from API-Football market odds.

    Called from the main engine after odds are fetched for a match.
    Updates any PENDING pick on this match (looked up by team names + date).

    market_odds format: {'HOME_WIN': 2.10, 'AWAY_WIN': 3.50, 'DRAW': 3.20,
                         'FT_OVER_2_5': 1.90, 'BTTS_YES': 1.85, ...}

    Returns: number of picks updated
    """
    if not market_odds or not home_team or not away_team:
        return 0

    CAPTURE_MIN_BEFORE = 180    # Only capture if kickoff is within 3h (was 720/12h — too early)
    CAPTURE_AFTER_KO   = 120    # Allow up to 120 min after kickoff
    now = int(time.time())

    # Time-gate: only update if kickoff is approaching
    if kickoff_epoch:
        mins_to_ko = (kickoff_epoch - now) // 60
        if mins_to_ko > CAPTURE_MIN_BEFORE:
            return 0       # Too early
        if mins_to_ko < -CAPTURE_AFTER_KO:
            return 0       # Too late

    # Fetch pending picks for this match by team name match + date
    try:
        if match_date:
            rows = db_helper.execute("""
                SELECT id, market, selection, open_odds
                FROM football_opportunities
                WHERE LOWER(home_team) = LOWER(%s)
                  AND LOWER(away_team) = LOWER(%s)
                  AND match_date       = %s
                  AND status           = 'pending'
                  AND close_odds       IS NULL
                  AND open_odds        IS NOT NULL
            """, (home_team, away_team, match_date), fetch='all') or []
        else:
            rows = db_helper.execute("""
                SELECT id, market, selection, open_odds
                FROM football_opportunities
                WHERE LOWER(home_team) = LOWER(%s)
                  AND LOWER(away_team) = LOWER(%s)
                  AND status           = 'pending'
                  AND close_odds       IS NULL
                  AND open_odds        IS NOT NULL
            """, (home_team, away_team), fetch='all') or []
    except Exception as exc:
        logger.error("CLV(AF): DB fetch error %s vs %s: %s", home_team, away_team, exc)
        return 0

    if not rows:
        return 0

    updated = 0
    for (bet_id, market, selection, open_odds_raw) in rows:
        open_odds = float(open_odds_raw) if open_odds_raw else 0
        if not _is_supported(market):
            continue

        # Map selection to market_odds key
        close_odds = _match_api_football_odds(market, selection, home_team, away_team, market_odds)
        if close_odds is None or close_odds <= 1.0:
            continue

        # Drift guard
        if open_odds > 1.0:
            drift = abs(close_odds - open_odds) / open_odds
            if drift > DRIFT_REJECT_PCT:
                logger.debug("CLV(AF): drift reject bet=%d open=%.2f close=%.2f drift=%.0f%%",
                             bet_id, open_odds, close_odds, drift * 100)
                continue

        try:
            clv = _clv_pct(open_odds, close_odds)
            status = 'soft'  # api_football is always soft — never sharp proof
        except ValueError:
            continue

        if clv > 3.0:
            steam_flag = 'early'
        elif clv < -3.0:
            steam_flag = 'late'
        else:
            steam_flag = 'neutral'

        try:
            db_helper.execute("""
                UPDATE football_opportunities
                SET close_odds      = %s,
                    close_ts        = %s,
                    clv_pct         = %s,
                    clv_status      = %s,
                    clv_source_book = %s,
                    steam_flag      = %s
                WHERE id = %s AND close_odds IS NULL
            """, (close_odds, now, clv, status, '~api_football (soft)', steam_flag, bet_id))
            logger.info(
                "CLV(AF): ✅ bet=%d  %s vs %s  %s|%s  "
                "open=%.3f close=%.3f  CLV=%+.2f%%",
                bet_id, home_team, away_team, market, selection,
                open_odds, close_odds, clv
            )
            updated += 1
        except Exception as exc:
            logger.error("CLV(AF): DB update error bet=%d: %s", bet_id, exc)

    return updated


def _match_api_football_odds(market: str, selection: str,
                              home: str, away: str,
                              odds_map: Dict[str, float]) -> Optional[float]:
    """Map a DB market+selection to an API-Football odds_map key."""
    m = market.lower()
    s = selection.lower()
    h = home.lower()
    a = away.lower()

    # ── Corners ──────────────────────────────────────────────────────────────
    if 'corner' in m or 'corner' in s:
        num_match = re.search(r'([\d.]+)', s)
        if not num_match:
            return None
        line = num_match.group(1).replace('.', '_')

        # Team corners: home or away team name in selection
        if h and any(word in s for word in h.split() if len(word) > 3):
            side = 'over' if 'over' in s else 'under'
            key = f"HOME_CORNERS_{side.upper()}_{line}"
            return odds_map.get(key)
        if a and any(word in s for word in a.split() if len(word) > 3):
            side = 'over' if 'over' in s else 'under'
            key = f"AWAY_CORNERS_{side.upper()}_{line}"
            return odds_map.get(key)

        # Match corners over/under
        if 'over' in s:
            return odds_map.get(f'CORNERS_OVER_{line}')
        if 'under' in s:
            return odds_map.get(f'CORNERS_UNDER_{line}')
        return None

    # ── Cards ─────────────────────────────────────────────────────────────────
    if 'card' in m or 'card' in s:
        num_match = re.search(r'([\d.]+)', s)
        if not num_match:
            return None
        line = num_match.group(1).replace('.', '_')

        if 'home' in s:
            side = 'over' if 'over' in s else 'under'
            return odds_map.get(f"HOME_CARDS_{side.upper()}_{line}")
        if 'away' in s:
            side = 'over' if 'over' in s else 'under'
            return odds_map.get(f"AWAY_CARDS_{side.upper()}_{line}")

        if 'over' in s:
            return (odds_map.get(f'MATCH_CARDS_OVER_{line}')
                    or odds_map.get(f'CARDS_OVER_{line}'))
        if 'under' in s:
            return (odds_map.get(f'MATCH_CARDS_UNDER_{line}')
                    or odds_map.get(f'CARDS_UNDER_{line}'))
        return None

    # ── 1X2 ───────────────────────────────────────────────────────────────────
    if 'home win' in s or (h and h in s and 'win' in s):
        return odds_map.get('HOME_WIN')
    if 'away win' in s or (a and a in s and 'win' in s):
        return odds_map.get('AWAY_WIN')
    if s == 'draw' or ('draw' in s and 'double' not in s and 'no' not in s):
        return odds_map.get('DRAW')

    # ── Over/Under totals (goals) ─────────────────────────────────────────────
    ov_match = re.search(r'over\s+([\d.]+)', s)
    un_match = re.search(r'under\s+([\d.]+)', s)
    if ov_match:
        line = ov_match.group(1).replace('.', '_')
        return odds_map.get(f'FT_OVER_{line}')
    if un_match:
        line = un_match.group(1).replace('.', '_')
        return odds_map.get(f'FT_UNDER_{line}')

    # ── BTTS ─────────────────────────────────────────────────────────────────
    if 'btts' in s or 'both teams' in s:
        if 'no' in s:
            return odds_map.get('BTTS_NO')
        return odds_map.get('BTTS_YES')

    # ── Double Chance ─────────────────────────────────────────────────────────
    if 'dc' in m or 'double chance' in m or 'double chance' in s:
        if 'home' in s and 'draw' in s:
            return odds_map.get('DC_HOME_DRAW')
        if 'home' in s and 'away' in s:
            return odds_map.get('DC_HOME_AWAY')
        if 'draw' in s and 'away' in s:
            return odds_map.get('DC_DRAW_AWAY')
    # home or draw / draw or away patterns
    if ('home' in s and 'draw' in s) or s in ('home or draw', 'draw or home'):
        return odds_map.get('DOUBLE_CHANCE_1X') or odds_map.get('DC_HOME_DRAW')
    if ('draw' in s and 'away' in s) or s in ('draw or away', 'away or draw'):
        return odds_map.get('DOUBLE_CHANCE_X2') or odds_map.get('DC_DRAW_AWAY')
    if ('home' in s and 'away' in s) or s in ('home or away', 'away or home'):
        return odds_map.get('DOUBLE_CHANCE_12') or odds_map.get('DC_HOME_AWAY')

    return None


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
