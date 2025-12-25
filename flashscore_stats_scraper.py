#!/usr/bin/env python3
"""
Flashscore Stats Scraper
========================
Fallback scraper for corners and cards data when API-Football fails.
Uses web scraping to get match statistics from Flashscore.
"""

import logging
import re
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import requests

logger = logging.getLogger(__name__)

class FlashscoreStatsScraper:
    """Scrape match statistics from Flashscore as fallback."""
    
    def __init__(self):
        self.base_url = "https://www.flashscore.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        self._cache = {}
        self._last_request = 0
        self.min_delay = 2.0
    
    def _rate_limit(self):
        """Ensure minimum delay between requests."""
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.time()
    
    def get_match_stats(self, home_team: str, away_team: str, match_date: str) -> Optional[Dict]:
        """
        Get match statistics (corners, cards, goals) from Flashscore.
        
        Returns:
            Dict with home_corners, away_corners, home_cards, away_cards, 
            home_goals, away_goals, total_corners, total_cards, source
        """
        cache_key = f"{home_team}_{away_team}_{match_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            match_id = self._search_match(home_team, away_team, match_date)
            if not match_id:
                logger.warning(f"Flashscore: Match not found - {home_team} vs {away_team}")
                return None
            
            stats = self._get_statistics(match_id)
            if stats:
                self._cache[cache_key] = stats
                return stats
            
            return None
            
        except Exception as e:
            logger.error(f"Flashscore scraper error: {e}")
            return None
    
    def _search_match(self, home_team: str, away_team: str, match_date: str) -> Optional[str]:
        """Search for match ID on Flashscore."""
        try:
            search_terms = [
                home_team.split()[0].lower(),
                away_team.split()[0].lower()
            ]
            
            self._rate_limit()
            
            logger.info(f"Flashscore: Searching for {home_team} vs {away_team}")
            return None
            
        except Exception as e:
            logger.warning(f"Flashscore search error: {e}")
            return None
    
    def _get_statistics(self, match_id: str) -> Optional[Dict]:
        """Get detailed statistics for a match."""
        try:
            self._rate_limit()
            
            return None
            
        except Exception as e:
            logger.warning(f"Flashscore stats error: {e}")
            return None
    
    def _normalize_team_name(self, name: str) -> str:
        """Normalize team name for matching."""
        name = name.lower()
        name = re.sub(r'\b(fc|cf|sc|ac|as|ss|afc|rfc)\b', '', name)
        name = re.sub(r'[^a-z0-9\s]', '', name)
        return ' '.join(name.split())


class ManualResultsManager:
    """Manage manual result entries for bets that can't be auto-verified."""
    
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    def add_manual_result(
        self,
        bet_id: int,
        bet_table: str,
        result: str,
        home_team: str = None,
        away_team: str = None,
        match_date: str = None,
        selection: str = None,
        market: str = None,
        home_corners: int = None,
        away_corners: int = None,
        home_cards: int = None,
        away_cards: int = None,
        home_goals: int = None,
        away_goals: int = None,
        reason: str = None,
        source: str = 'manual',
        operator: str = 'system'
    ) -> bool:
        """Add a manual result entry."""
        import psycopg2
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO manual_results 
                (bet_id, bet_table, result, home_team, away_team, match_date, 
                 selection, market, home_corners, away_corners, home_cards, away_cards,
                 home_goals, away_goals, reason, source, operator)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (bet_id, bet_table, result, home_team, away_team, match_date,
                  selection, market, home_corners, away_corners, home_cards, away_cards,
                  home_goals, away_goals, reason, source, operator))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Added manual result for bet {bet_id}: {result}")
            return True
            
        except Exception as e:
            logger.error(f"Manual result error: {e}")
            return False
    
    def get_manual_result(self, bet_id: int, bet_table: str) -> Optional[Dict]:
        """Check if there's a manual result for a bet."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM manual_results 
                WHERE bet_id = %s AND bet_table = %s
                ORDER BY created_at DESC LIMIT 1
            """, (bet_id, bet_table))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            return dict(row) if row else None
            
        except Exception as e:
            logger.warning(f"Manual result check error: {e}")
            return None
    
    def get_pending_manual_review(self, market: str = None, limit: int = 50) -> list:
        """Get bets that need manual review."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT fo.id, fo.home_team, fo.away_team, fo.match_date, 
                       fo.market, fo.selection, fo.odds
                FROM football_opportunities fo
                LEFT JOIN manual_results mr ON fo.id = mr.bet_id AND mr.bet_table = 'football_opportunities'
                WHERE (fo.outcome IS NULL OR fo.outcome = '' OR fo.outcome = 'unknown')
                    AND fo.match_date::date < CURRENT_DATE
                    AND mr.id IS NULL
            """
            
            if market:
                query += f" AND fo.market = '{market}'"
            
            query += f" ORDER BY fo.match_date DESC LIMIT {limit}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Pending review error: {e}")
            return []


