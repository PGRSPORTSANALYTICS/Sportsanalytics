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
from bankroll_manager import get_bankroll_manager
from discord_notifier import send_bet_to_discord


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

from collections import Counter

# Max times a single match can appear across selected parlays (for diversity)
MAX_PARLAYS_PER_MATCH = 2

# ---- PARLAY SCORING SETTINGS (tweakable) ----
EV_WEIGHT = 2.0
MID_ODDS_MIN = 2.0
MID_ODDS_MAX = 6.0
HIGH_ODDS_MIN = 6.0
HIGH_ODDS_MAX = 12.0
MID_ODDS_BONUS = 4.0
HIGH_ODDS_BONUS = 2.0
VERY_HIGH_ODDS_THRESHOLD = 15.0
VERY_HIGH_ODDS_PENALTY = 8.0
LEGS_PENALTY_START = 4
LEGS_PENALTY_PER_EXTRA = 1.5
MAX_LEGS_HARD_CAP = 7


def allowed_parlays(num_singles: int) -> int:
    """
    Returns max number of parlays based on how many singles we have.
    Rules:
    - Under 10 singles -> max 2 parlays
    - 10 or more singles -> max 5 parlays
    """
    if num_singles < 10:
        return 2
    return 5


def parlay_score(parlay: BasketPick) -> float:
    """
    Score a parlay for ranking. Higher = better.
    Uses EV, odds bonuses/penalties, and leg count penalties.
    """
    ev = parlay.ev
    odds = parlay.odds
    legs = parlay.meta.get("legs", 3)
    
    # Hard cap on legs
    if legs > MAX_LEGS_HARD_CAP:
        return -999.0
    
    # Base score from EV
    score = ev * 100.0 * EV_WEIGHT
    
    # Odds bonuses
    if MID_ODDS_MIN <= odds <= MID_ODDS_MAX:
        score += MID_ODDS_BONUS
    elif HIGH_ODDS_MIN < odds <= HIGH_ODDS_MAX:
        score += HIGH_ODDS_BONUS
    
    # Very high odds penalty
    if odds >= VERY_HIGH_ODDS_THRESHOLD:
        score -= VERY_HIGH_ODDS_PENALTY
    
    # Leg count penalty (starts at 4+ legs)
    if legs > LEGS_PENALTY_START:
        extra_legs = legs - LEGS_PENALTY_START
        score -= extra_legs * LEGS_PENALTY_PER_EXTRA
    
    return score


def pick_parlays_for_today(
    num_singles: int,
    parlay_candidates: List[BasketPick],
) -> List[BasketPick]:
    """
    Selects which parlays to use today based on:
    - How many singles we have (determines max parlays)
    - Max parlays per match (to avoid too much reuse)
    - Score (EV/odds) so we pick the best first
    """
    max_parlays = allowed_parlays(num_singles)
    
    if max_parlays <= 0 or not parlay_candidates:
        return []
    
    sorted_candidates = sorted(
        parlay_candidates,
        key=parlay_score,
        reverse=True,
    )
    
    selected: List[BasketPick] = []
    match_usage: Counter = Counter()
    
    for parlay in sorted_candidates:
        if len(selected) >= max_parlays:
            break
        
        parlay_matches = parlay.meta.get("matches", [])
        
        if any(match_usage[m] >= MAX_PARLAYS_PER_MATCH for m in parlay_matches):
            continue
        
        selected.append(parlay)
        for m in parlay_matches:
            match_usage[m] += 1
    
    return selected


