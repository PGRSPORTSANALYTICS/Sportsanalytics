"""
Prop Learning Model
====================
Learns from historical prop results to estimate real win rates.
Replaces the flat devig factor with data-driven probability estimates.

Updated automatically each cycle from settled results in the DB.
"""

import logging
from typing import Dict, Optional, Tuple
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Fallback rates when not enough data (min 30 settled required)
# Based on observed global patterns: Under beats Over, low odds = higher HR
FALLBACK_RATES: Dict[str, float] = {
    "player_points|Over|low":    0.48,
    "player_points|Over|mid":    0.37,
    "player_points|Over|high":   0.27,
    "player_points|Under|low":   0.77,
    "player_points|Under|mid":   0.58,
    "player_points|Under|high":  0.53,
    "player_rebounds|Over|low":  0.59,
    "player_rebounds|Over|mid":  0.42,
    "player_rebounds|Over|high": 0.36,
    "player_rebounds|Under|low": 0.66,
    "player_rebounds|Under|mid": 0.50,
    "player_rebounds|Under|high":0.44,
    "player_assists|Over|low":   0.58,
    "player_assists|Over|mid":   0.38,
    "player_assists|Over|high":  0.29,
    "player_assists|Under|low":  0.72,
    "player_assists|Under|mid":  0.52,
    "player_assists|Under|high": 0.44,
    "player_points_rebounds_assists|Over|low":   0.51,
    "player_points_rebounds_assists|Over|mid":   0.42,
    "player_points_rebounds_assists|Over|high":  0.35,
    "player_points_rebounds_assists|Under|low":  0.66,
    "player_points_rebounds_assists|Under|mid":  0.57,
    "player_points_rebounds_assists|Under|high": 0.52,
}

MIN_SAMPLES = 30
_cache: Dict[str, float] = {}
_cache_loaded = False


def _odds_tier(odds: float) -> str:
    if odds < 1.82:
        return "low"
    elif odds < 1.95:
        return "mid"
    else:
        return "high"


def load_learned_rates() -> Dict[str, float]:
    """Load win rates from DB, fall back to constants if not enough data."""
    global _cache, _cache_loaded
    rates = dict(FALLBACK_RATES)

    try:
        with DatabaseConnection.get_cursor() as cur:
            cur.execute("""
                SELECT market, selection,
                    CASE
                        WHEN odds < 1.80 THEN 'low'
                        WHEN odds < 1.95 THEN 'mid'
                        ELSE 'high'
                    END as odds_tier,
                    COUNT(*) FILTER (WHERE outcome IN ('won','lost')) as settled,
                    COUNT(*) FILTER (WHERE outcome='won') as wins
                FROM player_props
                WHERE outcome IN ('won','lost') AND sport='basketball'
                GROUP BY 1,2,3
                HAVING COUNT(*) FILTER (WHERE outcome IN ('won','lost')) >= %s
            """, (MIN_SAMPLES,))

            rows = cur.fetchall()
            learned_count = 0
            for row in rows:
                market, selection, tier, settled, wins = row
                key = f"{market}|{selection}|{tier}"
                learned_rate = wins / settled
                # Blend with fallback 80/20 (trust data more as sample grows)
                blend = min(settled / 200, 0.9)
                fallback = rates.get(key, 0.50)
                blended = blend * learned_rate + (1 - blend) * fallback
                rates[key] = round(blended, 4)
                learned_count += 1

            logger.info(f"PropLearnedModel: loaded {learned_count} learned rates from {sum(r[3] for r in rows)} settled bets")

    except Exception as e:
        logger.warning(f"PropLearnedModel: DB read failed, using fallbacks ({e})")

    _cache = rates
    _cache_loaded = True
    return rates


def get_model_prob(market: str, selection: str, odds: float) -> float:
    """
    Return data-driven win probability for this market/selection/odds combo.
    Falls back to implied_prob * 1.02 (near-neutral) if market unknown.
    """
    global _cache, _cache_loaded
    if not _cache_loaded:
        load_learned_rates()

    tier = _odds_tier(odds)
    key = f"{market}|{selection}|{tier}"

    if key in _cache:
        return _cache[key]

    # Unknown market/selection: neutral estimate slightly above implied
    implied = 1.0 / odds if odds > 0 else 0.50
    return min(implied * 1.02, 0.90)


def get_model_summary() -> list:
    """Returns sorted summary for dashboard display."""
    if not _cache_loaded:
        load_learned_rates()

    rows = []
    for key, rate in _cache.items():
        parts = key.split("|")
        if len(parts) == 3:
            market, selection, tier = parts
            implied_at_mid = {"low": 1.75, "mid": 1.87, "high": 2.05}
            ref_odds = implied_at_mid.get(tier, 2.0)
            ev = (rate * ref_odds - 1) * 100
            rows.append({
                "market": market.replace("player_", ""),
                "selection": selection,
                "odds_tier": tier,
                "hit_rate": rate,
                "est_ev": round(ev, 1),
            })

    rows.sort(key=lambda x: x["hit_rate"], reverse=True)
    return rows


def reload():
    """Force reload from DB (call after new results come in)."""
    global _cache_loaded
    _cache_loaded = False
    return load_learned_rates()
