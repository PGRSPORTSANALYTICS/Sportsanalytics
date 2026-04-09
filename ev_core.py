"""
ev_core.py — Single source of truth for all EV/edge calculations.

THREE distinct metrics — never mix them:

  EV%          = model_prob × (odds − 1) − (1 − model_prob)  → return per unit staked
  EDGE_FAIR%   = (book_odds / fair_odds − 1) × 100           → how much better than no-vig line
  PROB_EDGE%   = (model_prob − implied_prob) × 100           → raw probability gap

Always label which metric you're showing.
"""
from __future__ import annotations


def ev_pct(model_prob: float, decimal_odds: float) -> float:
    """
    EV expressed as percentage.
    Equivalent to (p * odds - 1) * 100 — the industry-standard formula.

    Example:
        model_prob=0.52, odds=2.20 → (0.52 × 2.20 − 1) × 100 = +14.4%
    """
    if model_prob <= 0 or decimal_odds <= 1.0:
        return 0.0
    return round((model_prob * decimal_odds - 1.0) * 100, 3)


def ev_decimal(model_prob: float, decimal_odds: float) -> float:
    """Same as ev_pct but as a decimal (0.144 instead of 14.4)."""
    return ev_pct(model_prob, decimal_odds) / 100.0


def edge_vs_fair(book_odds: float, fair_odds: float) -> float:
    """
    How much better the available odds are compared to the no-vig fair price.
    Positive = book is offering above fair value.

    Example:
        book_odds=2.20, fair_odds=2.10 → (2.20/2.10 − 1) × 100 = +4.8%
    """
    if fair_odds <= 1.0 or book_odds <= 1.0:
        return 0.0
    return round(((book_odds / fair_odds) - 1.0) * 100, 3)


def prob_gap(model_prob: float, book_odds: float) -> float:
    """
    Raw difference between model probability and bookmaker implied probability.

    Example:
        model_prob=0.52, book_odds=2.20 → (0.52 − 1/2.20) × 100 = +6.5%
    """
    if book_odds <= 1.0:
        return 0.0
    implied = 1.0 / book_odds
    return round((model_prob - implied) * 100, 3)


def devig_two_way(odds_a: float, odds_b: float) -> tuple[float, float]:
    """
    Remove bookmaker margin from a two-way market.
    Returns (fair_prob_a, fair_prob_b) — they sum to 1.0.
    """
    if odds_a <= 1.0 or odds_b <= 1.0:
        return 0.5, 0.5
    pa = 1.0 / odds_a
    pb = 1.0 / odds_b
    total = pa + pb
    return pa / total, pb / total


def fair_prob_consensus(books: list[tuple[float, float]]) -> tuple[float, float]:
    """
    Consensus fair probability from multiple bookmaker two-way lines.
    Returns average devigged (prob_a, prob_b).
    """
    if not books:
        return 0.5, 0.5
    pas, pbs = [], []
    for oa, ob in books:
        pa, pb = devig_two_way(oa, ob)
        pas.append(pa)
        pbs.append(pb)
    return sum(pas) / len(pas), sum(pbs) / len(pbs)


