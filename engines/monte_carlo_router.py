"""
Monte Carlo Router
Unified entry point for all sport-specific simulation engines.

Usage
-----
from engines.monte_carlo_router import run_simulation

results = run_simulation("football", {
    "match_id": "abc123",
    "home_xg": 1.45,
    "away_xg": 1.10,
    "odds_map": {"over_2_5": 2.05, "btts_yes": 1.95, "home_win": 2.30},
})
"""
from __future__ import annotations

from typing import Any

from engines import football_mc, hockey_mc, nba_mc, nfl_mc

_SPORT_MAP = {
    "football": football_mc,
    "hockey": hockey_mc,
    "nba": nba_mc,
    "nfl": nfl_mc,
}

MIN_EV = 0.05
MIN_ODDS = 1.70


def run_simulation(sport: str, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Route a simulation request to the correct sport engine.

    Parameters
    ----------
    sport : str
        One of: "football", "hockey", "nba", "nfl".
    inputs : dict
        Keyword arguments forwarded to the engine's run() function.
        Must include "match_id". See each engine module for full parameter docs.

    Returns
    -------
    list of opportunity dicts, filtered to EV >= 0.05 and odds >= 1.70.
    Each dict matches the standard output format:
        {
            "match_id": str,
            "sport": str,
            "market": str,
            "odds": float,
            "model_prob": float,
            "ev": float,
            "edge_score": float,
            "simulation_meta": {
                "n_sims": int,
                "avg_total": float,
                "home_win_prob": float,
                "away_win_prob": float,
            },
            "model_version": "mc_v1_multi_sport",
            "created_at": int (unix epoch),
        }

    Raises
    ------
    ValueError if sport is not supported.
    """
    sport = sport.lower().strip()
    engine = _SPORT_MAP.get(sport)
    if engine is None:
        supported = ", ".join(sorted(_SPORT_MAP.keys()))
        raise ValueError(
            f"Unsupported sport: '{sport}'. Supported: {supported}"
        )

    return engine.run(**inputs)


def supported_sports() -> list[str]:
    """Return list of currently supported sports."""
    return sorted(_SPORT_MAP.keys())
