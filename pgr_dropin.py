# =======================================================
# PGR DROP-IN | League Bias + Exact Score (auto data hookup)
# Klistra in i din Replit-app. Kör:
#   from pgr_dropin import run_pgr_dropin
#   run_pgr_dropin()
# =======================================================
import os, csv, json, math, glob
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ---------- UTIL ----------
def _now():
    return datetime.now(timezone.utc)

def _days_between(ts_now: datetime, ts_then: datetime) -> int:
    if isinstance(ts_then, str):
        # försök parse: ISO eller "YYYY-MM-DD ..."
        try:
            ts_then = datetime.fromisoformat(ts_then.replace("Z","")).replace(tzinfo=timezone.utc)
        except Exception:
            ts_then = _now() - timedelta(days=1)
    if ts_then.tzinfo is None:
        ts_then = ts_then.replace(tzinfo=timezone.utc)
    if ts_now.tzinfo is None:
        ts_now = ts_now.replace(tzinfo=timezone.utc)
    return max(0, (ts_now - ts_then).days)

def _ensure_dir(d):
    os.makedirs(d, exist_ok=True)

def _print_header(t):
    print("\n" + "="*8 + " " + t + " " + "="*8)

# ---------- AUTO-LOAD: DINA DATA (först försök dina funktioner) ----------
def _try_call(func_names):
    g = globals()
    for name in func_names:
        if name in g and callable(g[name]):
            try:
                return g[name]()
            except Exception:
                pass
    # försök importera från vanliga modulnamn
    for mod in ["data", "db", "store", "repo", "pgr_data"]:
        try:
            m = __import__(mod)
            for name in func_names:
                if hasattr(m, name) and callable(getattr(m, name)):
                    return getattr(m, name)()
        except Exception:
            continue
    return None

def _csv_or_json(path):
    if not os.path.exists(path): return None
    if path.endswith(".csv"):
        rows=[]
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
        return rows
    else:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

def _load_settled_rows():
    # 1) Försök dina befintliga funktioner
    out = _try_call(["fetch_settled_bets","get_settled_bets","db_get_settled_bets","load_settled_bets"])
    if out: return out
    # 2) Leta filer
    for p in ["settled_bets.csv","data/settled_bets.csv","logs/settled_bets.csv",
              "settled_bets.json","data/settled_bets.json","logs/settled_bets.json"]:
        rows = _csv_or_json(p)
        if rows: return rows
    # 3) Tom
    return []

def _load_upcoming_matches():
    out = _try_call(["fetch_upcoming_matches","get_upcoming_matches","db_get_upcoming_matches","load_upcoming_matches"])
    if out: return out
    for p in ["upcoming_matches.csv","data/upcoming_matches.csv",
              "upcoming_matches.json","data/upcoming_matches.json"]:
        rows = _csv_or_json(p)
        if rows: return rows
    return []

# ---------- NORMALISERING av fält ----------
def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _to_dt(x):
    if isinstance(x, datetime): return x
    try:
        return datetime.fromisoformat(str(x).replace("Z","")).replace(tzinfo=timezone.utc)
    except Exception:
        return _now() - timedelta(days=1)

def _norm_settled_row(r):
    # Försöker mappa rimliga fältnamn
    lg = r.get("league") or r.get("liga") or r.get("competition") or r.get("league_name") or "Unknown"
    profit = r.get("profit")
    if profit is None:
        # fallback: result + stake + odds
        res = str(r.get("result","")).upper()
        stake = _to_float(r.get("stake",1.0),1.0)
        odds  = _to_float(r.get("odds",0.0),0.0)
        if res in ["WIN","W","1"]: profit = stake*(odds-1.0)
        elif res in ["PUSH","VOID","V","0"]: profit = 0.0
        else: profit = -stake
    stake = _to_float(r.get("stake",1.0),1.0)
    ts = r.get("settled_ts") or r.get("settled_at") or r.get("date") or r.get("settled")
    ts = _to_dt(ts)
    return {"league": str(lg), "profit": _to_float(profit), "stake": stake, "settled_ts": ts}

