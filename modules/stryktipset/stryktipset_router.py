from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, validator

from sqlalchemy import (
    Column, Integer, String, DateTime, Float, ForeignKey, Text, JSON, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

# =========================
# CONFIG (change these)
# =========================

import os as _os
ADMIN_SECRET = _os.environ.get("ADMIN_API_KEY", "CHANGE_ME")
DATABASE_URL = "sqlite:///./app.db"  # or your postgres url

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(x_admin_secret: Optional[str]):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# =========================
# DB MODELS
# =========================

class StrykCoupon(Base):
    __tablename__ = "stryk_coupons"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    week_tag = Column(String(64), nullable=True)
    status = Column(String(32), default="draft")  # draft|published|settled
    created_at = Column(DateTime, default=datetime.utcnow)

    matches = relationship("StrykMatch", back_populates="coupon", cascade="all, delete-orphan")
    systems = relationship("StrykSystem", back_populates="coupon", cascade="all, delete-orphan")


class StrykMatch(Base):
    __tablename__ = "stryk_matches"
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("stryk_coupons.id"), nullable=False)
    match_no = Column(Integer, nullable=False)  # 1..13
    home_team = Column(String(255), nullable=False)
    away_team = Column(String(255), nullable=False)
    league = Column(String(255), nullable=True)
    kickoff_time = Column(DateTime, nullable=True)

    odds_1 = Column(Float, nullable=True)
    odds_x = Column(Float, nullable=True)
    odds_2 = Column(Float, nullable=True)

    public_pct_1 = Column(Float, nullable=True)  # 0-100
    public_pct_x = Column(Float, nullable=True)
    public_pct_2 = Column(Float, nullable=True)
    public_updated_at = Column(DateTime, nullable=True)

    result = Column(String(1), nullable=True)  # "1"|"X"|"2"
    settled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    coupon = relationship("StrykCoupon", back_populates="matches")
    probs = relationship("StrykProb", back_populates="match", cascade="all, delete-orphan")


class StrykProb(Base):
    __tablename__ = "stryk_probs"
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("stryk_coupons.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("stryk_matches.id"), nullable=False)

    p1 = Column(Float, nullable=False)
    px = Column(Float, nullable=False)
    p2 = Column(Float, nullable=False)

    model_version = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    match = relationship("StrykMatch", back_populates="probs")


class StrykSystem(Base):
    __tablename__ = "stryk_systems"
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("stryk_coupons.id"), nullable=False)
    mode = Column(String(16), default="reduced")  # reduced|full
    target_rows = Column(Integer, default=256)
    final_rows = Column(Integer, default=0)

    spik_count = Column(Integer, default=0)
    half_count = Column(Integer, default=0)
    full_count = Column(Integer, default=0)

    rules_json = Column(JSON, nullable=False, default=dict)
    system_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    coupon = relationship("StrykCoupon", back_populates="systems")
    rows = relationship("StrykRow", back_populates="system", cascade="all, delete-orphan")
    scores = relationship("StrykSystemScore", back_populates="system", cascade="all, delete-orphan")


class StrykRow(Base):
    __tablename__ = "stryk_rows"
    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, ForeignKey("stryk_systems.id"), nullable=False)
    row_no = Column(Integer, nullable=False)
    row_string = Column(String(13), nullable=False)  # e.g. "1X21...".

    row_prob = Column(Float, nullable=True)          # model-based prob product
    row_public_prob = Column(Float, nullable=True)   # public-based prob product
    contrarian_score = Column(Float, nullable=True)  # -log(row_public_prob)

    created_at = Column(DateTime, default=datetime.utcnow)

    system = relationship("StrykSystem", back_populates="rows")


class StrykSystemScore(Base):
    __tablename__ = "stryk_system_scores"
    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, ForeignKey("stryk_systems.id"), nullable=False)
    coupon_id = Column(Integer, nullable=False)

    computed_at = Column(DateTime, default=datetime.utcnow)
    total_rows = Column(Integer, nullable=False)
    best_correct = Column(Integer, nullable=False)
    dist_json = Column(JSON, nullable=False)  # {"0":..,"1":..,...,"13":..}

    best_row_public_prob = Column(Float, nullable=True)
    best_row_contrarian_score = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)

    system = relationship("StrykSystem", back_populates="scores")


