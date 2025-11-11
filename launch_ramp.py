from datetime import date

LAUNCH_DATE = date(2026, 1, 15)

RAMP = {
    "ES": [
        {"days_out": 56, "ev_min": 0.08},
        {"days_out": 42, "ev_min": 0.12},
        {"days_out": 28, "ev_min": 0.16},
        {"days_out": 14, "ev_min": 0.20},
        {"days_out": 0,  "ev_min": 0.22},  # efter launch kan du dra åt ytterligare
    ],
    "SGP": [
        {"days_out": 56, "ev_min": 0.06},
        {"days_out": 42, "ev_min": 0.10},
        {"days_out": 28, "ev_min": 0.12},
        {"days_out": 14, "ev_min": 0.15},
        {"days_out": 0,  "ev_min": 0.16},
    ],
}

def get_thresholds(product: str, today: date = date.today()):
    days_to_launch = (LAUNCH_DATE - today).days
    plan = sorted(RAMP[product], key=lambda x: x["days_out"], reverse=True)
    ev_min = plan[-1]["ev_min"]
    for step in plan:
        if days_to_launch >= step["days_out"]:
            ev_min = step["ev_min"]; break
    return {"ev_min": ev_min}

# kvalitets-grindar (enkla – byt mot din statsmodul)
def pass_quality_gates(product, rolling):
    """
    rolling: dict med nycklar 'hit_rate', 'roi', 'wins', 'n'
    grindar per produkt – justera fritt
    """
    gates = {
        "ES":  {"min_n": 150, "hr_min": 0.10, "roi_min": 0.05},
        "SGP": {"min_n": 200, "hr_min": 0.28, "roi_min": 0.03},
    }
    g = gates[product]
    return (rolling["n"] >= g["min_n"] and
            rolling["hit_rate"] >= g["hr_min"] and
            rolling["roi"] >= g["roi_min"])

def should_place(product, ev, rolling_metrics):
    th = get_thresholds(product)
    # krävs både EV-krav och att senaste rullande fönstret klarar grindarna
    return (ev >= th["ev_min"]) and pass_quality_gates(product, rolling_metrics)
