"""
NFL Monte Carlo Simulation Engine
Hybrid Poisson model: TDs (7 pts) + FGs (3 pts) + small noise for turnovers.
"""
from __future__ import annotations

import time
import numpy as np
from typing import Any

MODEL_VERSION = "mc_v1_multi_sport"
N_SIMS = 10_000
MIN_EV = 0.05
MIN_ODDS = 1.70

_TD_PTS = 7
_FG_PTS = 3
_TURNOVER_NOISE_STD = 1.5


def _ev(model_prob: float, odds: float) -> float:
    return (model_prob * odds) - 1


def _simulate_score(td_rate: float, fg_rate: float, rng: np.random.Generator) -> np.ndarray:
    """Simulate N_SIMS final scores for one team."""
    tds = rng.poisson(td_rate, N_SIMS)
    fgs = rng.poisson(fg_rate, N_SIMS)
    noise = rng.normal(0, _TURNOVER_NOISE_STD, N_SIMS)
    raw = (tds * _TD_PTS) + (fgs * _FG_PTS) + noise
    return np.maximum(raw, 0)


def run(
    match_id: str,
    home_td_rate: float,
    home_fg_rate: float,
    away_td_rate: float,
    away_fg_rate: float,
    spread: float = -3.5,
    total_line: float = 45.5,
    odds_map: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Simulate an NFL game.

    Parameters
    ----------
    match_id : str
    home_td_rate : float    Expected TDs per game for home team.
    home_fg_rate : float    Expected FGs per game for home team.
    away_td_rate : float    Expected TDs per game for away team.
    away_fg_rate : float    Expected FGs per game for away team.
    spread : float          AH spread on home team (negative = home favoured).
    total_line : float      Over/under total line.
    odds_map : dict, optional
        Supported keys: "home_win", "away_win",
                        "over_total", "under_total",
                        "home_spread", "away_spread".
    """
    rng = np.random.default_rng()

    home_score = _simulate_score(home_td_rate, home_fg_rate, rng)
    away_score = _simulate_score(away_td_rate, away_fg_rate, rng)

    home_win_prob = float(np.mean(home_score > away_score))
    away_win_prob = float(np.mean(away_score >= home_score))

    total = home_score + away_score
    avg_total = float(np.mean(total))
    over_total_prob = float(np.mean(total > total_line))
    under_total_prob = 1.0 - over_total_prob

    home_spread_prob = float(np.mean((home_score + spread) > away_score))
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
            "sport": "nfl",
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