def _norm_upcoming_match(m):
    lg = m.get("league") or m.get("liga") or m.get("competition") or "Unknown"
    # xG inputs
    xg_h_for   = _to_float(m.get("xg_h_for", m.get("home_xg", m.get("xhg", 1.2))), 1.2)
    xga_a_opp  = _to_float(m.get("xga_a_opp", m.get("away_xga", m.get("axga", 1.2))), 1.2)
    xg_a_for   = _to_float(m.get("xg_a_for", m.get("away_xg", m.get("axg", 1.1))), 1.1)
    xga_h_opp  = _to_float(m.get("xga_h_opp", m.get("home_xga", m.get("hxga", 1.2))), 1.2)
    # odds map för ES
    odds_es = m.get("odds_es")
    if not isinstance(odds_es, dict):
        # försök bygga av kolumner typ odds_1_0, odds_1_1, ...
        odds_es = {}
        for k,v in m.items():
            ks = str(k).lower().replace("odds_","")
            if "-" in ks and str(v).strip():
                try:
                    odds_es[ks] = float(v)
                except Exception:
                    pass
    return {
        "league": str(lg),
        "xg_h_for": xg_h_for, "xga_a_opp": xga_a_opp,
        "xg_a_for": xg_a_for, "xga_h_opp": xga_h_opp,
        "odds_es": odds_es or {}
    }

# ---------- LEAGUE BIAS ----------
def league_stats(rows):
    now = _now()
    lam = 0.97
    k_shrink = 80
    min_n = 40
    agg = defaultdict(lambda: {"units": 0.0, "staked": 0.0, "N": 0})
    for r in rows:
        d = _days_between(now, r["settled_ts"])
        w = lam ** d
        agg[r["league"]]["units"]  += w * float(r["profit"])
        agg[r["league"]]["staked"] += w * float(r["stake"])
        agg[r["league"]]["N"]      += 1
    out={}
    for lg,s in agg.items():
        if s["staked"]<=0: continue
        roi_hat = s["units"]/s["staked"]
        N = s["N"]
        shrink = N/(N+k_shrink)
        roi_shrunk = shrink*roi_hat
        if N < min_n: weight = 1.0
        elif roi_hat <= -0.20: weight = 0.0
        elif roi_hat >= 0.10:  weight = min(1.5, 1.0 + roi_shrunk)
        else:
            base = 1.0 + roi_shrunk
            weight = max(0.7, min(1.2, base))
        out[lg]={"N":N,"roi_hat":roi_hat,"roi_shrunk":roi_shrunk,"weight":weight}
    return out

def apply_league_weight(cands, lg_info):
    out=[]
    for c in cands:
        w = lg_info.get(c["league"],{}).get("weight",1.0)
        conf = (c["ev"] - 0.6*c.get("uncertainty",0.0))*w
        d=dict(c); d["league_weight"]=w; d["confidence"]=conf
        out.append(d)
    return out

# ---------- EXACT SCORE ----------
def mu_from_xg(xg_for, xga_vs_opp, home_flag, league_hp=1.06):
    xg_adj = float(xg_for) - float(xga_vs_opp)
    mu = xg_adj * (league_hp if home_flag else (2.0 - league_hp))
    return max(0.05, mu)

def pois_pmf(k, mu):
    return math.exp(-mu) * (mu ** k) / math.factorial(k)

def dixon_coles_correction(i, j, rho=0.06):
    if i==0 and j==0: return 1 - rho
    if i==0 and j==1: return 1 + rho
    if i==1 and j==0: return 1 + rho
    if i==1 and j==1: return 1 - rho
    return 1.0

def joint_score_map(mu_h, mu_a, rho=0.06, max_goals=4):
    pmap, total = {}, 0.0
    for h in range(max_goals+1):
        for a in range(max_goals+1):
            p = pois_pmf(h,mu_h)*pois_pmf(a,mu_a)
            if h<=1 and a<=1: p *= dixon_coles_correction(h,a,rho)
            pmap[(h,a)] = p; total += p
    if total>0:
        for k in pmap: pmap[k] /= total
    return pmap

def draw_trigger_adjust(pmap, xg_diff_abs, boost=1.15):
    if xg_diff_abs <= 0.5:
        for sc in [(0,0),(1,1)]:
            if sc in pmap: pmap[sc]*=boost
        s=sum(pmap.values())
        if s>0:
            for k in pmap: pmap[k]/=s
    return pmap

