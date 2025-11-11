# league_bias.py
# Auto-viktning av ligor baserat på historiska settled bets.
# Ingen extern dependency. Plug-and-play.

from collections import defaultdict
from datetime import datetime, timezone

DEFAULTS = {
    "decay_lambda": 0.97,   # viktminskning per dag bakåt i tiden
    "k_shrink": 80,         # shrinkage-styrka (empirical Bayes)
    "alpha": 1.0,           # hur starkt ROI_shrunk påverkar vikt
    "min_n": 40,            # minsta antal settled bets/liga för att agera
    "pause_roi": -0.20,     # pausa liga om ROI_hat <= -20%
    "boost_roi":  0.10,     # boosta liga om ROI_hat >= +10%
    "weight_cap_hi": 1.5,   # maxvikt
    "weight_floor_lo": 0.7  # lägsta vikt för neutrala ligor
}

def _days_between(ts_now: datetime, ts_then: datetime) -> int:
    if ts_then.tzinfo is None:
        ts_then = ts_then.replace(tzinfo=timezone.utc)
    if ts_now.tzinfo is None:
        ts_now = ts_now.replace(tzinfo=timezone.utc)
    return max(0, (ts_now - ts_then).days)

def league_stats(rows, now=None, cfg=None):
    """
    rows: iterable av dicts med fält:
      - 'league': str
      - 'profit': float (units, + vid vinst, - vid förlust)
      - 'stake' : float (>0)
      - 'settled_ts': datetime (UTC)
    return: dict {league: {"N", "roi_hat", "roi_shrunk", "weight"}}
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    now = now or datetime.now(timezone.utc)
    lam = cfg["decay_lambda"]

    agg = defaultdict(lambda: {"units": 0.0, "staked": 0.0, "N": 0})
    for r in rows:
        if r.get("stake", 0) <= 0:
            continue
        d = _days_between(now, r["settled_ts"])
        w = (lam ** d)
        agg[r["league"]]["units"]  += w * float(r["profit"])
        agg[r["league"]]["staked"] += w * float(r["stake"])
        agg[r["league"]]["N"]      += 1

    out = {}
    for lg, s in agg.items():
        staked = s["staked"]
        roi_hat = (s["units"] / staked) if staked > 0 else 0.0
        N = s["N"]
        shrink = N / (N + cfg["k_shrink"])
        roi_shrunk = shrink * roi_hat  # prior=0

        # policy
        if N < cfg["min_n"]:
            weight = 1.0
        elif roi_hat <= cfg["pause_roi"]:
            weight = 0.0
        elif roi_hat >= cfg["boost_roi"]:
            weight = min(cfg["weight_cap_hi"], 1.0 + cfg["alpha"] * roi_shrunk)
        else:
            base = 1.0 + cfg["alpha"] * roi_shrunk
            weight = max(cfg["weight_floor_lo"], min(1.2, base))

        out[lg] = {
            "N": N,
            "roi_hat": roi_hat,           # faktisk (decay-viktad)
            "roi_shrunk": roi_shrunk,     # shrinkad mot 0
            "weight": weight              # 0.0 = paus, 1.0 = neutral, 1.5 = max boost
        }
    return out

def apply_league_weight(candidates, lg_info, k_unc=0.6):
    """
    candidates: list av dict med minst:
      - 'league', 'ev', 'uncertainty'
    return: ny lista där 'confidence' = (ev - k_unc*uncertainty) * league_weight
    """
    out = []
    for c in candidates:
        w = lg_info.get(c["league"], {}).get("weight", 1.0)
        conf = (c["ev"] - k_unc * c.get("uncertainty", 0.0)) * w
        d = dict(c)
        d["league_weight"] = w
        d["confidence"] = conf
        out.append(d)
    return out
