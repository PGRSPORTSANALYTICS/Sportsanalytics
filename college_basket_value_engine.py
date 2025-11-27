"""
COLLEGE BASKET (NCAAB) VALUE ENGINE
- Fetches NCAAB odds from The Odds API (or compatible)
- Markets: h2h (moneyline), spreads, totals
- Computes fair probability from market consensus (devigged average)
- Finds value singles & optional 3/4-leg multi-game parlays
- Designed for low API call budget (100/day)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import os
import time
import math
import requests
from itertools import combinations


# ----------------------------
# Data classes
# ----------------------------

@dataclass
class BasketPick:
    match: str
    market: str
    selection: str
    odds: float
    prob: float
    ev: float
    confidence: float
    meta: Dict[str, Any] = field(default_factory=dict)


# ----------------------------
# Odds API Client
# ----------------------------

class OddsAPIClient:
    """
    Minimal client for The Odds API / similar JSON format.
    Expects env:
      THE_ODDS_API_KEY
    """

    BASE_URL = "https://api.the-odds-api.com/v4/sports"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("THE_ODDS_API_KEY")
        if not self.api_key:
            raise ValueError("THE_ODDS_API_KEY is missing")

    def get_upcoming(
        self,
        sport_key: str = "basketball_ncaab",
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
        odds_format: str = "decimal",
        date_format: str = "iso",
    ) -> List[Dict]:
        """
        Fetch upcoming games with odds.
        """
        url = f"{self.BASE_URL}/{sport_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }

        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()


# ----------------------------
# Helper math
# ----------------------------

def devig_two_way(odds_a: float, odds_b: float) -> Tuple[float, float]:
    """
    Convert two-way odds into vig-free probabilities.
    """
    pa = 1.0 / odds_a
    pb = 1.0 / odds_b
    s = pa + pb
    if s <= 0:
        return 0.5, 0.5
    return pa / s, pb / s


def fair_prob_from_books(two_way_books: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Books list of (odds_a, odds_b) -> return average devig prob for both sides.
    """
    probs_a = []
    probs_b = []
    for oa, ob in two_way_books:
        pa, pb = devig_two_way(oa, ob)
        probs_a.append(pa)
        probs_b.append(pb)
    if not probs_a:
        return 0.5, 0.5
    return sum(probs_a) / len(probs_a), sum(probs_b) / len(probs_b)


def ev_from_prob_odds(p: float, odds: float) -> float:
    """
    EV as decimal return relative to stake=1.
    EV = p*(odds-1) - (1-p)
    """
    return p * (odds - 1.0) - (1.0 - p)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ----------------------------
# Parlay builder (multi-game)
# ----------------------------

# Max times a single match can appear across selected parlays (for diversity)
MAX_PARLAYS_PER_MATCH = 2


def parlay_score(parlay: BasketPick) -> float:
    """
    Score a parlay for ranking. Higher = better.
    Uses EV as primary factor with small bonus for higher odds.
    """
    ev = parlay.ev
    odds = parlay.odds
    
    score = ev * 100.0
    
    if 2.0 <= odds <= 10.0:
        score += (odds - 2.0) * 1.0
    
    return score


def select_diverse_parlays(parlays: List[BasketPick], max_parlays: int) -> List[BasketPick]:
    """
    Select parlays with match diversity - limits how many parlays can use the same match.
    Returns up to max_parlays with good spread across different matches.
    """
    from collections import Counter
    
    if not parlays:
        return []
    
    parlays_sorted = sorted(parlays, key=parlay_score, reverse=True)
    
    selected: List[BasketPick] = []
    match_usage: Counter = Counter()
    
    for parlay in parlays_sorted:
        if len(selected) >= max_parlays:
            break
        
        parlay_matches = parlay.meta.get("matches", [])
        
        can_use = True
        for match in parlay_matches:
            if match_usage[match] >= MAX_PARLAYS_PER_MATCH:
                can_use = False
                break
        
        if can_use:
            selected.append(parlay)
            for match in parlay_matches:
                match_usage[match] += 1
    
    return selected