def expected_value(p, odds):
    return p*(odds-1.0) - (1.0-p)

def es_candidates(match):
    mu_h = mu_from_xg(match["xg_h_for"], match["xga_a_opp"], True)
    mu_a = mu_from_xg(match["xg_a_for"], match["xga_h_opp"], False)
    pmap = joint_score_map(mu_h, mu_a)
    xg_diff_abs = abs((match["xg_h_for"]-match["xga_a_opp"]) - (match["xg_a_for"]-match["xga_h_opp"]))
    pmap = draw_trigger_adjust(pmap, xg_diff_abs)
    out=[]
    for (h,a),p_raw in pmap.items():
        key=f"{h}-{a}"
        odds = match["odds_es"].get(key)
        if not odds: continue
        ev = expected_value(p_raw, float(odds))
        out.append({"league":match["league"],"score":key,"p":p_raw,"odds":float(odds),"ev":ev,"uncertainty":0.10})
    out.sort(key=lambda z: z["ev"], reverse=True)
    return out

def select_es_for_publication(cands, ev_min=0.20, max_per_match=3, odds_min=9.0, odds_max=14.0):
    sel=[c for c in cands if (c["ev"]>=ev_min and odds_min<=c["odds"]<=odds_max)]
    return sel[:max_per_match]

# ---------- PIPELINE ----------
def run_pgr_dropin(output_dir="pgr_out"):
    _print_header("Laddar historik (settled bets)")
    raw_settled = _load_settled_rows()
    settled = [_norm_settled_row(r) for r in raw_settled]
    print(f"Loaded settled rows: {len(settled)}")

    _print_header("Beräknar ligavikter")
    lg_info = league_stats(settled) if settled else {}
    for lg,info in lg_info.items():
        print(f"{lg}: N={info['N']} ROI={info['roi_hat']:.3f} W={info['weight']:.2f}")

    _print_header("Laddar kommande matcher")
    raw_upcoming = _load_upcoming_matches()
    upcoming = [_norm_upcoming_match(m) for m in raw_upcoming]
    print(f"Loaded upcoming matches: {len(upcoming)}")

    all_train, all_public = [], []

    for m in upcoming:
        if not m.get("odds_es"): 
            # hoppa matchen om vi saknar ES-odds
            continue
        cands = es_candidates(m)
        ranked = apply_league_weight(cands, lg_info)

        # TRAIN-LOG (EV ≥ 8%)
        train = [r for r in ranked if r["ev"] >= 0.08]
        for t in train:
            all_train.append({**t, "league_weight": t.get("league_weight",1.0)})
        print(f"[TRAIN] {m['league']} -> {len(train)} kandidater ≥ 8% EV")

        # PRO-picks
        public = select_es_for_publication(ranked, ev_min=0.20, max_per_match=3, odds_min=9.0, odds_max=14.0)
        all_public.extend(public)

    _print_header("PRO – Exact Score (publiceringskandidater)")
    for p in all_public:
        print(f"{p['league']} | {p['score']} @{p['odds']} | EV={p['ev']:.2f} | Conf={p['confidence']:.2f} | W={p['league_weight']:.2f}")

    # Spara ut
    _ensure_dir(output_dir)
    with open(os.path.join(output_dir,"league_weights.json"),"w",encoding="utf-8") as f:
        json.dump(lg_info, f, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir,"train_log_es.json"),"w",encoding="utf-8") as f:
        json.dump(all_train, f, ensure_ascii=False, indent=2)
    with open(os.path.join(output_dir,"public_es.json"),"w",encoding="utf-8") as f:
        json.dump(all_public, f, ensure_ascii=False, indent=2)

    # CSV-export (enkelt)
    def _csv(path, rows, fields):
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k:r.get(k) for k in fields})

    _csv(os.path.join(output_dir,"public_es.csv"), all_public,
         ["league","score","odds","ev","confidence","league_weight"])
    print(f"\n✔ Klart. Filer sparade i: {output_dir}/")

# Auto-run om filen körs direkt
if __name__ == "__main__":
    run_pgr_dropin()
