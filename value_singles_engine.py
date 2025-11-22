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

    def __init__(self, champion, ev_threshold: float = 0.05, min_confidence: int = 55):
        self.champion = champion
        self.ev_threshold = ev_threshold      # e.g. 0.05 = 5% EV
        self.min_confidence = min_confidence  # confidence gate

    def _calc_ev(self, p_model: float, odds: float) -> float:
        # Expected value = p*odds - 1
        return (p_model * odds) - 1.0

    def _build_single_markets(self, lh: float, la: float) -> Dict[str, float]:
        """
        Returns model probabilities per market.
        """
        p_over05_1h = prob_total_over(lh * 0.45, la * 0.45, 0.5)  # rough 1H scaling
        p_over15 = prob_total_over(lh, la, 1.5)
        p_over25 = prob_total_over(lh, la, 2.5)
        p_over35 = prob_total_over(lh, la, 3.5)
        p_btts = prob_btts(lh, la)
        p_hw, p_d, p_aw = prob_1x2(lh, la)

        return {
            "1H_OVER_0_5": p_over05_1h,
            "FT_OVER_1_5": p_over15,
            "FT_OVER_2_5": p_over25,
            "FT_OVER_3_5": p_over35,
            "BTTS_YES": p_btts,
            "HOME_WIN": p_hw,
            "DRAW": p_d,
            "AWAY_WIN": p_aw,
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

        for match in fixtures:
            match_id = match.get("match_id") or match.get("id") or f"{match.get('home_team')}_vs_{match.get('away_team')}"
            if match_id in avoid_match_ids:
                continue

            # 2) Odds
            if not hasattr(self.champion, "get_odds_for_match"):
                continue
            odds_dict = self.champion.get_odds_for_match(match) or {}
            if not odds_dict:
                continue

            # 3) Expected goals
            if hasattr(self.champion, "get_expected_goals"):
                lh, la = self.champion.get_expected_goals(match)
            else:
                lh = match.get("expected_home_goals")
                la = match.get("expected_away_goals")
            if lh is None or la is None:
                continue

            probs = self._build_single_markets(lh, la)

            # 4) Evaluate each market
            for market_key, p_model in probs.items():
                odds = odds_dict.get(market_key)
                if odds is None:
                    continue

                # Special rule: moneyline only in 1.75–1.90 sweet spot
                if market_key in ("HOME_WIN", "AWAY_WIN"):
                    if not (1.75 <= odds <= 1.90):
                        continue

                ev = self._calc_ev(p_model, odds)
                if ev < self.ev_threshold:
                    continue

                confidence = int(min(100, max(0, 50 + ev * 250)))  # simple confidence proxy
                if confidence < self.min_confidence:
                    continue

                selection_text = {
                    "1H_OVER_0_5": "1H Over 0.5 Goals",
                    "FT_OVER_1_5": "Over 1.5 Goals",
                    "FT_OVER_2_5": "Over 2.5 Goals",
                    "FT_OVER_3_5": "Over 3.5 Goals",
                    "BTTS_YES": "BTTS Yes",
                    "HOME_WIN": "Home Win",
                    "DRAW": "Draw",
                    "AWAY_WIN": "Away Win",
                }.get(market_key, market_key)

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
                    "match_date": match.get("match_date"),
                    "kickoff_time": match.get("kickoff_time"),
                    "quality_score": float(match.get("quality_score", 50)),
                    "recommended_tier": "SINGLE",
                    "daily_rank": 999
                }

                picks.append(opportunity)

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