def build_parlays(picks: List[BasketPick], legs: int = 3, min_parlay_ev: float = 0.02) -> List[BasketPick]:
    """
    Builds 3/4-leg multi-game parlays from top singles.
    Ensures only 1 pick per match inside the parlay.
    """
    parlays: List[BasketPick] = []
    if len(picks) < legs:
        return parlays

    best_by_match: Dict[str, BasketPick] = {}
    for p in picks:
        if p.match not in best_by_match or p.ev > best_by_match[p.match].ev:
            best_by_match[p.match] = p

    unique_picks = list(best_by_match.values())

    for combo in combinations(unique_picks, legs):
        odds_prod = 1.0
        prob_prod = 1.0
        matches = []
        selections = []
        markets = []
        base_evs = []
        confs = []

        for p in combo:
            odds_prod *= p.odds
            prob_prod *= p.prob
            matches.append(p.match)
            markets.append(p.market)
            selections.append(p.selection)
            base_evs.append(p.ev)
            confs.append(p.confidence)

        parlay_ev = ev_from_prob_odds(prob_prod, odds_prod)

        if parlay_ev >= min_parlay_ev:
            name = " + ".join([m.split(" vs ")[0] for m in matches])
            parlays.append(
                BasketPick(
                    match=f"PARLAY: {name}",
                    market=f"{legs}-LEG PARLAY",
                    selection=" | ".join(selections),
                    odds=odds_prod,
                    prob=prob_prod,
                    ev=parlay_ev,
                    confidence=min(confs),
                    meta={"legs": legs, "matches": matches, "markets": markets, "base_evs": base_evs},
                )
            )

    parlays.sort(key=lambda x: x.ev, reverse=True)
    return parlays[:10]


# ----------------------------
# College Basket Value Engine
# ----------------------------

