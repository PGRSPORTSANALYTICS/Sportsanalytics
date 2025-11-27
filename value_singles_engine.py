# value_singles_engine.py
# ------------------------------------------------------------
# VALUE SINGLES ENGINE
# - Builds single bets from model xG / Poisson probabilities
# - Supports multiple markets
# - Avoids duplicates vs other systems
# ------------------------------------------------------------

import math
import time
import json
from typing import Dict, Any, List, Optional, Tuple, Set


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
    champion: your RealFootballChampion instance
    It must provide:
      - get_todays_fixtures() -> List[Dict]  (or similar)
      - get_odds_for_match(match) -> Dict[str, float]
      - get_expected_goals(match) -> Tuple[float, float]
      - save_opportunity(dict_or_object) OR save_exact_score_opportunity for dicts
    If some are missing, the engine will skip gracefully.
    """

    def __init__(self, champion, ev_threshold: float = 0.03, min_confidence: int = 50):
        self.champion = champion
        self.ev_threshold = ev_threshold      # e.g. 0.03 = 3% EV (lowered from 5%)
        self.min_confidence = min_confidence  # confidence gate (lowered from 55%)
        self._exact_score_cache = {}  # Cache for exact score predictions
    
    def _get_exact_score_outcome(self, home_team: str, away_team: str) -> Optional[str]:
        """
        Check if there's an existing exact score prediction for this match.
        Returns 'HOME_WIN', 'DRAW', 'AWAY_WIN' or None if no prediction exists.
        """
        from db_helper import db_helper
        
        cache_key = f"{home_team}_{away_team}"
        if cache_key in self._exact_score_cache:
            return self._exact_score_cache[cache_key]
        
        try:
            query = """
                SELECT selection FROM football_opportunities 
                WHERE home_team = %s AND away_team = %s 
                  AND market = 'exact_score'
                  AND outcome IS NULL
                LIMIT 1
            """
            rows = db_helper.execute(query, (home_team, away_team), fetch='all')
            
            if rows and rows[0][0]:
                selection = rows[0][0]  # e.g., "Exact Score: 2-1"
                # Parse the score to determine outcome
                import re
                match = re.search(r'(\d+)-(\d+)', selection)
                if match:
                    home_goals = int(match.group(1))
                    away_goals = int(match.group(2))
                    if home_goals > away_goals:
                        result = 'HOME_WIN'
                    elif away_goals > home_goals:
                        result = 'AWAY_WIN'
                    else:
                        result = 'DRAW'
                    self._exact_score_cache[cache_key] = result
                    return result
            
            self._exact_score_cache[cache_key] = None
            return None
        except Exception as e:
            print(f"⚠️ Error checking exact score: {e}")
            return None
    
    def _get_exact_score_goals(self, home_team: str, away_team: str) -> Optional[tuple]:
        """
        Get the exact score prediction goals for this match.
        Returns tuple of (home_goals, away_goals) or None if no prediction.
        """
        cache_key = f"{home_team}_{away_team}_goals"
        if cache_key in self._exact_score_cache:
            return self._exact_score_cache[cache_key]
        
        try:
            query = """
                SELECT selection FROM football_opportunities 
                WHERE home_team = %s AND away_team = %s 
                  AND market = 'exact_score'
                  AND outcome IS NULL
                LIMIT 1
            """
            rows = db_helper.execute(query, (home_team, away_team), fetch='all')
            
            if rows and rows[0][0]:
                selection = rows[0][0]
                import re
                match = re.search(r'(\d+)-(\d+)', selection)
                if match:
                    result = (int(match.group(1)), int(match.group(2)))
                    self._exact_score_cache[cache_key] = result
                    return result
            
            self._exact_score_cache[cache_key] = None
            return None
        except Exception as e:
            return None
    
    def _is_1x2_conflicting(self, home_team: str, away_team: str, market_key: str) -> bool:
        """
        Check if a 1X2 selection conflicts with existing exact score prediction.
        Returns True if conflicting (should skip), False if OK to proceed.
        """
        if market_key not in ('HOME_WIN', 'AWAY_WIN', 'DRAW'):
            return False  # Only check 1X2 markets
        
        existing_outcome = self._get_exact_score_outcome(home_team, away_team)
        if existing_outcome is None:
            return False  # No exact score prediction, OK to proceed
        
        # Conflict if exact score says one outcome but singles says another
        if existing_outcome != market_key:
            print(f"⚠️ CONFLICT BLOCKED: {home_team} vs {away_team} has exact score predicting {existing_outcome}, but value single would be {market_key}")
            return True
        
        return False  # Same prediction, OK
    
    def _get_exact_score_ev(self, home_team: str, away_team: str) -> Optional[tuple]:
        """
        Get the exact score prediction's EV and ID for this match.
        Returns tuple of (ev_percentage, prediction_id) or None if no prediction.
        """
        try:
            query = """
                SELECT id, edge_percentage FROM football_opportunities 
                WHERE home_team = %s AND away_team = %s 
                  AND market = 'exact_score'
                  AND status = 'pending'
                ORDER BY timestamp DESC
                LIMIT 1
            """
            rows = db_helper.execute(query, (home_team, away_team), fetch='all')
            
            if rows and rows[0]:
                return (float(rows[0][1] or 0), rows[0][0])  # (ev, id)
            return None
        except Exception as e:
            print(f"⚠️ Error getting exact score EV: {e}")
            return None
    
    def _delete_exact_score_prediction(self, prediction_id: int, home_team: str, away_team: str, reason: str):
        """Delete an exact score prediction when Value Single has better EV."""
        try:
            db_helper.execute(
                "DELETE FROM football_opportunities WHERE id = %s AND status = 'pending'",
                (prediction_id,)
            )
            print(f"🔄 REPLACED: Deleted Exact Score #{prediction_id} for {home_team} vs {away_team} - {reason}")
        except Exception as e:
            print(f"⚠️ Error deleting exact score: {e}")
    
    def _check_conflict_with_ev_comparison(self, home_team: str, away_team: str, market_key: str, 
                                            value_single_ev: float) -> str:
        """
        Smart conflict resolution: Compare EVs and decide which prediction to keep.
        
        Returns:
            'skip' - Skip Value Single (Exact Score has better EV)
            'replace' - Replace Exact Score with Value Single (Value Single has better EV)
            'ok' - No conflict, proceed normally
        """
        # Check if this is a goals market that could conflict
        if not market_key.startswith('FT_OVER_') and not market_key.startswith('FT_UNDER_'):
            return 'ok'  # Not a goals market, no conflict possible
        
        exact_goals = self._get_exact_score_goals(home_team, away_team)
        if exact_goals is None:
            return 'ok'  # No exact score prediction
        
        total_goals = exact_goals[0] + exact_goals[1]
        
        # Parse the line (e.g., "FT_OVER_2_5" -> line = 2.5)
        parts = market_key.split('_')
        if len(parts) >= 4:
            try:
                line = float(f"{parts[2]}.{parts[3]}")
            except ValueError:
                return 'ok'
        else:
            return 'ok'
        
        is_over = 'OVER' in market_key
        
        # Check if there's a conflict
        has_conflict = False
        if is_over and total_goals <= line:
            has_conflict = True
        elif not is_over and total_goals >= line:
            has_conflict = True
        
        if not has_conflict:
            return 'ok'
        
        # There's a conflict - compare EVs
        exact_score_data = self._get_exact_score_ev(home_team, away_team)
        if exact_score_data is None:
            return 'ok'
        
        exact_score_ev, exact_score_id = exact_score_data
        
        # Convert Value Single EV to percentage for comparison (it's already decimal like 0.05 for 5%)
        value_single_ev_pct = value_single_ev * 100
        
        print(f"⚖️  EV COMPARISON: {home_team} vs {away_team}")
        print(f"   Value Single ({market_key}): {value_single_ev_pct:.1f}% EV")
        print(f"   Exact Score ({exact_goals[0]}-{exact_goals[1]}): {exact_score_ev:.1f}% EV")
        
        if value_single_ev_pct > exact_score_ev:
            # Value Single is better - delete exact score and use value single
            self._delete_exact_score_prediction(
                exact_score_id, home_team, away_team,
                f"Value Single EV ({value_single_ev_pct:.1f}%) > Exact Score EV ({exact_score_ev:.1f}%)"
            )
            return 'replace'
        else:
            # Exact Score is better - skip value single
            print(f"   ➡️  Keeping Exact Score (better EV)")
            return 'skip'
    
    def _is_goals_conflicting(self, home_team: str, away_team: str, market_key: str) -> bool:
        """
        DEPRECATED: Use _check_conflict_with_ev_comparison instead.
        Kept for backward compatibility but now just returns False.
        """
        return False  # Now handled by _check_conflict_with_ev_comparison

    def _calc_ev(self, p_model: float, odds: float) -> float:
        # Expected value = p*odds - 1
        return (p_model * odds) - 1.0

    def _build_single_markets(self, lh: float, la: float) -> Dict[str, float]:
        """
        Returns model probabilities for ALL single-bet markets.
        """
        # Over/Under Goals (0.5 - 4.5)
        p_over05 = prob_total_over(lh, la, 0.5)
        p_under05 = 1 - p_over05
        p_over15 = prob_total_over(lh, la, 1.5)
        p_under15 = 1 - p_over15
        p_over25 = prob_total_over(lh, la, 2.5)
        p_under25 = 1 - p_over25
        p_over35 = prob_total_over(lh, la, 3.5)
        p_under35 = 1 - p_over35
        p_over45 = prob_total_over(lh, la, 4.5)
        p_under45 = 1 - p_over45
        
        # 1H Over/Under
        p_over05_1h = prob_total_over(lh * 0.45, la * 0.45, 0.5)
        
        # BTTS
        p_btts_yes = prob_btts(lh, la)
        p_btts_no = 1 - p_btts_yes
        
        # 1X2 Moneyline
        p_hw, p_d, p_aw = prob_1x2(lh, la)
        
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

        print("🔥 VALUE SINGLES START")
        print("   min_ev =", getattr(self, "min_ev", getattr(self, "ev_threshold", None)))
        print("   min_conf =", getattr(self, "min_confidence", None))

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

                # Relaxed moneyline filter: avoid extreme favorites/underdogs
                if market_key in ("HOME_WIN", "AWAY_WIN", "DRAW"):
                    if odds < 1.40 or odds > 4.00:  # More relaxed range
                        continue
                    # Check for conflict with exact score prediction
                    if self._is_1x2_conflicting(home_team, away_team, market_key):
                        continue  # Skip conflicting 1X2 selections

                ev = self._calc_ev(p_model, odds)
                if ev < self.ev_threshold:
                    continue
                
                # Smart conflict resolution for Over/Under goals vs Exact Score
                # Compare EVs - keep whichever has better value
                conflict_result = self._check_conflict_with_ev_comparison(home_team, away_team, market_key, ev)
                if conflict_result == 'skip':
                    continue  # Exact Score has better EV, skip this Value Single
                # If 'replace', the Exact Score was deleted, continue with this Value Single

                confidence = int(min(100, max(0, 50 + ev * 250)))  # simple confidence proxy
                if confidence < self.min_confidence:
                    continue

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
                    "stake": match.get("stake", 100),
                    "match_date": match_date,
                    "kickoff_time": kickoff_time,
                    "quality_score": float(match.get("quality_score", 50)),
                    "recommended_tier": "SINGLE",
                    "daily_rank": 999
                }

                picks.append(opportunity)

        # Debug: Show top candidates
        if picks:
            picks.sort(key=lambda x: x["edge_percentage"], reverse=True)
            top = picks[:3]
            for c in top:
                ev_show = c.get("edge_percentage", 0)
                p_model = json.loads(c.get("analysis", "{}")).get("p_model", 0)
                print(f"   TOP CAND: {c.get('market')} {c.get('selection')} | odds={c.get('odds', 0):.2f} p={p_model:.2%} EV={ev_show:.2f}%")

        # 5) Sort by EV and enforce unique matches
        picks.sort(key=lambda x: x["edge_percentage"], reverse=True)

        unique: List[Dict[str, Any]] = []
        used_matches: Set[str] = set()
        for p in picks:
            if p["match_id"] in used_matches:
                continue
            unique.append(p)
            used_matches.add(p["match_id"])
            if len(unique) >= max_picks:
                break

        return unique

    def save_value_singles(self, singles: List[Dict[str, Any]]) -> int:
        saved = 0
        for s in singles:
            try:
                # Prefer generic save_opportunity if it exists
                if hasattr(self.champion, "save_opportunity"):
                    ok = self.champion.save_opportunity(s)
                else:
                    ok = self.champion.save_exact_score_opportunity(s)

                if ok:
                    saved += 1
                    print(f"✅ VALUE SINGLE SAVED: {s['home_team']} vs {s['away_team']} -> {s['selection']} @ {s['odds']:.2f} (EV {s['edge_percentage']:.1f}%)")
            except Exception as e:
                print(f"❌ Value single save failed: {e}")
        return saved
