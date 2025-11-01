# main.py
# ---- Single-file SGP AI MVP (FastAPI + minimal UI) ----
# Requirements: fastapi, uvicorn, numpy
# Run: uvicorn main:app --host 0.0.0.0 --port 8000

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
import numpy as np
from math import erf

APP_TITLE = "SGP AI Platform (Single-File MVP)"
APP_VERSION = "0.1.0"

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

# CORS for easy testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# -----------------------------
# Models / Schemas
# -----------------------------
class Leg(BaseModel):
    market_type: Literal["OVER_UNDER_GOALS","BTTS","PLAYER_TO_SCORE"] = Field(..., description="Market type")
    outcome: str = Field(..., description="Outcome label, e.g. OVER / YES / TRUE")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Extra params like {'line':2.5,'player_id':123}")

class PriceParlayIn(BaseModel):
    event_id: int
    legs: List[Leg]
    bookmaker_odds: float = Field(..., gt=1.0)
    method: Literal["copula","biv_poisson"] = "copula"
    simulations: int = 200_000

class PriceParlayOut(BaseModel):
    p_all: float
    fair_odds: float
    ev_pct: float
    simulations: int

class StakeIn(BaseModel):
    bankroll: float = Field(..., gt=0)
    decimal_odds: float = Field(..., gt=1.0)
    win_prob: float = Field(..., ge=0.0, le=1.0)
    kelly_fraction_cap: float = Field(0.05, gt=0.0)  # cap at 5% by default
    risk_level: Literal["low","medium","high"] = "medium"  # scales kelly

class StakeOut(BaseModel):
    kelly_raw: float
    kelly_scaled: float
    stake_amount: float

# -----------------------------
# Correlation heuristics
# -----------------------------
# Simple rules between leg types/outcomes.
CORR_RULES = {
    ("OVER_UNDER_GOALS:OVER", "BTTS:YES"): 0.35,
    ("PLAYER_TO_SCORE:TRUE", "OVER_UNDER_GOALS:OVER"): 0.25,
    ("PLAYER_TO_SCORE:TRUE", "BTTS:YES"): 0.20,
    # A few extra helpful heuristics:
    ("OVER_UNDER_GOALS:UNDER", "BTTS:NO"): 0.30,
    ("PLAYER_TO_SCORE:FALSE", "BTTS:NO"): 0.15,
}

def leg_key(mt: str, outcome: str) -> str:
    return f"{mt}:{outcome.upper()}"

def build_corr(legs: List[Dict[str, Any]]) -> np.ndarray:
    n = len(legs)
    C = np.eye(n)
    keys = [leg_key(l["market_type"], l["outcome"]) for l in legs]
    for i in range(n):
        for j in range(i+1, n):
            corr = CORR_RULES.get((keys[i], keys[j])) or CORR_RULES.get((keys[j], keys[i])) or 0.0
            # clamp to safe range
            corr = max(min(corr, 0.8), -0.3)
            C[i, j] = C[j, i] = corr
    # Ensure positive-definite (jitter if needed)
    # If Cholesky fails, we gradually shrink off-diagonals.
    for attempt in range(5):
        try:
            _ = np.linalg.cholesky(C)
            return C
        except np.linalg.LinAlgError:
            C = C * 0.95 + np.eye(n) * 0.05
    # last resort: identity
    return np.eye(n)

# -----------------------------
# Probability calibration (MVP)
# -----------------------------
def calibrate_leg_prob(leg: Dict[str, Any], context: Dict[str, Any]) -> float:
    mt = leg["market_type"]
    outcome = leg["outcome"].upper()
    params = leg.get("params") or {}

    # SUPER simple baselines; replace with models later (Poisson, logistic on xG, etc.)
    if mt == "OVER_UNDER_GOALS":
        line = float(params.get("line", 2.5))
        # crude baseline curve around world-football scoring rates
        # center near 2.6 avg goals; rough sigmoid-ish mapping
        x = 2.6 - line
        # Convert to probability of OVER
        p_over = 1 / (1 + np.exp(-2.0 * x))
        return float(p_over if outcome == "OVER" else 1 - p_over)

    if mt == "BTTS":
        # baseline around 50% globally; can be tuned by teams later
        p_yes = 0.50
        return float(p_yes if outcome in ("YES","TRUE") else 1 - p_yes)

    if mt == "PLAYER_TO_SCORE":
        # crude prior; tweak via player xG share/minutes when available
        # Allow manual override via params: {"base_prob": 0.30}
        p_score = float(params.get("base_prob", 0.30))
        return float(p_score if outcome in ("TRUE","YES") else 1 - p_score)

    # default safety
    return 0.50