Base.metadata.create_all(bind=engine)

# =========================
# Pydantic Schemas
# =========================

Outcome = Literal["1", "X", "2"]

class MatchIn(BaseModel):
    match_no: int = Field(..., ge=1, le=13)
    home_team: str
    away_team: str
    kickoff_time: Optional[datetime] = None
    league: Optional[str] = None

    odds_1: Optional[float] = Field(None, gt=1.0)
    odds_X: Optional[float] = Field(None, gt=1.0)
    odds_2: Optional[float] = Field(None, gt=1.0)

    public_pct_1: Optional[float] = Field(None, ge=0.0, le=100.0)
    public_pct_X: Optional[float] = Field(None, ge=0.0, le=100.0)
    public_pct_2: Optional[float] = Field(None, ge=0.0, le=100.0)


class CouponCreateIn(BaseModel):
    name: str
    week_tag: Optional[str] = None
    matches: List[MatchIn]

    @validator("matches")
    def validate_13(cls, v):
        if len(v) != 13:
            raise ValueError("Coupon must have exactly 13 matches")
        nos = sorted(m.match_no for m in v)
        if nos != list(range(1, 14)):
            raise ValueError("match_no must be exactly 1..13")
        return v


class PredictOut(BaseModel):
    match_no: int
    home_team: str
    away_team: str
    p1: float
    px: float
    p2: float
    pick: Outcome
    confidence: float


class SystemGenerateIn(BaseModel):
    preset: Literal["jackpot_aggressive"] = "jackpot_aggressive"
    target_rows: int = Field(256, ge=16, le=8192)

    # jackpot preset defaults (you can override)
    min_spikes: int = 4
    max_full_guards: int = 2
    max_half_guards: int = 7
    include_draws_policy: Literal["high", "normal", "low"] = "high"
    min_outcome_prob: float = Field(0.10, ge=0.01, le=0.30)
    alpha_public_bias: float = Field(0.25, ge=0.0, le=0.7)  # bias away from popular outcomes


class SettleIn(BaseModel):
    results: Dict[str, Outcome]  # keys "1".."13"

    @validator("results")
    def validate_results(cls, v):
        keys = sorted(int(k) for k in v.keys())
        if keys != list(range(1, 14)):
            raise ValueError("results must contain keys '1'..'13'")
        return v


class PublicUpdateIn(BaseModel):
    public: Dict[str, Dict[Outcome, float]]  # {"1":{"1":48,"X":27,"2":25}, ...}

    @validator("public")
    def validate_public(cls, v):
        keys = sorted(int(k) for k in v.keys())
        if keys != list(range(1, 14)):
            raise ValueError("public must contain keys '1'..'13'")
        for k, d in v.items():
            s = float(d.get("1", 0)) + float(d.get("X", 0)) + float(d.get("2", 0))
            if not (98.0 <= s <= 102.0):
                raise ValueError(f"public percentages for match {k} must sum ~100 (got {s})")
        return v


# =========================
# Your existing football model hook
# =========================
def predict_1x2_probabilities(home_team: str, away_team: str) -> Tuple[float, float, float, str]:
    """
    Replace this with your actual model call.
    Must return (p1, px, p2, model_version).
    """
    # --- dummy fallback (remove) ---
    r = random.random()
    p1 = 0.35 + 0.30 * r
    px = 0.20 + 0.10 * (1 - r)
    p2 = max(0.01, 1.0 - p1 - px)
    s = p1 + px + p2
    return p1 / s, px / s, p2 / s, "dummy_v1"


# =========================
# Helper functions
# =========================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def pick_outcome(p1: float, px: float, p2: float) -> Outcome:
    if p1 >= px and p1 >= p2:
        return "1"
    if px >= p1 and px >= p2:
        return "X"
    return "2"

def draw_allowed(px: float, policy: str) -> bool:
    if policy == "high":
        return px >= 0.18
    if policy == "normal":
        return px >= 0.22
    return px >= 0.26

