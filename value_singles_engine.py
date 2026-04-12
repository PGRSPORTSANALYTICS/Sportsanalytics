# value_singles_engine.py
# ------------------------------------------------------------
# VALUE SINGLES ENGINE
# - Builds single bets from model xG / Poisson probabilities
# - Supports multiple markets
# - Avoids duplicates vs other systems
# - Monte Carlo integration for accurate probabilities (Dec 2025)
# - Tiered trust system (L1/L2/L3) for performance tracking
# ------------------------------------------------------------

import math
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set
from bankroll_manager import get_bankroll_manager
from data_collector import get_collector
from monte_carlo_integration import run_monte_carlo, classify_trust_level, analyze_bet_with_monte_carlo
from discord_notifier import send_bet_to_discord
from datetime_utils import normalize_kickoff, to_iso_utc, now_utc
from probability_calibrator import calibrate_and_ev, log_calibration_batch
from pgr_scoring import compute_pgr_score, get_league_tier, route_candidate

try:
    from auto_promoter import get_promoter
    AUTO_PROMOTER_AVAILABLE = True
except ImportError:
    AUTO_PROMOTER_AVAILABLE = False

try:
    from learning_engine import compute_bet_confidence, get_league_scores, get_market_scores
    LEARNING_ENGINE_AVAILABLE = True
except ImportError:
    LEARNING_ENGINE_AVAILABLE = False

try:
    from live_learning_config import apply_ev_controls, is_stability_mode_active
    STABILITY_MODE = True
except ImportError:
    STABILITY_MODE = False
    def apply_ev_controls(ev): return (ev * 0.4, False, None)
    def is_stability_mode_active(): return False

MIN_COMBINED_CONFIDENCE = 0.01


# ============================================================
# NOVA v2.0 BETTING FILTERS (Dec 9, 2025)
# Retuned for higher daily volume while maintaining safety
# Goal: 5-15 Value Singles on typical match days
# ============================================================

# ============================================================
# VALUE SINGLES — THREE-LAYER ARCHITECTURE (Mar 30, 2026)
# PRO PICK / VALUE OPPORTUNITY / WATCHLIST
# Single broad scan, then route by EV / confidence / odds / pgr_score
# ============================================================

# Layer 1: PRO PICK — official bets, count toward public ROI/units/record
PRO_MIN_EV = 0.25              # 25% EV
PRO_MIN_CONFIDENCE = 0.70      # 70% model confidence
PRO_MIN_ODDS = 2.10            # Raised from 1.75 — data shows edge only at 2.10+ (Apr 2026)
PRO_MAX_ODDS = 2.30
# Minimum Expected Value (EV) for candidate generation scan (three-layer routing, Mar 30 2026)
# Candidates below 7% EV are rejected before PGR scoring.
MIN_VALUE_SINGLE_EV = 0.07  # 7% floor — candidates then scored and routed to PRO/VALUE/WATCHLIST
MAX_VALUE_SINGLES_PER_DAY = 8  # Max 8 PRO picks/day

# Layer 2: VALUE OPPORTUNITY — published in dashboard + Discord, NOT official bets
VALUE_MIN_EV = 0.12            # 12% EV
VALUE_MIN_CONFIDENCE = 0.60    # 60% model confidence
VALUE_MIN_ODDS = 2.10          # Raised from 1.60 — data shows edge only at 2.10+ (Apr 2026)
VALUE_MAX_ODDS = 4.00

# Layer 3: WATCHLIST — saved internally for model learning, never public
WATCHLIST_MIN_EV = 0.07        # 7% EV
WATCHLIST_MIN_CONFIDENCE = 0.50

# Broad scan floor — all candidates enter here, routing decides their layer
MIN_VALUE_SINGLE_ODDS = 2.10   # Raised from 1.60 — data shows edge only at 2.10+ (Apr 2026)
MAX_VALUE_SINGLE_ODDS = 2.30   # PRO upper bound (legacy compat)
MAX_LEARNING_ODDS = 4.00       # Outer scan ceiling

# Candidate scan floor — raised from 5% to 12% (Apr 2026, bleeding control)
# PRO picks still need PRO_MIN_EV (25%) via pgr_scoring routing
MIN_VALUE_SINGLE_EV = 0.12     # 12% floor — raised from 5%
MIN_VALUE_SINGLE_CONFIDENCE = PRO_MIN_CONFIDENCE

# Market-specific EV floors (conservative overrides for high-volume markets)
MARKET_SPECIFIC_MIN_EV: dict = {
    "FT_OVER_2_5": 0.14,
    "FT_OVER_3_5": 0.14,
}

MARKET_SPECIFIC_MIN_ODDS: dict = {}  # Handled by pgr_scoring module

# Learning-only markets — saved for AI training, never PRO or VALUE_OPP
LEARNING_ONLY_MARKETS = {
    "HOME_WIN",      # 36.6% hit rate, -12.5u — blocked Feb 6, 2026
    "AWAY_WIN",      # 31.6% hit rate, -10.1u — blocked Feb 6, 2026
    "DRAW",          # 12.5% hit rate, -5.0u — blocked Feb 6, 2026
    # FT_UNDER_* removed entirely Mar 24, 2026 — systematic xG calibration bias
    # AH: collecting data, not yet production-ready
    "AH_HOME_-0.5", "AH_HOME_-1.0", "AH_HOME_-1.5",
    "AH_AWAY_-0.5", "AH_AWAY_-1.0", "AH_AWAY_-1.5",
    "AH_HOME_+0.5", "AH_HOME_+1.0", "AH_HOME_+1.5",
    "AH_AWAY_+0.5", "AH_AWAY_+1.0", "AH_AWAY_+1.5",
    # ── Data collection from Apr 12, 2026 — review May 12, 2026 ──────────────
    # DNB: high Pinnacle liquidity, model has edge signal but insufficient samples
    "DNB_HOME",      # Draw No Bet Home — LEARNING from Apr 12, 2026
    "DNB_AWAY",      # Draw No Bet Away — LEARNING from Apr 12, 2026
    # 1H: first-half market, model uses Poisson split, odds from totals_h1 API
    "1H_OVER_0_5",   # 1st Half Over 0.5 Goals — LEARNING from Apr 12, 2026
    "1H_OVER_1_5",   # 1st Half Over 1.5 Goals — LEARNING from Apr 12, 2026
}

# ============================================================
# MARKET-SPECIFIC MIN_ODDS (Jan 11, 2026)
# Require higher odds for markets showing value only at longer prices
# ============================================================
MARKET_SPECIFIC_MIN_ODDS = {
    # HOME_WIN: Removed — now LEARNING_ONLY (Feb 6, 2026)
}

# Odds range for candidate generation (three-layer routing, Mar 30 2026)
# Routing tiers apply tighter filters: PRO 2.10-2.30, VALUE/WATCHLIST up to 4.00
MIN_VALUE_SINGLE_ODDS = 2.10  # Candidate floor — raised from 1.60 (Apr 2026)
MAX_VALUE_SINGLE_ODDS = 2.30  # PRO PICK upper limit (kept for save_value_singles legacy usage)
MAX_LEARNING_ODDS = 4.00      # Candidate ceiling

# Minimum model confidence for candidate generation (loose floor; routing tiers enforce stricter thresholds)
MIN_VALUE_SINGLE_CONFIDENCE = 0.50  # 50% floor — routing tiers enforce stricter per-tier minimums

# Maximum PRO PICK per day (max 5 PRO_PICK; VALUE/WATCHLIST have no hard daily cap)
MAX_VALUE_SINGLES_PER_DAY = 5  # Mar 30, 2026: aligned to PRO_PICK_MAX_PER_DAY = 5
# Tournament filter mode: relaxed thresholds for UCL/UEL
TOURNAMENT_LEAGUES = {
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league", 
    "soccer_uefa_europa_conf_league",
}
TOURNAMENT_MIN_EV = 0.015  # 1.5% EV for tournaments (less H2H data)
TOURNAMENT_MIN_CONFIDENCE = 0.50  # 50% confidence for tournaments