# -----------------------------
# Copula Monte Carlo pricing
# -----------------------------
def normal_cdf(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + erf(z / np.sqrt(2.0)))

def price_parlay_copula(legs: List[Dict[str, Any]], simulations: int = 200_000) -> float:
    n = len(legs)
    if n == 0:
        return 0.0

    probs = np.array([calibrate_leg_prob(l, {}) for l in legs])
    probs = np.clip(probs, 1e-6, 1 - 1e-6)

    C = build_corr(legs)
    try:
        L = np.linalg.cholesky(C)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky((C + C.T) / 2 + np.eye(n) * 1e-6)

    z = np.random.normal(size=(simulations, n))
    z_corr = z @ L.T
    u = normal_cdf(z_corr)

    hits = (u < probs).all(axis=1)
    p_all = hits.mean()
    return float(p_all)

def fair_odds_from_p(p: float) -> float:
    return 1.0 / max(p, 1e-12)

def ev_pct(book_odds: float, fair_odds: float) -> float:
    return (book_odds / fair_odds - 1.0) * 100.0

# -----------------------------
# Kelly staking helper
# -----------------------------
def kelly_fraction(prob: float, decimal_odds: float) -> float:
    # Kelly = (p*O - 1) / (O - 1)
    O = decimal_odds
    p = prob
    denom = (O - 1.0)
    if denom <= 0:
        return 0.0
    kv = (p * O - 1.0) / denom
    return max(0.0, kv)

def risk_scale(level: str) -> float:
    return {"low": 0.25, "medium": 0.5, "high": 1.0}.get(level, 0.5)

# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True, "version": APP_VERSION}

@app.post("/api/v1/parlays/price", response_model=PriceParlayOut)
def price_parlay(payload: PriceParlayIn):
    legs = [l.dict() for l in payload.legs]
    if payload.method != "copula":
        # For now only copula implemented in this single-file MVP
        return JSONResponse(
            status_code=400,
            content={"detail": "Only 'copula' method is implemented in MVP."}
        )
    p_all = price_parlay_copula(legs, payload.simulations)
    fair = fair_odds_from_p(p_all)
    ev = ev_pct(payload.bookmaker_odds, fair)
    return {"p_all": p_all, "fair_odds": fair, "ev_pct": ev, "simulations": payload.simulations}

@app.post("/api/v1/stake/kelly", response_model=StakeOut)
def compute_stake(payload: StakeIn):
    raw = kelly_fraction(payload.win_prob, payload.decimal_odds)
    scaled = raw * risk_scale(payload.risk_level)
    capped = min(scaled, payload.kelly_fraction_cap)
    stake_amount = payload.bankroll * capped
    return {"kelly_raw": raw, "kelly_scaled": scaled, "stake_amount": stake_amount}

