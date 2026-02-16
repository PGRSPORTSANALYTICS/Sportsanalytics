"""
PGR Module 2 — Fair Odds Engine (Model → Probabilities)
=========================================================
Converts model outputs into probabilities per market,
applies rolling calibration by league+market, computes confidence.

fair_odds = 1 / probability
Calibration: rolling by league+market with global fallback.
"""

import math
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from db_helper import db_helper
from pgr_models import FairOddsResult

logger = logging.getLogger(__name__)

CALIBRATION_CACHE: Dict[str, Dict] = {}
CALIBRATION_CACHE_TS = 0
CALIBRATION_CACHE_TTL = 3600

MIN_LEAGUE_SAMPLE = 30
GLOBAL_SHRINK_WEIGHT = 0.15


def _load_calibration_data():
    global CALIBRATION_CACHE, CALIBRATION_CACHE_TS
    import time
    now = time.time()
    if CALIBRATION_CACHE and (now - CALIBRATION_CACHE_TS) < CALIBRATION_CACHE_TTL:
        return

    try:
        rows = []
        try:
            rows = db_helper.execute("""
                SELECT league, market, 
                       COUNT(*) as n,
                       AVG(CASE WHEN result IN ('won','win') THEN 1 ELSE 0 END) as actual_rate,
                       AVG(model_prob) as avg_model_prob,
                       AVG(calibrated_prob) as avg_calibrated_prob
                FROM football_opportunities
                WHERE status = 'settled'
                AND model_prob IS NOT NULL AND model_prob > 0
                AND mode != 'TEST'
                GROUP BY league, market
                HAVING COUNT(*) >= 10
            """, fetch='all') or []
        except Exception:
            pass

        if not rows:
            rows = db_helper.execute("""
                SELECT league_id, market_type,
                       COUNT(*) as n,
                       AVG(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as actual_rate,
                       AVG(model_prob) as avg_model_prob,
                       AVG(model_prob) as avg_calibrated_prob
                FROM pgr_bet_lifecycle
                WHERE status = 'settled'
                AND model_prob IS NOT NULL AND model_prob > 0
                GROUP BY league_id, market_type
                HAVING COUNT(*) >= 10
            """, fetch='all') or []

        CALIBRATION_CACHE.clear()
        for r in rows:
            league = r[0] or 'Unknown'
            market = r[1] or 'Unknown'
            key = f"{league}|{market}"
            n = r[2]
            actual = float(r[3]) if r[3] else 0
            model_avg = float(r[4]) if r[4] else 0

            if model_avg > 0 and actual > 0:
                cal_factor = actual / model_avg
            else:
                cal_factor = 1.0

            CALIBRATION_CACHE[key] = {
                'n': n,
                'actual_rate': actual,
                'model_avg_prob': model_avg,
                'calibration_factor': cal_factor,
            }

        CALIBRATION_CACHE_TS = now
        logger.info(f"Loaded calibration data for {len(CALIBRATION_CACHE)} league+market combos")
    except Exception as e:
        logger.error(f"Error loading calibration: {e}")


def _get_global_calibration() -> float:
    _load_calibration_data()
    if not CALIBRATION_CACHE:
        return 1.0
    factors = [v['calibration_factor'] for v in CALIBRATION_CACHE.values() if v['n'] >= MIN_LEAGUE_SAMPLE]
    if not factors:
        factors = [v['calibration_factor'] for v in CALIBRATION_CACHE.values()]
    return sum(factors) / len(factors) if factors else 1.0


def calibrate_probability(model_prob: float, league_id: str, market_type: str) -> Tuple[float, str]:
    _load_calibration_data()

    key = f"{league_id}|{market_type}"
    cal_data = CALIBRATION_CACHE.get(key)

    if cal_data and cal_data['n'] >= MIN_LEAGUE_SAMPLE:
        league_factor = cal_data['calibration_factor']
        global_factor = _get_global_calibration()
        blended = (1 - GLOBAL_SHRINK_WEIGHT) * league_factor + GLOBAL_SHRINK_WEIGHT * global_factor
        calibrated = model_prob * blended
        source = f"league+market ({cal_data['n']} bets)"
    elif cal_data:
        global_factor = _get_global_calibration()
        league_weight = cal_data['n'] / MIN_LEAGUE_SAMPLE
        blended = league_weight * cal_data['calibration_factor'] + (1 - league_weight) * global_factor
        calibrated = model_prob * blended
        source = f"blended ({cal_data['n']} bets)"
    else:
        global_factor = _get_global_calibration()
        calibrated = model_prob * global_factor
        source = "global"

    calibrated = max(0.01, min(0.99, calibrated))
    return calibrated, source