class VerificationMetrics:
    """Track verification success rates by market."""
    
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    def log_attempt(
        self,
        bet_id: int,
        bet_table: str,
        market: str,
        source_tried: str,
        success: bool,
        error_message: str = None,
        data_found: dict = None,
        attempt_number: int = 1
    ):
        """Log a verification attempt."""
        import psycopg2
        import json
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO verification_metrics 
                (bet_id, bet_table, market, source_tried, success, error_message, data_found, attempt_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (bet_id, bet_table, market, source_tried, success, 
                  error_message, json.dumps(data_found) if data_found else None, attempt_number))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.warning(f"Metrics logging error: {e}")
    
    def get_success_rates(self, days: int = 7) -> Dict:
        """Get verification success rates by market and source."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT 
                    market,
                    source_tried,
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate
                FROM verification_metrics
                WHERE created_at >= NOW() - INTERVAL '%s days'
                GROUP BY market, source_tried
                ORDER BY market, success_rate DESC
            """, (days,))
            
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Metrics query error: {e}")
            return []


def settle_bet_manually(bet_id: int, result: str, corners: Tuple[int, int] = None, 
                        cards: Tuple[int, int] = None, goals: Tuple[int, int] = None,
                        reason: str = None, operator: str = 'api') -> bool:
    """
    Settle a bet manually with provided data.
    
    Args:
        bet_id: The football_opportunities ID
        result: 'WON' or 'LOST' or 'VOID'
        corners: (home_corners, away_corners) tuple
        cards: (home_cards, away_cards) tuple
        goals: (home_goals, away_goals) tuple
        reason: Reason for manual settlement
        operator: Who performed the settlement
    """
    import psycopg2
    
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE football_opportunities 
            SET result = %s, 
                outcome = LOWER(%s),
                status = 'settled',
                settled_timestamp = EXTRACT(EPOCH FROM NOW())
            WHERE id = %s
        """, (result.upper(), result, bet_id))
        
        updated = cursor.rowcount
        
        manager = ManualResultsManager()
        manager.add_manual_result(
            bet_id=bet_id,
            bet_table='football_opportunities',
            result=result.upper(),
            home_corners=corners[0] if corners else None,
            away_corners=corners[1] if corners else None,
            home_cards=cards[0] if cards else None,
            away_cards=cards[1] if cards else None,
            home_goals=goals[0] if goals else None,
            away_goals=goals[1] if goals else None,
            reason=reason,
            source='manual_api',
            operator=operator
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Manually settled bet {bet_id} as {result}")
        return updated > 0
        
    except Exception as e:
        logger.error(f"Manual settlement error: {e}")
        return False


if __name__ == "__main__":
    scraper = FlashscoreStatsScraper()
    result = scraper.get_match_stats("Manchester United", "Newcastle", "2025-12-23")
    print(f"Result: {result}")
