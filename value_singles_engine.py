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


# ============================================================
# VALUE SINGLES HARD FILTERS (Nov 30, 2025)
# These filters ensure ONLY high-quality, low-variance bets
# ============================================================

# ============================================================
# VALUE SINGLES - NOW THE CORE PRODUCT (Dec 9, 2025 Pivot)
# Lower bookmaker margins (4-8%) vs SGP (28-45%) = better ROI
# ============================================================

# Minimum Expected Value (EV) - balanced for volume + quality
MIN_VALUE_SINGLE_EV = 0.05  # 5% edge - realistic threshold

# Odds range filter - sweet spot for value
MIN_VALUE_SINGLE_ODDS = 1.55  # Slightly lower min for more supply
MAX_VALUE_SINGLE_ODDS = 1.95  # Moderate range, lower variance
MAX_LEARNING_ODDS = 2.50      # Still collect predictions up to 2.50 for AI training

# Minimum model confidence/probability required
MIN_VALUE_SINGLE_CONFIDENCE = 0.56  # Balanced threshold

# Maximum number of value singles per day - THIS IS NOW CORE PRODUCT
MAX_VALUE_SINGLES_PER_DAY = 10  # Increased - Value Singles are the focus now

# Major league whitelist (using odds_api_key identifiers)
# Only bet on leagues with reliable data and predictable outcomes
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
    # Nordic
    "soccer_sweden_allsvenskan",     # Allsvenskan
    # Americas
    "soccer_usa_mls",                # MLS
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
        # Use hard-coded constants for strict filtering (Nov 30, 2025)
        self.ev_threshold = MIN_VALUE_SINGLE_EV  # 5% EV requirement (core product)
        self.min_confidence = 50  # Base confidence threshold (probability filter is separate)
    
    def _check_conflict_with_ev_comparison(self, home_team: str, away_team: str, market_key: str, 
                                            value_single_ev: float) -> str:
        """
        No longer needed - Exact Score product removed Dec 2025.
        Always returns 'ok' to proceed with Value Singles.
        """
        return 'ok'

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
            p_under25 = 1 - p_over25
            p_btts_no = 1 - p_btts_yes
            
            print(f"🎲 Monte Carlo: HW={p_hw:.1%} D={p_d:.1%} AW={p_aw:.1%} O2.5={p_over25:.1%} BTTS={p_btts_yes:.1%}")
        else:
            # Fall back to basic Poisson
            p_hw, p_d, p_aw = prob_1x2(lh, la)
            p_btts_yes = prob_btts(lh, la)
            p_over25 = prob_total_over(lh, la, 2.5)
            p_over35 = prob_total_over(lh, la, 3.5)
            p_under25 = 1 - p_over25
            p_btts_no = 1 - p_btts_yes
        
        # Over/Under Goals (0.5 - 4.5) - keep Poisson for less common lines
        p_over05 = prob_total_over(lh, la, 0.5)
        p_under05 = 1 - p_over05
        p_over15 = prob_total_over(lh, la, 1.5)
        p_under15 = 1 - p_over15
        p_over45 = prob_total_over(lh, la, 4.5)
        p_under45 = 1 - p_over45
        p_under35 = 1 - p_over35
        
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
        
        # Team Totals (individual team over/under)
        p_home_over05 = prob_total_over(lh, 0, 0.5)
        p_home_over15 = prob_total_over(lh, 0, 1.5)
        p_away_over05 = prob_total_over(0, la, 0.5)
        p_away_over15 = prob_total_over(0, la, 1.5)

        return {
            # Over/Under Goals
            "FT_OVER_0_5": p_over05,
            "FT_UNDER_0_5": p_under05,
            "FT_OVER_1_5": p_over15,
            "FT_UNDER_1_5": p_under15,
            "FT_OVER_2_5": p_over25,
            "FT_UNDER_2_5": p_under25,
            "FT_OVER_3_5": p_over35,
            "FT_UNDER_3_5": p_under35,
            "FT_OVER_4_5": p_over45,
            "FT_UNDER_4_5": p_under45,
            
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
            
            # Team Totals
            "HOME_OVER_0_5": p_home_over05,
            "HOME_OVER_1_5": p_home_over15,
            "AWAY_OVER_0_5": p_away_over05,
            "AWAY_OVER_1_5": p_away_over15,
        }

    def generate_value_singles(
        self,
        avoid_match_ids: Optional[Set[str]] = None,
        max_picks: int = 6
    ) -> List[Dict[str, Any]]:
        avoid_match_ids = avoid_match_ids or set()
        picks: List[Dict[str, Any]] = []

        print("🔥 VALUE SINGLES START (HARD FILTERS ACTIVE)")
        print(f"   min_ev = {MIN_VALUE_SINGLE_EV*100:.0f}%")
        print(f"   betting_odds = {MIN_VALUE_SINGLE_ODDS} - {MAX_VALUE_SINGLE_ODDS} | learning_odds = {MIN_VALUE_SINGLE_ODDS} - {MAX_LEARNING_ODDS}")
        print(f"   min_model_prob = {MIN_VALUE_SINGLE_CONFIDENCE*100:.0f}%")
        print(f"   max_picks/day = {MAX_VALUE_SINGLES_PER_DAY}")
        print(f"   leagues = {len(VALUE_SINGLE_LEAGUE_WHITELIST)} whitelisted")

        # 1) Get fixtures
        if not hasattr(self.champion, "get_todays_fixtures"):
            print("⚠️ ValueSinglesEngine: champion.get_todays_fixtures() missing")
            return picks

        fixtures = self.champion.get_todays_fixtures()
        if not fixtures:
            print("⚠️ ValueSinglesEngine: No fixtures today")
            return picks

        from datetime import datetime, timezone
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        for match in fixtures:
            match_id = match.get("match_id") or match.get("id") or f"{match.get('home_team')}_vs_{match.get('away_team')}"
            if match_id in avoid_match_ids:
                continue

            home_team = match.get("home_team")
            away_team = match.get("away_team")
            if not home_team or not away_team:
                continue
            
            # SAME-DAY FILTER: Only generate predictions for matches playing TODAY
            commence_time = match.get('commence_time', '')
            match_date = match.get('formatted_date') or match.get('match_date')
            
            if not match_date and commence_time:
                try:
                    dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                    match_date = dt.strftime("%Y-%m-%d")
                except:
                    match_date = commence_time[:10] if len(commence_time) > 10 else ""
            
            if match_date and match_date != today_str:
                print(f"⏭️ Skipping {home_team} vs {away_team} - plays on {match_date}, not today ({today_str})")
                continue
            
            # LEAGUE WHITELIST FILTER: Only major leagues for lower variance
            league_key = match.get('sport_key') or match.get('league_key') or match.get('odds_api_key') or ''
            if league_key and league_key not in VALUE_SINGLE_LEAGUE_WHITELIST:
                print(f"⏭️ Skipping {home_team} vs {away_team} - league '{league_key}' not in whitelist")
                continue

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
                odds = odds_dict.get(market_key)
                if odds is None:
                    continue
                
                # ODDS FILTER: Generate predictions for 1.60-2.50 (learning), bet only 1.60-1.79
                if not (MIN_VALUE_SINGLE_ODDS <= odds <= MAX_LEARNING_ODDS):
                    continue  # Skip bets outside learning range
                
                # HARD FILTER: Model probability >= 58% for high confidence
                if p_model < MIN_VALUE_SINGLE_CONFIDENCE:
                    continue  # Skip low-confidence predictions

                # Check for conflict with exact score prediction (1X2 markets only)
                if market_key in ("HOME_WIN", "AWAY_WIN", "DRAW"):
                    if self._is_1x2_conflicting(home_team, away_team, market_key):
                        continue  # Skip conflicting 1X2 selections

                ev = self._calc_ev(p_model, odds)
                
                # HARD FILTER: Minimum 8% EV
                if ev < MIN_VALUE_SINGLE_EV:
                    continue
                
                # Smart conflict resolution for Over/Under goals vs Exact Score
                conflict_result = self._check_conflict_with_ev_comparison(home_team, away_team, market_key, ev)
                if conflict_result == 'skip':
                    continue  # Exact Score has better EV, skip this Value Single

                confidence = int(min(100, max(0, 50 + ev * 250)))  # simple confidence proxy
                if confidence < self.min_confidence:
                    continue

                # 🎯 TRUST LEVEL CLASSIFICATION (Dec 2025)
                # Calculate simulation EV and disagreement
                sim_prob = p_model  # Monte Carlo probability already used
                ev_sim = ev  # Already calculated with MC probability
                disagreement = abs(sim_prob - p_model)  # Will be 0 since using same prob
                sim_approved = ev_sim >= 0.03  # 3% EV threshold
                
                trust_level = classify_trust_level(
                    ev_sim=ev_sim,
                    ev_model=ev,
                    confidence=sim_prob,
                    disagreement=disagreement,
                    sim_approved=sim_approved,
                    odds=odds
                )
                
                # Print trust level for visibility
                print(f"   🏷️ Trust: {trust_level} | EV={ev:.1%} | Conf={sim_prob:.0%}")

                selection_text = {
                    # Over/Under Goals
                    "FT_OVER_0_5": "Over 0.5 Goals",
                    "FT_UNDER_0_5": "Under 0.5 Goals",
                    "FT_OVER_1_5": "Over 1.5 Goals",
                    "FT_UNDER_1_5": "Under 1.5 Goals",
                    "FT_OVER_2_5": "Over 2.5 Goals",
                    "FT_UNDER_2_5": "Under 2.5 Goals",
                    "FT_OVER_3_5": "Over 3.5 Goals",
                    "FT_UNDER_3_5": "Under 3.5 Goals",
                    "FT_OVER_4_5": "Over 4.5 Goals",
                    "FT_UNDER_4_5": "Under 4.5 Goals",
                    # 1H Goals
                    "1H_OVER_0_5": "1H Over 0.5 Goals",
                    # BTTS
                    "BTTS_YES": "BTTS Yes",
                    "BTTS_NO": "BTTS No",
                    # 1X2
                    "HOME_WIN": "Home Win",
                    "DRAW": "Draw",
                    "AWAY_WIN": "Away Win",
                    # Double Chance
                    "DC_HOME_DRAW": "Home or Draw",
                    "DC_HOME_AWAY": "Home or Away",
                    "DC_DRAW_AWAY": "Draw or Away",
                    # Draw No Bet
                    "DNB_HOME": "Draw No Bet - Home",
                    "DNB_AWAY": "Draw No Bet - Away",
                    # Corners
                    "CORNERS_OVER_8_5": "Corners Over 8.5",
                    "CORNERS_OVER_9_5": "Corners Over 9.5",
                    "CORNERS_OVER_10_5": "Corners Over 10.5",
                    "CORNERS_OVER_11_5": "Corners Over 11.5",
                    # Team Totals
                    "HOME_OVER_0_5": f"{home_team} Over 0.5 Goals",
                    "HOME_OVER_1_5": f"{home_team} Over 1.5 Goals",
                    "AWAY_OVER_0_5": f"{away_team} Over 0.5 Goals",
                    "AWAY_OVER_1_5": f"{away_team} Over 1.5 Goals",
                }.get(market_key, market_key)

                # Extract match_date and kickoff_time from commence_time if not present
                commence_time = match.get('commence_time', '')
                match_date = match.get('formatted_date') or match.get('match_date')
                kickoff_time = match.get('formatted_time') or match.get('kickoff_time')
                
                # Parse from commence_time if date not available
                if not match_date and commence_time:
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                        match_date = dt.strftime("%Y-%m-%d")
                        kickoff_time = dt.strftime("%H:%M")
                    except:
                        # Fallback: extract from string
                        match_date = commence_time[:10] if len(commence_time) > 10 else ""
                        kickoff_time = commence_time[11:16] if len(commence_time) > 16 else ""
                
                # Fixed stake for Value Singles: 460 SEK (~$42 USD)
                VALUE_SINGLES_STAKE = 460.0  # SEK - standard stake for value singles
                
                opportunity = {
                    "timestamp": int(time.time()),
                    "match_id": match_id,
                    "home_team": match.get("home_team"),
                    "away_team": match.get("away_team"),
                    "league": match.get("league"),
                    "market": "Value Single",
                    "selection": selection_text,
                    "odds": float(odds),
                    "edge_percentage": float(ev * 100),
                    "confidence": int(confidence),
                    "analysis": json.dumps({
                        "market_key": market_key,
                        "p_model": float(p_model),
                        "ev": float(ev),
                        "expected_home_goals": float(lh),
                        "expected_away_goals": float(la)
                    }),
                    "stake": VALUE_SINGLES_STAKE,
                    "match_date": match_date,
                    "kickoff_time": kickoff_time,
                    "quality_score": float(match.get("quality_score", 50)),
                    "recommended_tier": "SINGLE",
                    "daily_rank": 999,
                    # Monte Carlo + Trust Level fields (Dec 2025)
                    "trust_level": trust_level,
                    "sim_probability": float(sim_prob),
                    "ev_sim": float(ev_sim),
                    "disagreement": float(disagreement)
                }

                picks.append(opportunity)

        # Debug: Show all candidates that passed hard filters
        print(f"\n📊 VALUE SINGLES SUMMARY: {len(picks)} candidates passed hard filters")
        if picks:
            picks.sort(key=lambda x: x["edge_percentage"], reverse=True)
            for c in picks[:5]:  # Show top 5
                ev_show = c.get("edge_percentage", 0)
                p_model = json.loads(c.get("analysis", "{}")).get("p_model", 0)
                print(f"   CANDIDATE: {c['home_team']} vs {c['away_team']} | {c.get('selection')} | odds={c.get('odds', 0):.2f} p={p_model:.2%} EV={ev_show:.1f}%")

        # 5) Sort by EV, enforce unique matches, and LIMIT TO MAX_VALUE_SINGLES_PER_DAY
        picks.sort(key=lambda x: x["edge_percentage"], reverse=True)

        unique: List[Dict[str, Any]] = []
        used_matches: Set[str] = set()
        for p in picks:
            if p["match_id"] in used_matches:
                continue
            unique.append(p)
            used_matches.add(p["match_id"])
            # HARD LIMIT: Maximum 4 value singles per day
            if len(unique) >= MAX_VALUE_SINGLES_PER_DAY:
                break
        
        print(f"🎯 SELECTED: Top {len(unique)} value singles (max {MAX_VALUE_SINGLES_PER_DAY}/day)")
        for i, p in enumerate(unique, 1):
            print(f"   #{i}: {p['home_team']} vs {p['away_team']} | {p['selection']} @ {p['odds']:.2f} (EV {p['edge_percentage']:.1f}%)")

        return unique

    def save_value_singles(self, singles: List[Dict[str, Any]]) -> int:
        saved = 0
        bets_placed = 0
        
        # Check bankroll before saving any bets
        try:
            bankroll_mgr = get_bankroll_manager()
        except Exception as e:
            print(f"⚠️ Bankroll manager init failed: {e}")
            bankroll_mgr = None
        
        for s in singles:
            # Bankroll check for each bet - determines if actual bet placed
            bet_placed = True
            odds = s.get('odds', 0)
            
            # ODDS FILTER: Only bet 1.60-1.79, collect data for 1.80-2.50 (Dec 6, 2025)
            if odds > MAX_VALUE_SINGLE_ODDS:
                bet_placed = False
                print(f"📊 LEARNING DATA: {s['home_team']} vs {s['away_team']} @ {odds:.2f} (odds > {MAX_VALUE_SINGLE_ODDS} - collecting for AI training)")
            
            if bankroll_mgr and bet_placed:
                can_bet, reason = bankroll_mgr.can_place_bet(s.get("stake", 460.0))
                if not can_bet:
                    bet_placed = False
                    print(f"⛔ BANKROLL LIMIT: {reason} - Saving prediction only (no bet)")
            
            # Add bet_placed flag to the single
            s["bet_placed"] = bet_placed
            if not bet_placed:
                s["stake"] = 0  # Zero stake for prediction-only entries
            
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
                    
                    # 📊 COLLECT DATA FOR AI TRAINING
                    try:
                        collector = get_collector()
                        analysis = json.loads(s.get('analysis', '{}'))
                        match_dt = None
                        if s.get('match_date'):
                            try:
                                match_dt = datetime.strptime(s['match_date'], '%Y-%m-%d')
                            except:
                                pass
                        
                        collector.collect_value_single(
                            home_team=s['home_team'],
                            away_team=s['away_team'],
                            league=s.get('league', ''),
                            match_date=match_dt,
                            market_type=analysis.get('market_key', ''),
                            odds=s.get('odds', 0),
                            model_probability=analysis.get('p_model', 0),
                            edge=analysis.get('ev', 0),
                            home_xg=analysis.get('expected_home_goals'),
                            away_xg=analysis.get('expected_away_goals'),
                            odds_data={'odds': s.get('odds'), 'market': analysis.get('market_key')},
                            bet_placed=bet_placed
                        )
                    except Exception as e:
                        pass  # Silent fail for data collection
            except Exception as e:
                print(f"❌ Value single save failed: {e}")
        
        print(f"📈 Summary: {saved} predictions saved, {bets_placed} bets placed")
        return saved