# Leagues blocked for Value Singles based on historical performance data (Apr 2026)
# La Liga: 36.5% hit, -13.6u | Championship: 41.3% hit, -17.3u | Serie A: 45.3% hit, -6.2u
VALUE_SINGLES_BLOCKED_LEAGUES = {
    "soccer_spain_la_liga",       # La Liga
    "soccer_england_efl_champ",   # EFL Championship
    "soccer_italy_serie_a",       # Serie A
}

# League filtering mode: False = allow ALL leagues
LEAGUE_WHITELIST_ENABLED = False  # Disable whitelist - allow all leagues

# EXPANDED league whitelist (all supported leagues - approx 30)
# Includes all leagues with reliable data and predictable outcomes
VALUE_SINGLE_LEAGUE_WHITELIST = {
    # Top 5 European Leagues
    "soccer_epl",                    # Premier League
    "soccer_spain_la_liga",          # La Liga  
    "soccer_italy_serie_a",          # Serie A
    "soccer_germany_bundesliga",     # Bundesliga
    "soccer_france_ligue_one",       # Ligue 1
    # European Cups
    "soccer_uefa_champs_league",     # Champions League
    "soccer_uefa_europa_league",     # Europa League
    "soccer_uefa_europa_conf_league", # Conference League
    # Second Tier European
    "soccer_germany_bundesliga2",    # Bundesliga 2
    "soccer_england_efl_champ",      # EFL Championship
    "soccer_spain_segunda",          # La Liga 2
    "soccer_italy_serie_b",          # Serie B
    "soccer_france_ligue_two",       # Ligue 2
    # Other Major European
    "soccer_netherlands_eredivisie", # Eredivisie
    "soccer_portugal_primeira_liga", # Primeira Liga
    "soccer_belgium_first_div",      # Belgian First Division
    "soccer_turkey_super_league",    # Turkish Super Lig
    "soccer_greece_super_league",    # Greek Super League
    "soccer_spl",                    # Scottish Premiership
    # Nordic Leagues
    "soccer_sweden_allsvenskan",     # Allsvenskan
    "soccer_norway_eliteserien",     # Eliteserien
    "soccer_denmark_superliga",      # Danish Superliga
    # Americas
    "soccer_usa_mls",                # MLS
    "soccer_brazil_serie_a",         # Brasileirao
    "soccer_argentina_primera",      # Argentina Primera
    "soccer_mexico_ligamx",          # Liga MX
    # Other
    "soccer_australia_aleague",      # A-League
    "soccer_japan_j_league",         # J-League
    "soccer_korea_kleague1",         # K-League 1
}


def poisson_pmf(lmb: float, k: int) -> float:
    return math.exp(-lmb) * (lmb ** k) / math.factorial(k)


def prob_total_over(lh: float, la: float, line: float, max_goals: int = 8) -> float:
    """
    Probability(total goals > line) using Poisson independence for home/away goals.
    line examples: 0.5, 1.5, 2.5, 3.5 ...
    """
    # Compute distribution for total goals 0..max_goals
    p_total = [0.0] * (max_goals + 1)
    for h in range(max_goals + 1):
        ph = poisson_pmf(lh, h)
        for a in range(max_goals + 1):
            pa = poisson_pmf(la, a)
            t = h + a
            if t <= max_goals:
                p_total[t] += ph * pa

    # Sum probs for t > line
    threshold = int(math.floor(line + 1e-9))  # e.g 2.5 -> 2
    return sum(p_total[t] for t in range(threshold + 1, max_goals + 1))


def prob_btts(lh: float, la: float, max_goals: int = 8) -> float:
    """P(home>=1 and away>=1)"""
    p_home_0 = poisson_pmf(lh, 0)
    p_away_0 = poisson_pmf(la, 0)
    p_both_0 = p_home_0 * p_away_0
    return 1.0 - p_home_0 - p_away_0 + p_both_0


def prob_1x2(lh: float, la: float, max_goals: int = 8) -> Tuple[float, float, float]:
    """
    Returns (P(home win), P(draw), P(away win))
    """
    p_hw = p_d = p_aw = 0.0
    for h in range(max_goals + 1):
        ph = poisson_pmf(lh, h)
        for a in range(max_goals + 1):
            pa = poisson_pmf(la, a)
            p = ph * pa
            if h > a:
                p_hw += p
            elif h == a:
                p_d += p
            else:
                p_aw += p
    return p_hw, p_d, p_aw