def kelly_fraction(model_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly fraction. Always apply a safety multiplier (e.g. 0.25) before sizing.
    Returns 0 if negative.

    Formula: (p × odds − 1) / (odds − 1)
    """
    if model_prob <= 0 or decimal_odds <= 1.0:
        return 0.0
    k = (model_prob * decimal_odds - 1.0) / (decimal_odds - 1.0)
    return max(0.0, round(k, 6))


def confidence_tier(raw_confidence: float) -> str:
    """
    Convert a raw confidence score into a human-readable tier.

    Args:
        raw_confidence: Either 0–1 decimal (0.72) or 0–100 integer (72).
                        Both formats are handled.

    Returns:
        "HIGH", "MEDIUM", or "LOW"

    Mapping:
        >= 0.75  →  HIGH   (stable markets, top leagues, strong model agreement)
        >= 0.60  →  MEDIUM (semi-stable)
        < 0.60   →  LOW    (volatile: props, alt lines, small leagues)
    """
    v = raw_confidence / 100.0 if raw_confidence > 1.0 else raw_confidence
    if v >= 0.75:
        return "HIGH"
    if v >= 0.60:
        return "MEDIUM"
    return "LOW"


def clv_pct(open_odds: float, closing_odds: float) -> float:
    """
    Closing Line Value — did you beat the market?
    Positive = you got better price than what the market settled at.

    Formula: (closing_odds / open_odds − 1) × 100
    Note: CLV uses closing as baseline, so numerator is closing.
    """
    if open_odds <= 1.0 or closing_odds <= 1.0:
        return 0.0
    return round(((closing_odds / open_odds) - 1.0) * 100, 3)


def verify(model_prob: float, decimal_odds: float, fair_odds: float | None = None) -> dict:
    """
    Return a full breakdown of every metric for a single bet.
    Use this to audit/debug any pick.

    Args:
        model_prob:   Our model's win probability (0–1)
        decimal_odds: Best available decimal odds
        fair_odds:    No-vig fair odds (optional; from devigging market)

    Returns dict with EV%, edge_fair%, prob_gap%, kelly, implied_prob, vig_pct
    """
    implied = 1.0 / decimal_odds if decimal_odds > 1.0 else 0.0
    result = {
        "model_prob":     round(model_prob, 4),
        "decimal_odds":   decimal_odds,
        "implied_prob":   round(implied, 4),
        "ev_pct":         ev_pct(model_prob, decimal_odds),
        "prob_gap_pct":   prob_gap(model_prob, decimal_odds),
        "kelly_full":     kelly_fraction(model_prob, decimal_odds),
        "kelly_quarter":  round(kelly_fraction(model_prob, decimal_odds) * 0.25, 6),
    }
    if fair_odds and fair_odds > 1.0:
        result["fair_odds"] = fair_odds
        result["edge_fair_pct"] = edge_vs_fair(decimal_odds, fair_odds)
    return result


def calibrated_ev_pct(
    raw_ev: float,
    market: str = "",
    league: str = "",
    odds: float = 0.0,
) -> dict:
    """
    Wrapper around model_calibrator.calibrate_ev().
    Returns the calibrated EV figure safe to display publicly.

    Returns:
        {
          "calibrated_ev"  : float  (the shrunk EV%, e.g. 6.1),
          "shrink_factor"  : float,
          "label"          : str    (e.g. "Early calibration (N=23)"),
          "phase"          : int,
          "n"              : int,
        }
    """
    try:
        from model_calibrator import calibrate_ev
        return calibrate_ev(raw_ev=raw_ev, market=market, league=league, odds=odds)
    except ImportError:
        # Fallback if model_calibrator not available
        fallback = round(raw_ev * 0.25, 2)
        return {
            "calibrated_ev": fallback,
            "shrink_factor": 0.25,
            "label": "Early calibration",
            "phase": 1,
            "n": 0,
        }


if __name__ == "__main__":
    print("=== EV Core — self-test ===\n")

    cases = [
        # (label, model_prob, decimal_odds, fair_odds)
        ("Arsenal win  ", 0.52, 2.20, 2.10),
        ("Over 2.5     ", 0.60, 1.85, 1.80),
        ("Exact score 1-0", 0.11, 9.50, None),
        ("BTTS No      ", 0.45, 2.05, 2.00),
    ]

    for label, p, odds, fair in cases:
        r = verify(p, odds, fair)
        print(f"{label} | odds={odds} | model={p:.0%} | "
              f"EV={r['ev_pct']:+.1f}%  "
              f"prob_gap={r['prob_gap_pct']:+.1f}%  "
              + (f"edge_fair={r.get('edge_fair_pct',0):+.1f}%  " if fair else "              ")
              + f"kelly_q={r['kelly_quarter']:.3f}")
