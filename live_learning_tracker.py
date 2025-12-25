#!/usr/bin/env python3
"""
Live Learning Tracker
=====================
Full data capture system for LIVE LEARNING MODE.

Captures ALL picks across all trust tiers with:
- CLV tracking (opening/closing odds)
- Syndicate engine details (raw_ev, boosted_ev, weighted_ev)
- Profile boost factors
- Market weight data
- Hidden value status
- Unit-based P/L tracking
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from db_helper import db_helper
from datetime_utils import normalize_kickoff, validate_kickoff, now_utc, to_iso_utc, now_epoch
from live_learning_config import get_live_learning_config, is_live_learning_active
from profile_boost_engine import ProfileBoostEngine, BoostResult
from market_weight_engine import MarketWeightEngine, WeightResult
from hidden_value_scanner import HiddenValueScanner, RejectedCandidate, HiddenValuePick

logger = logging.getLogger(__name__)


@dataclass
class LiveLearningPick:
    """A pick captured in Live Learning Mode with full data."""
    
    match_id: str
    home_team: str
    away_team: str
    league: str
    match_date: str
    kickoff_time: str
    market: str
    market_key: str
    selection: str
    opening_odds: float
    current_odds: float
    
    kickoff_utc: Optional[str] = None
    kickoff_epoch: Optional[int] = None
    closing_odds: Optional[float] = None
    clv_delta: Optional[float] = None
    
    raw_ev: float = 0.0
    boosted_ev: float = 0.0
    weighted_ev: float = 0.0
    
    model_prob: float = 0.0
    sim_prob: float = 0.0
    confidence: float = 0.0
    
    trust_tier: str = "L3_SOFT_VALUE"
    
    profile_boost_score: float = 0.0
    profile_boost_factors: List[Tuple[str, float]] = field(default_factory=list)
    
    market_weight: float = 1.0
    market_weight_group: str = ""
    
    hidden_value_score: Optional[float] = None
    hidden_value_status: str = "NOT_SCANNED"
    
    mode: str = "LIVE_LEARNING"
    stake_units: float = 1.0
    
    status: str = "pending"
    result: Optional[str] = None
    units_profit: float = 0.0
    
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "match_id": self.match_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "league": self.league,
            "match_date": self.match_date,
            "kickoff_time": self.kickoff_time,
            "kickoff_utc": self.kickoff_utc,
            "kickoff_epoch": self.kickoff_epoch,
            "market": self.market,
            "market_key": self.market_key,
            "selection": self.selection,
            "opening_odds": self.opening_odds,
            "current_odds": self.current_odds,
            "closing_odds": self.closing_odds,
            "clv_delta": self.clv_delta,
            "raw_ev": self.raw_ev,
            "boosted_ev": self.boosted_ev,
            "weighted_ev": self.weighted_ev,
            "model_prob": self.model_prob,
            "sim_prob": self.sim_prob,
            "confidence": self.confidence,
            "trust_tier": self.trust_tier,
            "profile_boost_score": self.profile_boost_score,
            "profile_boost_factors": json.dumps([
                {"factor": f[0], "score": f[1]} for f in self.profile_boost_factors
            ]),
            "market_weight": self.market_weight,
            "market_weight_group": self.market_weight_group,
            "hidden_value_score": self.hidden_value_score,
            "hidden_value_status": self.hidden_value_status,
            "mode": self.mode,
            "stake_units": self.stake_units,
            "status": self.status,
            "units_profit": self.units_profit,
        }


class LiveLearningTracker:
    """
    Tracker for Live Learning Mode.
    Captures all picks with full syndicate engine data.
    """
    
    def __init__(self):
        self.config = get_live_learning_config()
        self.pb_engine = ProfileBoostEngine()
        self.mw_engine = MarketWeightEngine()
        self.hv_scanner = HiddenValueScanner()
        self._session_picks: List[LiveLearningPick] = []
        self._session_start = datetime.now()
        
        logger.info(f"[LIVE_LEARNING] Tracker initialized at {self._session_start}")
    
    def process_pick(
        self,
        match_id: str,
        home_team: str,
        away_team: str,
        league: str,
        match_date: str,
        kickoff_time: str,
        market: str,
        market_key: str,
        selection: str,
        odds: float,
        raw_ev: float,
        model_prob: float,
        sim_prob: float,
        confidence: float,
        trust_tier: str,
        context: Optional[Dict[str, Any]] = None,
        commence_time: Optional[str] = None
    ) -> LiveLearningPick:
        """
        Process a pick through all syndicate engines and capture full data.
        
        This runs:
        1. Profile Boost Engine
        2. Market Weight Engine
        3. Hidden Value Scanner (if applicable)
        
        Returns the fully processed LiveLearningPick.
        """
        context = context or {}
        
        kickoff_utc, kickoff_epoch = normalize_kickoff(commence_time)
        
        boost_result = self.pb_engine.calculate_boost(
            base_ev=raw_ev,
            base_confidence=confidence,
            market_type=market_key,
            context=context
        )
        
        weight_result = self.mw_engine.get_market_weight(market_key)
        
        weighted_ev = boost_result.boosted_ev * weight_result.weight
        
        hv_score = None
        hv_status = "NOT_APPLICABLE"
        
        ev_min, ev_max = self.config.ev_near_miss_range if hasattr(self.config, 'ev_near_miss_range') else (-0.01, 0.02)
        
        if ev_min <= weighted_ev <= ev_max:
            candidate = RejectedCandidate(
                match_id=match_id,
                home_team=home_team,
                away_team=away_team,
                match_date=datetime.now(),
                market_key=market_key,
                selection=selection,
                odds=odds,
                raw_ev=raw_ev,
                boosted_ev=boost_result.boosted_ev,
                final_ev=weighted_ev,
                raw_confidence=confidence,
                boosted_confidence=boost_result.boosted_confidence,
                boost_score=boost_result.boost_score,
                market_weight=weight_result.weight,
                profile_boost_factors=boost_result.contributing_factors,
            )
            
            hv_picks = self.hv_scanner.scan_candidates([candidate])
            if hv_picks:
                hv_score = hv_picks[0].soft_edge_score
                hv_status = "SELECTED"
                if trust_tier in ["L3_SOFT_VALUE", "REJECTED"]:
                    trust_tier = "HIDDEN_VALUE"
            else:
                hv_status = "SCANNED_NOT_SELECTED"
        elif weighted_ev >= 0.02:
            hv_status = "ABOVE_THRESHOLD"
        else:
            hv_status = "BELOW_THRESHOLD"
        
        pick = LiveLearningPick(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league=league,
            match_date=match_date,
            kickoff_time=kickoff_time,
            market=market,
            market_key=market_key,
            selection=selection,
            opening_odds=odds,
            current_odds=odds,
            kickoff_utc=kickoff_utc,
            kickoff_epoch=kickoff_epoch,
            raw_ev=raw_ev,
            boosted_ev=boost_result.boosted_ev,
            weighted_ev=weighted_ev,
            model_prob=model_prob,
            sim_prob=sim_prob,
            confidence=confidence,
            trust_tier=trust_tier,
            profile_boost_score=boost_result.boost_score,
            profile_boost_factors=boost_result.contributing_factors,
            market_weight=weight_result.weight,
            market_weight_group=weight_result.market_group,
            hidden_value_score=hv_score,
            hidden_value_status=hv_status,
            mode="LIVE_LEARNING",
            stake_units=1.0,
            context=context,
        )
        
        self._session_picks.append(pick)
        
        if self.config.log_every_pick:
            self._log_pick(pick)
        
        return pick
    
    def save_pick_to_db(self, pick: LiveLearningPick) -> bool:
        """Save a processed pick to the database with proper column mapping."""
        try:
            if pick.kickoff_utc and pick.kickoff_epoch:
                is_valid, error_msg = validate_kickoff(pick.kickoff_utc, pick.kickoff_epoch)
                if not is_valid:
                    logger.warning(f"[LIVE_LEARNING] Invalid kickoff time: {error_msg}")
            
            open_prob = 1 / pick.opening_odds if pick.opening_odds > 0 else 0
            close_prob = 1 / pick.current_odds if pick.current_odds > 0 else 0
            clv_pct = (close_prob - open_prob) * 100 if pick.closing_odds else 0
            
            created_at_utc = to_iso_utc(now_utc())
            
            query = """
                INSERT INTO football_opportunities (
                    timestamp, match_id, home_team, away_team, league,
                    market, selection, odds, edge_percentage, confidence,
                    status, match_date, kickoff_time, kickoff_utc, kickoff_epoch,
                    created_at_utc, mode, trust_level,
                    model_prob, sim_probability, 
                    open_odds, close_odds, clv_pct,
                    raw_ev, boosted_ev, weighted_ev,
                    profile_boost_score, profile_boost_factors,
                    market_weight, hidden_value_score, hidden_value_status
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, 
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (match_id, market, selection) 
                DO UPDATE SET
                    odds = EXCLUDED.odds,
                    edge_percentage = EXCLUDED.edge_percentage,
                    open_odds = COALESCE(football_opportunities.open_odds, EXCLUDED.open_odds),
                    close_odds = EXCLUDED.close_odds,
                    clv_pct = EXCLUDED.clv_pct,
                    raw_ev = EXCLUDED.raw_ev,
                    boosted_ev = EXCLUDED.boosted_ev,
                    weighted_ev = EXCLUDED.weighted_ev,
                    profile_boost_score = EXCLUDED.profile_boost_score,
                    profile_boost_factors = EXCLUDED.profile_boost_factors,
                    market_weight = EXCLUDED.market_weight,
                    hidden_value_score = EXCLUDED.hidden_value_score,
                    hidden_value_status = EXCLUDED.hidden_value_status,
                    mode = EXCLUDED.mode,
                    trust_level = EXCLUDED.trust_level,
                    kickoff_utc = COALESCE(EXCLUDED.kickoff_utc, football_opportunities.kickoff_utc),
                    kickoff_epoch = COALESCE(EXCLUDED.kickoff_epoch, football_opportunities.kickoff_epoch)
            """
            
            params = (
                now_epoch(),
                pick.match_id,
                pick.home_team,
                pick.away_team,
                pick.league,
                pick.market,
                pick.selection,
                pick.current_odds,
                pick.weighted_ev * 100,
                int(pick.confidence * 100),
                "pending",
                pick.match_date,
                pick.kickoff_time,
                pick.kickoff_utc,
                pick.kickoff_epoch,
                created_at_utc,
                "LIVE_LEARNING",
                pick.trust_tier,
                pick.model_prob,
                pick.sim_prob,
                pick.opening_odds,
                pick.closing_odds if pick.closing_odds else pick.current_odds,
                clv_pct,
                pick.raw_ev,
                pick.boosted_ev,
                pick.weighted_ev,
                pick.profile_boost_score,
                json.dumps([{"f": f[0], "s": round(f[1], 3)} for f in pick.profile_boost_factors]),
                pick.market_weight,
                pick.hidden_value_score,
                pick.hidden_value_status,
            )
            
            db_helper.execute(query, params)
            logger.info(f"[LIVE_LEARNING] Saved: {pick.home_team} vs {pick.away_team} - {pick.selection} | kickoff_epoch={pick.kickoff_epoch}")
            return True
            
        except Exception as e:
            logger.error(f"[LIVE_LEARNING] Failed to save pick: {e}")
            return False
    
    def update_clv(self, match_id: str, market: str, selection: str, closing_odds: float) -> bool:
        """Update closing odds and calculate CLV for a pick."""
        try:
            result = db_helper.execute(
                "SELECT open_odds FROM football_opportunities WHERE match_id = %s AND market = %s AND selection = %s",
                (match_id, market, selection)
            )
            
            if not result:
                return False
            
            open_odds = float(result[0].get("open_odds", closing_odds))
            
            open_prob = 1 / open_odds if open_odds > 0 else 0
            close_prob = 1 / closing_odds if closing_odds > 0 else 0
            clv_pct = (close_prob - open_prob) * 100
            
            db_helper.execute("""
                UPDATE football_opportunities
                SET close_odds = %s, clv_pct = %s
                WHERE match_id = %s AND market = %s AND selection = %s
            """, (closing_odds, clv_pct, match_id, market, selection))
            
            if self.config.log_clv_updates:
                logger.info(f"[LIVE_LEARNING] CLV Updated: {match_id} {selection} - CLV: {clv_pct:.2f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"[LIVE_LEARNING] CLV update failed: {e}")
            return False
    
    def settle_result(
        self,
        match_id: str,
        market: str,
        selection: str,
        won: bool,
        actual_odds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Settle a pick result and calculate units profit/loss.
        Also triggers market weight learning.
        """
        try:
            result = db_helper.execute("""
                SELECT odds, trust_level, market, weighted_ev
                FROM football_opportunities
                WHERE match_id = %s AND market = %s AND selection = %s
            """, (match_id, market, selection))
            
            if not result:
                return {"success": False, "error": "Pick not found"}
            
            row = result[0]
            odds = actual_odds or float(row.get("odds", 0))
            trust_tier = row.get("trust_level", "L3_SOFT_VALUE")
            
            stake_units = 1.0
            if won:
                units_profit = (odds - 1) * stake_units
                status = "won"
            else:
                units_profit = -stake_units
                status = "lost"
            
            db_helper.execute("""
                UPDATE football_opportunities
                SET status = %s, profit_loss = %s, outcome = %s
                WHERE match_id = %s AND market = %s AND selection = %s
            """, (status, units_profit, "WIN" if won else "LOSS", match_id, market, selection))
            
            if self.config.log_result_settlements:
                logger.info(
                    f"[LIVE_LEARNING] Settled: {match_id} {selection} - "
                    f"{'WON' if won else 'LOST'} {units_profit:+.2f}u @ {odds:.2f}"
                )
            
            return {
                "success": True,
                "match_id": match_id,
                "selection": selection,
                "won": won,
                "odds": odds,
                "units_profit": units_profit,
                "trust_tier": trust_tier,
            }
            
        except Exception as e:
            logger.error(f"[LIVE_LEARNING] Settlement failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for the current learning session."""
        total = len(self._session_picks)
        
        by_tier = {}
        by_market = {}
        total_ev = 0.0
        
        for pick in self._session_picks:
            tier = pick.trust_tier
            by_tier[tier] = by_tier.get(tier, 0) + 1
            
            market = pick.market_key
            by_market[market] = by_market.get(market, 0) + 1
            
            total_ev += pick.weighted_ev
        
        return {
            "mode": "LIVE_LEARNING",
            "session_start": self._session_start.isoformat(),
            "total_picks": total,
            "by_trust_tier": by_tier,
            "by_market": by_market,
            "avg_weighted_ev": round(total_ev / max(1, total) * 100, 2),
            "config": self.config.to_dict(),
        }
    
    def get_learning_progress(self) -> Dict[str, Any]:
        """Get overall learning progress from database."""
        try:
            stats = db_helper.execute("""
                SELECT 
                    trust_level,
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    AVG(weighted_ev) as avg_weighted_ev,
                    AVG(clv_pct) as avg_clv,
                    SUM(profit_loss) as total_profit_units
                FROM football_opportunities
                WHERE mode = 'LIVE_LEARNING'
                GROUP BY trust_level
            """)
            
            result = {
                "mode": "LIVE_LEARNING",
                "by_trust_tier": {},
                "totals": {
                    "picks": 0,
                    "settled": 0,
                    "pending": 0,
                    "profit_units": 0.0,
                    "avg_clv": 0.0,
                }
            }
            
            total_picks = 0
            total_settled = 0
            total_pending = 0
            total_profit = 0.0
            clv_sum = 0.0
            clv_count = 0
            
            for row in (stats or []):
                tier = row.get("trust_level", "UNKNOWN")
                total = int(row.get("total", 0))
                wins = int(row.get("wins", 0))
                losses = int(row.get("losses", 0))
                pending = int(row.get("pending", 0))
                settled = wins + losses
                profit = float(row.get("total_profit_units", 0) or 0)
                avg_clv = float(row.get("avg_clv", 0) or 0)
                
                result["by_trust_tier"][tier] = {
                    "total": total,
                    "wins": wins,
                    "losses": losses,
                    "pending": pending,
                    "hit_rate": round(wins / max(1, settled) * 100, 1),
                    "profit_units": round(profit, 2),
                    "roi": round(profit / max(1, settled) * 100, 1),
                    "avg_clv": round(avg_clv, 2),
                }
                
                total_picks += total
                total_settled += settled
                total_pending += pending
                total_profit += profit
                if avg_clv != 0:
                    clv_sum += avg_clv * settled
                    clv_count += settled
            
            result["totals"] = {
                "picks": total_picks,
                "settled": total_settled,
                "pending": total_pending,
                "profit_units": round(total_profit, 2),
                "roi": round(total_profit / max(1, total_settled) * 100, 1),
                "avg_clv": round(clv_sum / max(1, clv_count), 2),
            }
            
            return result
            
        except Exception as e:
            logger.error(f"[LIVE_LEARNING] Failed to get progress: {e}")
            return {"mode": "LIVE_LEARNING", "error": str(e)}
    
    def _log_pick(self, pick: LiveLearningPick):
        """Log a pick in verbose mode."""
        tier_emoji = {
            "L1_HIGH_TRUST": "🔵",
            "L2_MEDIUM_TRUST": "🟢", 
            "L3_SOFT_VALUE": "🟡",
            "HIDDEN_VALUE": "🟣",
        }.get(pick.trust_tier, "⚪")
        
        logger.info(
            f"[LIVE_LEARNING] {tier_emoji} {pick.trust_tier} | "
            f"{pick.home_team} vs {pick.away_team} | "
            f"{pick.selection} @ {pick.current_odds:.2f} | "
            f"EV: raw={pick.raw_ev*100:.1f}% boost={pick.boosted_ev*100:.1f}% weight={pick.weighted_ev*100:.1f}% | "
            f"MW={pick.market_weight:.2f} | PB={pick.profile_boost_score:.3f}"
        )


_tracker_instance: Optional[LiveLearningTracker] = None


def get_live_learning_tracker() -> LiveLearningTracker:
    """Get or create the live learning tracker singleton."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = LiveLearningTracker()
    return _tracker_instance


def process_live_pick(**kwargs) -> LiveLearningPick:
    """Convenience function to process a pick through the tracker."""
    tracker = get_live_learning_tracker()
    return tracker.process_pick(**kwargs)


def save_live_pick(pick: LiveLearningPick) -> bool:
    """Convenience function to save a pick."""
    tracker = get_live_learning_tracker()
    return tracker.save_pick_to_db(pick)


def enrich_pending_picks_with_syndicate_data() -> Dict[str, Any]:
    """
    Post-process pending picks to add syndicate engine data.
    Called periodically to enrich picks that were saved without syndicate data.
    """
    tracker = get_live_learning_tracker()
    
    try:
        pending_picks = db_helper.execute("""
            SELECT match_id, home_team, away_team, league, match_date, kickoff_time,
                   market, selection, odds, edge_percentage, confidence, model_prob,
                   sim_probability, trust_level
            FROM football_opportunities
            WHERE status = 'pending' 
            AND mode != 'LIVE_LEARNING'
            AND raw_ev IS NULL
            LIMIT 50
        """)
        
        if not pending_picks:
            return {"enriched": 0, "message": "No picks to enrich"}
        
        enriched = 0
        for row in pending_picks:
            try:
                raw_ev = float(row.get("edge_percentage", 0) or 0) / 100.0
                confidence = float(row.get("confidence", 0) or 0) / 100.0
                model_prob = float(row.get("model_prob", 0) or 0)
                sim_prob = float(row.get("sim_probability", 0) or 0)
                odds = float(row.get("odds", 0) or 0)
                market = row.get("market", "")
                
                boost_result = tracker.pb_engine.calculate_boost(
                    base_ev=raw_ev,
                    base_confidence=confidence,
                    market_type=market,
                    context={}
                )
                
                weight_result = tracker.mw_engine.get_market_weight(market)
                weighted_ev = boost_result.boosted_ev * weight_result.weight
                
                db_helper.execute("""
                    UPDATE football_opportunities
                    SET raw_ev = %s,
                        boosted_ev = %s,
                        weighted_ev = %s,
                        profile_boost_score = %s,
                        profile_boost_factors = %s,
                        market_weight = %s,
                        mode = 'LIVE_LEARNING'
                    WHERE match_id = %s AND market = %s AND selection = %s
                """, (
                    raw_ev,
                    boost_result.boosted_ev,
                    weighted_ev,
                    boost_result.boost_score,
                    json.dumps([{"f": f[0], "s": round(f[1], 3)} for f in boost_result.contributing_factors]),
                    weight_result.weight,
                    row.get("match_id"),
                    row.get("market"),
                    row.get("selection"),
                ))
                enriched += 1
                
            except Exception as e:
                logger.error(f"[LIVE_LEARNING] Failed to enrich pick: {e}")
                continue
        
        logger.info(f"[LIVE_LEARNING] Enriched {enriched} picks with syndicate data")
        return {"enriched": enriched, "message": f"Enriched {enriched} picks"}
        
    except Exception as e:
        logger.error(f"[LIVE_LEARNING] Enrichment failed: {e}")
        return {"enriched": 0, "error": str(e)}
