"""
pricing_engine.py
=================
Single source of truth for ALL price/edge calculations.

Doctrine compliance:
  - Sharp anchor = Pinnacle | Betfair | Matchbook (in priority order).
  - If no sharp price exists for a market+selection -> returns None.
    Caller MUST treat None as "signal does not exist" (NO SHARP = NO SIGNAL).
  - Best price = the placement price, taken from any book (incl. soft).
    Used for display and bet-sizing only, NEVER for EV.
  - EV is computed against de-vigged sharp probability when both sides are
    available; otherwise against raw sharp implied probability.

Public API:
    get_sharp_anchor(match, market_key, selection, point=None)
        -> SharpAnchor | None

    get_best_price(match, market_key, selection, point=None,
                   exclude_books=None)
        -> BestPrice | None

    compute_edge_pct(model_prob, sharp_anchor)  -> float
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Priority order matters: if multiple sharps quote the same market,
# we prefer Pinnacle, then Betfair, then Matchbook.
SHARP_PRIORITY: Tuple[str, ...] = ("Pinnacle", "Betfair", "Matchbook")
SHARP_SET = set(SHARP_PRIORITY)


@dataclass
class SharpAnchor:
    book: str                     # "Pinnacle" | "Betfair" | "Matchbook"
    price: float                  # raw decimal odds from sharp
    opposite_price: Optional[float]   # opposite-side sharp price for de-vig (if found)
    implied_prob: float           # raw 1/price
    devigged_prob: float          # de-vigged if opposite found, else == implied_prob
    market_key: str
    selection: str
    point: Optional[float]
    timestamp_utc: int            # epoch sec when this snapshot was taken


@dataclass
class BestPrice:
    book: str
    price: float
    market_key: str
    selection: str
    point: Optional[float]
    timestamp_utc: int


# ── Internal helpers ────────────────────────────────────────────────────────
def _team_match(outcome_name: str, team: str) -> bool:
    if not outcome_name or not team:
        return False
    o = outcome_name.lower().strip()
    t = team.lower().strip()
    return o == t or o in t or t in o


def _outcome_matches(market_key: str, selection: str, outcome: Dict[str, Any],
                     home: str, away: str, point: Optional[float]) -> bool:
    name = outcome.get("name", "")
    pt = outcome.get("point")

    if market_key == "h2h":
        if selection == "Home Win" and _team_match(name, home):
            return True
        if selection == "Away Win" and _team_match(name, away):
            return True
        if selection == "Draw" and name.lower() == "draw":
            return True
        return False

    if market_key == "totals":
        if "Over" in selection and "Over" in name:
            return point is None or pt == point
        if "Under" in selection and "Under" in name:
            return point is None or pt == point
        return False

    if market_key == "btts":
        if "Yes" in selection and name == "Yes":
            return True
        if "No" in selection and name == "No":
            return True
        return False

    if market_key == "spreads":
        if name in selection and (point is None or pt == point):
            return True
        return False

    return False


def _opposite_selection(market_key: str, selection: str) -> Optional[str]:
    """Returns the natural 2-way opposite selection, used for de-vig."""
    if market_key == "totals":
        if "Over" in selection:
            return selection.replace("Over", "Under")
        if "Under" in selection:
            return selection.replace("Under", "Over")
    if market_key == "btts":
        if "Yes" in selection:
            return selection.replace("Yes", "No")
        if "No" in selection:
            return selection.replace("No", "Yes")
    # h2h is 3-way; spreads are 2-way per line. We only de-vig 2-way clean cases.
    return None


def _scan_books(match: Dict[str, Any], market_key: str, selection: str,
                point: Optional[float],
                allowed_books: Optional[Iterable[str]] = None,
                excluded_books: Optional[Iterable[str]] = None) -> List[Tuple[str, float]]:
    home = match.get("home_team", "")
    away = match.get("away_team", "")
    allowed = set(allowed_books) if allowed_books else None
    excluded = set(excluded_books) if excluded_books else set()

    out: List[Tuple[str, float]] = []
    for bm in match.get("bookmakers", []) or []:
        book_name = bm.get("title") or bm.get("key") or "Unknown"
        if allowed is not None and book_name not in allowed:
            continue
        if book_name in excluded:
            continue
        for market in bm.get("markets", []) or []:
            if market.get("key") != market_key:
                continue
            for outcome in market.get("outcomes", []) or []:
                price = outcome.get("price", 0)
                if price <= 0:
                    continue
                if _outcome_matches(market_key, selection, outcome, home, away, point):
                    out.append((book_name, float(price)))
    return out


def _devig_two_way(p_a: float, p_b: float) -> float:
    if p_a <= 0 or p_b <= 0:
        return p_a
    s = p_a + p_b
    return p_a / s if s > 0 else p_a


# ── Public API ──────────────────────────────────────────────────────────────
def get_sharp_anchor(match: Dict[str, Any], market_key: str, selection: str,
                     point: Optional[float] = None) -> Optional[SharpAnchor]:
    """
    Returns the sharp anchor for (market, selection) or None.

    None means: this signal does not exist as far as the doctrine is concerned.
    """
    sharp_quotes = _scan_books(match, market_key, selection, point,
                               allowed_books=SHARP_SET)
    if not sharp_quotes:
        return None

    # Honour Pinny > Betfair > Matchbook priority.
    chosen_book: Optional[str] = None
    chosen_price: Optional[float] = None
    for preferred in SHARP_PRIORITY:
        for book, price in sharp_quotes:
            if book == preferred:
                chosen_book = book
                chosen_price = price
                break
        if chosen_book:
            break

    if chosen_book is None or chosen_price is None:
        return None

    implied = 1.0 / chosen_price

    # De-vig with opposite side if it's a clean 2-way market and the same sharp
    # (or any sharp) quotes the opposite.
    opposite_sel = _opposite_selection(market_key, selection)
    opposite_price: Optional[float] = None
    devigged = implied
    if opposite_sel is not None:
        opp_quotes = _scan_books(match, market_key, opposite_sel, point,
                                 allowed_books=SHARP_SET)
        # Prefer opposite quote from the SAME sharp book; else any sharp.
        same_book = [p for b, p in opp_quotes if b == chosen_book]
        if same_book:
            opposite_price = same_book[0]
        elif opp_quotes:
            opposite_price = opp_quotes[0][1]
        if opposite_price:
            devigged = _devig_two_way(implied, 1.0 / opposite_price)

    return SharpAnchor(
        book=chosen_book,
        price=round(chosen_price, 4),
        opposite_price=round(opposite_price, 4) if opposite_price else None,
        implied_prob=round(implied, 6),
        devigged_prob=round(devigged, 6),
        market_key=market_key,
        selection=selection,
        point=point,
        timestamp_utc=int(time.time()),
    )


def get_best_price(match: Dict[str, Any], market_key: str, selection: str,
                   point: Optional[float] = None,
                   exclude_books: Optional[Iterable[str]] = None) -> Optional[BestPrice]:
    """Returns the highest available price across ALL books (incl. soft)."""
    quotes = _scan_books(match, market_key, selection, point,
                         excluded_books=exclude_books)
    if not quotes:
        return None
    best_book, best_price = max(quotes, key=lambda x: x[1])
    return BestPrice(
        book=best_book,
        price=round(best_price, 4),
        market_key=market_key,
        selection=selection,
        point=point,
        timestamp_utc=int(time.time()),
    )


def compute_edge_pct(model_prob: float, anchor: SharpAnchor) -> float:
    """
    Edge in pp vs the de-vigged sharp probability.
    Always uses sharp truth — never the soft placement price.
    """
    if not anchor or model_prob <= 0:
        return 0.0
    return round((model_prob - anchor.devigged_prob) * 100.0, 3)


__all__ = [
    "SharpAnchor",
    "BestPrice",
    "SHARP_PRIORITY",
    "SHARP_SET",
    "get_sharp_anchor",
    "get_best_price",
    "compute_edge_pct",
]