def build_parlays(picks: List[BasketPick], legs: int = 3, min_parlay_ev: float = 0.02, max_parlay_odds: float = 50.0) -> List[BasketPick]:
    """
    Builds 3/4-leg multi-game parlays from top singles.
    Ensures only 1 pick per match inside the parlay.
    Caps parlay odds to max_parlay_odds to avoid unrealistic longshots.
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

        # Skip parlays with unrealistic odds (lottery tickets)
        if odds_prod > max_parlay_odds:
            continue

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
    NOVA v2.0 - College Basketball Value Engine (Dec 9, 2025)
    Finds value singles in NCAAB using consensus fair odds.
    Retuned for higher volume while maintaining quality.
    """

    def __init__(
        self,
        client: OddsAPIClient,
        min_ev: float = 0.015,      # 1.5% EV - increased volume
        min_conf: float = 0.52,     # 52% confidence - aligned with football L2
        max_singles: int = 12,      # Increased from 10
        max_parlays: int = 3,
        min_odds: float = 1.40,     # Kept at 1.40
        max_odds: float = 3.00,     # Kept at 3.00 (AI-learned)
        allow_parlays: bool = False,  # DISABLED - parlays losing money
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
        
        # DEDUP: Keep only the best EV bet per game
        best_by_match: Dict[str, BasketPick] = {}
        for pick in all_picks:
            if pick.match not in best_by_match:
                best_by_match[pick.match] = pick
            elif pick.ev > best_by_match[pick.match].ev:
                best_by_match[pick.match] = pick
        
        # Get unique picks (one per game, best EV)
        unique_picks = list(best_by_match.values())
        unique_picks.sort(key=lambda x: (x.ev, x.confidence), reverse=True)
        
        # Limit singles to max_singles
        singles = unique_picks[: self.max_singles]

        if self.allow_parlays and singles:
            # Build parlays from unique picks (already deduped - one per game)
            top_for_parlay = unique_picks[:25]
            parlays_3 = build_parlays(top_for_parlay, legs=3, min_parlay_ev=0.02)
            parlays_4 = build_parlays(top_for_parlay, legs=4, min_parlay_ev=0.03)
            
            # Combine all parlay candidates
            all_parlays = parlays_3 + parlays_4
            
            # Select parlays with diversity constraints:
            # - Uses allowed_parlays() for dynamic limit (2 if <10 singles, else 5)
            # - Each match can only appear in MAX_PARLAYS_PER_MATCH parlays
            # - Picks best by score (EV + odds bonus)
            parlays = pick_parlays_for_today(len(singles), all_parlays)
            
            # Combine singles and parlays
            value_picks = singles + parlays
        else:
            value_picks = singles

        return value_picks

    def save_picks(self, picks: List[BasketPick]) -> int:
        """
        Saves to PostgreSQL database using basketball_predictions table
        Enforces DAILY LIMITS: max 15 singles + 3 parlays per day (total 18 bets)
        """
        if not picks or self.db_conn is None:
            return 0

        # Check bankroll before saving any bets
        try:
            bankroll_mgr = get_bankroll_manager()
        except Exception as e:
            print(f"⚠️ Bankroll manager init failed: {e}")
            bankroll_mgr = None

        saved = 0
        bets_placed = 0
        
        # DAILY LIMIT CHECK - Count already placed bets TODAY
        with self.db_conn.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN is_parlay = false AND bet_placed = true THEN 1 ELSE 0 END), 0) as singles_today,
                    COALESCE(SUM(CASE WHEN is_parlay = true AND bet_placed = true THEN 1 ELSE 0 END), 0) as parlays_today
                FROM basketball_predictions
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            row = cursor.fetchone()
            singles_today = int(row[0]) if row else 0
            parlays_today = int(row[1]) if row else 0
        
        singles_remaining = max(0, self.max_singles - singles_today)
        parlays_remaining = max(0, self.max_parlays - parlays_today)
        
        print(f"📊 Daily limits: Singles {singles_today}/{self.max_singles}, Parlays {parlays_today}/{self.max_parlays}")
        print(f"   Remaining: {singles_remaining} singles, {parlays_remaining} parlays")
        
        if singles_remaining == 0 and parlays_remaining == 0:
            print("⛔ DAILY LIMIT REACHED - No more basketball bets today")
            return 0

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
                    bet_placed BOOLEAN DEFAULT TRUE,
                    UNIQUE(match, market, selection, created_at)
                )
            """)
            conn.commit()
            
            singles_placed = 0
            parlays_placed = 0
            
            for p in picks:
                is_parlay = "PARLAY" in p.match
                
                # DAILY LIMIT CHECK - Skip if we've hit the daily limit for this type
                if is_parlay and parlays_placed >= parlays_remaining:
                    print(f"⏭️ DAILY LIMIT: Skipping parlay {p.match} (already have {parlays_today + parlays_placed})")
                    continue
                if not is_parlay and singles_placed >= singles_remaining:
                    print(f"⏭️ DAILY LIMIT: Skipping single {p.match} (already have {singles_today + singles_placed})")
                    continue
                
                # Calculate 1.6% Kelly stake of bankroll
                kelly_stake = 160  # default fallback
                if bankroll_mgr:
                    current_bankroll = bankroll_mgr.get_current_bankroll()
                    kelly_stake = round(current_bankroll * 0.016, 2)  # 1.6% Kelly
                
                # Bankroll check for each pick - determines if actual bet placed
                bet_placed = True
                if bankroll_mgr:
                    can_bet, reason = bankroll_mgr.can_place_bet(kelly_stake)
                    if not can_bet:
                        bet_placed = False
                        print(f"⛔ BANKROLL LIMIT: {reason} - Saving prediction only (no bet)")
                
                try:
                    parlay_legs = p.meta.get("legs", 1) if is_parlay else 1
                    commence_time = p.meta.get("commence_time")
                    bookmaker = p.meta.get("book", "Unknown")
                    
                    # Check if this exact pick already exists (same match, market, selection)
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM basketball_predictions
                        WHERE match = %s AND market = %s AND selection = %s
                        AND DATE(created_at) = CURRENT_DATE
                        """,
                        (p.match, p.market, p.selection)
                    )
                    if cursor.fetchone()[0] > 0:
                        print(f"⏭️ DUPLICATE: Skipping {p.match} {p.selection} (already saved today)")
                        continue
                    
                    cursor.execute(
                        """
                        INSERT INTO basketball_predictions
                        (match, league, market, selection, odds, probability, ev_percentage, 
                         confidence, commence_time, bookmaker, is_parlay, parlay_legs, mode, bet_placed)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                            'PROD',  # Production mode
                            bet_placed
                        )
                    )
                    saved += 1
                    if bet_placed:
                        bets_placed += 1
                        if is_parlay:
                            parlays_placed += 1
                        else:
                            singles_placed += 1
                        print(f"✅ BET PLACED: {p.match} -> {p.selection} @ {p.odds:.2f}")
                        try:
                            product_type = "BASKET_PARLAY" if is_parlay else "BASKET_SINGLE"
                            send_bet_to_discord({
                                'league': 'NCAAB',
                                'home_team': p.match.split(' vs ')[0] if ' vs ' in p.match else p.match,
                                'away_team': p.match.split(' vs ')[1] if ' vs ' in p.match else '',
                                'match_date': str(commence_time) if commence_time else '',
                                'product': product_type,
                                'selection': p.selection,
                                'odds': p.odds,
                                'ev': p.ev * 100,
                                'stake': kelly_stake
                            }, product_type=product_type)
                        except Exception as e:
                            print(f"Discord notification failed: {e}")
                    else:
                        print(f"📊 PREDICTION ONLY: {p.match} -> {p.selection} @ {p.odds:.2f}")
                except Exception as e:
                    print(f"Error saving pick: {e}")
                    continue
            
            conn.commit()
        
        print(f"📈 Basketball: {saved} predictions saved, {bets_placed} bets placed")
        return saved
