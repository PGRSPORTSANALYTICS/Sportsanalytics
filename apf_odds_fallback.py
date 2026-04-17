"""
APF ODDS FALLBACK
=================
Supplements missing markets from The Odds API with odds from API-Football.

The Odds API excels at 1X2/Totals/Spreads for major leagues but has poor
coverage of BTTS, Asian Handicap, Corners, and Cards for lower leagues.
API-Football (Ultra plan, 75k/day) covers 64+ markets across all leagues.

Usage:
    from apf_odds_fallback import get_apf_odds_supplement

    odds_dict = champion.get_odds_for_match(match) or {}
    if not _has_full_coverage(odds_dict):
        extra = get_apf_odds_supplement(home_team, away_team, commence_time)
        for k, v in extra.items():
            if k not in odds_dict:           # never override The Odds API
                odds_dict[k] = v

Budget impact:
    - get_fixture_by_teams_and_date: cached 24h (1 API call per new fixture)
    - get_fixture_odds: 20-min TTL cache (shared with CLV service)
    - In-memory skip-set: avoids repeated lookups for fixtures with no APF data
"""
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Markets we expect from The Odds API — if ALL are present, skip APF lookup
_CORE_MARKETS = {"HOME_WIN", "DRAW", "AWAY_WIN"}
_EXTENDED_MARKETS = {"BTTS_YES", "FT_OVER_2_5", "FT_UNDER_2_5"}

# In-memory cache: (home, away, date) → odds_dict  (30-min TTL)
_cache: Dict[str, tuple] = {}   # key → (timestamp, odds_dict | None)
_CACHE_TTL = 1800               # 30 minutes

# Fixtures known to have no APF odds data — skip re-lookup for the session
_no_data_set: set = set()


def _cache_key(home: str, away: str, date: str) -> str:
    return f"{home}|{away}|{date}"


def _is_fresh(ts: float) -> bool:
    return (time.time() - ts) < _CACHE_TTL


def _has_apf_worth_fetching(odds_dict: dict) -> bool:
    """Return True if The Odds API is missing markets we want from APF."""
    missing = _EXTENDED_MARKETS - set(odds_dict.keys())
    return len(missing) > 0


# ── APF client (lazy singleton) ───────────────────────────────────────────────
_apf_client = None

def _get_apf_client():
    global _apf_client
    if _apf_client is None:
        try:
            from api_football_client import APIFootballClient
            _apf_client = APIFootballClient()
        except Exception as exc:
            logger.debug("apf_fallback: APIFootballClient unavailable: %s", exc)
    return _apf_client


# ── Public API ────────────────────────────────────────────────────────────────

def get_apf_odds_supplement(
    home_team: str,
    away_team: str,
    commence_time: str,     # ISO-8601 string from The Odds API
    odds_dict: Optional[dict] = None
) -> Dict[str, float]:
    """
    Fetch API-Football odds for markets missing from The Odds API.

    Returns a dict of {market_key: best_odds} for markets NOT already in
    odds_dict.  Returns {} on any error so the engine never crashes.

    Caching:
      - 30-min in-memory cache per (home, away, date) to avoid repeated calls
        within one engine cycle.
      - Delegates to API-Football's own 20-min odds cache via get_fixture_odds.
    """
    if odds_dict and not _has_apf_worth_fetching(odds_dict):
        return {}

    # Extract date part for cache key
    date_str = (commence_time or '')[:10]          # "2026-04-18"
    ck = _cache_key(home_team, away_team, date_str)

    if ck in _no_data_set:
        return {}

    # In-memory hit
    if ck in _cache:
        ts, cached_odds = _cache[ck]
        if _is_fresh(ts):
            return _filter_missing(cached_odds or {}, odds_dict)
        del _cache[ck]

    apf = _get_apf_client()
    if not apf:
        return {}

    try:
        # Step 1: resolve fixture_id (24h cached)
        fixture = apf.get_fixture_by_teams_and_date(
            home_team, away_team, commence_time or date_str
        )
        if not fixture:
            logger.debug("apf_fallback: no fixture for %s vs %s on %s",
                         home_team, away_team, date_str)
            _no_data_set.add(ck)
            _cache[ck] = (time.time(), None)
            return {}

        fixture_id = fixture.get('fixture', {}).get('id')
        if not fixture_id:
            _no_data_set.add(ck)
            return {}

        # Step 2: fetch odds (20-min APF cache)
        odds_data = apf.get_fixture_odds(fixture_id)
        markets = odds_data.get('markets', {}) if odds_data else {}

        if not markets:
            logger.debug("apf_fallback: empty odds for fixture_id=%s (%s vs %s)",
                         fixture_id, home_team, away_team)
            _no_data_set.add(ck)
            _cache[ck] = (time.time(), None)
            return {}

        # Normalize keys: DC and DNB rename
        normalized = _normalize_markets(markets)

        logger.info(
            "apf_fallback: %s vs %s → %d markets from API-Football (fixture=%s)",
            home_team, away_team, len(normalized), fixture_id
        )
        _cache[ck] = (time.time(), normalized)
        return _filter_missing(normalized, odds_dict)

    except Exception as exc:
        logger.debug("apf_fallback: error for %s vs %s: %s", home_team, away_team, exc)
        return {}


def _filter_missing(apf_odds: dict, existing: Optional[dict]) -> dict:
    """Return only markets not present in existing odds_dict."""
    if not existing:
        return apf_odds
    return {k: v for k, v in apf_odds.items() if k not in existing}


def _normalize_markets(markets: dict) -> dict:
    """
    Rename API-Football market keys to match value_singles_engine conventions.
    API-Football _parse_odds_response already produces most correct keys.
    We only rename the few that differ.
    """
    renames = {
        "DOUBLE_CHANCE_1X": "DC_HOME_DRAW",
        "DOUBLE_CHANCE_X2": "DC_DRAW_AWAY",
        "DOUBLE_CHANCE_12": "DC_HOME_AWAY",
        "HOME_DNB": "DNB_HOME",
        "AWAY_DNB": "DNB_AWAY",
    }
    result = {}
    for k, v in markets.items():
        result[renames.get(k, k)] = v
    return result


def clear_session_cache() -> None:
    """Call at start of each engine cycle to avoid stale data."""
    global _no_data_set
    _cache.clear()
    _no_data_set = set()
    logger.debug("apf_fallback: session cache cleared")