def compute_confidence(model_prob: float, league_id: str, market_type: str,
                       market_dispersion: float = 0.0,
                       league_sample: int = 0) -> Tuple[float, str, float, float]:
    uncertainty = abs(model_prob - 0.5)
    uncertainty_score = 1.0 - (uncertainty * 2)

    if league_sample >= 100:
        data_quality = 1.0
    elif league_sample >= 50:
        data_quality = 0.8
    elif league_sample >= 20:
        data_quality = 0.6
    else:
        data_quality = 0.4

    disp_penalty = min(market_dispersion * 5, 0.3) if market_dispersion > 0 else 0

    prob_strength = 0.0
    if model_prob > 0.65 or model_prob < 0.35:
        prob_strength = 0.2
    elif model_prob > 0.55 or model_prob < 0.45:
        prob_strength = 0.1

    confidence = max(0.1, min(1.0,
        0.3 * (1 - uncertainty_score) +
        0.3 * data_quality +
        0.2 * prob_strength +
        0.2 * (1 - disp_penalty)
    ))

    if confidence >= 0.7:
        badge = "HIGH"
    elif confidence >= 0.45:
        badge = "MEDIUM"
    else:
        badge = "LOW"

    volatility = market_dispersion * 100

    return confidence, badge, uncertainty_score, volatility


def compute_fair_odds(event_id: str, market_type: str, selection: str,
                      model_prob: float, league_id: str,
                      line: float = None,
                      market_dispersion: float = 0.0) -> FairOddsResult:
    if model_prob <= 0 or model_prob >= 1:
        model_prob = max(0.01, min(0.99, model_prob))

    calibrated_prob, cal_source = calibrate_probability(model_prob, league_id, market_type)

    fair = round(1.0 / calibrated_prob, 3)

    _load_calibration_data()
    key = f"{league_id}|{market_type}"
    cal_data = CALIBRATION_CACHE.get(key, {})
    league_sample = cal_data.get('n', 0)

    confidence, badge, uncertainty, volatility = compute_confidence(
        model_prob, league_id, market_type, market_dispersion, league_sample
    )

    return FairOddsResult(
        event_id=event_id,
        market_type=market_type,
        selection=selection,
        line=line,
        model_prob=round(model_prob, 5),
        fair_odds=fair,
        calibrated_prob=round(calibrated_prob, 5),
        calibration_source=cal_source,
        confidence=round(confidence, 3),
        confidence_badge=badge,
        uncertainty=round(uncertainty, 3),
        data_quality=round(1.0 if league_sample >= 100 else league_sample / 100, 2),
        league_sample_size=league_sample,
        market_dispersion=round(market_dispersion, 4),
        volatility=round(volatility, 2),
    )


def persist_fair_odds(result: FairOddsResult) -> bool:
    try:
        db_helper.execute("""
            INSERT INTO pgr_fair_odds
            (event_id, market_type, selection, line, model_prob, fair_odds,
             calibrated_prob, calibration_source, confidence, confidence_badge,
             uncertainty, data_quality, league_sample_size, market_dispersion, volatility)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (event_id, market_type, selection, line)
            DO UPDATE SET
                model_prob = EXCLUDED.model_prob,
                fair_odds = EXCLUDED.fair_odds,
                calibrated_prob = EXCLUDED.calibrated_prob,
                calibration_source = EXCLUDED.calibration_source,
                confidence = EXCLUDED.confidence,
                confidence_badge = EXCLUDED.confidence_badge,
                uncertainty = EXCLUDED.uncertainty,
                data_quality = EXCLUDED.data_quality,
                league_sample_size = EXCLUDED.league_sample_size,
                market_dispersion = EXCLUDED.market_dispersion,
                volatility = EXCLUDED.volatility,
                created_at = NOW()
        """, (
            result.event_id, result.market_type, result.selection, result.line,
            result.model_prob, result.fair_odds,
            result.calibrated_prob, result.calibration_source,
            result.confidence, result.confidence_badge,
            result.uncertainty, result.data_quality,
            result.league_sample_size, result.market_dispersion, result.volatility,
        ))
        return True
    except Exception as e:
        logger.error(f"Persist fair odds error: {e}")
        return False


def batch_compute_fair_odds(event_id: str, market_states: List[Dict],
                            model_probs: Dict[str, float],
                            league_id: str) -> List[FairOddsResult]:
    results = []
    for ms in market_states:
        mkt = ms.get('market_type', '')
        sel = ms.get('selection', '')
        line = ms.get('line')
        disp = ms.get('dispersion', 0)

        prob_key = f"{mkt}|{sel}|{line}"
        model_prob = model_probs.get(prob_key, 0)
        if model_prob <= 0:
            prob_key_simple = f"{mkt}|{sel}"
            model_prob = model_probs.get(prob_key_simple, 0)

        if model_prob <= 0:
            continue

        result = compute_fair_odds(event_id, mkt, sel, model_prob, league_id, line, disp)
        persist_fair_odds(result)
        results.append(result)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = compute_fair_odds(
        event_id="test_001",
        market_type="totals",
        selection="Over",
        model_prob=0.55,
        league_id="Epl",
        line=2.5,
        market_dispersion=0.02,
    )
    print(f"Fair odds result: {result.model_dump()}")
