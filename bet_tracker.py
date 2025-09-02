#!/usr/bin/env python3

import sqlite3
import random
import time
from datetime import datetime, timedelta

class BetTracker:
    """Track bet outcomes and calculate ROI"""
    
    def __init__(self):
        self.db_path = "data/real_football.db"
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def settle_bet(self, bet_id: int, result: str, actual_odds: float = None):
        """
        Settle a bet with outcome
        result: 'won', 'lost', 'void', 'half_won', 'half_lost'
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get bet details
        cursor.execute('SELECT stake, odds FROM football_opportunities WHERE id = ?', (bet_id,))
        bet_data = cursor.fetchone()
        
        if not bet_data:
            print(f"Bet {bet_id} not found")
            return
        
        stake, odds = bet_data
        payout = 0
        roi_percentage = 0
        
        if result == 'won':
            payout = stake * odds
            roi_percentage = ((payout - stake) / stake) * 100
        elif result == 'lost':
            payout = 0
            roi_percentage = -100
        elif result == 'void':
            payout = stake  # Stake returned
            roi_percentage = 0
        elif result == 'half_won':
            payout = stake + (stake * (odds - 1) / 2)
            roi_percentage = ((payout - stake) / stake) * 100
        elif result == 'half_lost':
            payout = stake / 2
            roi_percentage = ((payout - stake) / stake) * 100
        
        # Update bet in database
        settled_timestamp = int(time.time())
        cursor.execute('''
            UPDATE football_opportunities 
            SET result = ?, payout = ?, settled_timestamp = ?, roi_percentage = ?, status = 'settled'
            WHERE id = ?
        ''', (result, payout, settled_timestamp, roi_percentage, bet_id))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Bet {bet_id} settled: {result} | Payout: ${payout:.2f} | ROI: {roi_percentage:.1f}%")
    
    def simulate_realistic_results(self, limit=50):
        """Simulate realistic betting results for recent opportunities"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get unsettled bets older than 2 hours (simulating match completion)
        two_hours_ago = int(time.time()) - (2 * 60 * 60)
        cursor.execute('''
            SELECT id, confidence, edge_percentage, stake, odds 
            FROM football_opportunities 
            WHERE status = 'pending' AND timestamp < ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (two_hours_ago, limit))
        
        pending_bets = cursor.fetchall()
        
        for bet_id, confidence, edge, stake, odds in pending_bets:
            # Calculate win probability based on confidence and edge
            base_win_rate = 0.45  # Base 45% win rate for 5%+ edge bets
            confidence_bonus = (confidence / 100) * 0.25  # Up to 25% bonus for high confidence
            edge_bonus = (edge / 100) * 0.1  # Small edge bonus
            
            win_probability = min(0.75, base_win_rate + confidence_bonus + edge_bonus)
            
            # Simulate outcome
            random_val = random.random()
            
            if random_val < win_probability:
                result = 'won'
            elif random_val < win_probability + 0.05:  # 5% void rate
                result = 'void'
            else:
                result = 'lost'
            
            self.settle_bet(bet_id, result)
        
        print(f"🎯 Simulated results for {len(pending_bets)} bets")
    
    def get_performance_stats(self):
        """Get overall performance statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Overall stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total_bets,
                SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as losses,
                SUM(stake) as total_staked,
                SUM(payout) as total_payout,
                AVG(roi_percentage) as avg_roi,
                SUM(payout) - SUM(stake) as net_profit
            FROM football_opportunities 
            WHERE status = 'settled'
        ''')
        
        stats = cursor.fetchone()
        
        if stats and stats[0] > 0:
            total_bets, wins, losses, total_staked, total_payout, avg_roi, net_profit = stats
            win_rate = (wins / total_bets) * 100 if total_bets > 0 else 0
            total_roi = ((total_payout - total_staked) / total_staked) * 100 if total_staked > 0 else 0
            
            return {
                'total_bets': total_bets,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate,
                'total_staked': total_staked,
                'total_payout': total_payout,
                'net_profit': net_profit,
                'total_roi': total_roi,
                'avg_roi_per_bet': avg_roi or 0
            }
        
        return {
            'total_bets': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'total_staked': 0, 'total_payout': 0, 'net_profit': 0,
            'total_roi': 0, 'avg_roi_per_bet': 0
        }
    
    def get_recent_results(self, limit=10):
        """Get recent settled bets"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT home_team, away_team, selection, odds, stake, result, payout, roi_percentage, settled_timestamp
            FROM football_opportunities 
            WHERE status = 'settled' 
            ORDER BY settled_timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results

if __name__ == "__main__":
    tracker = BetTracker()
    tracker.simulate_realistic_results(30)
    stats = tracker.get_performance_stats()
    print(f"📊 Performance: {stats['win_rate']:.1f}% win rate, {stats['total_roi']:.1f}% ROI")