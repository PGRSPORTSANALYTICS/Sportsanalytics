"""
NBA Monte Carlo Simulation Engine
Uses Normal distribution for team scoring; overtime if tied.
"""
from __future__ import annotations

import time
import numpy as np
from typing import Any

MODEL_VERSION = "mc_v1_multi_sport"
N_SIMS = 10_000
MIN_EV = 0.05
MIN_ODDS = 1.70

_OT_POINTS = 5.0      # average extra points per OT period per team
_OT_STD = 2.0         # std for OT scoring


def _ev(model_prob: float, odds: float) -> float:
    return (model_prob * odds) - 1


def run(
    match_id: str,
    home_points_avg: float,
    away_points_avg: float,
    home_std: float,
    away_std: float,
    spread: float = -3.5,
    total_line: float = 225.5,
    odds_map: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Simulate an NBA game using Normal-distributed scoring.

    Parameters
    ----------
    match_id : str
    home_points_avg : float     Home team season average points per game.
    away_points_avg : float     Away team season average points per game.
    home_std : float            Std deviation of home team scoring.
    away_std : float            Std deviation of away team scoring.
    spread : float              AH spread applied to home team (e.g. -3.5 means home -3.5).
    total_line : float          Over/under total line (e.g. 225.5).
    odds_map : dict, optional
        Supported keys: "home_win", "away_win",
                        "over_total", "under_total",
                        "home_spread", "away_spread".
    """
    rng = np.random.default_rng()
    home_pts = rng.normal(home_points_avg, home_std, N_SIMS)
    away_pts = rng.normal(away_points_avg, away_std, N_SIMS)

    tied = np.abs(home_pts - away_pts) < 0.5

    ot_home = rng.normal(_OT_POINTS, _OT_STD, N_SIMS)
    ot_away = rng.normal(_OT_POINTS, _OT_STD, N_SIMS)

    final_home = np.where(tied, home_pts + ot_home, home_pts)
    final_away = np.where(tied, away_pts + ot_away, away_pts)

    home_win_prob = float(np.mean(final_home > final_away))
    away_win_prob = 1.0 - home_win_prob

    total = final_home + final_away
    avg_total = float(np.mean(total))

    over_total_prob = float(np.mean(total > total_line))
    under_total_prob = 1.0 - over_total_prob

    home_spread_prob = float(np.mean((final_home + spread) > final_away))
    away_spread_prob = 1.0 - home_spread_prob

    simulation_meta = {
        "n_sims": N_SIMS,
        "avg_total": round(avg_total, 1),
        "home_win_prob": round(home_win_prob, 4),
        "away_win_prob": round(away_win_prob, 4),
    }

    odds_map = odds_map or {}

    markets = {
        "home_win": home_win_prob,
        "away_win": away_win_prob,
        "over_total": over_total_prob,
        "under_total": under_total_prob,
        "home_spread": home_spread_prob,
        "away_spread": away_spread_prob,
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
            "sport": "nba",
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