# -----------------------------
# Minimal HTML UI to test
# -----------------------------
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>SGP AI – Demo</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 980px; margin: 32px auto; padding: 0 16px; }
    h1 { margin-bottom: 8px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 12px 0; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    input, select, button, textarea { padding: 8px 10px; border-radius: 8px; border: 1px solid #bbb; }
    code { background: #f6f8fa; padding: 2px 4px; border-radius: 6px; }
    .legs { margin-top: 8px; }
    .leg { display:flex; gap:8px; align-items:center; margin:6px 0; }
    .result { white-space: pre-wrap; background:#0b1; color:#fff; padding:10px; border-radius:8px; display:none; }
    .error { white-space: pre-wrap; background:#b00; color:#fff; padding:10px; border-radius:8px; display:none; }
  </style>
</head>
<body>
  <h1>SGP AI – Single-File Demo</h1>
  <p>Bygg en SGP med 2–5 ben och beräkna fair odds + EV% via copula-simulering.</p>

  <div class="card">
    <div class="row">
      <label>Event ID <input id="eventId" type="number" value="1001"></label>
      <label>Bookmaker Odds <input id="bookOdds" type="number" step="0.01" value="6.20"></label>
      <label>Simulations <input id="sims" type="number" value="200000"></label>
    </div>

    <div class="legs" id="legs"></div>
    <button onclick="addLeg()">+ Add Leg</button>
    <button onclick="price()">Price Parlay</button>

    <div class="result" id="result"></div>
    <div class="error" id="error"></div>
  </div>

  <div class="card">
    <h3>Stake (Kelly)</h3>
    <div class="row">
      <label>Bankroll <input id="bankroll" type="number" step="0.01" value="1000"></label>
      <label>Decimal Odds <input id="stakeOdds" type="number" step="0.01" value="6.20"></label>
      <label>Win Prob p(all legs) <input id="winProb" type="number" step="0.0001" value="0.17"></label>
      <label>Risk
        <select id="riskLevel">
          <option>low</option>
          <option selected>medium</option>
          <option>high</option>
        </select>
      </label>
      <label>Kelly Cap <input id="kellyCap" type="number" step="0.001" value="0.05"></label>
    </div>
    <button onclick="stake()">Compute Stake</button>
    <div class="result" id="stakeRes"></div>
    <div class="error" id="stakeErr"></div>
  </div>

  <div class="card">
    <h3>Tips</h3>
    <ul>
      <li>Marketer: <code>OVER_UNDER_GOALS</code> (params: <code>{ "line": 2.5 }</code>), outcome: <code>OVER</code> eller <code>UNDER</code></li>
      <li>Marketer: <code>BTTS</code> (utan params), outcome: <code>YES</code> eller <code>NO</code></li>
      <li>Marketer: <code>PLAYER_TO_SCORE</code> (params: <code>{ "player_id": 9, "base_prob": 0.33 }</code>), outcome: <code>TRUE</code> eller <code>FALSE</code></li>
    </ul>
  </div>

<script>
let legCount = 0;
function legTemplate(i){
  return `
  <div class="leg" id="leg-${i}">
    <select id="mt-${i}">
      <option>OVER_UNDER_GOALS</option>
      <option>BTTS</option>
      <option>PLAYER_TO_SCORE</option>
    </select>
    <select id="outcome-${i}">
      <option>OVER</option>
      <option>UNDER</option>
      <option>YES</option>
      <option>NO</option>
      <option>TRUE</option>
      <option>FALSE</option>
    </select>
    <input id="params-${i}" placeholder='params JSON e.g. {"line":2.5}'>
    <button onclick="removeLeg(${i})">x</button>
  </div>`
}
function addLeg(){
  const c = document.getElementById('legs');
  c.insertAdjacentHTML('beforeend', legTemplate(legCount));
  legCount++;
}
function removeLeg(i){
  const el = document.getElementById('leg-'+i);
  if (el) el.remove();
}
function collectLegs(){
  const legsDiv = document.getElementById('legs');
  const legs = [];
  for (const child of legsDiv.children){
    if (!child.id || !child.id.startsWith("leg-")) continue;
    const idx = child.id.split("-")[1];
    const mt = document.getElementById('mt-'+idx).value;
    const oc = document.getElementById('outcome-'+idx).value;
    const pstr = document.getElementById('params-'+idx).value.trim();
    let params = undefined;
    if (pstr) {
      try { params = JSON.parse(pstr); } catch(e){ params = null; }
    }
    legs.push({market_type: mt, outcome: oc, params: params});
  }
  return legs;
}
async function price(){
  const eventId = parseInt(document.getElementById('eventId').value || "0");
  const bookOdds = parseFloat(document.getElementById('bookOdds').value || "1");
  const sims = parseInt(document.getElementById('sims').value || "200000");
  const legs = collectLegs();
  const resBox = document.getElementById('result');
  const errBox = document.getElementById('error');
  resBox.style.display = "none"; errBox.style.display="none";
  try{
    const r = await fetch("/api/v1/parlays/price", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({event_id:eventId, legs, bookmaker_odds:bookOdds, method:"copula", simulations:sims})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Error");
    resBox.textContent = JSON.stringify(data, null, 2);
    resBox.style.display = "block";
  }catch(e){
    errBox.textContent = e.message;
    errBox.style.display = "block";
  }
}
async function stake(){
  const bankroll = parseFloat(document.getElementById('bankroll').value || "0");
  const odds = parseFloat(document.getElementById('stakeOdds').value || "1");
  const p = parseFloat(document.getElementById('winProb').value || "0");
  const risk = document.getElementById('riskLevel').value;
  const cap = parseFloat(document.getElementById('kellyCap').value || "0.05");
  const resBox = document.getElementById('stakeRes');
  const errBox = document.getElementById('stakeErr');
  resBox.style.display = "none"; errBox.style.display="none";
  try{
    const r = await fetch("/api/v1/stake/kelly", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({bankroll, decimal_odds:odds, win_prob:p, risk_level:risk, kelly_fraction_cap:cap})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Error");
    resBox.textContent = JSON.stringify(data, null, 2);
    resBox.style.display = "block";
  }catch(e){
    errBox.textContent = e.message;
    errBox.style.display = "block";
  }
}

// Add a couple of starter legs for convenience
window.addEventListener('DOMContentLoaded', ()=>{
  addLeg();
  document.getElementById('mt-0').value = "OVER_UNDER_GOALS";
  document.getElementById('outcome-0').value = "OVER";
  document.getElementById('params-0').value = '{"line":2.5}';
  addLeg();
  document.getElementById('mt-1').value = "BTTS";
  document.getElementById('outcome-1').value = "YES";
});
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
