"""
Football Monte Carlo Simulation Engine
Uses Poisson distribution to simulate match outcomes.
"""
from __future__ import annotations

import uuid
import time
import numpy as np
from typing import Any

MODEL_VERSION = "mc_v1_multi_sport"
N_SIMS = 10_000
MIN_EV = 0.05
MIN_ODDS = 1.70


def _ev(model_prob: float, odds: float) -> float:
    return (model_prob * odds) - 1


def run(
    match_id: str,
    home_xg: float,
    away_xg: float,
    odds_map: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Simulate a football match using Poisson-distributed goals.

    Parameters
    ----------
    match_id : str
        Unique identifier for the match.
    home_xg : float
        Expected goals for the home team.
    away_xg : float
        Expected goals for the away team.
    odds_map : dict, optional
        Bookmaker odds keyed by market name.
        Supported keys: "over_2_5", "btts_yes", "home_win", "draw", "away_win".
        If not provided, EV is computed against implied odds only.

    Returns
    -------
    list of opportunity dicts — only markets where EV >= MIN_EV and odds >= MIN_ODDS.
    """
    rng = np.random.default_rng()
    home_goals = rng.poisson(home_xg, N_SIMS)
    away_goals = rng.poisson(away_xg, N_SIMS)

    total_goals = home_goals + away_goals

    home_win_prob = float(np.mean(home_goals > away_goals))
    draw_prob = float(np.mean(home_goals == away_goals))
    away_win_prob = float(np.mean(away_goals > home_goals))
    over_25_prob = float(np.mean(total_goals > 2.5))
    btts_prob = float(np.mean((home_goals > 0) & (away_goals > 0)))
    avg_total = float(np.mean(total_goals))

    simulation_meta = {
        "n_sims": N_SIMS,
        "avg_total": round(avg_total, 2),
        "home_win_prob": round(home_win_prob, 4),
        "away_win_prob": round(away_win_prob, 4),
    }

    odds_map = odds_map or {}

    markets = {
        "over_2_5": over_25_prob,
        "btts_yes": btts_prob,
        "home_win": home_win_prob,
        "draw": draw_prob,
        "away_win": away_win_prob,
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
            "sport": "football",
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
