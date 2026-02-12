"""
Probability Calibrator
=======================
Shrink-to-market calibration to reduce model overconfidence.

The ensemble model tends to overestimate probabilities (points below the
diagonal on calibration plots). This module blends the raw ensemble
probability with the market-implied probability to pull predictions
closer to reality.

Formula:
    market_prob     = 1 / odds_decimal
    calibrated_prob = ENSEMBLE_WEIGHT * ensemble_prob + MARKET_WEIGHT * market_prob
    clamped to [0.02, 0.98]

After calibration, EV is recalculated as:
    EV = calibrated_prob * odds - 1
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ENSEMBLE_WEIGHT = 0.85
MARKET_WEIGHT = 0.15

PROB_FLOOR = 0.02
PROB_CEILING = 0.98


def calibrate_probability(
    ensemble_prob: float,
    odds_decimal: float,
) -> float:
    if odds_decimal < 1.01:
        return max(PROB_FLOOR, min(PROB_CEILING, ensemble_prob))

    market_prob = 1.0 / odds_decimal

    calibrated = ENSEMBLE_WEIGHT * ensemble_prob + MARKET_WEIGHT * market_prob

    calibrated = max(PROB_FLOOR, min(PROB_CEILING, calibrated))

    return round(calibrated, 6)


def calibrated_ev(calibrated_prob: float, odds_decimal: float) -> float:
    return (calibrated_prob * odds_decimal) - 1.0


def calibrate_and_ev(
    ensemble_prob: float,
    odds_decimal: float,
) -> Dict[str, float]:
    cal_prob = calibrate_probability(ensemble_prob, odds_decimal)
    cal_ev = calibrated_ev(cal_prob, odds_decimal)
    raw_ev = (ensemble_prob * odds_decimal) - 1.0

    return {
        'raw_prob': round(ensemble_prob, 6),
        'calibrated_prob': round(cal_prob, 6),
        'raw_ev': round(raw_ev, 6),
        'calibrated_ev': round(cal_ev, 6),
        'prob_shift': round((ensemble_prob - cal_prob) * 100, 2),
    }


def log_calibration_batch(picks: List[Dict], label: str = "VALUE_SINGLES") -> None:
    if not picks:
        return

    raw_probs = []
    cal_probs = []
    raw_evs = []
    cal_evs = []
    big_shift_count = 0

    for p in picks:
        rp = p.get('raw_prob') or p.get('p_model') or 0
        cp = p.get('calibrated_prob') or rp
        re = p.get('raw_ev') or p.get('edge_percentage', 0) / 100 if p.get('edge_percentage') else 0
        ce = p.get('calibrated_ev') or re

        raw_probs.append(rp)
        cal_probs.append(cp)
        raw_evs.append(re)
        cal_evs.append(ce)

        if abs(rp - cp) > 0.05:
            big_shift_count += 1

    n = len(picks)
    avg_raw_p = sum(raw_probs) / n if n else 0
    avg_cal_p = sum(cal_probs) / n if n else 0
    avg_raw_ev = sum(raw_evs) / n if n else 0
    avg_cal_ev = sum(cal_evs) / n if n else 0

    logger.info(
        f"📐 CALIBRATION [{label}] n={n} | "
        f"avg_raw_prob={avg_raw_p:.3f} → avg_cal_prob={avg_cal_p:.3f} | "
        f"avg_raw_ev={avg_raw_ev:.3f} → avg_cal_ev={avg_cal_ev:.3f} | "
        f"big_shifts(>5pp)={big_shift_count}"
    )