class ValueSinglesEngine:
    """
    Value Singles Engine - Core Prediction Product (Dec 2025)
    
    Generates AI-powered single bet recommendations across multiple markets:
    - Match Result (1X2): Home Win, Draw, Away Win
    - Goals Markets: Over/Under 0.5 to 4.5
    - BTTS: Both Teams to Score Yes/No
    - Double Chance: Home/Draw, Draw/Away
    - Corners: Over/Under various lines
    
    Uses Monte Carlo simulation for probability calculation and
    strict EV filtering (5%+ edge required).
    """

    def __init__(self, champion, ev_threshold: float = None, min_confidence: int = None):
        self.champion = champion
        # Use caller-supplied threshold; fall back to constant (raised to 12% Apr 2026)
        self.ev_threshold = ev_threshold if ev_threshold is not None else MIN_VALUE_SINGLE_EV
        self.min_confidence = 50  # Base confidence threshold (probability filter is separate)
    
    def _check_conflict_with_ev_comparison(self, home_team: str, away_team: str, market_key: str, 
                                            value_single_ev: float) -> str:
        """
        No longer needed - Exact Score product removed Dec 2025.
        Always returns 'ok' to proceed with Value Singles.
        """
        return 'ok'
    
    def _is_1x2_conflicting(self, home_team: str, away_team: str, market_key: str) -> bool:
        """
        No longer needed - Exact Score product removed Dec 2025.
        Always returns False (no conflict) to proceed with 1X2 selections.
        """
        return False

    def _calc_ev(self, p_model: float, odds: float) -> float:
        # Expected value = p*odds - 1
        return (p_model * odds) - 1.0

    def _build_single_markets(self, lh: float, la: float, use_monte_carlo: bool = True) -> Dict[str, float]:
        """
        Returns model probabilities for ALL single-bet markets.
        Uses Monte Carlo simulation for more accurate probabilities (Dec 2025).
        """
        if use_monte_carlo:
            # Run Monte Carlo simulation (10,000 iterations)
            mc = run_monte_carlo(lh, la, n_sim=10000)
            
            # Use simulation probabilities
            p_hw = mc.home_win_prob
            p_d = mc.draw_prob
            p_aw = mc.away_win_prob
            p_btts_yes = mc.btts_yes_prob
            p_over25 = mc.over_25_prob
            p_over35 = mc.over_35_prob
            
            # Derive other markets from simulation
            p_btts_no = 1 - p_btts_yes
            
            print(f"🎲 Monte Carlo: HW={p_hw:.1%} D={p_d:.1%} AW={p_aw:.1%} O2.5={p_over25:.1%} BTTS={p_btts_yes:.1%}")
        else:
            # Fall back to basic Poisson
            p_hw, p_d, p_aw = prob_1x2(lh, la)
            p_btts_yes = prob_btts(lh, la)
            p_over25 = prob_total_over(lh, la, 2.5)
            p_over35 = prob_total_over(lh, la, 3.5)
            p_btts_no = 1 - p_btts_yes
        
        # Over Goals (0.5 - 4.5) - keep Poisson for less common lines
        p_over05 = prob_total_over(lh, la, 0.5)
        p_over15 = prob_total_over(lh, la, 1.5)
        p_over45 = prob_total_over(lh, la, 4.5)
        
        # 1H Over/Under
        p_over05_1h = prob_total_over(lh * 0.45, la * 0.45, 0.5)
        
        # Double Chance
        p_home_or_draw = p_hw + p_d
        p_home_or_away = p_hw + p_aw
        p_draw_or_away = p_d + p_aw
        
        # Draw No Bet (exclude draw, normalize)
        total_no_draw = p_hw + p_aw
        p_dnb_home = p_hw / total_no_draw if total_no_draw > 0 else 0.5
        p_dnb_away = p_aw / total_no_draw if total_no_draw > 0 else 0.5
        
        # Corners (simple model: ~10-11 corners average, variance by match intensity)
        total_xg = lh + la
        corners_lambda = 10.5 + (total_xg - 2.8) * 0.5  # Higher scoring = more corners
        p_corners_over85 = prob_total_over(corners_lambda / 2, corners_lambda / 2, 8.5)
        p_corners_over95 = prob_total_over(corners_lambda / 2, corners_lambda / 2, 9.5)
        p_corners_over105 = prob_total_over(corners_lambda / 2, corners_lambda / 2, 10.5)
        p_corners_over115 = prob_total_over(corners_lambda / 2, corners_lambda / 2, 11.5)
        
        # Cards (model: ~3.5 cards average, higher in intense/derby matches)
        cards_lambda = 3.5 + (total_xg - 2.8) * 0.3  # Slightly more cards in higher-xG matches
        p_cards_over25 = prob_total_over(cards_lambda / 2, cards_lambda / 2, 2.5)
        p_cards_over35 = prob_total_over(cards_lambda / 2, cards_lambda / 2, 3.5)
        p_cards_over45 = prob_total_over(cards_lambda / 2, cards_lambda / 2, 4.5)
        p_cards_over55 = prob_total_over(cards_lambda / 2, cards_lambda / 2, 5.5)
        
        # Team Totals (individual team over/under)
        p_home_over05 = prob_total_over(lh, 0, 0.5)
        p_home_over15 = prob_total_over(lh, 0, 1.5)
        p_away_over05 = prob_total_over(0, la, 0.5)
        p_away_over15 = prob_total_over(0, la, 1.5)
        
        # Asian Handicap (from Monte Carlo simulation if available)
        if use_monte_carlo:
            from monte_carlo_simulator import simulate_match
            sim = simulate_match(lh, la, n_sim=10000)
            p_ah_home_m05 = sim.get("home_ah_-0.5", p_hw)
            p_ah_home_m10 = sim.get("home_ah_-1.0", 0.30)
            p_ah_home_m15 = sim.get("home_ah_-1.5", 0.20)
            p_ah_home_p05 = sim.get("home_ah_+0.5", p_home_or_draw)
            p_ah_home_p10 = sim.get("home_ah_+1.0", 0.80)
            p_ah_home_p15 = sim.get("home_ah_+1.5", 0.85)
            p_ah_away_m05 = sim.get("away_ah_-0.5", p_aw)
            p_ah_away_m10 = sim.get("away_ah_-1.0", 0.25)
            p_ah_away_m15 = sim.get("away_ah_-1.5", 0.15)
            p_ah_away_p05 = sim.get("away_ah_+0.5", p_draw_or_away)
            p_ah_away_p10 = sim.get("away_ah_+1.0", 0.75)
            p_ah_away_p15 = sim.get("away_ah_+1.5", 0.82)
        else:
            # Basic approximations for AH without MC
            p_ah_home_m05 = p_hw
            p_ah_home_m10 = p_hw * 0.7
            p_ah_home_m15 = p_hw * 0.5
            p_ah_home_p05 = p_home_or_draw
            p_ah_home_p10 = p_home_or_draw + p_aw * 0.3
            p_ah_home_p15 = p_home_or_draw + p_aw * 0.5
            p_ah_away_m05 = p_aw
            p_ah_away_m10 = p_aw * 0.7
            p_ah_away_m15 = p_aw * 0.5
            p_ah_away_p05 = p_draw_or_away
            p_ah_away_p10 = p_draw_or_away + p_hw * 0.3
            p_ah_away_p15 = p_draw_or_away + p_hw * 0.5

        return {
            # Over Goals (Under markets removed Mar 24, 2026 — systematic xG bias)
            "FT_OVER_0_5": p_over05,
            "FT_OVER_1_5": p_over15,
            "FT_OVER_2_5": p_over25,
            "FT_OVER_3_5": p_over35,
            "FT_OVER_4_5": p_over45,
            
            # 1H Goals
            "1H_OVER_0_5": p_over05_1h,
            
            # BTTS
            "BTTS_YES": p_btts_yes,
            "BTTS_NO": p_btts_no,
            
            # 1X2 Moneyline
            "HOME_WIN": p_hw,
            "DRAW": p_d,
            "AWAY_WIN": p_aw,
            
            # Double Chance
            "DC_HOME_DRAW": p_home_or_draw,
            "DC_HOME_AWAY": p_home_or_away,
            "DC_DRAW_AWAY": p_draw_or_away,
            
            # Draw No Bet
            "DNB_HOME": p_dnb_home,
            "DNB_AWAY": p_dnb_away,
            
            # Corners
            "CORNERS_OVER_8_5": p_corners_over85,
            "CORNERS_OVER_9_5": p_corners_over95,
            "CORNERS_OVER_10_5": p_corners_over105,
            "CORNERS_OVER_11_5": p_corners_over115,
            
            # Cards
            "CARDS_OVER_2_5": p_cards_over25,
            "CARDS_OVER_3_5": p_cards_over35,
            "CARDS_OVER_4_5": p_cards_over45,
            "CARDS_OVER_5_5": p_cards_over55,
            
            # Team Totals
            "HOME_OVER_0_5": p_home_over05,
            "HOME_OVER_1_5": p_home_over15,
            "AWAY_OVER_0_5": p_away_over05,
            "AWAY_OVER_1_5": p_away_over15,
            
            # Asian Handicap - Home
            "AH_HOME_-0.5": p_ah_home_m05,
            "AH_HOME_-1.0": p_ah_home_m10,
            "AH_HOME_-1.5": p_ah_home_m15,
            "AH_HOME_+0.5": p_ah_home_p05,
            "AH_HOME_+1.0": p_ah_home_p10,
            "AH_HOME_+1.5": p_ah_home_p15,
            
            # Asian Handicap - Away
            "AH_AWAY_-0.5": p_ah_away_m05,
            "AH_AWAY_-1.0": p_ah_away_m10,
            "AH_AWAY_-1.5": p_ah_away_m15,
            "AH_AWAY_+0.5": p_ah_away_p05,
            "AH_AWAY_+1.0": p_ah_away_p10,
            "AH_AWAY_+1.5": p_ah_away_p15,
        }

    def generate_value_singles(
        self,
        avoid_match_ids: Optional[Set[str]] = None,
        max_picks: int = 8,
        league_filter: Optional[Set[str]] = None,
        exclude_leagues: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        avoid_match_ids = avoid_match_ids or set()
        picks: List[Dict[str, Any]] = []
        data_picks: List[Dict[str, Any]] = []  # VALUE_OPP + WATCHLIST candidates

        try:
            from pgr_scoring import (
                compute_pgr_score, route_candidate, get_league_tier,
                PRO_PICK_MAX_PER_DAY,
            )
            PGR_SCORING_AVAILABLE = True
        except ImportError:
            PGR_SCORING_AVAILABLE = False
            PRO_PICK_MAX_PER_DAY = MAX_VALUE_SINGLES_PER_DAY  # fallback

        rejection_counts: dict = {}
        _candidates_evaluated = 0  # Total market evaluations (before any filter)

        # Unified rejection helper — logs candidate identity + reason for every reject path.
        def _reject(reason: str, home: str = "", away: str = "", market: str = "",
                    ev: float = 0.0, odds: float = 0.0) -> None:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            if home and away:
                print(f"   ❌ [{reason}]: {home} vs {away} | {market} odds={odds:.2f} ev={ev:.1%}")

        print("🔥 THREE-LAYER SIGNAL ROUTING START")
        print(f"   candidate floor: EV≥{MIN_VALUE_SINGLE_EV*100:.0f}% | odds {MIN_VALUE_SINGLE_ODDS}-{MAX_LEARNING_ODDS}")
        print(f"   PRO PICK: EV≥25%, Conf≥70%, Odds 1.75-2.30, Tier A/B, max {PRO_PICK_MAX_PER_DAY if PGR_SCORING_AVAILABLE else MAX_VALUE_SINGLES_PER_DAY}/day")
        print(f"   VALUE OPP: EV≥12%, Conf≥60%, Odds 1.60-4.00")
        print(f"   WATCHLIST: EV 7-12%, Conf≥50% (DB only, not public)")
        print(f"   leagues = {len(VALUE_SINGLE_LEAGUE_WHITELIST)} whitelisted")

        # ── Query DB for today's existing PRO PICK count (day-scope cap enforcement) ──
        pro_picks_in_db = 0
        try:
            if hasattr(self.champion, 'get_todays_count'):
                pro_picks_in_db = self.champion.get_todays_count() or 0
                print(f"   DB: {pro_picks_in_db} existing PRO PICKs today")
        except Exception as _e:
            print(f"   ⚠️ Could not fetch today's PRO count from DB: {_e}")

        # raw_candidates: all signals that pass hard pre-routing filters (PGR scored, not yet routed)
        raw_candidates: List[Dict[str, Any]] = []

        # 1) Get fixtures
        if not hasattr(self.champion, "get_todays_fixtures"):
            print("⚠️ ValueSinglesEngine: champion.get_todays_fixtures() missing")
            return picks

        fixtures = self.champion.get_todays_fixtures()
        if not fixtures:
            print("⚠️ ValueSinglesEngine: No fixtures today")
            return picks

        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone.utc).date()
        max_lookahead_days = 3  # Generate picks for today + next 2 days
        max_date = today + timedelta(days=max_lookahead_days)
        
        for match in fixtures:
            match_id = match.get("match_id") or match.get("id") or f"{match.get('home_team')}_vs_{match.get('away_team')}"
            if match_id in avoid_match_ids:
                continue

            home_team = match.get("home_team")
            away_team = match.get("away_team")
            if not home_team or not away_team:
                continue
            
            # LOOKAHEAD FILTER: Generate predictions for matches in the next few days
            commence_time = match.get('commence_time', '')
            match_date = match.get('formatted_date') or match.get('match_date')
            
            if not match_date and commence_time:
                try:
                    dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                    match_date = dt.strftime("%Y-%m-%d")
                except:
                    match_date = commence_time[:10] if len(commence_time) > 10 else ""
            
            # Check if match is within our lookahead window
            if match_date:
                try:
                    match_dt = datetime.strptime(match_date, "%Y-%m-%d").date()
                    if match_dt > max_date:
                        continue  # Too far in the future, skip silently
                except:
                    pass  # Couldn't parse, allow it through
            
            league_key = match.get('sport_key') or match.get('league_key') or match.get('odds_api_key') or ''
            is_tournament = league_key in TOURNAMENT_LEAGUES

            if league_filter and league_key not in league_filter:
                continue
            if exclude_leagues and league_key in exclude_leagues:
                continue

            # Per-match cooldown: skip matches already scanned within the last 30 min.
            # IMPORTANT: cooldown check happens AFTER league filter so that the euro
            # engine never marks summer-league matches (e.g. Allsvenskan) as scanned —
            # each engine manages its own cooldown scope via league_filter/exclude_leagues.
            # Build a date-scoped cooldown key to avoid conflating different-day fixtures.
            _ck_date = (match.get('formatted_date') or match.get('match_date') or
                        (match.get('commence_time', '')[:10] if match.get('commence_time') else ''))
            cooldown_key = f"vs_{home_team}_{away_team}_{_ck_date}".replace(' ', '_')
            try:
                from combined_sports_runner import is_match_on_cooldown, mark_match_scanned
                if is_match_on_cooldown(cooldown_key):
                    continue  # Silently skip — will pick up next cycle
                mark_match_scanned(cooldown_key)  # Record attempt before odds/API calls
            except ImportError:
                pass  # Runner not loaded (standalone/test run) — skip cooldown guard

            if LEAGUE_WHITELIST_ENABLED and league_key and league_key not in VALUE_SINGLE_LEAGUE_WHITELIST:
                print(f"⏭️ Skipping {home_team} vs {away_team} - league '{league_key}' not in whitelist")
                continue

            if league_key in VALUE_SINGLES_BLOCKED_LEAGUES:
                print(f"🚫 Blocked: {home_team} vs {away_team} - '{league_key}' blocked for Value Singles (poor historical ROI)")
                continue
            
            # Dynamic thresholds for tournament matches (less H2H data available)
            match_ev_threshold = TOURNAMENT_MIN_EV if is_tournament else MIN_VALUE_SINGLE_EV
            match_confidence_threshold = TOURNAMENT_MIN_CONFIDENCE if is_tournament else MIN_VALUE_SINGLE_CONFIDENCE
            if is_tournament:
                print(f"🏆 Tournament match: {home_team} vs {away_team} - using relaxed thresholds (EV: {match_ev_threshold:.1%}, Conf: {match_confidence_threshold:.0%})")

            # 2) Odds
            if not hasattr(self.champion, "get_odds_for_match"):
                continue
            odds_dict = self.champion.get_odds_for_match(match) or {}
            if not odds_dict:
                continue
            
            print("🧾 Odds keys found:", list(odds_dict.keys()))

            # 3) Real team form analysis pipeline (same as exact score system)
            lh = 1.5  # Default xG values
            la = 1.3
            home_form = None
            away_form = None
            
            try:
                # Get team IDs (may be None for OddsAPI team names)
                home_id = self.champion.get_team_id_by_name(home_team) if hasattr(self.champion, "get_team_id_by_name") else None
                away_id = self.champion.get_team_id_by_name(away_team) if hasattr(self.champion, "get_team_id_by_name") else None
                
                # Analyze team form (venue-specific) - even without IDs, try scraper fallback
                if hasattr(self.champion, "analyze_team_form"):
                    home_form = self.champion.analyze_team_form(home_team, home_id)
                    away_form = self.champion.analyze_team_form(away_team, away_id)
                    
                    # Get H2H data
                    h2h = self.champion.get_head_to_head(home_team, away_team) if hasattr(self.champion, "get_head_to_head") else None
                    
                    # Calculate xG using champion's method
                    if home_form and away_form and hasattr(self.champion, "calculate_xg_edge"):
                        xg = self.champion.calculate_xg_edge(home_form, away_form, h2h)
                        lh = float(xg.get("home_xg", 1.5))
                        la = float(xg.get("away_xg", 1.3))
                        print(f"⚽ Real xG: {home_team} {lh:.2f} vs {away_team} {la:.2f}")
                    else:
                        print(f"⚠️ Using default xG for {home_team} vs {away_team} (form data incomplete)")
                else:
                    print(f"⚠️ Using default xG for {home_team} vs {away_team} (no form analysis available)")
                
            except Exception as e:
                print(f"⚠️ Team analysis error for {home_team} vs {away_team}: {e}, using default xG")

            probs = self._build_single_markets(lh, la)

            # 4) Evaluate each market
            for market_key, p_model in probs.items():
                bookmaker_data = {}  # Reset per market to avoid stale data leaking between markets
                odds = odds_dict.get(market_key)
                _candidates_evaluated += 1  # Count every market evaluation before any filter
                if odds is None:
                    _reject("rejected_no_odds", home_team, away_team, market_key, 0.0, 0.0)
                    continue
                
                # ODDS FILTER: Allow bets in candidate range (1.60–4.00)
                if not (MIN_VALUE_SINGLE_ODDS <= odds <= MAX_LEARNING_ODDS):
                    _rr = "rejected_low_odds" if odds < MIN_VALUE_SINGLE_ODDS else "rejected_high_odds"
                    _reject(_rr, home_team, away_team, market_key, 0.0, float(odds))
                    continue
                
                # MARKET-SPECIFIC MIN_ODDS FILTER (Jan 11, 2026)
                # Some markets only profitable at longer odds
                market_min_odds = MARKET_SPECIFIC_MIN_ODDS.get(market_key)
                if market_min_odds and odds < market_min_odds:
                    _reject("rejected_low_odds", home_team, away_team, market_key, 0.0, float(odds))
                    continue
                
                # CONFIDENCE FLOOR: Skip below candidate minimum (50%)
                if p_model < MIN_VALUE_SINGLE_CONFIDENCE:
                    _reject("rejected_low_confidence", home_team, away_team, market_key, 0.0, float(odds))
                    continue

                # Check for conflict with exact score prediction (1X2 markets only)
                if market_key in ("HOME_WIN", "AWAY_WIN", "DRAW"):
                    if self._is_1x2_conflicting(home_team, away_team, market_key):
                        _reject("rejected_1x2_conflict", home_team, away_team, market_key, 0.0, float(odds))
                        continue

                cal_data = calibrate_and_ev(p_model, odds)
                raw_prob = cal_data['raw_prob']
                calibrated_prob = cal_data['calibrated_prob']
                raw_ev = cal_data['raw_ev']
                ev_after_cal = cal_data['calibrated_ev']
                prob_shift = cal_data['prob_shift']

                if abs(prob_shift) > 3:
                    print(f"   📐 CAL: {market_key} p={raw_prob:.3f}→{calibrated_prob:.3f} (shift {prob_shift:+.1f}pp) ev={raw_ev:.3f}→{ev_after_cal:.3f}")

                adj_ev, is_blocked, block_reason = apply_ev_controls(ev_after_cal)
                if is_blocked:
                    print(f"   🚫 BLOCKED: {market_key} cal_ev={ev_after_cal:.1%} - {block_reason}")
                    _reject("rejected_ev_controls", home_team, away_team, market_key, float(ev_after_cal), float(odds))
                    continue
                
                # ── Three-layer routing ──────────────────────────────────────────────
                ev = adj_ev

                # Candidate EV floor (12% minimum, Apr 2026)
                if ev < self.ev_threshold:
                    _reject("rejected_low_ev", home_team, away_team, market_key, float(ev), float(odds))
                    continue

                # ── PGR SCORE (Pass 1: compute only, no routing decision yet) ──────
                _league_key_for_routing = match.get('sport_key') or match.get('league_key') or match.get('odds_api_key') or ''
                if PGR_SCORING_AVAILABLE:
                    pgr_score = compute_pgr_score(
                        ev=ev,
                        confidence=calibrated_prob,
                        market_key=market_key,
                        league_key=_league_key_for_routing,
                    )
                    _league_tier = get_league_tier(_league_key_for_routing)
                else:
                    pgr_score = ev * 100 + calibrated_prob * 20
                    _league_tier = "B"

                # ── Collect bookmaker data ────────────────────────────────────────
                bookmaker_data = {}
                _mbb = match.get('markets_by_bookmaker', {})
                if market_key in _mbb and _mbb[market_key]:
                    _bk = _mbb[market_key]
                    _vals = [v for v in _bk.values() if v > 0]
                    if _vals:
                        bookmaker_data = {
                            'odds_by_bookmaker': _bk,
                            'best_odds_value': max(_vals),
                            'best_odds_bookmaker': max(_bk, key=lambda k: _bk[k]),
                            'avg_odds': round(sum(_vals) / len(_vals), 3),
                        }
                if not bookmaker_data and hasattr(self.champion, 'collect_bookmaker_odds'):
                    _api_mkt = 'h2h' if market_key in ('HOME_WIN', 'AWAY_WIN', 'DRAW') else \
                               'totals' if 'OVER' in market_key else None
                    _pt = None
                    if _api_mkt == 'totals':
                        _parts = market_key.split('_')
                        try: _pt = float(f"{_parts[-2]}.{_parts[-1]}")
                        except: _pt = 2.5
                    if _api_mkt:
                        try:
                            bookmaker_data = self.champion.collect_bookmaker_odds(
                                match, market_key.replace("_", " ").title(), _api_mkt, _pt)
                        except Exception:
                            bookmaker_data = {}

                _ko_utc, _ko_epoch = normalize_kickoff(commence_time)
                _league_display = match.get("league_name") or match.get("league") or match.get("sport_title") or "Unknown"

                # ── Check learning-only / auto-promoter status (pre-routing) ──────
                _lk = _league_key_for_routing or _league_display
                is_learning_only = market_key in LEARNING_ONLY_MARKETS
                if AUTO_PROMOTER_AVAILABLE:
                    promoter = get_promoter()
                    if promoter.has_explicit_status('football', _lk, market_key):
                        dynamic_status = promoter.get_market_status('football', _lk, market_key)
                        if dynamic_status == 'DISABLED':
                            _reject("rejected_market_type", home_team, away_team, market_key, float(ev), float(odds))
                            continue
                        elif dynamic_status == 'PRODUCTION':
                            is_learning_only = False
                        elif dynamic_status == 'LEARNING_ONLY':
                            is_learning_only = True

                if is_learning_only:
                    _reject("rejected_market_type", home_team, away_team, market_key, float(ev), float(odds))
                    continue

                if LEARNING_ENGINE_AVAILABLE:
                    combined_conf = compute_bet_confidence(ev, _lk, market_key, 'football')
                    if combined_conf < MIN_COMBINED_CONFIDENCE:
                        _reject("rejected_low_confidence", home_team, away_team, market_key, float(ev), float(odds))
                        continue

                # ── Extract selection text and kickoff ───────────────────────────
                _sel_map = {
                    "FT_OVER_0_5": "Over 0.5 Goals", "FT_OVER_1_5": "Over 1.5 Goals",
                    "FT_OVER_2_5": "Over 2.5 Goals", "FT_OVER_3_5": "Over 3.5 Goals",
                    "FT_OVER_4_5": "Over 4.5 Goals", "BTTS_YES": "BTTS Yes", "BTTS_NO": "BTTS No",
                    "HOME_WIN": "Home Win", "AWAY_WIN": "Away Win", "DRAW": "Draw",
                    "DOUBLE_CHANCE_1X": "Double Chance 1X", "DOUBLE_CHANCE_X2": "Double Chance X2",
                    "DOUBLE_CHANCE_12": "Double Chance 12", "1H_OVER_0_5": "1H Over 0.5 Goals",
                    "1H_OVER_1_5": "1H Over 1.5 Goals",
                    "DC_HOME_DRAW": "Home or Draw", "DC_HOME_AWAY": "Home or Away",
                    "DC_DRAW_AWAY": "Draw or Away", "DNB_HOME": "Draw No Bet - Home",
                    "DNB_AWAY": "Draw No Bet - Away",
                    "CORNERS_OVER_8_5": "Corners Over 8.5", "CORNERS_OVER_9_5": "Corners Over 9.5",
                    "CORNERS_OVER_10_5": "Corners Over 10.5", "CORNERS_OVER_11_5": "Corners Over 11.5",
                    "CARDS_OVER_2_5": "Cards Over 2.5", "CARDS_OVER_3_5": "Cards Over 3.5",
                    "CARDS_OVER_4_5": "Cards Over 4.5", "CARDS_OVER_5_5": "Cards Over 5.5",
                    "HOME_OVER_0_5": f"{home_team} Over 0.5 Goals",
                    "HOME_OVER_1_5": f"{home_team} Over 1.5 Goals",
                    "AWAY_OVER_0_5": f"{away_team} Over 0.5 Goals",
                    "AWAY_OVER_1_5": f"{away_team} Over 1.5 Goals",
                    "AH_HOME_-0.5": f"{home_team} -0.5 (AH)", "AH_HOME_-1.0": f"{home_team} -1.0 (AH)",
                    "AH_HOME_-1.5": f"{home_team} -1.5 (AH)", "AH_HOME_+0.5": f"{home_team} +0.5 (AH)",
                    "AH_HOME_+1.0": f"{home_team} +1.0 (AH)", "AH_HOME_+1.5": f"{home_team} +1.5 (AH)",
                    "AH_AWAY_-0.5": f"{away_team} -0.5 (AH)", "AH_AWAY_-1.0": f"{away_team} -1.0 (AH)",
                    "AH_AWAY_-1.5": f"{away_team} -1.5 (AH)", "AH_AWAY_+0.5": f"{away_team} +0.5 (AH)",
                    "AH_AWAY_+1.0": f"{away_team} +1.0 (AH)", "AH_AWAY_+1.5": f"{away_team} +1.5 (AH)",
                }
                selection_text = _sel_map.get(market_key, market_key.replace("_", " ").title())

                kickoff_time = match.get('formatted_time') or match.get('kickoff_time')
                if not match_date and commence_time:
                    from datetime import datetime as _dt
                    try:
                        _d = _dt.fromisoformat(commence_time.replace('Z', '+00:00'))
                        match_date = _d.strftime("%Y-%m-%d")
                        kickoff_time = _d.strftime("%H:%M")
                    except Exception:
                        match_date = commence_time[:10] if len(commence_time) > 10 else ""
                        kickoff_time = commence_time[11:16] if len(commence_time) > 16 else ""

                sim_prob = calibrated_prob
                ev_sim = ev
                disagreement = abs(raw_prob - calibrated_prob)
                sim_approved = ev_sim >= 0.03
                trust_level = classify_trust_level(
                    ev_sim=ev_sim, ev_model=ev, confidence=sim_prob,
                    disagreement=disagreement, sim_approved=sim_approved, odds=odds
                )
                fair_odds = round(1.0 / p_model, 3) if p_model > 0 else None
                confidence = int(min(100, max(0, calibrated_prob * 100)))

                # ── Store as raw candidate (routing deferred to pass 2) ───────────
                raw_candidates.append({
                    # identity
                    "match_id": match_id,
                    "home_team": match.get("home_team"),
                    "away_team": match.get("away_team"),
                    "league": _league_display,
                    "market_key": market_key,
                    "selection": selection_text,
                    # probabilities & EV
                    "ev": float(ev),
                    "raw_prob": float(raw_prob),
                    "calibrated_prob": float(calibrated_prob),
                    "raw_ev": float(raw_ev),
                    "prob_shift": float(prob_shift),
                    "confidence": confidence,
                    # PGR scoring
                    "pgr_score": float(pgr_score),
                    "league_tier": _league_tier,
                    "league_key": _lk,
                    # odds
                    "odds": float(odds),
                    "fair_odds": fair_odds,
                    "bookmaker_data": bookmaker_data,
                    # match info
                    "match_date": match_date,
                    "kickoff_time": kickoff_time,
                    "kickoff_utc": _ko_utc,
                    "kickoff_epoch": _ko_epoch,
                    "quality_score": float(match.get("quality_score", 50)),
                    "fixture_id": match.get("fixture_id"),
                    "lh": float(lh),
                    "la": float(la),
                    # trust / sim
                    "trust_level": trust_level,
                    "sim_prob": float(sim_prob),
                    "ev_sim": float(ev_sim),
                    "disagreement": float(disagreement),
                    "is_learning_only": is_learning_only,
                    "_home_form": home_form,
                    "_away_form": away_form,
                })
                print(f"   📦 CANDIDATE: {market_key} EV={ev:.1%} Conf={calibrated_prob:.0%} Odds={float(odds):.2f} PGR={pgr_score:.1f} Tier={_league_tier}")

        # ════════════════════════════════════════════════════════════════════
        # PASS 2: Sort all raw candidates by PGR score (desc), then route
        #         deterministically using DB-sourced pro_picks_in_db counter.
        #         This ensures highest-quality candidates always get first access
        #         to the PRO PICK slots before VALUE_OPP / WATCHLIST assignment.
        # ════════════════════════════════════════════════════════════════════
        raw_candidates.sort(key=lambda c: (c["pgr_score"], c["ev"]), reverse=True)
        print(f"\n📊 PASS 2: Routing {len(raw_candidates)} candidates (sorted by PGR score)")
        print(f"   Starting pro_picks_in_db = {pro_picks_in_db}")

        _pro_cap = PRO_PICK_MAX_PER_DAY if PGR_SCORING_AVAILABLE else MAX_VALUE_SINGLES_PER_DAY
        # NOTE: pro_picks_today is NOT used during routing (daily cap is applied at selection step).
        # It's tracked here only for the telemetry summary.
        pro_picks_today = pro_picks_in_db

        for c in raw_candidates:
            ev = c["ev"]
            calibrated_prob = c["calibrated_prob"]
            raw_prob = c["raw_prob"]
            raw_ev = c["raw_ev"]
            prob_shift = c["prob_shift"]
            pgr_score = c["pgr_score"]
            _league_tier = c["league_tier"]
            odds = c["odds"]
            market_key = c["market_key"]
            _lk = c["league_key"]
            match_id = c["match_id"]
            home_team = c["home_team"]
            away_team = c["away_team"]
            bookmaker_data = c["bookmaker_data"]
            match_date = c["match_date"]
            kickoff_time = c["kickoff_time"]
            _ko_utc = c["kickoff_utc"]
            _ko_epoch = c["kickoff_epoch"]
            lh = c["lh"]
            la = c["la"]
            trust_level = c["trust_level"]
            sim_prob = c["sim_prob"]
            ev_sim = c["ev_sim"]
            disagreement = c["disagreement"]
            fair_odds = c["fair_odds"]
            confidence = c["confidence"]
            is_learning_only = c["is_learning_only"]
            selection_text = c["selection"]

            # ── Determine routing tier ────────────────────────────────────────
            # IMPORTANT: Pass pro_picks_today=0 here so routing is purely quality-based.
            # The daily cap is enforced after unique-match dedup in the selection step,
            # ensuring the best distinct matches fill available slots before overflow
            # candidates are rerouted to VALUE_OPP.
            if PGR_SCORING_AVAILABLE:
                _routing, _routing_reason = route_candidate(
                    ev=ev,
                    confidence=calibrated_prob,
                    odds=odds,
                    market_key=market_key,
                    league_key=_lk,
                    pgr_score=pgr_score,
                    pro_picks_today=0,  # Cap applied at selection step, not here
                )
            else:
                if ev >= 0.25 and calibrated_prob >= 0.70 and 1.75 <= odds <= 2.30 and pgr_score >= 55.0:
                    _routing, _routing_reason = "PRO_PICK", "routed_pro_pick"
                elif ev >= 0.12 and calibrated_prob >= 0.60 and pgr_score >= 35.0:
                    _routing, _routing_reason = "VALUE_OPP", "routed_value_opp"
                elif pgr_score >= 20.0:
                    _routing, _routing_reason = "WATCHLIST", "routed_watchlist"
                else:
                    _routing, _routing_reason = "REJECTED", "rejected_score_below_threshold"

            if _routing == "REJECTED":
                _reject(_routing_reason, home_team, away_team, market_key, float(ev), float(odds))
                continue

            print(f"   🏷️ [{_routing}] {market_key} EV={ev:.1%} Conf={calibrated_prob:.0%} Odds={odds:.2f} PGR={pgr_score:.1f} Tier={_league_tier}")

            # ── Build analysis blob shared by both tier paths ─────────────────
            _created = to_iso_utc(now_utc())

            # ── VALUE_OPP and WATCHLIST → data_picks (never official P&L) ──────
            if _routing in ("VALUE_OPP", "WATCHLIST"):
                _mode = "VALUE_OPP" if _routing == "VALUE_OPP" else "WATCHLIST"
                data_picks.append({
                    "timestamp": int(time.time()),
                    "match_id": match_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": c["league"],
                    "market": "Value Single",
                    "selection": selection_text,
                    "odds": odds,
                    "edge_percentage": float(ev * 100),
                    "confidence": confidence,
                    "analysis": json.dumps({
                        "market_key": market_key,
                        "p_model": raw_prob,
                        "calibrated_prob": calibrated_prob,
                        "ev": ev,
                        "pgr_score": pgr_score,
                        "league_tier": _league_tier,
                        "routing": _routing,
                    }),
                    "match_date": match_date,
                    "kickoff_utc": _ko_utc,
                    "kickoff_epoch": _ko_epoch,
                    "created_at_utc": _created,
                    "mode": _mode,
                    "stake": 0,
                    "bet_placed": False,
                    "odds_by_bookmaker": bookmaker_data.get('odds_by_bookmaker'),
                    "best_odds_value": bookmaker_data.get('best_odds_value'),
                    "best_odds_bookmaker": bookmaker_data.get('best_odds_bookmaker'),
                    "avg_odds": bookmaker_data.get('avg_odds'),
                    "fair_odds": fair_odds,
                    "fixture_id": c.get("fixture_id"),
                    "trust_level": _routing,
                    "sim_probability": sim_prob,
                    "ev_sim": ev_sim,
                    "model_prob": raw_prob,
                    "calibrated_prob": calibrated_prob,
                    "disagreement": disagreement,
                    "pgr_score": pgr_score,
                    "league_tier": _league_tier,
                    "routing_reason": _routing_reason,
                })
                continue

            # ── PRO PICK path ─────────────────────────────────────────────────
            # Smart conflict resolution for Over/Under goals vs Exact Score
            conflict_result = self._check_conflict_with_ev_comparison(home_team, away_team, market_key, ev)
            if conflict_result == 'skip':
                _reject("rejected_1x2_conflict", home_team, away_team, market_key, float(ev), float(odds))
                continue

            if confidence < self.min_confidence:
                _reject("rejected_low_confidence", home_team, away_team, market_key, float(ev), float(odds))
                continue

            pro_picks_today += 1

            opportunity = {
                "timestamp": int(time.time()),
                "match_id": match_id,
                "home_team": home_team,
                "away_team": away_team,
                "league": c["league"],
                "market": "Value Single",
                "selection": selection_text,
                "odds": odds,
                "edge_percentage": float(ev * 100),
                "confidence": confidence,
                "analysis": json.dumps({
                    "market_key": market_key,
                    "p_model": raw_prob,
                    "calibrated_prob": calibrated_prob,
                    "prob_shift_pp": prob_shift,
                    "ev": ev,
                    "raw_ev": raw_ev,
                    "expected_home_goals": lh,
                    "expected_away_goals": la,
                    "pgr_score": pgr_score,
                    "league_tier": _league_tier,
                    "routing": "PRO_PICK",
                }),
                "model_prob": raw_prob,
                "calibrated_prob": calibrated_prob,
                "stake": 1,
                "match_date": match_date,
                "kickoff_time": kickoff_time,
                "kickoff_utc": _ko_utc,
                "kickoff_epoch": _ko_epoch,
                "created_at_utc": _created,
                "quality_score": c["quality_score"],
                "recommended_tier": "SINGLE",
                "daily_rank": 999,
                "trust_level": trust_level,
                "sim_probability": sim_prob,
                "ev_sim": ev_sim,
                "disagreement": disagreement,
                "odds_by_bookmaker": bookmaker_data.get('odds_by_bookmaker'),
                "best_odds_value": bookmaker_data.get('best_odds_value'),
                "best_odds_bookmaker": bookmaker_data.get('best_odds_bookmaker'),
                "avg_odds": bookmaker_data.get('avg_odds'),
                "fair_odds": fair_odds,
                "fixture_id": c.get("fixture_id"),
                "is_learning_only": is_learning_only,
                "market_key_raw": market_key,
                "mode": "PROD",
                "pgr_score": pgr_score,
                "league_tier": _league_tier,
                "routing_reason": _routing_reason,
            }
            picks.append(opportunity)

        # ── Telemetry summary ─────────────────────────────────────────────────
        # _candidates_evaluated: all market evaluations before any filter (true denominator)
        # _total_pre_routing_candidates: passed all hard filters → entered pass-2 routing
        # _total_routed: routed to a tier (PRO/VALUE_OPP/WATCHLIST)
        # routing_rejects: failed pass-2 thresholds (PGR/EV/Conf/cap etc.)
        # scan_rejects: failed pre-routing hard filters
        _n_pro = len(picks)
        _n_value_opp = sum(1 for d in data_picks if d.get('mode') == 'VALUE_OPP')
        _n_watchlist = sum(1 for d in data_picks if d.get('mode') == 'WATCHLIST')
        _total_pre_routing = len(raw_candidates)
        _total_routed = _n_pro + _n_value_opp + _n_watchlist
        _routing_rejects = _total_pre_routing - _total_routed
        _scan_rejects = _candidates_evaluated - _total_pre_routing
        print(f"\n📊 THREE-TIER ROUTING SUMMARY")
        print(f"   Total evaluated: {_candidates_evaluated} | Hard-filter pass: {_total_pre_routing} | Scan rejects: {_scan_rejects}")
        print(f"   Routed: PRO PICK={_n_pro} | VALUE OPP={_n_value_opp} | WATCHLIST={_n_watchlist} | Routing rejects={_routing_rejects}")
        print(f"   PRO cap: {pro_picks_today}/{_pro_cap} (including {pro_picks_in_db} from earlier cycles today)")
        print(f"   Rejection breakdown: {rejection_counts}")

        production_picks = [p for p in picks if not p.get('is_learning_only')]
        learning_picks = [p for p in picks if p.get('is_learning_only')]


        # ── Conflict resolution for PRO picks only ────────────────────────────────
        def _resolve_over_under_conflicts(pick_list):
            import re
            conflict_groups = {}
            non_conflicting = []
            for p in pick_list:
                analysis = json.loads(p.get('analysis', '{}'))
                mk = analysis.get('market_key', '')
                m = re.match(r'(FT_)(OVER|UNDER)(_\d+_\d+)', mk)
                if m:
                    group_key = f"{p['match_id']}_{m.group(1)}{m.group(3)}"
                    conflict_groups.setdefault(group_key, []).append(p)
                else:
                    non_conflicting.append(p)
            resolved = list(non_conflicting)
            for group_key, group in conflict_groups.items():
                best = max(group, key=lambda x: x['edge_percentage'])
                resolved.append(best)
                if len(group) > 1:
                    kept_sel = best.get('selection', '?')
                    dropped = [g.get('selection', '?') for g in group if g is not best]
                    print(f"   🔀 CONFLICT: {best['home_team']} vs {best['away_team']} kept {kept_sel}, dropped {', '.join(dropped)}")
            return resolved

        pro_picks = _resolve_over_under_conflicts(picks)

        if pro_picks:
            log_calibration_batch(
                [{'raw_prob': json.loads(c.get('analysis', '{}')).get('p_model', 0),
                  'calibrated_prob': c.get('calibrated_prob', 0),
                  'raw_ev': json.loads(c.get('analysis', '{}')).get('raw_ev', 0),
                  'calibrated_ev': c.get('edge_percentage', 0) / 100}
                 for c in pro_picks],
                label="VALUE_SINGLES"
            )
            for c in production_picks[:5]:
                ev_show = c.get("edge_percentage", 0)
                pgr_show = c.get("pgr_score", 0) or 0
                analysis = json.loads(c.get("analysis", "{}"))
                p_raw = analysis.get("p_model", 0)
                p_cal = analysis.get("calibrated_prob", p_raw)
                print(f"   PRO CANDIDATE: {c['home_team']} vs {c['away_team']} | {c.get('selection')} | odds={c.get('odds', 0):.2f} p={p_raw:.2%}→{p_cal:.2%} EV={ev_show:.1f}% PGR={pgr_show:.1f}")

        # Already sorted by PGR in pass 2, but apply one final sort to production_picks
        # (conflict resolution may have dropped some items, re-sort to be safe)
        production_picks.sort(key=lambda x: (x.get("pgr_score") or 0, x["edge_percentage"]), reverse=True)

        # Apply unique-match cap + daily limit using remaining PRO slots
        remaining_slots = max(0, _pro_cap - pro_picks_in_db)
        effective_limit = min(remaining_slots, max_picks)
        unique: List[Dict[str, Any]] = []
        used_matches: Set[str] = set()
        if effective_limit > 0:
            for p in production_picks:
                if p["match_id"] in used_matches:
                    continue
                unique.append(p)
                used_matches.add(p["match_id"])
                if len(unique) >= effective_limit:
                    break

        print(f"🎯 SELECTED: Top {len(unique)} production singles (remaining_slots={remaining_slots}, max_picks={max_picks})")
        for i, p in enumerate(unique, 1):
            print(f"   #{i}: {p['home_team']} vs {p['away_team']} | {p['selection']} @ {p['odds']:.2f} (EV {p['edge_percentage']:.1f}% PGR={p.get('pgr_score',0):.1f})")

        # ── Reroute PRO candidates dropped by uniqueness/daily cap → VALUE_OPP ──
        # Any PRO-quality pick that didn't make the final selection is too good to
        # discard — downgrade to VALUE_OPP so it still appears in the dashboard
        # and Discord value channel rather than being silently lost.
        prod_dropped = [p for p in production_picks if p not in unique]
        for dp in prod_dropped:
            _rr_reason = "routed_value_opp_from_pro_cap"
            print(f"   🔄 REROUTE PRO→VALUE_OPP (cap/dup): {dp['home_team']} vs {dp['away_team']} | {dp.get('selection')} EV={dp.get('edge_percentage',0):.1f}% PGR={dp.get('pgr_score',0):.1f}")
            data_picks.append({
                "timestamp": int(time.time()),
                "match_id": dp["match_id"],
                "home_team": dp["home_team"],
                "away_team": dp["away_team"],
                "league": dp.get("league", ""),
                "market": "Value Single",
                "selection": dp.get("selection", ""),
                "odds": dp.get("odds", 0),
                "edge_percentage": dp.get("edge_percentage", 0),
                "confidence": dp.get("confidence", 0),
                "analysis": dp.get("analysis", "{}"),
                "match_date": dp.get("match_date"),
                "kickoff_utc": dp.get("kickoff_utc"),
                "kickoff_epoch": dp.get("kickoff_epoch"),
                "created_at_utc": dp.get("created_at_utc"),
                "mode": "VALUE_OPP",
                "stake": 0,
                "bet_placed": False,
                "odds_by_bookmaker": dp.get("odds_by_bookmaker"),
                "best_odds_value": dp.get("best_odds_value"),
                "best_odds_bookmaker": dp.get("best_odds_bookmaker"),
                "avg_odds": dp.get("avg_odds"),
                "fair_odds": dp.get("fair_odds"),
                "fixture_id": dp.get("fixture_id"),
                "trust_level": dp.get("trust_level"),
                "sim_probability": dp.get("sim_probability"),
                "ev_sim": dp.get("ev_sim"),
                "model_prob": dp.get("model_prob"),
                "calibrated_prob": dp.get("calibrated_prob"),
                "disagreement": dp.get("disagreement"),
                "pgr_score": dp.get("pgr_score"),
                "league_tier": dp.get("league_tier"),
                "routing_reason": _rr_reason,
            })

        self._learning_picks = learning_picks
        self._data_picks = data_picks
        _n_value_opp_final = sum(1 for d in data_picks if d.get('mode') == 'VALUE_OPP')
        _n_watchlist_final = sum(1 for d in data_picks if d.get('mode') == 'WATCHLIST')
        print(f"📡 SIGNAL PICKS (Discord): {len(data_picks)} signals queued (VALUE_OPP={_n_value_opp_final}, WATCHLIST={_n_watchlist_final})")

        # ── MISSADE SPEL ──────────────────────────────────────────────────────
        all_missed = []
        for dp in data_picks:
            all_missed.append({
                "match": f"{dp.get('home_team','?')} vs {dp.get('away_team','?')}",
                "selection": dp.get("selection", "?"),
                "odds": dp.get("odds", 0),
                "ev": dp.get("edge_percentage", 0),
                "reason": f"Routed {dp.get('mode','?')} — {dp.get('routing_reason','?')}",
                "league": dp.get("league", "?"),
            })
        all_missed.sort(key=lambda x: x["ev"], reverse=True)
        if all_missed:
            print(f"\n👉 MISSADE SPEL — {len(all_missed)} value opportunities (EJ PROD picks):")
            for i, m in enumerate(all_missed[:20], 1):
                print(f"   #{i}: [{m['league']}] {m['match']} | {m['selection']} @ {m['odds']:.2f} | {m['reason']}")
            if len(all_missed) > 20:
                print(f"   ... och {len(all_missed)-20} till")
        else:
            print("👉 MISSADE SPEL: Inga missade value opportunities denna cykel")

        return unique

    def save_value_singles(self, singles: List[Dict[str, Any]]) -> int:
        """Save picks to DB. Mode/bet_placed already set by routing; bankroll check for PRO."""
        saved = 0
        bets_placed = 0

        try:
            bankroll_mgr = get_bankroll_manager()
        except Exception as e:
            print(f"⚠️ Bankroll manager init failed: {e}")
            bankroll_mgr = None

        for s in singles:
            # Respect mode set by three-layer router
            mode = s.get('mode', 'PROD')
            bet_placed = (mode == 'PROD')

            # Bankroll check only for PRO picks
            if bet_placed and bankroll_mgr:
                can_bet, reason = bankroll_mgr.can_place_bet(s.get("stake", 1.0))
                if not can_bet:
                    bet_placed = False
                    print(f"⛔ BANKROLL LIMIT: {reason} — saving as VALUE_OPP instead")
                    s['mode'] = 'VALUE_OPP'
                    s['routing_reason'] = 'bankroll_limit'

            s['bet_placed'] = bet_placed
            if not bet_placed:
                s['stake'] = 0
            
            try:
                # Prefer generic save_opportunity if it exists
                if hasattr(self.champion, "save_opportunity"):
                    ok = self.champion.save_opportunity(s)
                else:
                    ok = self.champion.save_exact_score_opportunity(s)

                if ok:
                    saved += 1
                    if bet_placed:
                        bets_placed += 1
                        print(f"✅ BET PLACED: {s['home_team']} vs {s['away_team']} -> {s['selection']} @ {s['odds']:.2f} (EV {s['edge_percentage']:.1f}%)")
                    else:
                        print(f"📊 PREDICTION ONLY: {s['home_team']} vs {s['away_team']} -> {s['selection']} @ {s['odds']:.2f} (EV {s['edge_percentage']:.1f}%)")
                    
                    # 📊 COLLECT DATA FOR AI TRAINING (with full form data)
                    try:
                        collector = get_collector()
                        analysis = json.loads(s.get('analysis', '{}'))
                        match_dt = None
                        if s.get('match_date'):
                            try:
                                match_dt = datetime.strptime(s['match_date'], '%Y-%m-%d')
                            except:
                                pass
                        
                        _hf_obj = s.get('_home_form')
                        _af_obj = s.get('_away_form')
                        
                        def _form_to_dict(f):
                            if not f:
                                return {}
                            games = getattr(f, 'last_5_games', []) or []
                            n = len(games)
                            wins   = sum(1 for g in games if g.get('result') == 'W')
                            draws  = sum(1 for g in games if g.get('result') == 'D')
                            losses = sum(1 for g in games if g.get('result') == 'L')
                            ppg    = round((wins * 3 + draws) / n, 2) if n else None
                            return {
                                'goals_scored':   round(float(getattr(f, 'goals_scored', 0) or 0), 2),
                                'goals_conceded': round(float(getattr(f, 'goals_conceded', 0) or 0), 2),
                                'wins': wins, 'draws': draws, 'losses': losses, 'ppg': ppg,
                            }
                        
                        collector.collect_value_single(
                            home_team=s['home_team'],
                            away_team=s['away_team'],
                            league=s.get('league', ''),
                            match_date=match_dt,
                            market_type=analysis.get('market_key', s.get('market_key', '')),
                            odds=s.get('odds', 0),
                            model_probability=analysis.get('p_model', 0),
                            edge=analysis.get('ev', s.get('ev', 0)),
                            home_xg=analysis.get('expected_home_goals') or s.get('lh'),
                            away_xg=analysis.get('expected_away_goals') or s.get('la'),
                            home_form=_form_to_dict(_hf_obj),
                            away_form=_form_to_dict(_af_obj),
                            odds_data={'odds': s.get('odds'), 'market': analysis.get('market_key', s.get('market_key'))},
                            bet_placed=bet_placed
                        )
                    except Exception as e:
                        pass  # Silent fail for data collection
            except Exception as e:
                print(f"❌ Value single save failed: {e}")
        
        print(f"📈 Summary: {saved} predictions saved, {bets_placed} bets placed")
        return saved
