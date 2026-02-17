import os
import logging
import requests
from typing import Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

SMART_ODDS_MIN = 1.70
SMART_ODDS_MAX = 2.00


def devig_two_way(odds_a: float, odds_b: float) -> Tuple[float, float]:
    pa = 1.0 / odds_a
    pb = 1.0 / odds_b
    s = pa + pb
    if s <= 0:
        return 0.5, 0.5
    return pa / s, pb / s


def fair_prob_from_books(two_way_books: List[Tuple[float, float]]) -> Tuple[float, float]:
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
    return p * (odds - 1.0) - (1.0 - p)


def fetch_ncaab_moneyline_smart_picks() -> List[dict]:
    api_key = os.getenv("THE_ODDS_API_KEY")
    if not api_key:
        logger.warning("THE_ODDS_API_KEY not set")
        return []

    url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
    params = {
        "apiKey": api_key,
        "regions": "us,eu,uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            logger.error(f"Odds API error: {r.status_code}")
            return []
        events = r.json()
    except Exception as e:
        logger.error(f"Error fetching NCAAB odds: {e}")
        return []

    smart_picks = []

    for event in events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        commence = event.get("commence_time", "")
        bookmakers = event.get("bookmakers", [])

        if not bookmakers:
            continue

        h2h_books = []
        best_home = None
        best_away = None
        home_by_book = {}
        away_by_book = {}

        for b in bookmakers:
            book_name = b.get("title", "")
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
                home_by_book[book_name] = home_odds
                away_by_book[book_name] = away_odds

                if best_home is None or home_odds > best_home[0]:
                    best_home = (home_odds, book_name)
                if best_away is None or away_odds > best_away[0]:
                    best_away = (away_odds, book_name)

        if not h2h_books or not best_home or not best_away:
            continue

        fair_p_home, fair_p_away = fair_prob_from_books(h2h_books)

        for side, fair_p, best, odds_by_book in [
            ("Home Win", fair_p_home, best_home, home_by_book),
            ("Away Win", fair_p_away, best_away, away_by_book),
        ]:
            best_odds, best_book = best
            if not (SMART_ODDS_MIN <= best_odds <= SMART_ODDS_MAX):
                continue

            ev = ev_from_prob_odds(fair_p, best_odds)

            team_name = home if side == "Home Win" else away

            sorted_books = sorted(odds_by_book.items(), key=lambda x: x[1], reverse=True)

            smart_picks.append({
                'match': f"{home} vs {away}",
                'home_team': home,
                'away_team': away,
                'selection': side,
                'team': team_name,
                'odds': best_odds,
                'best_bookmaker': best_book,
                'probability': round(fair_p * 100, 1),
                'ev_percentage': round(ev * 100, 1),
                'commence_time': commence,
                'odds_by_bookmaker': dict(sorted_books[:5]),
                'bookmaker_count': len(odds_by_book),
            })

    smart_picks.sort(key=lambda x: x['probability'], reverse=True)

    return smart_picks
