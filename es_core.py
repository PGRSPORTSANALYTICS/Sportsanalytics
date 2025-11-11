# es_core.py
# Exact Score-pipeline: xG -> Poisson -> Dixon-Coles, draw-trigger, kalibrering & EV.
# Ingen extern dependency. Plug-and-play.

import math

def mu_from_xg(xg_for, xga_vs_opp, home_flag, league_hp=1.06):
    """
    Enkel μ-skattning från xG med motståndskorrigering och hemmaplansfaktor.
    xg_for: lagets offensiva xG (rolling/ewa)
    xga_vs_opp: motståndarens defensiva xGA (rolling/ewa)
    home_flag: bool
    league_hp: hemmaplansmultiplikator (kan göras ligaspecifik)
    """
    xg_adj = float(xg_for) - float(xga_vs_opp)
    mu = xg_adj * (league_hp if home_flag else (2.0 - league_hp))
    return max(0.05, mu)

def pois_pmf(k, mu):
    return math.exp(-mu) * (mu ** k) / math.factorial(k)

def dixon_coles_correction(i, j, rho=0.06):
    """
    Standard DC-justering för lågmål (0-1 zon).
    """
    # klassisk approx enligt Dixon-Coles
    if i == 0 and j == 0:
        return 1 - (mu_small(rho))
    elif i == 0 and j == 1:
        return 1 + rho
    elif i == 1 and j == 0:
        return 1 + rho
    elif i == 1 and j == 1:
        return 1 - rho
    else:
        return 1.0

def mu_small(rho):
    # liten hjälpterm för (0,0) korrigeringen (kan hållas simpel)
    return rho

def joint_score_map(mu_h, mu_a, rho=0.06, max_goals=4):
    """
    Poisson x Poisson med DC-justering i lågmålsrutor. Klipper svansen > max_goals och renormaliserar.
    Returnerar dict {(h,a): p}
    """
    pmap = {}
    total = 0.0
    for h in range(0, max_goals + 1):
        for a in range(0, max_goals + 1):
            p = pois_pmf(h, mu_h) * pois_pmf(a, mu_a)
            # DC-justering i 0/1-zon
            if h <= 1 and a <= 1:
                p *= dixon_coles_correction(h, a, rho=rho)
            pmap[(h, a)] = p
            total += p
    # renormalisera
    for k in pmap:
        pmap[k] /= total if total > 0 else 1.0
    return pmap

def draw_trigger_adjust(pmap, xg_diff_abs, boost=1.15):
    """
    Boostar P(0-0) och P(1-1) i matcher där xG-diff är liten (typisk draw-zon).
    """
    if xg_diff_abs <= 0.5:
        for sc in [(0,0), (1,1)]:
            if sc in pmap:
                pmap[sc] *= boost
        # renormalisera
        s = sum(pmap.values())
        for k in pmap:
            pmap[k] /= s if s > 0 else 1.0
    return pmap

def calibrate_prob(p_raw, league, scoreline, calibrators=None):
    """
    Hook för kalibrering per liga & scoreline (isotonic/beta externt).
    calibrators: dict key=(league, scoreline) -> object med .transform([p])->[p_cal]
    """
    if not calibrators:
        return p_raw
    key = (league, scoreline)
    cal = calibrators.get(key)
    if cal is None:
        return p_raw
    try:
        return float(cal.transform([p_raw])[0])
    except Exception:
        return p_raw

def expected_value(p, odds):
    return p * (odds - 1.0) - (1.0 - p)

def es_candidates(match_row, calibrators=None, rho=0.06, max_goals=4, league_hp=1.06):
    """
    Bygger ES-kandidater för en match.
    match_row (dict) behöver:
      'league', 'odds_es' (dict: "H-A"->odds),
      'xg_h_for', 'xga_a_opp', 'xg_a_for', 'xga_h_opp'
    return: lista av dicts: {'score','p','p_raw','odds','ev'}
    """
    mu_h = mu_from_xg(match_row["xg_h_for"], match_row["xga_a_opp"], True, league_hp=league_hp)
    mu_a = mu_from_xg(match_row["xg_a_for"], match_row["xga_h_opp"], False, league_hp=league_hp)

    pmap = joint_score_map(mu_h, mu_a, rho=rho, max_goals=max_goals)

    xg_diff_abs = abs((match_row["xg_h_for"] - match_row["xga_a_opp"]) -
                      (match_row["xg_a_for"] - match_row["xga_h_opp"]))
    pmap = draw_trigger_adjust(pmap, xg_diff_abs)

    out = []
    league = match_row["league"]
    odds_map = match_row["odds_es"]  # dict: "H-A" -> float
    for (h, a), p_raw in pmap.items():
        key = f"{h}-{a}"
        odds = odds_map.get(key)
        if not odds:
            continue
        p_cal = calibrate_prob(p_raw, league, key, calibrators=calibrators)
        ev = expected_value(p_cal, odds)
        out.append({
            "score": key,
            "p": p_cal,
            "p_raw": p_raw,
            "odds": odds,
            "ev": ev
        })
    # sortera bäst först (EV)
    out.sort(key=lambda z: z["ev"], reverse=True)
    return out

def select_es_for_publication(cands, ev_min=0.20, max_per_match=3, odds_min=9.0, odds_max=14.0):
    """
    Välj ut ES-spel för PRO-läge.
    - EV >= ev_min
    - odds i ett sunt intervall (undvik svansar)
    - max X spel/match
    """
    sel = [c for c in cands if (c["ev"] >= ev_min and odds_min <= c["odds"] <= odds_max)]
    return sel[:max_per_match]
