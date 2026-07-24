---
name: EV and CLV removed as signal gates
description: July 2026 — EV and CLV removed as gating criteria; signals now route purely by model confidence + odds range + market softness
---

## The rule
EV and CLV are computed and logged but never block or downgrade a signal.
Routing is done by:
- **PRO PICK**: confidence ≥ 70% + odds 2.10–2.30 + PGR ≥ 55 + league A/B
- **VALUE OPP**: confidence ≥ 60% + odds 1.70–4.00 + PGR ≥ 35
- **WATCHLIST**: confidence ≥ 52% + PGR ≥ 20

## PGR score formula (weights sum to 1.0)
- Confidence: 80%
- Market softness: 12%
- League tier: 8%
- EV_WEIGHT = 0.0 (informational only)
- CLV_WEIGHT = 0.0 (informational only)

## Why
User: "Sluta med EV betting" (Jul 23 2026) + "I dont want to use clv" (Jul 23 2026).
Pure confidence + odds range routing is more stable and less model-sensitive.

## How to apply
- `pgr_scoring.py`: EV_WEIGHT=CLV_WEIGHT=0.0; CONFIDENCE_WEIGHT=0.80; MARKET=0.12; LEAGUE=0.08
- `value_singles_engine.py`: MIN_VALUE_SINGLE_EV=0.0; apply_ev_controls() non-blocking;
  CLV advisory downgrade removed; fallback routing uses confidence+PGR only
- `real_football_champion.py`: ValueSinglesEngine called with ev_threshold=0.0
- `api.py`: startup_event() try/except so DB-offline doesn't crash the API server