def public_prob_for_outcome(m: StrykMatch, o: Outcome) -> Optional[float]:
    if m.public_pct_1 is None or m.public_pct_x is None or m.public_pct_2 is None:
        return None
    if o == "1":
        return clamp(m.public_pct_1 / 100.0, 0.0001, 0.9999)
    if o == "X":
        return clamp(m.public_pct_x / 100.0, 0.0001, 0.9999)
    return clamp(m.public_pct_2 / 100.0, 0.0001, 0.9999)

def outcome_weight(model_p: float, pub_p: Optional[float], alpha: float) -> float:
    # effective_weight = model_p * (1 - alpha * pub_p)
    if pub_p is None:
        return model_p
    return max(1e-9, model_p * (1.0 - alpha * pub_p))

def row_prob_product(probs_by_no: Dict[int, Dict[Outcome, float]], row: str) -> float:
    p = 1.0
    for i in range(13):
        match_no = i + 1
        o = row[i]  # "1"/"X"/"2"
        p *= probs_by_no[match_no][o]  # type: ignore[index]
    return p

def row_public_prob_product(matches_by_no: Dict[int, StrykMatch], row: str) -> Optional[float]:
    p = 1.0
    has_pub = False
    for i in range(13):
        match_no = i + 1
        o: Outcome = row[i]  # type: ignore[assignment]
        pub = public_prob_for_outcome(matches_by_no[match_no], o)
        if pub is None:
            continue
        has_pub = True
        p *= pub
    return p if has_pub else None

def contrarian_score_from_public_prob(pub_prob: Optional[float]) -> Optional[float]:
    if pub_prob is None or pub_prob <= 0:
        return None
    return -math.log(pub_prob)

# =========================
# Router
# =========================

router = APIRouter(prefix="/admin/stryk", tags=["stryktipset-admin"])


