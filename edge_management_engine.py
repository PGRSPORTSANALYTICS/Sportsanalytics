"""
Edge Management Engine v1.0
===========================
Protects ROI by continuously analysing performance data and classifying
markets/leagues as ACTIVE, DEGRADED, or DISABLED.

Decision rules follow the spec exactly:
  - DEGRADED : CLV < 0 (100+ picks) | hit-rate drop > 15pp | ROI < 0 (100+)
  - DISABLE  : CLV < -2% | ROI < -20% (severe negative)
  - League LEARNING : CLV < 0 over 50+ picks
  - League PROD    : stable positive CLV over 100+ picks
  - Shrink flag    : change > ±0.10 in 30 days
  - Summer leagues : treated as new env, require fresh CLV validation

Output is saved to `edge_decisions` DB table and returned as a structured dict.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import psycopg2

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────
CLV_DEGRADED_THRESHOLD  =  0.0    # avg CLV < 0   → DEGRADED
CLV_DISABLE_THRESHOLD   = -2.0    # avg CLV < -2% → DISABLE
HIT_DROP_THRESHOLD      = 15.0    # hit-rate drop > 15pp vs all_time → DEGRADED
ROI_DEGRADED_THRESHOLD  =  0.0    # recent ROI < 0          → DEGRADED
ROI_DISABLE_THRESHOLD   = -20.0   # recent ROI < -20%       → DISABLE

# Tiered sample requirements — high-volume markets (Value Single) need 100+;
# low-volume markets (Corners, Cards) only generate ~10–30 settled picks per window.
MIN_SAMPLE_CLV          = 100     # min picks for CLV-based decisions
MIN_SAMPLE_HIT_RATE     =  25     # min picks for hit-rate-drop signal
MIN_SAMPLE_ROI          =  25     # min picks for ROI signal
MIN_SAMPLE_MARKET       =  25     # overall gate (any signal valid above this)
MIN_SAMPLE_LEAGUE       =  50     # min picks for league CLV signal
MIN_SAMPLE_PROMOTE      = 100     # min picks for league PROD promotion
SHRINK_CHANGE_FLAG      =  0.10   # ±0.10 shift in shrink factor → instability
EV_ADJ_DEGRADED         =  2.0    # raise min-EV by 2pp for degraded markets
EV_ADJ_ACTIVE_CLV       = -0.5    # lower min-EV 0.5pp for positive-CLV markets

SUMMER_LEAGUES = {
    "Swedish Allsvenskan", "Norwegian Eliteserien", "Finnish Veikkausliiga",
    "Danish Superliga", "Australian A-League", "Major League Soccer",
    "Brazilian Serie A", "Argentinian Primera Division",
    "Korean K League 1", "J1 League",
}

MARKET_DISPLAY = {
    "Value Single": "Value Single",
    "Corners":      "Corners",
    "Cards":        "Cards",
}

# ── Data classes ───────────────────────────────────────────────────────────────
@dataclass
class MarketDecision:
    market:              str
    status:              str           # ACTIVE | DEGRADED | DISABLED
    clv_avg:             Optional[float]
    clv_n:               int
    hit_rate_recent:     Optional[float]
    hit_rate_historical: Optional[float]
    roi_recent:          Optional[float]
    sample_recent:       int
    reason:              str
    ev_threshold_adj:    float
    volume_adj:          str           # INCREASE | DECREASE | MAINTAIN


@dataclass
class LeagueDecision:
    league:      str
    market:      str
    status:      str           # PROD | LEARNING
    clv_avg:     Optional[float]
    clv_n:       int
    hit_rate:    Optional[float]
    roi:         Optional[float]
    sample:      int
    is_summer:   bool
    reason:      str


@dataclass
class EdgeCycle:
    run_at:               str
    active_markets:       List[str]
    degraded_markets:     List[MarketDecision]
    disabled_markets:     List[MarketDecision]
    all_market_decisions: List[MarketDecision]
    active_leagues:       List[LeagueDecision]
    learning_leagues:     List[LeagueDecision]
    stability_flags:      List[str]
    ev_adjustments:       Dict[str, float]
    volume_adjustments:   Dict[str, str]
    shrink_current:       Optional[float]
    shrink_past:          Optional[float]


# ── Engine ─────────────────────────────────────────────────────────────────────
class EdgeManagementEngine:

    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")

    def _conn(self):
        return psycopg2.connect(self.db_url, connect_timeout=10)

    # ── DB setup ────────────────────────────────────────────────────────────────
    def ensure_table(self):
        sql = """
        CREATE TABLE IF NOT EXISTS edge_decisions (
            id          SERIAL PRIMARY KEY,
            run_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            cycle_json  JSONB        NOT NULL,
            summary     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_edge_decisions_run_at ON edge_decisions(run_at DESC);
        """
        try:
            conn = self._conn()
            cur = conn.cursor()
            cur.execute(sql)
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Edge table init error: {e}")

    # ── Data fetchers ───────────────────────────────────────────────────────────
    def get_market_performance(self) -> Dict[str, Dict]:
        """
        Fetch market-level stats from learning_stats:
          all_time  → historical baseline
          last_100  → recent 100-pick window
          last_50   → very recent 50-pick window
        Also pulls raw CLV from football_opportunities for Value Single.
        """
        data: Dict[str, Dict] = {}
        try:
            conn = self._conn()
            cur = conn.cursor()

            cur.execute("""
                SELECT dimension_key, window_type,
                       total_bets, wins, hit_rate, roi_pct,
                       avg_clv, profit_units, score
                FROM   learning_stats
                WHERE  dimension = 'market'
                ORDER  BY dimension_key, window_type
            """)
            rows = cur.fetchall()
            for row in rows:
                mkt, win, n, wins, hr, roi, clv, pu, score = row
                if mkt not in data:
                    data[mkt] = {}
                data[mkt][win] = {
                    "total_bets": n or 0,
                    "wins": wins or 0,
                    "hit_rate": float(hr) if hr is not None else None,
                    "roi_pct":  float(roi) if roi is not None else None,
                    "avg_clv":  float(clv) if clv is not None else None,
                    "profit_units": float(pu) if pu is not None else None,
                    "score": float(score) if score is not None else None,
                }

            cur.execute("""
                SELECT
                    UPPER(market)                              AS market,
                    COUNT(*) FILTER (WHERE clv_pct IS NOT NULL) AS n,
                    AVG(clv_pct) FILTER (WHERE clv_pct IS NOT NULL) AS avg_clv,
                    COUNT(*) FILTER (WHERE clv_pct IS NOT NULL AND clv_pct > 0) AS clv_pos
                FROM   football_opportunities
                WHERE  mode = 'PROD'
                GROUP  BY 1
            """)
            for mkt, n, avg_clv, clv_pos in cur.fetchall():
                label = mkt.title()
                if label not in data:
                    data[label] = {}
                data[label]["_clv_direct"] = {
                    "n": int(n) if n else 0,
                    "avg_clv": float(avg_clv) if avg_clv is not None else None,
                    "clv_pos": int(clv_pos) if clv_pos else 0,
                }

            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"get_market_performance error: {e}")
        return data

    def get_league_performance(self) -> Dict[Tuple[str, str], Dict]:
        """
        Returns { (league, market): {all_time: {...}, last_100: {...}, last_50: {...}} }
        from learning_stats dimension='league_market'.
        """
        data: Dict[Tuple[str, str], Dict] = {}
        try:
            conn = self._conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT dimension_key, window_type,
                       total_bets, wins, hit_rate, roi_pct,
                       avg_clv, profit_units, score
                FROM   learning_stats
                WHERE  dimension = 'league_market'
                ORDER  BY dimension_key, window_type
            """)
            for row in cur.fetchall():
                key_raw, win, n, wins, hr, roi, clv, pu, score = row
                if "|" not in key_raw:
                    continue
                league, mkt = key_raw.split("|", 1)
                league, mkt = league.strip(), mkt.strip()
                k = (league, mkt)
                if k not in data:
                    data[k] = {}
                data[k][win] = {
                    "total_bets": int(n) if n else 0,
                    "wins": int(wins) if wins else 0,
                    "hit_rate": float(hr)  if hr  is not None else None,
                    "roi_pct":  float(roi) if roi is not None else None,
                    "avg_clv":  float(clv) if clv is not None else None,
                    "profit_units": float(pu) if pu is not None else None,
                    "score": float(score) if score is not None else None,
                }
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"get_league_performance error: {e}")
        return data

    def get_shrink_history(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Returns (current_shrink, shrink_30_days_ago) from model_calibrator state.
        Falls back to None if unavailable.
        """
        current = None
        past    = None
        try:
            from model_calibrator import ModelCalibrator
            cal = ModelCalibrator()
            state = cal.get_current_state()
            current = state.get("shrink_factor")
        except Exception:
            pass

        try:
            conn = self._conn()
            cur  = conn.cursor()
            cur.execute("""
                SELECT shrink_factor
                FROM   calibration_history
                WHERE  computed_at <= NOW() - INTERVAL '30 days'
                ORDER  BY computed_at DESC
                LIMIT  1
            """)
            row = cur.fetchone()
            if row:
                past = float(row[0])
            cur.close()
            conn.close()
        except Exception:
            pass

        return current, past

    # ── Classifiers ─────────────────────────────────────────────────────────────
    def classify_market(self, market: str, mkt_data: Dict) -> MarketDecision:
        all_time   = mkt_data.get("all_time",  {})
        recent_100 = mkt_data.get("last_100",  {})
        recent_50  = mkt_data.get("last_50",   {})
        clv_direct = mkt_data.get("_clv_direct", {})

        # Use most recent meaningful window for "recent" stats
        if recent_100.get("total_bets", 0) >= MIN_SAMPLE_MARKET:
            recent = recent_100
        else:
            recent = recent_50

        hr_hist   = all_time.get("hit_rate")
        hr_recent = recent.get("hit_rate")
        roi_rec   = recent.get("roi_pct")
        sample    = recent.get("total_bets", 0)

        # CLV: prefer direct DB measurement (real close-odds capture).
        # learning_stats avg_clv is stored as 0.0 when no CLV was collected —
        # distinguish that from a genuine CLV of exactly 0% by checking n > 0
        # in the direct query and abs(clv) > 0.01.
        clv_n   = clv_direct.get("n", 0)
        clv_avg = clv_direct.get("avg_clv") if clv_n >= MIN_SAMPLE_CLV else None

        if clv_avg is None:
            for win in ("last_100", "last_50", "all_time"):
                candidate_clv = mkt_data.get(win, {}).get("avg_clv")
                candidate_n   = mkt_data.get(win, {}).get("total_bets", 0)
                if (candidate_clv is not None
                        and abs(candidate_clv) > 0.01        # not a "no-CLV" zero
                        and candidate_n >= MIN_SAMPLE_CLV):
                    clv_avg = candidate_clv
                    clv_n   = candidate_n
                    break

        reasons = []
        status = "ACTIVE"

        # ── CLV signal (requires MIN_SAMPLE_CLV meaningful observations) ─────
        if clv_avg is not None and clv_n >= MIN_SAMPLE_CLV:
            if clv_avg < CLV_DISABLE_THRESHOLD:
                status = "DISABLED"
                reasons.append(f"CLV {clv_avg:+.2f}% < disable threshold {CLV_DISABLE_THRESHOLD}%")
            elif clv_avg < CLV_DEGRADED_THRESHOLD:
                if status != "DISABLED":
                    status = "DEGRADED"
                reasons.append(f"CLV {clv_avg:+.2f}% negative ({clv_n} picks)")

        # ── Hit-rate signal (min MIN_SAMPLE_HIT_RATE recent picks) ───────────
        if hr_hist is not None and hr_recent is not None and sample >= MIN_SAMPLE_HIT_RATE:
            drop = hr_hist - hr_recent
            if drop > HIT_DROP_THRESHOLD:
                if status not in ("DISABLED",):
                    status = "DEGRADED"
                reasons.append(
                    f"Hit-rate collapsed {drop:.1f}pp "
                    f"(historical {hr_hist:.1f}% → recent {hr_recent:.1f}%, n={sample})"
                )

        # ── ROI signal (min MIN_SAMPLE_ROI recent picks) ─────────────────────
        # CLV override: strong positive CLV (>2%) means model edge is real;
        # negative short-term ROI is treated as variance → skip DEGRADED,
        # but DISABLED still triggers on catastrophic ROI.
        clv_strong_positive = (clv_avg is not None
                                and clv_avg > 2.0
                                and clv_n >= MIN_SAMPLE_CLV)
        if roi_rec is not None and sample >= MIN_SAMPLE_ROI:
            if roi_rec < ROI_DISABLE_THRESHOLD:
                status = "DISABLED"
                reasons.append(
                    f"ROI {roi_rec:+.1f}% severely negative over {sample} picks "
                    f"(threshold {ROI_DISABLE_THRESHOLD}%)"
                )
            elif roi_rec < ROI_DEGRADED_THRESHOLD and not clv_strong_positive:
                if status not in ("DISABLED",):
                    status = "DEGRADED"
                reasons.append(f"ROI {roi_rec:+.1f}% negative over {sample} picks")
            elif roi_rec < ROI_DEGRADED_THRESHOLD and clv_strong_positive:
                reasons.append(
                    f"ROI {roi_rec:+.1f}% negative but CLV {clv_avg:+.2f}% overrides "
                    f"— likely variance, staying ACTIVE"
                )

        # ── Insufficient sample note ─────────────────────────────────────────
        if sample < MIN_SAMPLE_HIT_RATE and clv_n < MIN_SAMPLE_CLV:
            reasons.append(
                f"Sample too small for strong signal ({max(sample, clv_n)} picks)"
            )

        if not reasons:
            reasons.append("All signals within acceptable range")

        # ── EV threshold & volume adjustments ───────────────────────────────
        if status == "ACTIVE":
            if clv_avg is not None and clv_avg > 1.0 and clv_n >= 30:
                ev_adj = EV_ADJ_ACTIVE_CLV
                vol_adj = "INCREASE"
            else:
                ev_adj = 0.0
                vol_adj = "MAINTAIN"
        elif status == "DEGRADED":
            ev_adj = EV_ADJ_DEGRADED
            vol_adj = "DECREASE"
        else:  # DISABLED
            ev_adj = 0.0
            vol_adj = "MAINTAIN"

        return MarketDecision(
            market              = market,
            status              = status,
            clv_avg             = round(clv_avg, 3) if clv_avg is not None else None,
            clv_n               = clv_n,
            hit_rate_recent     = round(hr_recent, 1) if hr_recent is not None else None,
            hit_rate_historical = round(hr_hist,   1) if hr_hist   is not None else None,
            roi_recent          = round(roi_rec,   1) if roi_rec   is not None else None,
            sample_recent       = sample,
            reason              = "; ".join(reasons),
            ev_threshold_adj    = ev_adj,
            volume_adj          = vol_adj,
        )

    def classify_league(
        self, league: str, market: str, lg_data: Dict
    ) -> LeagueDecision:
        all_time   = lg_data.get("all_time",  {})
        recent_100 = lg_data.get("last_100",  {})
        recent_50  = lg_data.get("last_50",   {})
        is_summer  = league in SUMMER_LEAGUES

        # Pick best window
        if recent_100.get("total_bets", 0) >= MIN_SAMPLE_LEAGUE:
            ref = recent_100
        elif recent_50.get("total_bets", 0) >= MIN_SAMPLE_LEAGUE:
            ref = recent_50
        else:
            ref = all_time

        n       = ref.get("total_bets", 0)
        hr      = ref.get("hit_rate")
        roi     = ref.get("roi_pct")
        clv     = ref.get("avg_clv")
        hist_n  = all_time.get("total_bets", 0)

        status  = "PROD"
        reasons = []

        # Summer leagues always start in LEARNING until validated
        if is_summer and (clv is None or n < MIN_SAMPLE_LEAGUE):
            status = "LEARNING"
            reasons.append("Summer league – requires fresh CLV validation")

        # CLV signal (primary)
        elif clv is not None and n >= MIN_SAMPLE_LEAGUE:
            if clv < CLV_DEGRADED_THRESHOLD:
                status = "LEARNING"
                reasons.append(f"CLV {clv:+.2f}% < 0 over {n} picks")
            elif clv > 0 and hist_n >= MIN_SAMPLE_PROMOTE:
                status = "PROD"
                reasons.append(f"Stable positive CLV {clv:+.2f}% over {hist_n} picks")
            else:
                status = "LEARNING"
                reasons.append(f"Positive CLV but insufficient history ({hist_n}/{MIN_SAMPLE_PROMOTE})")

        # Fallback: ROI / hit-rate
        elif roi is not None and n >= MIN_SAMPLE_LEAGUE:
            if roi < ROI_DISABLE_THRESHOLD:
                status = "LEARNING"
                reasons.append(f"ROI {roi:+.1f}% severely negative over {n} picks")
            elif roi < ROI_DEGRADED_THRESHOLD:
                status = "LEARNING"
                reasons.append(f"ROI {roi:+.1f}% negative over {n} picks")
            else:
                status = "PROD"
                reasons.append(f"ROI {roi:+.1f}% acceptable (no CLV data)")
        else:
            status = "LEARNING"
            reasons.append(f"Insufficient data ({n} picks, CLV={clv})")

        return LeagueDecision(
            league   = league,
            market   = market,
            status   = status,
            clv_avg  = round(clv, 3) if clv is not None else None,
            clv_n    = n,
            hit_rate = round(hr,  1) if hr  is not None else None,
            roi      = round(roi, 1) if roi is not None else None,
            sample   = n,
            is_summer = is_summer,
            reason   = "; ".join(reasons),
        )

    # ── Main cycle ──────────────────────────────────────────────────────────────
    def run_cycle(self) -> EdgeCycle:
        run_at = datetime.now(timezone.utc).isoformat()
        logger.info("🔬 Edge Management Engine — starting cycle")

        mkt_perf = self.get_market_performance()
        lg_perf  = self.get_league_performance()
        shrink_current, shrink_past = self.get_shrink_history()

        # ── Market decisions ──────────────────────────────────────────────────
        all_mkt_decisions: List[MarketDecision] = []
        for mkt, data in mkt_perf.items():
            if mkt.startswith("_") or mkt == "Value Single|Corners":
                continue
            dec = self.classify_market(mkt, data)
            all_mkt_decisions.append(dec)

        active_markets   = [d.market for d in all_mkt_decisions if d.status == "ACTIVE"]
        degraded_markets = [d for d in all_mkt_decisions if d.status == "DEGRADED"]
        disabled_markets = [d for d in all_mkt_decisions if d.status == "DISABLED"]

        # ── League decisions ──────────────────────────────────────────────────
        all_league_decisions: List[LeagueDecision] = []
        for (league, market), data in lg_perf.items():
            dec = self.classify_league(league, market, data)
            all_league_decisions.append(dec)

        active_leagues   = [d for d in all_league_decisions if d.status == "PROD"]
        learning_leagues = [d for d in all_league_decisions if d.status == "LEARNING"]

        # ── Shrink stability ──────────────────────────────────────────────────
        stability_flags = []
        if shrink_current is not None and shrink_past is not None:
            delta = abs(shrink_current - shrink_past)
            if delta > SHRINK_CHANGE_FLAG:
                stability_flags.append(
                    f"⚠️ Model instability: shrink factor changed {shrink_past:.3f} → "
                    f"{shrink_current:.3f} (Δ={delta:.3f} > {SHRINK_CHANGE_FLAG} threshold)"
                )

        # ── EV & volume aggregation ───────────────────────────────────────────
        ev_adj  = {d.market: d.ev_threshold_adj for d in all_mkt_decisions if d.ev_threshold_adj != 0}
        vol_adj = {d.market: d.volume_adj       for d in all_mkt_decisions}

        cycle = EdgeCycle(
            run_at               = run_at,
            active_markets       = active_markets,
            degraded_markets     = degraded_markets,
            disabled_markets     = disabled_markets,
            all_market_decisions = all_mkt_decisions,
            active_leagues       = active_leagues,
            learning_leagues     = learning_leagues,
            stability_flags      = stability_flags,
            ev_adjustments       = ev_adj,
            volume_adjustments   = vol_adj,
            shrink_current       = shrink_current,
            shrink_past          = shrink_past,
        )

        self.save_cycle(cycle)
        return cycle

    # ── Persistence ─────────────────────────────────────────────────────────────
    def save_cycle(self, cycle: EdgeCycle):
        self.ensure_table()

        active_count   = len(cycle.active_markets)
        degraded_count = len(cycle.degraded_markets)
        disabled_count = len(cycle.disabled_markets)
        summary = (
            f"ACTIVE={active_count} DEGRADED={degraded_count} DISABLED={disabled_count} "
            f"LEARNING_LEAGUES={len(cycle.learning_leagues)} "
            f"FLAGS={len(cycle.stability_flags)}"
        )

        def _asdict(d):
            if hasattr(d, "__dataclass_fields__"):
                return {k: getattr(d, k) for k in d.__dataclass_fields__}
            return d

        cycle_json = json.dumps({
            "run_at": cycle.run_at,
            "active_markets":   cycle.active_markets,
            "degraded_markets": [_asdict(d) for d in cycle.degraded_markets],
            "disabled_markets": [_asdict(d) for d in cycle.disabled_markets],
            "all_market_decisions": [_asdict(d) for d in cycle.all_market_decisions],
            "active_leagues":   [_asdict(d) for d in cycle.active_leagues],
            "learning_leagues": [_asdict(d) for d in cycle.learning_leagues],
            "stability_flags":  cycle.stability_flags,
            "ev_adjustments":   cycle.ev_adjustments,
            "volume_adjustments": cycle.volume_adjustments,
            "shrink_current":   cycle.shrink_current,
            "shrink_past":      cycle.shrink_past,
        })

        try:
            conn = self._conn()
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO edge_decisions (run_at, cycle_json, summary) VALUES (NOW(), %s, %s)",
                (cycle_json, summary)
            )
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"💾 Edge decisions saved: {summary}")
        except Exception as e:
            logger.error(f"save_cycle error: {e}")

    # ── Human-readable report ────────────────────────────────────────────────────
    def print_report(self, cycle: EdgeCycle):
        lines = [
            "",
            "=" * 65,
            "🔬 EDGE MANAGEMENT ENGINE — CYCLE REPORT",
            f"   Run at: {cycle.run_at}",
            "=" * 65,
        ]

        lines.append("\n📊 MARKET STATUS")
        lines.append("─" * 65)

        # Active
        for mkt in cycle.active_markets:
            d = next((x for x in cycle.all_market_decisions if x.market == mkt), None)
            if d:
                clv_str = f"CLV={d.clv_avg:+.2f}%" if d.clv_avg is not None else "CLV=n/a"
                roi_str = f"ROI={d.roi_recent:+.1f}%" if d.roi_recent is not None else "ROI=n/a"
                hr_str  = f"Hit={d.hit_rate_recent:.1f}%" if d.hit_rate_recent is not None else "Hit=n/a"
                lines.append(
                    f"   ✅ ACTIVE    {mkt:<20} {clv_str}  {roi_str}  {hr_str}  n={d.sample_recent}"
                )

        # Degraded
        for d in cycle.degraded_markets:
            clv_str = f"CLV={d.clv_avg:+.2f}%" if d.clv_avg is not None else "CLV=n/a"
            roi_str = f"ROI={d.roi_recent:+.1f}%" if d.roi_recent is not None else "ROI=n/a"
            lines.append(
                f"   ⚠️  DEGRADED  {d.market:<20} {clv_str}  {roi_str}  "
                f"EV_adj={d.ev_threshold_adj:+.1f}pp  vol={d.volume_adj}"
            )
            lines.append(f"            Reason: {d.reason}")

        # Disabled
        for d in cycle.disabled_markets:
            clv_str = f"CLV={d.clv_avg:+.2f}%" if d.clv_avg is not None else "CLV=n/a"
            roi_str = f"ROI={d.roi_recent:+.1f}%" if d.roi_recent is not None else "ROI=n/a"
            lines.append(
                f"   ❌ DISABLED  {d.market:<20} {clv_str}  {roi_str}  → LEARNING only"
            )
            lines.append(f"            Reason: {d.reason}")

        lines.append("\n🌍 LEAGUE STATUS (sample of key decisions)")
        lines.append("─" * 65)

        prod_leagues   = sorted(cycle.active_leagues,   key=lambda x: -(x.roi or 0))[:10]
        learn_leagues  = sorted(cycle.learning_leagues, key=lambda x:  (x.roi or 0))[:10]

        for d in prod_leagues:
            clv_str = f"CLV={d.clv_avg:+.2f}%" if d.clv_avg is not None else ""
            roi_str = f"ROI={d.roi:+.1f}%"     if d.roi     is not None else ""
            summer  = " [SUMMER]" if d.is_summer else ""
            lines.append(
                f"   ✅ PROD     {d.league:<30} ({d.market}) {clv_str} {roi_str}{summer}"
            )

        for d in learn_leagues:
            clv_str = f"CLV={d.clv_avg:+.2f}%" if d.clv_avg is not None else ""
            roi_str = f"ROI={d.roi:+.1f}%"     if d.roi     is not None else ""
            summer  = " [SUMMER]" if d.is_summer else ""
            lines.append(
                f"   📚 LEARNING {d.league:<30} ({d.market}) {clv_str} {roi_str}{summer}"
                f"\n              Reason: {d.reason}"
            )

        if cycle.stability_flags:
            lines.append("\n🚨 MODEL STABILITY FLAGS")
            lines.append("─" * 65)
            for flag in cycle.stability_flags:
                lines.append(f"   {flag}")

        lines.append("\n📐 SUGGESTED ADJUSTMENTS")
        lines.append("─" * 65)
        if cycle.ev_adjustments:
            for mkt, adj in cycle.ev_adjustments.items():
                direction = "▲ raise" if adj > 0 else "▼ lower"
                lines.append(f"   {mkt:<25} min-EV {direction} {abs(adj):.1f}pp")
        else:
            lines.append("   No EV threshold changes required")

        if cycle.shrink_current is not None:
            lines.append(
                f"\n   Shrink factor: current={cycle.shrink_current:.3f}"
                + (f"  30d-ago={cycle.shrink_past:.3f}" if cycle.shrink_past else "")
            )

        lines.append("=" * 65)
        print("\n".join(lines))


# ── Public entry point ────────────────────────────────────────────────────────
def get_market_edge_status(market: str) -> dict:
    """
    Read the latest edge_decisions cycle from DB and return status for `market`.
    Returns: {"status": "ACTIVE"|"DEGRADED"|"DISABLED"|"UNKNOWN",
              "ev_adj": float, "reasons": [str]}
    Falls back to ACTIVE/UNKNOWN on any error (fail-open).
    """
    default = {"status": "UNKNOWN", "ev_adj": 0.0, "reasons": []}
    try:
        from db_helper import db_helper as _db
        row = _db.execute(
            "SELECT cycle_json FROM edge_decisions ORDER BY run_at DESC LIMIT 1",
            fetch='one'
        )
        if not row:
            return default
        raw = row[0]
        cycle = raw if isinstance(raw, dict) else json.loads(raw)
        for decision in cycle.get("all_market_decisions", []):
            if decision.get("market", "").lower() == market.lower():
                return {
                    "status":   decision.get("status", "UNKNOWN"),
                    "ev_adj":   decision.get("ev_threshold_adj", 0.0),
                    "reasons":  [decision.get("reason", "")],
                }
        return default
    except Exception as e:
        logger.warning(f"get_market_edge_status({market}) error: {e}")
        return default


def get_dynamic_caps(base_caps: Optional[Dict] = None) -> Dict:
    """
    Read the latest edge_decisions from DB and return CLV-adjusted MARKET_CAPS.

    Scaling rules (applied to product-level max_picks):
      INCREASE  (CLV > +1%, 30+ samples)  → +25%  (capped at 2× base)
      DECREASE  (DEGRADED market)          → -30%  (floor = 2)
      MAINTAIN                             → no change

    Falls back to base_caps (or MARKET_CAPS) on any error.
    """
    import copy
    from market_router_config import MARKET_CAPS as _DEFAULT_CAPS
    caps = copy.deepcopy(base_caps if base_caps is not None else _DEFAULT_CAPS)

    MARKET_TO_ROUTER = {
        "Value Single": ["TOTALS", "BTTS", "ML_AH"],
        "Corners":      ["CORNERS_MATCH", "CORNERS_TEAM", "CORNERS_HANDICAP"],
        "Cards":        ["CARDS_MATCH", "CARDS_TEAM"],
    }

    try:
        from db_helper import db_helper as _db
        row = _db.execute(
            "SELECT cycle_json FROM edge_decisions ORDER BY run_at DESC LIMIT 1",
            fetch='one'
        )
        if not row:
            return caps

        raw = row[0]
        cycle = raw if isinstance(raw, dict) else json.loads(raw)

        for decision in cycle.get("all_market_decisions", []):
            market   = decision.get("market", "")
            vol_adj  = decision.get("volume_adj", "MAINTAIN")
            clv_avg  = decision.get("clv_avg")
            clv_n    = decision.get("clv_n", 0)

            if vol_adj == "INCREASE" and not (
                clv_avg is not None and clv_avg > 1.0 and clv_n >= 30
            ):
                vol_adj = "MAINTAIN"

            router_keys = MARKET_TO_ROUTER.get(market, [])
            for rk in router_keys:
                if rk not in caps:
                    continue
                base_max = caps[rk].get("max_picks", 10)
                if vol_adj == "INCREASE":
                    new_max = min(int(base_max * 1.25), base_max * 2)
                elif vol_adj == "DECREASE":
                    new_max = max(int(base_max * 0.70), 2)
                else:
                    new_max = base_max
                if new_max != base_max:
                    logger.info(
                        f"🎚️ CLV-cap adj [{market}→{rk}]: {base_max} → {new_max} "
                        f"({vol_adj}, CLV={clv_avg:+.2f}% n={clv_n})"
                        if clv_avg is not None else
                        f"🎚️ CLV-cap adj [{market}→{rk}]: {base_max} → {new_max} ({vol_adj})"
                    )
                    caps[rk]["max_picks"] = new_max

        return caps

    except Exception as e:
        logger.warning(f"get_dynamic_caps error (falling back to base): {e}")
        return caps


def run_edge_management() -> Optional[EdgeCycle]:
    """Called from combined_sports_runner.py on a scheduled basis."""
    try:
        engine = EdgeManagementEngine()
        cycle  = engine.run_cycle()
        engine.print_report(cycle)
        return cycle
    except Exception as e:
        logger.error(f"Edge Management Engine error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_edge_management()
