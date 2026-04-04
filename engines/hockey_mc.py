"""
Hockey (NHL) Monte Carlo Simulation Engine
Uses Poisson distribution for goals; overtime coin-flip for drawn games.
"""
from __future__ import annotations

import time
import numpy as np
from typing import Any

MODEL_VERSION = "mc_v1_multi_sport"
N_SIMS = 10_000
MIN_EV = 0.05
MIN_ODDS = 1.70

_OT_LINE = 5.5


def _ev(model_prob: float, odds: float) -> float:
    return (model_prob * odds) - 1


def run(
    match_id: str,
    home_goals_avg: float,
    away_goals_avg: float,
    odds_map: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Simulate an NHL game using Poisson-distributed goals.
    Tied games go to overtime — winner picked with equal probability (50/50 coin flip).

    Parameters
    ----------
    match_id : str
    home_goals_avg : float   Season average goals scored by home team per game.
    away_goals_avg : float   Season average goals scored by away team per game.
    odds_map : dict, optional
        Supported keys: "home_win", "away_win", "over_5_5".
    """
    rng = np.random.default_rng()
    home_goals = rng.poisson(home_goals_avg, N_SIMS)
    away_goals = rng.poisson(away_goals_avg, N_SIMS)
    total_goals = home_goals + away_goals

    draws = home_goals == away_goals
    ot_winner = rng.integers(0, 2, N_SIMS)  # 0 = home, 1 = away

    home_wins = (home_goals > away_goals) | (draws & (ot_winner == 0))
    away_wins = ~home_wins

    home_win_prob = float(np.mean(home_wins))
    away_win_prob = float(np.mean(away_wins))
    over_55_prob = float(np.mean(total_goals > _OT_LINE))
    avg_total = float(np.mean(total_goals))

    simulation_meta = {
        "n_sims": N_SIMS,
        "avg_total": round(avg_total, 2),
        "home_win_prob": round(home_win_prob, 4),
        "away_win_prob": round(away_win_prob, 4),
    }

    odds_map = odds_map or {}

    markets = {
        "home_win": home_win_prob,
        "away_win": away_win_prob,
        "over_5_5": over_55_prob,
    }

    results: list[dict[str, Any]] = []
    ts = int(time.time())

    for market, model_prob in markets.items():
        odds = odds_map.get(market, 0.0)
        if odds < MIN_ODDS:
            continue
        ev = _ev(model_prob, odds)
        if ev < MIN_EV:
            continue

        results.append({
            "match_id": match_id,
            "sport": "hockey",
            "market": market,
            "odds": round(odds, 3),
            "model_prob": round(model_prob, 4),
            "ev": round(ev, 4),
            "edge_score": round(ev * 100, 2),
            "simulation_meta": simulation_meta,
            "model_version": MODEL_VERSION,
            "created_at": ts,
        })

    return results