@router.post("/coupons")
def create_coupon(
    payload: CouponCreateIn,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    coupon = StrykCoupon(name=payload.name, week_tag=payload.week_tag, status="draft")
    db.add(coupon)
    db.flush()  # get id

    for m in payload.matches:
        sm = StrykMatch(
            coupon_id=coupon.id,
            match_no=m.match_no,
            home_team=m.home_team.strip(),
            away_team=m.away_team.strip(),
            league=m.league,
            kickoff_time=m.kickoff_time,
            odds_1=m.odds_1,
            odds_x=m.odds_X,
            odds_2=m.odds_2,
            public_pct_1=m.public_pct_1,
            public_pct_x=m.public_pct_X,
            public_pct_2=m.public_pct_2,
            public_updated_at=datetime.utcnow() if (m.public_pct_1 is not None) else None,
        )
        db.add(sm)

    db.commit()
    return {"coupon_id": coupon.id, "status": coupon.status}


@router.post("/coupons/{coupon_id}/predict")
def predict_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    coupon: StrykCoupon | None = db.get(StrykCoupon, coupon_id)
    if not coupon:
        raise HTTPException(404, "Coupon not found")

    matches = db.query(StrykMatch).filter(StrykMatch.coupon_id == coupon_id).order_by(StrykMatch.match_no).all()
    if len(matches) != 13:
        raise HTTPException(400, "Coupon must have 13 matches")

    # delete old probs for coupon
    db.query(StrykProb).filter(StrykProb.coupon_id == coupon_id).delete()

    out: List[PredictOut] = []
    for m in matches:
        p1, px, p2, ver = predict_1x2_probabilities(m.home_team, m.away_team)
        p1, px, p2 = clamp(p1, 0.001, 0.999), clamp(px, 0.001, 0.999), clamp(p2, 0.001, 0.999)
        s = p1 + px + p2
        p1, px, p2 = p1 / s, px / s, p2 / s

        db.add(StrykProb(
            coupon_id=coupon_id,
            match_id=m.id,
            p1=p1, px=px, p2=p2,
            model_version=ver
        ))

        pick = pick_outcome(p1, px, p2)
        conf = max(p1, px, p2)
        out.append(PredictOut(
            match_no=m.match_no,
            home_team=m.home_team,
            away_team=m.away_team,
            p1=p1, px=px, p2=p2,
            pick=pick,
            confidence=conf
        ))

    db.commit()
    return {"coupon_id": coupon_id, "predictions": [o.dict() for o in out]}


@router.post("/coupons/{coupon_id}/public")
def update_public(
    coupon_id: int,
    payload: PublicUpdateIn,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    matches = db.query(StrykMatch).filter(StrykMatch.coupon_id == coupon_id).all()
    if len(matches) != 13:
        raise HTTPException(400, "Coupon must have 13 matches")

    by_no = {m.match_no: m for m in matches}
    now = datetime.utcnow()

    for k, d in payload.public.items():
        no = int(k)
        m = by_no[no]
        m.public_pct_1 = float(d["1"])
        m.public_pct_x = float(d["X"])
        m.public_pct_2 = float(d["2"])
        m.public_updated_at = now

    db.commit()
    return {"coupon_id": coupon_id, "updated": 13}


@router.post("/coupons/{coupon_id}/generate_system")
def generate_system(
    coupon_id: int,
    payload: SystemGenerateIn,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    matches = db.query(StrykMatch).filter(StrykMatch.coupon_id == coupon_id).order_by(StrykMatch.match_no).all()
    probs = (
        db.query(StrykProb, StrykMatch.match_no)
        .join(StrykMatch, StrykProb.match_id == StrykMatch.id)
        .filter(StrykProb.coupon_id == coupon_id)
        .all()
    )
    if len(matches) != 13:
        raise HTTPException(400, "Coupon must have 13 matches")
    if len(probs) != 13:
        raise HTTPException(400, "Run /predict first so we have p1/px/p2 for all matches")

    matches_by_no = {m.match_no: m for m in matches}
    probs_by_no: Dict[int, Dict[Outcome, float]] = {}

    # Build probabilities map
    for prob, match_no in probs:
        probs_by_no[match_no] = {"1": prob.p1, "X": prob.px, "2": prob.p2}

    # --- 1) Decide allowed outcomes sets per match (jackpot_aggressive) ---
    # We classify using top, second, entropy/gap, draw policy, and min_outcome_prob.
    allowed: Dict[int, List[Outcome]] = {}
    spike_candidates: List[Tuple[int, float, float]] = []  # (match_no, top_prob, gap)

    for no in range(1, 14):
        p = probs_by_no[no]
        sorted_outs = sorted(p.items(), key=lambda kv: kv[1], reverse=True)
        top_o, top_p = sorted_outs[0][0], sorted_outs[0][1]
        second_o, second_p = sorted_outs[1][0], sorted_outs[1][1]
        gap = top_p - second_p

        # base allowed outcomes: top+second, maybe add third if uncertain
        base = [top_o, second_o]

        # enforce draw policy: include X more in jackpot mode
        if "X" in base and not draw_allowed(p["X"], payload.include_draws_policy):
            # replace X with third best if X not allowed by policy
            third_o = sorted_outs[2][0]
            base = [top_o, third_o]

        # prune too-low outcomes in reduced mode
        base = [o for o in base if p[o] >= payload.min_outcome_prob]  # type: ignore[index]
        if len(base) == 0:
            base = [top_o]

        # mark good spike candidates (high top + decent gap)
        spike_candidates.append((no, top_p, gap))

        allowed[no] = base

    # choose spikes: prioritize high top_prob AND high gap
    spike_candidates.sort(key=lambda t: (t[1], t[2]), reverse=True)
    spikes = set([no for no, _, _ in spike_candidates[:payload.min_spikes]])

    # now choose full guards (uncertain matches): low gap / high entropy
    uncertainty = []
    for no in range(1, 14):
        p = probs_by_no[no]
        # entropy
        ent = -sum(v * math.log(v) for v in p.values())
        sorted_outs = sorted(p.values(), reverse=True)
        gap = sorted_outs[0] - sorted_outs[1]
        uncertainty.append((no, ent, -gap))
    uncertainty.sort(key=lambda t: (t[1], t[2]), reverse=True)
    fulls = set([no for no, _, _ in uncertainty[:payload.max_full_guards]])

    # build final allowed sets
    spik_count = half_count = full_count = 0
    for no in range(1, 14):
        p = probs_by_no[no]
        sorted_outs = sorted(p.items(), key=lambda kv: kv[1], reverse=True)
        top_o = sorted_outs[0][0]
        second_o = sorted_outs[1][0]
        third_o = sorted_outs[2][0]

        if no in fulls:
            # full guard but still prune extreme low if configured? in jackpot keep all
            allowed[no] = ["1", "X", "2"]
            full_count += 1
            continue

        if no in spikes:
            allowed[no] = [top_o]
            spik_count += 1
            continue

        # half guard
        base = [top_o, second_o]
        if "X" in base and not draw_allowed(p["X"], payload.include_draws_policy):
            base = [top_o, third_o]
        # prune too low
        base = [o for o in base if p[o] >= payload.min_outcome_prob]  # type: ignore[index]
        if len(base) == 1:
            # stays a spike effectively
            spik_count += 1
        else:
            half_count += 1
        allowed[no] = base  # type: ignore[assignment]

    # enforce max_half_guards by turning lowest-value halves into spikes
    # (turn halves with biggest top_prob into spikes first to keep "jackpot edge")
    halves = [no for no in range(1, 14) if len(allowed[no]) == 2]
    if len(halves) > payload.max_half_guards:
        halves_rank = []
        for no in halves:
            p = probs_by_no[no]
            top_p = max(p.values())
            halves_rank.append((no, top_p))
        halves_rank.sort(key=lambda t: t[1], reverse=True)
        to_spike = [no for no, _ in halves_rank[payload.max_half_guards:]]
        for no in to_spike:
            p = probs_by_no[no]
            top_o = max(p.items(), key=lambda kv: kv[1])[0]
            allowed[no] = [top_o]
            half_count -= 1
            spik_count += 1

    # compute theoretical full rows count
    theoretical_rows = 1
    for no in range(1, 14):
        theoretical_rows *= len(allowed[no])

    # --- 2) Create system row candidates via weighted sampling + dedupe + greedy pick ---
    target_rows = payload.target_rows
    candidate_count = min(max(target_rows * 50, 5000), 200000)

    candidates = {}
    alpha = payload.alpha_public_bias

    for _ in range(candidate_count):
        row_chars: List[str] = []
        for no in range(1, 14):
            choices = allowed[no]
            # build weights
            weights = []
            for o in choices:
                mp = probs_by_no[no][o]  # type: ignore[index]
                pub = public_prob_for_outcome(matches_by_no[no], o)
                weights.append(outcome_weight(mp, pub, alpha))
            # random.choices supports weights
            chosen: Outcome = random.choices(choices, weights=weights, k=1)[0]  # type: ignore[assignment]
            row_chars.append(chosen)
        row = "".join(row_chars)
        candidates[row] = 1  # dedupe

    candidate_rows = list(candidates.keys())

    # score candidates by row_prob and a small diversity bonus via Hamming distance later
    # For speed: take top by row_prob first
    scored: List[Tuple[str, float]] = []
    for row in candidate_rows:
        rp = row_prob_product(probs_by_no, row)
        scored.append((row, rp))
    scored.sort(key=lambda t: t[1], reverse=True)

    # take a manageable pool for greedy selection
    pool = scored[: min(len(scored), max(target_rows * 10, 2000))]

    selected: List[str] = []
    selected_set = set()

    def min_hamming(row: str, others: List[str]) -> int:
        if not others:
            return 13
        best = 13
        for r in others[-100:]:  # only compare last 100 for speed
            d = sum(1 for i in range(13) if row[i] != r[i])
            if d < best:
                best = d
        return best

    for row, rp in pool:
        if row in selected_set:
            continue
        # prefer diversity: require a minimum distance for early picks
        if len(selected) < target_rows:
            md = min_hamming(row, selected)
            if len(selected) < 30 and md < 4:
                continue
            if len(selected) < 200 and md < 3:
                continue
        selected.append(row)
        selected_set.add(row)
        if len(selected) >= target_rows:
            break

    # if we still don't have enough, fill with best remaining
    if len(selected) < target_rows:
        for row, _rp in pool:
            if row not in selected_set:
                selected.append(row)
                selected_set.add(row)
                if len(selected) >= target_rows:
                    break

    final_rows = selected[:target_rows]

    # store system
    system = StrykSystem(
        coupon_id=coupon_id,
        mode="reduced",
        target_rows=target_rows,
        final_rows=len(final_rows),
        spik_count=spik_count,
        half_count=half_count,
        full_count=full_count,
        rules_json={
            "preset": payload.preset,
            "allowed": {str(k): v for k, v in allowed.items()},
            "theoretical_rows": theoretical_rows,
            "alpha_public_bias": alpha,
            "min_outcome_prob": payload.min_outcome_prob,
            "include_draws_policy": payload.include_draws_policy,
        },
        system_summary=f"jackpot_aggressive reduced {len(final_rows)} rows | spikes={spik_count} half={half_count} full={full_count} | theoretical={theoretical_rows}"
    )
    db.add(system)
    db.flush()

    # store rows
    db.query(StrykRow).filter(StrykRow.system_id == system.id).delete()
    for idx, row in enumerate(final_rows, start=1):
        rp = row_prob_product(probs_by_no, row)
        pubp = row_public_prob_product(matches_by_no, row)
        cs = contrarian_score_from_public_prob(pubp)
        db.add(StrykRow(
            system_id=system.id,
            row_no=idx,
            row_string=row,
            row_prob=rp,
            row_public_prob=pubp,
            contrarian_score=cs
        ))

    db.commit()

    return {
        "coupon_id": coupon_id,
        "system_id": system.id,
        "mode": system.mode,
        "target_rows": system.target_rows,
        "final_rows": system.final_rows,
        "spikes": system.spik_count,
        "half_guards": system.half_count,
        "full_guards": system.full_count,
        "theoretical_rows": theoretical_rows,
        "summary": system.system_summary,
    }


@router.post("/coupons/{coupon_id}/settle")
def settle_coupon(
    coupon_id: int,
    payload: SettleIn,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    matches = db.query(StrykMatch).filter(StrykMatch.coupon_id == coupon_id).order_by(StrykMatch.match_no).all()
    if len(matches) != 13:
        raise HTTPException(400, "Coupon must have 13 matches")
    by_no = {m.match_no: m for m in matches}
    now = datetime.utcnow()

    for k, res in payload.results.items():
        no = int(k)
        by_no[no].result = res
        by_no[no].settled_at = now

    # mark coupon settled
    coupon = db.get(StrykCoupon, coupon_id)
    if coupon:
        coupon.status = "settled"

    db.commit()
    return {"coupon_id": coupon_id, "status": "settled"}


@router.post("/coupons/{coupon_id}/score_system/{system_id}")
def score_system(
    coupon_id: int,
    system_id: int,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    matches = db.query(StrykMatch).filter(StrykMatch.coupon_id == coupon_id).order_by(StrykMatch.match_no).all()
    if len(matches) != 13:
        raise HTTPException(400, "Coupon must have 13 matches")
    results = {m.match_no: m.result for m in matches}
    if any(results[i] is None for i in range(1, 14)):
        raise HTTPException(400, "Coupon not fully settled (missing results)")

    system = db.get(StrykSystem, system_id)
    if not system or system.coupon_id != coupon_id:
        raise HTTPException(404, "System not found for coupon")

    rows = db.query(StrykRow).filter(StrykRow.system_id == system_id).order_by(StrykRow.row_no).all()
    if not rows:
        raise HTTPException(400, "No rows stored for this system")

    dist = {str(k): 0 for k in range(0, 14)}
    best_correct = 0
    best_rows: List[StrykRow] = []

    for r in rows:
        correct = 0
        for i in range(13):
            no = i + 1
            if r.row_string[i] == results[no]:
                correct += 1
        dist[str(correct)] += 1
        if correct > best_correct:
            best_correct = correct
            best_rows = [r]
        elif correct == best_correct:
            best_rows.append(r)

    # pick "best" among best_correct rows by row_prob if available
    best_row = None
    if best_rows:
        best_row = sorted(best_rows, key=lambda x: (x.row_prob or 0.0), reverse=True)[0]

    score = StrykSystemScore(
        system_id=system_id,
        coupon_id=coupon_id,
        total_rows=len(rows),
        best_correct=best_correct,
        dist_json=dist,
        best_row_public_prob=(best_row.row_public_prob if best_row else None),
        best_row_contrarian_score=(best_row.contrarian_score if best_row else None),
        notes=f"best_row={best_row.row_string if best_row else None}"
    )
    db.add(score)
    db.commit()

    return {
        "coupon_id": coupon_id,
        "system_id": system_id,
        "total_rows": len(rows),
        "best_correct": best_correct,
        "distribution": dist,
        "best_row_public_prob": score.best_row_public_prob,
        "best_row_contrarian_score": score.best_row_contrarian_score,
        "notes": score.notes,
    }


@router.get("/coupons/{coupon_id}")
def get_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    coupon = db.get(StrykCoupon, coupon_id)
    if not coupon:
        raise HTTPException(404, "Coupon not found")

    matches = db.query(StrykMatch).filter(StrykMatch.coupon_id == coupon_id).order_by(StrykMatch.match_no).all()
    probs = (
        db.query(StrykProb, StrykMatch.match_no)
        .join(StrykMatch, StrykProb.match_id == StrykMatch.id)
        .filter(StrykProb.coupon_id == coupon_id)
        .all()
    )
    probs_by_no = {match_no: p for p, match_no in probs}

    out_matches = []
    for m in matches:
        p = probs_by_no.get(m.match_no)
        out_matches.append({
            "match_no": m.match_no,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "kickoff_time": m.kickoff_time,
            "league": m.league,
            "odds": {"1": m.odds_1, "X": m.odds_x, "2": m.odds_2},
            "public_pct": {"1": m.public_pct_1, "X": m.public_pct_x, "2": m.public_pct_2},
            "result": m.result,
            "probs": {"1": p.p1, "X": p.px, "2": p.p2} if p else None,
        })

    systems = db.query(StrykSystem).filter(StrykSystem.coupon_id == coupon_id).order_by(StrykSystem.created_at.desc()).all()
    out_systems = [{
        "system_id": s.id,
        "mode": s.mode,
        "target_rows": s.target_rows,
        "final_rows": s.final_rows,
        "spikes": s.spik_count,
        "half_guards": s.half_count,
        "full_guards": s.full_count,
        "summary": s.system_summary,
        "rules": s.rules_json,
        "created_at": s.created_at,
    } for s in systems]

    return {"coupon": {"id": coupon.id, "name": coupon.name, "status": coupon.status, "created_at": coupon.created_at},
            "matches": out_matches,
            "systems": out_systems}


@router.get("/scores/summary")
def scores_summary(
    last_n: int = 20,
    db: Session = Depends(get_db),
    x_admin_secret: Optional[str] = Header(default=None),
):
    require_admin(x_admin_secret)

    scores = db.query(StrykSystemScore).order_by(StrykSystemScore.computed_at.desc()).limit(last_n).all()
    agg = {"ge10": 0, "ge11": 0, "ge12": 0, "eq13": 0, "avg_best": 0.0}
    if scores:
        agg["avg_best"] = sum(s.best_correct for s in scores) / len(scores)
        for s in scores:
            if s.best_correct >= 10: agg["ge10"] += 1
            if s.best_correct >= 11: agg["ge11"] += 1
            if s.best_correct >= 12: agg["ge12"] += 1
            if s.best_correct == 13: agg["eq13"] += 1

    return {
        "last_n": last_n,
        "aggregate": agg,
        "items": [{
            "system_id": s.system_id,
            "coupon_id": s.coupon_id,
            "best_correct": s.best_correct,
            "total_rows": s.total_rows,
            "dist": s.dist_json,
            "computed_at": s.computed_at,
            "best_row_contrarian_score": s.best_row_contrarian_score,
        } for s in scores]
    }
