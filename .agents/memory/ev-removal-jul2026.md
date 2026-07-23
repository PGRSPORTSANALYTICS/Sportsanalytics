---
name: EV removal as signal gate
description: July 2026 — EV (Expected Value) removed as the primary gating criterion; signals now route by confidence + PGR score + odds range
---

## The rule
EV is computed and logged but never blocks a signal. Routing is done by:
- **PRO PICK**: confidence ≥ 70% + odds 2.10–2.30 + PGR ≥ 55 + league A/B
- **VALUE OPP**: confidence ≥ 60% + odds 1.70–4.00 + PGR ≥ 35
- **WATCHLIST**: confidence ≥ 52% + PGR ≥ 20

## PGR score formula (weights sum to 1.0)
- Confidence: 55% (was 25%)
- CLV: 25% (was 15%); fallback when no CLV data = conf_score * 0.80 (was ev_score)
- Market softness: 10%
- League tier: 10%
- EV_WEIGHT = 0.0 (was 0.40)

## Why
User request Jul 23 2026: "Sluta med EV betting och hitta endast bra bet med samma odds range."
EV is model-sensitive and was the primary rejection reason. Confidence + CLV is more robust.

## How to apply
- `pgr_scoring.py`: EV_WEIGHT=0.0, constants PRO/VALUE/WATCHLIST_MIN_EV all = 0.0 (legacy stubs)
- `value_singles_engine.py`: MIN_VALUE_SINGLE_EV=0.0, apply_ev_controls() no longer blocks
- `real_football_champion.py`: ValueSinglesEngine called with ev_threshold=0.0
- `api.py`: startup_event() wrapped in try/except so DB-offline doesn't crash the server