class CollegeBasketValueEngine:
    """
    Finds value singles in NCAAB using consensus fair odds.
    """

    def __init__(
        self,
        client: OddsAPIClient,
        min_ev: float = 0.03,
        min_conf: float = 0.50,
        max_singles: int = 10,
        max_parlays: int = 3,
        min_odds: float = 1.40,
        max_odds: float = 5.50,
        allow_parlays: bool = True,
    ):
        self.client = client
        self.min_ev = min_ev
        self.min_conf = min_conf
        self.max_singles = max_singles
        self.max_parlays = max_parlays
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.allow_parlays = allow_parlays

        try:
            from db_connection import DatabaseConnection
            self.db_conn = DatabaseConnection
        except Exception:
            self.db_conn = None

    def generate_value_singles(self) -> List[BasketPick]:
        games = self.client.get_upcoming(
            sport_key="basketball_ncaab",
            markets="h2h,spreads,totals",
            regions="us"
        )

        all_picks: List[BasketPick] = []

        for g in games:
            home = g.get("home_team")
            away = g.get("away_team")
            commence_time = g.get("commence_time", "")
            match_name = f"{home} vs {away}"

            books = g.get("bookmakers", [])
            if not books:
                continue

            # ---------------- H2H (moneyline)
            h2h_books: List[Tuple[float, float]] = []
            best_home = None
            best_away = None

            for b in books:
                for m in b.get("markets", []):
                    if m.get("key") != "h2h":
                        continue
                    outcomes = m.get("outcomes", [])
                    if len(outcomes) != 2:
                        continue
                    o1, o2 = outcomes[0], outcomes[1]
                    if o1["name"] == home:
                        home_odds, away_odds = o1["price"], o2["price"]
                    else:
                        home_odds, away_odds = o2["price"], o1["price"]

                    h2h_books.append((home_odds, away_odds))

                    if (best_home is None) or (home_odds > best_home[0]):
                        best_home = (home_odds, b.get("title", "book"))
                    if (best_away is None) or (away_odds > best_away[0]):
                        best_away = (away_odds, b.get("title", "book"))

            if h2h_books and best_home and best_away:
                fair_p_home, fair_p_away = fair_prob_from_books(h2h_books)

                for side, fair_p, best in [
                    ("Home Win", fair_p_home, best_home),
                    ("Away Win", fair_p_away, best_away),
                ]:
                    odds, book = best
                    if not (self.min_odds <= odds <= self.max_odds):
                        continue
                    ev = ev_from_prob_odds(fair_p, odds)
                    conf = clamp(fair_p, 0.05, 0.95)

                    if ev >= self.min_ev and conf >= self.min_conf:
                        all_picks.append(
                            BasketPick(
                                match=match_name,
                                market="1X2 Moneyline",
                                selection=side,
                                odds=odds,
                                prob=fair_p,
                                ev=ev,
                                confidence=conf,
                                meta={"book": book, "commence_time": commence_time},
                            )
                        )

            # ---------------- SPREADS
            spread_books: Dict[float, List[Tuple[float, float]]] = {}
            best_spread: Dict[Tuple[str, float], Tuple[float, str]] = {}

            for b in books:
                for m in b.get("markets", []):
                    if m.get("key") != "spreads":
                        continue
                    outcomes = m.get("outcomes", [])
                    if len(outcomes) != 2:
                        continue

                    o1, o2 = outcomes[0], outcomes[1]
                    if o1["name"] == home:
                        home_point, home_odds = o1["point"], o1["price"]
                        away_point, away_odds = o2["point"], o2["price"]
                    else:
                        home_point, home_odds = o2["point"], o2["price"]
                        away_point, away_odds = o1["point"], o1["price"]

                    key_line = float(home_point)
                    spread_books.setdefault(key_line, []).append((home_odds, away_odds))

                    if (("home", key_line) not in best_spread) or (home_odds > best_spread[("home", key_line)][0]):
                        best_spread[("home", key_line)] = (home_odds, b.get("title", "book"))
                    if (("away", key_line) not in best_spread) or (away_odds > best_spread[("away", key_line)][0]):
                        best_spread[("away", key_line)] = (away_odds, b.get("title", "book"))

            for line, books_list in spread_books.items():
                fair_p_home, fair_p_away = fair_prob_from_books(books_list)

                if ("home", line) in best_spread:
                    odds, book = best_spread[("home", line)]
                    if self.min_odds <= odds <= self.max_odds:
                        ev = ev_from_prob_odds(fair_p_home, odds)
                        conf = clamp(fair_p_home, 0.05, 0.95)
                        if ev >= self.min_ev and conf >= self.min_conf:
                            all_picks.append(
                                BasketPick(
                                    match=match_name,
                                    market="Spread",
                                    selection=f"{home} {line:+}",
                                    odds=odds,
                                    prob=fair_p_home,
                                    ev=ev,
                                    confidence=conf,
                                    meta={"book": book, "line": line, "commence_time": commence_time},
                                )
                            )

                if ("away", line) in best_spread:
                    odds, book = best_spread[("away", line)]
                    if self.min_odds <= odds <= self.max_odds:
                        ev = ev_from_prob_odds(fair_p_away, odds)
                        conf = clamp(fair_p_away, 0.05, 0.95)
                        if ev >= self.min_ev and conf >= self.min_conf:
                            all_picks.append(
                                BasketPick(
                                    match=match_name,
                                    market="Spread",
                                    selection=f"{away} {-line:+}",
                                    odds=odds,
                                    prob=fair_p_away,
                                    ev=ev,
                                    confidence=conf,
                                    meta={"book": book, "line": line, "commence_time": commence_time},
                                )
                            )

            # ---------------- TOTALS (Over/Under)
            totals_books: Dict[float, List[Tuple[float, float]]] = {}
            best_totals: Dict[Tuple[str, float], Tuple[float, str]] = {}

            for b in books:
                for m in b.get("markets", []):
                    if m.get("key") != "totals":
                        continue
                    outcomes = m.get("outcomes", [])
                    if len(outcomes) != 2:
                        continue

                    o1, o2 = outcomes[0], outcomes[1]
                    if o1["name"].lower().startswith("over"):
                        over_point, over_odds = o1["point"], o1["price"]
                        under_point, under_odds = o2["point"], o2["price"]
                    else:
                        over_point, over_odds = o2["point"], o2["price"]
                        under_point, under_odds = o1["point"], o1["price"]

                    key_line = float(over_point)
                    totals_books.setdefault(key_line, []).append((over_odds, under_odds))

                    if (("over", key_line) not in best_totals) or (over_odds > best_totals[("over", key_line)][0]):
                        best_totals[("over", key_line)] = (over_odds, b.get("title", "book"))
                    if (("under", key_line) not in best_totals) or (under_odds > best_totals[("under", key_line)][0]):
                        best_totals[("under", key_line)] = (under_odds, b.get("title", "book"))

            for line, books_list in totals_books.items():
                fair_p_over, fair_p_under = fair_prob_from_books(books_list)

                if ("over", line) in best_totals:
                    odds, book = best_totals[("over", line)]
                    if self.min_odds <= odds <= self.max_odds:
                        ev = ev_from_prob_odds(fair_p_over, odds)
                        conf = clamp(fair_p_over, 0.05, 0.95)
                        if ev >= self.min_ev and conf >= self.min_conf:
                            all_picks.append(
                                BasketPick(
                                    match=match_name,
                                    market="Totals",
                                    selection=f"Over {line}",
                                    odds=odds,
                                    prob=fair_p_over,
                                    ev=ev,
                                    confidence=conf,
                                    meta={"book": book, "line": line, "commence_time": commence_time},
                                )
                            )

                if ("under", line) in best_totals:
                    odds, book = best_totals[("under", line)]
                    if self.min_odds <= odds <= self.max_odds:
                        ev = ev_from_prob_odds(fair_p_under, odds)
                        conf = clamp(fair_p_under, 0.05, 0.95)
                        if ev >= self.min_ev and conf >= self.min_conf:
                            all_picks.append(
                                BasketPick(
                                    match=match_name,
                                    market="Totals",
                                    selection=f"Under {line}",
                                    odds=odds,
                                    prob=fair_p_under,
                                    ev=ev,
                                    confidence=conf,
                                    meta={"book": book, "line": line, "commence_time": commence_time},
                                )
                            )

        all_picks.sort(key=lambda x: (x.ev, x.confidence), reverse=True)
        
        # Limit singles to max_singles
        singles = all_picks[: self.max_singles]

        if self.allow_parlays and singles:
            # Build parlays from top singles
            top_for_parlay = all_picks[:25]
            parlays_3 = build_parlays(top_for_parlay, legs=3, min_parlay_ev=0.02)
            parlays_4 = build_parlays(top_for_parlay, legs=4, min_parlay_ev=0.03)
            
            # Dynamic parlay limit based on number of singles:
            # 10+ singles → max 5 parlays
            # <10 singles → max 2 parlays
            dynamic_max_parlays = 5 if len(singles) >= 10 else 2
            
            # Combine all parlays and select with match diversity
            # Each match can only appear in MAX_PARLAYS_PER_MATCH parlays
            all_parlays = parlays_3 + parlays_4
            parlays = select_diverse_parlays(all_parlays, dynamic_max_parlays)
            
            # Combine singles and parlays
            value_picks = singles + parlays
        else:
            value_picks = singles

        return value_picks

    def save_picks(self, picks: List[BasketPick]) -> int:
        """
        Saves to PostgreSQL database using basketball_predictions table
        """
        if not picks or self.db_conn is None:
            return 0

        saved = 0
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS basketball_predictions (
                    id SERIAL PRIMARY KEY,
                    match VARCHAR(255) NOT NULL,
                    league VARCHAR(100) DEFAULT 'NCAAB',
                    market VARCHAR(100) NOT NULL,
                    selection VARCHAR(255) NOT NULL,
                    odds DECIMAL(10, 2) NOT NULL,
                    probability DECIMAL(5, 2) NOT NULL,
                    ev_percentage DECIMAL(5, 2) NOT NULL,
                    confidence DECIMAL(5, 2) NOT NULL,
                    commence_time TIMESTAMP,
                    bookmaker VARCHAR(100),
                    is_parlay BOOLEAN DEFAULT FALSE,
                    parlay_legs INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending',
                    UNIQUE(match, market, selection, created_at)
                )
            """)
            conn.commit()
            
            for p in picks:
                try:
                    is_parlay = "PARLAY" in p.match
                    parlay_legs = p.meta.get("legs", 1) if is_parlay else 1
                    commence_time = p.meta.get("commence_time")
                    bookmaker = p.meta.get("book", "Unknown")
                    
                    cursor.execute(
                        """
                        INSERT INTO basketball_predictions
                        (match, league, market, selection, odds, probability, ev_percentage, 
                         confidence, commence_time, bookmaker, is_parlay, parlay_legs, mode)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (match, market, selection, created_at) DO NOTHING
                        """,
                        (
                            p.match,
                            "NCAAB",
                            p.market,
                            p.selection,
                            float(p.odds),
                            float(p.prob) * 100.0,
                            float(p.ev) * 100.0,
                            float(p.confidence) * 100.0,
                            commence_time,
                            bookmaker,
                            is_parlay,
                            parlay_legs,
                            'PROD'  # Production mode
                        )
                    )
                    saved += 1
                except Exception as e:
                    print(f"Error saving pick: {e}")
                    continue
            
            conn.commit()
        
        return saved
