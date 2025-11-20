#!/usr/bin/env python3
"""
En fristående Value Singles-motor.
Just nu kör vi med testdata – sen kan vi koppla den mot din riktiga matchdata.
"""

from typing import List, Dict


def find_value_singles(
    matches: List[Dict],
    min_odds: float = 1.75,
    max_odds: float = 2.10,
    min_ev: float = 0.05,
) -> List[Dict]:
    """
    Hittar value singlar på 1X2-marknaden.

    Varje match-dict förväntas ha:
      - home_team
      - away_team
      - league
      - kickoff
      - prob_home, prob_draw, prob_away   (modellens sannolikheter 0–1)
      - odds_home, odds_draw, odds_away   (bookmaker-odds)
    """

    picks: List[Dict] = []

    for m in matches:
        league = m["league"]
        home = m["home_team"]
        away = m["away_team"]
        kickoff = m["kickoff"]

        prob_home = float(m["prob_home"])
        prob_draw = float(m["prob_draw"])
        prob_away = float(m["prob_away"])

        odds_home = float(m["odds_home"])
        odds_draw = float(m["odds_draw"])
        odds_away = float(m["odds_away"])

        # Helper-funktion internt
        def _check(side: str, prob: float, odds: float):
            if odds < min_odds or odds > max_odds:
                return None
            ev = prob * odds - 1.0
            if ev < min_ev:
                return None
            return {
                "bet_type": "value_single",
                "side": side,          # "home", "draw", "away"
                "selection": {
                    "home": home,
                    "draw": "Draw",
                    "away": away,
                }[side],
                "league": league,
                "home_team": home,
                "away_team": away,
                "odds": round(odds, 2),
                "model_prob": round(prob, 3),
                "ev": round(ev, 3),
                "kickoff": kickoff,
            }

        for side, prob, odds in [
            ("home", prob_home, odds_home),
            ("draw", prob_draw, odds_draw),
            ("away", prob_away, odds_away),
        ]:
            pick = _check(side, prob, odds)
            if pick:
                picks.append(pick)

    return picks


if __name__ == "__main__":
    # Enkel testkörning med fejkdata – bara för att se att motorn funkar
    test_matches = [
        {
            "league": "Premier League",
            "home_team": "Liverpool",
            "away_team": "Arsenal",
            "kickoff": "2025-11-21 20:00",
            "prob_home": 0.55,
            "prob_draw": 0.23,
            "prob_away": 0.22,
            "odds_home": 1.90,
            "odds_draw": 3.70,
            "odds_away": 4.10,
        },
        {
            "league": "La Liga",
            "home_team": "Real Madrid",
            "away_team": "Sevilla",
            "kickoff": "2025-11-21 21:00",
            "prob_home": 0.70,
            "prob_draw": 0.18,
            "prob_away": 0.12,
            "odds_home": 1.40,  # för lågt, ska filtreras bort
            "odds_draw": 4.20,
            "odds_away": 7.00,
        },
    ]

    picks = find_value_singles(test_matches)
    print("Value singles hittade:")
    for p in picks:
        print(
            f"{p['league']} | {p['home_team']} - {p['away_team']} | "
            f"{p['selection']} @ {p['odds']} (EV {p['ev']*100:.1f}%, "
            f"P={p['model_prob']*100:.1f}%)"
        )
