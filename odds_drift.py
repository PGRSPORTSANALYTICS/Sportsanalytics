"""
Odds Drift Analysis Module
Tracks odds movement and calculates drift scores for bet filtering
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import os

logger = logging.getLogger(__name__)


@dataclass
class OddsDriftInfo:
    fixture_id: str
    market_key: str
    open_odds: float
    last_odds: float
    drift_pct: float
    drift_score: float
    direction: str
    market_favors: str


class OddsDriftTracker:
    """
    Tracks odds movement over time and provides drift analysis.
    
    Drift score interpretation:
    - Positive: Market moving toward our model (favorable)
    - Negative: Market moving against our model (unfavorable)
    - Zero: No significant movement
    """
    
    def __init__(self):
        self.db_url = os.environ.get("DATABASE_URL")
        logger.info("✅ OddsDriftTracker initialized")
    
    def get_connection(self):
        """Get database connection."""
        if not self.db_url:
            return None
        try:
            return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            return None
    
    def record_odds_snapshot(
        self,
        fixture_id: str,
        market_key: str,
        odds: float,
        bookmaker: str = "generic",
        match_date: Optional[str] = None
    ) -> bool:
        """
        Record a new odds snapshot or update existing.
        Uses upsert to track open and last odds.
        """
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT open_odds, open_timestamp 
                    FROM odds_snapshots 
                    WHERE fixture_id = %s AND market_key = %s AND bookmaker = %s
                """, (fixture_id, market_key, bookmaker))
                
                existing = cur.fetchone()
                
                now = datetime.utcnow()
                
                if existing:
                    open_odds = float(existing['open_odds']) if existing and existing.get('open_odds') else 0
                    drift_pct = (odds - open_odds) / open_odds if open_odds > 0 else 0
                    
                    cur.execute("""
                        UPDATE odds_snapshots 
                        SET last_odds = %s, 
                            last_update = %s, 
                            drift_pct = %s
                        WHERE fixture_id = %s AND market_key = %s AND bookmaker = %s
                    """, (odds, now, drift_pct, fixture_id, market_key, bookmaker))
                else:
                    cur.execute("""
                        INSERT INTO odds_snapshots 
                        (fixture_id, market_key, bookmaker, open_odds, last_odds, 
                         open_timestamp, last_update, drift_pct, match_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s)
                    """, (fixture_id, market_key, bookmaker, odds, odds, now, now, match_date))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error recording odds snapshot: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_odds_drift(
        self,
        fixture_id: str,
        market_key: str,
        bookmaker: str = "generic"
    ) -> Optional[Dict]:
        """Get current odds drift info for a market."""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT open_odds, last_odds, drift_pct, 
                           open_timestamp, last_update
                    FROM odds_snapshots 
                    WHERE fixture_id = %s AND market_key = %s AND bookmaker = %s
                """, (fixture_id, market_key, bookmaker))
                
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Error getting odds drift: {e}")
            return None
        finally:
            conn.close()
    
    def calculate_drift_score(
        self,
        drift_pct: float,
        model_prob: float,
        book_prob: float
    ) -> Tuple[float, str]:
        """
        Calculate drift score based on odds movement vs model.
        
        Args:
            drift_pct: Percentage change in odds (negative = shortening)
            model_prob: Our model's probability
            book_prob: Implied probability from current book odds
        
        Returns:
            (drift_score, interpretation)
            
        Score interpretation:
        - +1.0 to +2.0: Strong positive drift (market confirms model)
        - 0 to +1.0: Mild positive drift
        - -1.0 to 0: Mild negative drift (some disagreement)
        - -2.0 to -1.0: Strong negative drift (market disagrees)
        """
        our_edge = model_prob - book_prob
        
        if drift_pct < 0:
            if our_edge > 0:
                score = abs(drift_pct) * 10
                interpretation = "FAVORABLE"
            else:
                score = drift_pct * 10
                interpretation = "UNFAVORABLE"
        elif drift_pct > 0:
            if our_edge > 0:
                score = -abs(drift_pct) * 10
                interpretation = "MARKET_DISAGREES"
            else:
                score = abs(drift_pct) * 5
                interpretation = "CORRECTING"
        else:
            score = 0
            interpretation = "STABLE"
        
        score = max(-2.0, min(2.0, score))
        
        return score, interpretation
    
    def get_drift_analysis(
        self,
        fixture_id: str,
        market_key: str,
        model_prob: float,
        current_odds: float,
        bookmaker: str = "generic"
    ) -> OddsDriftInfo:
        """
        Get comprehensive drift analysis for a market selection.
        
        Returns OddsDriftInfo with drift score for bet filtering.
        """
        book_prob = 1 / current_odds if current_odds > 1 else 0
        
        drift_data = self.get_odds_drift(fixture_id, market_key, bookmaker)
        
        if drift_data and drift_data.get('open_odds'):
            open_odds = drift_data['open_odds']
            last_odds = drift_data['last_odds'] or current_odds
            drift_pct = (last_odds - open_odds) / open_odds if open_odds > 0 else 0
        else:
            open_odds = current_odds
            last_odds = current_odds
            drift_pct = 0.0
        
        drift_score, direction = self.calculate_drift_score(
            drift_pct, model_prob, book_prob
        )
        
        if drift_pct < 0:
            market_favors = "BACKING"
        elif drift_pct > 0:
            market_favors = "FADING"
        else:
            market_favors = "NEUTRAL"
        
        return OddsDriftInfo(
            fixture_id=fixture_id,
            market_key=market_key,
            open_odds=open_odds,
            last_odds=last_odds,
            drift_pct=drift_pct,
            drift_score=drift_score,
            direction=direction,
            market_favors=market_favors
        )
    
    def should_block_bet(
        self,
        drift_info: OddsDriftInfo,
        trust_tier: str
    ) -> Tuple[bool, str]:
        """
        Determine if a bet should be blocked based on drift.
        
        L1 bets: Block if drift_score < -0.5 (market strongly against)
        L2 bets: Block if drift_score < -1.0
        L3 bets: Never block, but flag as "market disagrees"
        
        Returns:
            (should_block, reason)
        """
        if trust_tier == "L1_HIGH_TRUST":
            if drift_info.drift_score < -0.5:
                return True, f"Market moving against L1 bet (drift={drift_info.drift_pct:.1%})"
        
        elif trust_tier == "L2_MEDIUM_TRUST":
            if drift_info.drift_score < -1.0:
                return True, f"Strong negative drift on L2 bet (drift={drift_info.drift_pct:.1%})"
        
        return False, ""
    
    def cleanup_old_snapshots(self, days: int = 7) -> int:
        """Remove snapshots older than specified days."""
        conn = self.get_connection()
        if not conn:
            return 0
        
        try:
            with conn.cursor() as cur:
                cutoff = datetime.utcnow() - timedelta(days=days)
                cur.execute("""
                    DELETE FROM odds_snapshots 
                    WHERE match_date < %s OR last_update < %s
                """, (cutoff.date(), cutoff))
                
                deleted = cur.rowcount
                conn.commit()
                
                if deleted > 0:
                    logger.info(f"🧹 Cleaned up {deleted} old odds snapshots")
                
                return deleted
                
        except Exception as e:
            logger.error(f"Error cleaning up snapshots: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()


def record_batch_odds(
    tracker: OddsDriftTracker,
    fixture_id: str,
    odds_snapshot: Dict[str, float],
    match_date: Optional[str] = None
) -> int:
    """
    Record a batch of odds for a fixture.
    Returns count of successfully recorded odds.
    """
    count = 0
    for market_key, odds in odds_snapshot.items():
        if odds and odds > 1:
            if tracker.record_odds_snapshot(fixture_id, market_key, odds, match_date=match_date):
                count += 1
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    tracker = OddsDriftTracker()
    
    test_cases = [
        {"drift_pct": -0.05, "model_prob": 0.55, "book_prob": 0.50},
        {"drift_pct": 0.10, "model_prob": 0.55, "book_prob": 0.50},
        {"drift_pct": 0.0, "model_prob": 0.52, "book_prob": 0.50},
        {"drift_pct": -0.08, "model_prob": 0.48, "book_prob": 0.50},
    ]
    
    print("\n=== Drift Score Tests ===")
    for case in test_cases:
        score, direction = tracker.calculate_drift_score(
            case["drift_pct"],
            case["model_prob"],
            case["book_prob"]
        )
        print(f"  Drift: {case['drift_pct']:.1%} | Model: {case['model_prob']:.0%} | Book: {case['book_prob']:.0%}")
        print(f"    Score: {score:.2f} | Direction: {direction}")
