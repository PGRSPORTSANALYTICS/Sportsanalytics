"""
Sharp Money Tracker
Detects where professional bettors place their money
Odds movements reveal insider information
"""
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SharpMoneyTracker:
    """
    Track odds movements to detect sharp (professional) money
    
    Sharp money indicators:
    1. Odds drop despite majority of public bets on other side
    2. Steam moves (rapid odds changes)
    3. Reverse line movement
    """
    
    def __init__(self):
        self.conn = sqlite3.connect('data/real_football.db')
        self.create_odds_history_table()
    
    def create_odds_history_table(self):
        """Store odds movements over time"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS odds_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,
                match_id TEXT,
                home_team TEXT,
                away_team TEXT,
                market TEXT,
                selection TEXT,
                odds REAL,
                bookmaker TEXT,
                volume_indicator REAL
            )
        ''')
        self.conn.commit()
    
    def record_odds(self, match_id: str, home_team: str, away_team: str,
                   market: str, selection: str, odds: float, bookmaker: str = 'default'):
        """Record odds at this moment in time"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO odds_history 
            (timestamp, match_id, home_team, away_team, market, selection, odds, bookmaker)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(time.time()),
            match_id,
            home_team,
            away_team,
            market,
            selection,
            odds,
            bookmaker
        ))
        self.conn.commit()
    
    def detect_sharp_money(self, match_id: str, market: str, selection: str) -> Dict:
        """
        Analyze odds movements to detect sharp money
        
        Returns:
            {
                'sharp_indicator': float,  # 0-100 score
                'movement': str,           # 'steam', 'reverse', 'stable'
                'odds_drop': float,        # How much odds dropped
                'velocity': float,         # Speed of movement
                'recommendation': str      # 'bet', 'avoid', 'neutral'
            }
        """
        cursor = self.conn.cursor()
        
        # Get odds history for this selection
        cursor.execute('''
            SELECT timestamp, odds FROM odds_history
            WHERE match_id = ? AND market = ? AND selection = ?
            ORDER BY timestamp ASC
        ''', (match_id, market, selection))
        
        history = cursor.fetchall()
        
        if len(history) < 2:
            return {
                'sharp_indicator': 0,
                'movement': 'insufficient_data',
                'odds_drop': 0,
                'velocity': 0,
                'recommendation': 'neutral'
            }
        
        # Calculate movement metrics
        first_odds = history[0][1]
        last_odds = history[-1][1]
        time_span = history[-1][0] - history[0][0]
        
        odds_drop = first_odds - last_odds
        odds_drop_pct = (odds_drop / first_odds * 100) if first_odds > 0 else 0
        
        # Velocity: How fast are odds changing?
        velocity = abs(odds_drop) / max(time_span / 3600, 0.1)  # Odds change per hour
        
        # SHARP MONEY INDICATORS:
        
        # 1. Steam Move: Rapid odds drop (>5% in <2 hours)
        is_steam = abs(odds_drop_pct) > 5 and time_span < 7200
        
        # 2. Significant drop: >10% movement
        is_significant = abs(odds_drop_pct) > 10
        
        # 3. Reverse Line Movement: Odds drop despite time (public usually bets favorites)
        is_reverse = odds_drop < 0  # Odds dropping = sharp money coming in
        
        # Calculate sharp indicator score
        sharp_score = 0
        if is_steam:
            sharp_score += 40
        if is_significant:
            sharp_score += 30
        if is_reverse:
            sharp_score += 30
        
        # Movement classification
        if is_steam:
            movement = 'steam'
        elif is_reverse and is_significant:
            movement = 'reverse'
        else:
            movement = 'stable'
        
        # Recommendation
        if sharp_score >= 60:
            recommendation = 'bet'  # Strong sharp money signal
        elif sharp_score >= 30:
            recommendation = 'consider'  # Moderate signal
        else:
            recommendation = 'neutral'
        
        return {
            'sharp_indicator': min(100, sharp_score),
            'movement': movement,
            'odds_drop': odds_drop,
            'odds_drop_pct': odds_drop_pct,
            'velocity': velocity,
            'recommendation': recommendation,
            'history_points': len(history)
        }
    
    def get_sharp_bets_today(self) -> List[Dict]:
        """Get all bets with sharp money indicators today"""
        # Find matches with significant odds movements
        cursor = self.conn.cursor()
        
        # Get unique matches from today
        today_start = int(time.time()) - 86400  # Last 24 hours
        
        cursor.execute('''
            SELECT DISTINCT match_id, home_team, away_team, market, selection
            FROM odds_history
            WHERE timestamp > ?
        ''', (today_start,))
        
        matches = cursor.fetchall()
        
        sharp_bets = []
        for match_id, home, away, market, selection in matches:
            analysis = self.detect_sharp_money(match_id, market, selection)
            
            if analysis['sharp_indicator'] >= 30:  # Threshold for sharp money
                sharp_bets.append({
                    'match_id': match_id,
                    'home_team': home,
                    'away_team': away,
                    'market': market,
                    'selection': selection,
                    'sharp_score': analysis['sharp_indicator'],
                    'movement': analysis['movement'],
                    'recommendation': analysis['recommendation']
                })
        
        # Sort by sharp indicator
        sharp_bets.sort(key=lambda x: x['sharp_score'], reverse=True)
        
        return sharp_bets


if __name__ == '__main__':
    print("="*80)
    print("SHARP MONEY TRACKER TEST")
    print("="*80)
    
    tracker = SharpMoneyTracker()
    
    # Simulate odds movements
    match_id = "test_match_001"
    
    print("\n📊 Simulating odds movements...")
    print("   Initial odds: 9.50")
    tracker.record_odds(match_id, "Team A", "Team B", "exact_score", "2-1", 9.50)
    time.sleep(1)
    
    print("   1 hour later: 9.20 (small drop)")
    tracker.record_odds(match_id, "Team A", "Team B", "exact_score", "2-1", 9.20)
    time.sleep(1)
    
    print("   2 hours later: 8.50 (sharp drop!)")
    tracker.record_odds(match_id, "Team A", "Team B", "exact_score", "2-1", 8.50)
    
    print("\n🔍 Analyzing for sharp money...")
    analysis = tracker.detect_sharp_money(match_id, "exact_score", "2-1")
    
    print(f"\n✅ SHARP MONEY ANALYSIS:")
    print(f"   Sharp Indicator: {analysis['sharp_indicator']}/100")
    print(f"   Movement Type: {analysis['movement']}")
    print(f"   Odds Drop: {analysis['odds_drop']:.2f} ({analysis['odds_drop_pct']:.1f}%)")
    print(f"   Velocity: {analysis['velocity']:.2f} points/hour")
    print(f"   Recommendation: {analysis['recommendation'].upper()}")
    
    print("\n" + "="*80)
    print("Sharp money tracking = Follow the smart money!")
