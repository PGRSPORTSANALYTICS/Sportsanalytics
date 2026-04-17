"""
validation_engine.py
====================
The single gate every signal MUST pass before it can become a published pick.

Doctrine (immutable):
  1. NO SHARP = NO SIGNAL
       Sharp = Pinnacle | Betfair | Matchbook.
       Missing sharp price -> signal is REJECTED, not "UNVERIFIED" or "fallback".
  2. APIs are discovery only. They are NEVER allowed as the EV anchor.
  3. Snapshot is mandatory: timestamp, best_price, sharp_price, bookmaker_source.
  4. EV must be computed against the de-vigged sharp probability, never against
     the soft book that holds the placement price.
  5. Cross-line comparisons (e.g. Over 2.5 vs Over 3.0) are forbidden unless
     explicitly interpolated and labeled INTERPOLATED. Default = REJECT.
  6. Stale snapshots (> STALE_SNAPSHOT_SECONDS old) are REJECTED.

This module has ONE public surface:

    decision = validate_signal(signal_dict, mode="enforce" | "dry_run")

Returns a `ValidationDecision` dataclass with:
    .allowed         -> bool
    .label           -> "SHARP_CONFIRMED" | "INTERPOLATED" | None
    .reasons         -> list[str]   (why it was rejected, empty if allowed)
    .normalized      -> dict        (the doctrine-compliant fields to persist)

Until the engine is fully wired, callers run with mode="dry_run" which always
returns allowed=True but populates `.would_reject_reasons` so we can audit
real production traffic against the doctrine without losing a single pick.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("validation_engine")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [validation] %(levelname)s %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

# ── Doctrine constants ──────────────────────────────────────────────────────
SHARP_BOOKS: Set[str] = {"Pinnacle", "Betfair", "Matchbook"}

# Anything containing one of these substrings is treated as a sharp aggregate.
# Used for parsing legacy / aggregator strings like "sharp_avg(Pinnacle,Betfair;n=2)".
SHARP_AGG_MARKERS: Set[str] = {"sharp_avg", "Pinnacle", "Betfair", "Matchbook"}

# Sources that look authoritative but are NOT. Hard-banned as anchor.
BANNED_ANCHOR_SOURCES: Set[str] = {
    "api_football", "API-Football", "the_odds_api", "TheOddsAPI",
    "1xBet", "SBO", "Betano", "Unibet", "Unibet (NL)", "Unibet (SE)",
    "Bet365", "Marathonbet", "188Bet", "10Bet", "Coolbet", "Betsson",
    "Casumo", "William Hill", "BetOnline.ag", "LowVig.ag", "GTbets",
    "Superbet", "Smarkets", "Grosvenor", "Nordic Bet",
}

STALE_SNAPSHOT_SECONDS = int(os.getenv("VALIDATION_STALE_SECONDS", "900"))   # 15 min
MIN_SHARP_ODDS = 1.20
MAX_SHARP_ODDS = 30.0
MIN_BEST_ODDS = 1.20
MAX_BEST_ODDS = 30.0


# ── Result type ────────────────────────────────────────────────────────────
@dataclass
class ValidationDecision:
    allowed: bool
    label: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    would_reject_reasons: List[str] = field(default_factory=list)
    normalized: Dict[str, Any] = field(default_factory=dict)

    def as_log(self) -> str:
        if self.allowed and not self.would_reject_reasons:
            return f"OK label={self.label}"
        if self.allowed and self.would_reject_reasons:
            return f"DRY_RUN_WOULD_REJECT reasons={self.would_reject_reasons}"
        return f"REJECTED reasons={self.reasons}"


# ── Helpers ────────────────────────────────────────────────────────────────
def _is_sharp_book(name: Optional[str]) -> bool:
    if not name:
        return False
    if name in SHARP_BOOKS:
        return True
    # Tolerate sharp aggregate strings like "sharp_avg(Pinnacle,Matchbook;n=2)"
    return any(m in name for m in SHARP_AGG_MARKERS)


def _is_banned_anchor(name: Optional[str]) -> bool:
    if not name:
        return False
    return name in BANNED_ANCHOR_SOURCES


def _devig_two_way(p_a: float, p_b: float) -> float:
    """Power-method de-vig for a 2-way market. Returns the de-vigged prob of side A."""
    if p_a <= 0 or p_b <= 0:
        return p_a
    s = p_a + p_b
    if s <= 0:
        return p_a
    return p_a / s


# ── Core API ───────────────────────────────────────────────────────────────
def validate_signal(signal: Dict[str, Any], mode: str = "dry_run") -> ValidationDecision:
    """
    Validate a candidate signal against the doctrine.

    Required keys in `signal`:
        match_id, market, selection
        best_price, best_price_book              (placement price, can be soft)
        sharp_price, sharp_book                  (anchor price, MUST be sharp)
        timestamp_utc                            (epoch seconds, when snapshot taken)
        model_prob                               (model's true prob estimate)

    Optional:
        line / point                             (for over/under, handicap)
        opposite_sharp_price                     (for de-vig; if absent we skip de-vig)
        cross_line                               (bool, True if we're comparing across
                                                  different points -> forced INTERPOLATED)

    Behaviour:
        mode="dry_run"  -> always returns allowed=True; rejection reasons go to
                           .would_reject_reasons and are logged at WARNING level.
        mode="enforce"  -> returns allowed=False on any doctrine violation.
    """
    reasons: List[str] = []

    # 1. Snapshot completeness
    for required in ("match_id", "market", "selection",
                     "best_price", "best_price_book",
                     "sharp_price", "sharp_book",
                     "timestamp_utc", "model_prob"):
        if signal.get(required) in (None, "", 0, 0.0):
            # 0 odds / 0 prob are also invalid, not just missing keys
            reasons.append(f"missing_or_zero:{required}")

    # 2. Sharp book identity (NO SHARP = NO SIGNAL)
    sharp_book = signal.get("sharp_book")
    if sharp_book and not _is_sharp_book(sharp_book):
        reasons.append(f"sharp_book_not_sharp:{sharp_book}")

    if _is_banned_anchor(sharp_book):
        reasons.append(f"banned_anchor_source:{sharp_book}")

    # 3. Sharp price sanity
    sp = signal.get("sharp_price")
    if isinstance(sp, (int, float)) and sp > 0:
        if sp < MIN_SHARP_ODDS or sp > MAX_SHARP_ODDS:
            reasons.append(f"sharp_price_out_of_range:{sp}")

    # 4. Best price sanity
    bp = signal.get("best_price")
    if isinstance(bp, (int, float)) and bp > 0:
        if bp < MIN_BEST_ODDS or bp > MAX_BEST_ODDS:
            reasons.append(f"best_price_out_of_range:{bp}")

    # 5. Snapshot freshness
    ts = signal.get("timestamp_utc")
    now = int(time.time())
    if isinstance(ts, (int, float)) and ts > 0:
        age = now - int(ts)
        if age > STALE_SNAPSHOT_SECONDS:
            reasons.append(f"snapshot_stale:{age}s")
        if age < -60:
            reasons.append(f"snapshot_in_future:{age}s")

    # 6. Cross-line: forced INTERPOLATED label, never SHARP_CONFIRMED.
    label: Optional[str] = "SHARP_CONFIRMED"
    if signal.get("cross_line") is True:
        label = "INTERPOLATED"
        # Doctrine rule 6: INTERPOLATED is excluded from CLV proof.
        # We allow it as a SIGNAL but mark it.

    # 7. EV must be against the sharp price, not the best (soft) price.
    #    If caller passed a precomputed `edge_pct`, sanity-check direction.
    model_prob = signal.get("model_prob")
    if isinstance(model_prob, (int, float)) and model_prob > 0 and isinstance(sp, (int, float)) and sp > 0:
        sharp_implied = 1.0 / sp
        # Optional de-vig if opposite side present
        opp = signal.get("opposite_sharp_price")
        if isinstance(opp, (int, float)) and opp > 0:
            opp_implied = 1.0 / opp
            sharp_devigged = _devig_two_way(sharp_implied, opp_implied)
        else:
            sharp_devigged = sharp_implied
        edge_vs_sharp = (model_prob - sharp_devigged) * 100.0
        signal["_computed_edge_vs_sharp"] = round(edge_vs_sharp, 3)
        signal["_sharp_devigged_prob"] = round(sharp_devigged, 6)

        passed_edge = signal.get("edge_pct")
        if isinstance(passed_edge, (int, float)):
            # If the engine handed us an edge that disagrees with sharp-anchored
            # truth by more than 3pp, that's almost certainly soft-anchored EV.
            if abs(passed_edge - edge_vs_sharp) > 3.0:
                reasons.append(
                    f"edge_mismatch_vs_sharp: passed={passed_edge:.2f} "
                    f"sharp_truth={edge_vs_sharp:.2f}"
                )

    # ── Build decision ──────────────────────────────────────────────────────
    normalized = {
        "best_price_book":          signal.get("best_price_book"),
        "best_price":               signal.get("best_price"),
        "sharp_book_at_detection":  signal.get("sharp_book"),
        "sharp_price_at_detection": signal.get("sharp_price"),
        "pinny_open_odds":          signal.get("sharp_price") if signal.get("sharp_book") == "Pinnacle" else None,
        "pinny_open_ts":            signal.get("timestamp_utc") if signal.get("sharp_book") == "Pinnacle" else None,
        "confidence_label":         label if not reasons else None,
        "signal_status":            "VERIFIED" if not reasons else "REJECTED",
    }

    if mode == "dry_run":
        decision = ValidationDecision(
            allowed=True,
            label=label,
            reasons=[],
            would_reject_reasons=reasons,
            normalized=normalized,
        )
        if reasons:
            logger.warning(
                f"DRY_RUN would reject {signal.get('match_id')} "
                f"{signal.get('market')}/{signal.get('selection')}: {reasons}"
            )
        return decision

    # enforce mode
    if reasons:
        logger.warning(
            f"REJECT {signal.get('match_id')} "
            f"{signal.get('market')}/{signal.get('selection')}: {reasons}"
        )
        return ValidationDecision(
            allowed=False,
            label=None,
            reasons=reasons,
            normalized=normalized,
        )

    return ValidationDecision(
        allowed=True,
        label=label,
        reasons=[],
        normalized=normalized,
    )


# ── Convenience: single-call assertion guard ───────────────────────────────
def assert_publishable(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strict guard for the publishing layer. Raises if signal is not SHARP_CONFIRMED.
    Use this at the absolute last step before a Discord/UI write.
    """
    decision = validate_signal(signal, mode="enforce")
    if not decision.allowed:
        raise ValueError(f"signal blocked by validation_engine: {decision.reasons}")
    if decision.label != "SHARP_CONFIRMED":
        raise ValueError(f"signal label {decision.label} is not publishable")
    return decision.normalized


__all__ = [
    "ValidationDecision",
    "validate_signal",
    "assert_publishable",
    "SHARP_BOOKS",
    "BANNED_ANCHOR_SOURCES",
    "STALE_SNAPSHOT_SECONDS",
]
