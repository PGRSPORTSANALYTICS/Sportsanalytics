"""
Bet Status Service - Unified monitoring for Exact Score and SGP predictions
Provides real-time bet tracking for dashboard and Telegram bot
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pytz

class BetStatusService:
    """Centralized service for monitoring all bets across both products"""
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self.stockholm_tz = pytz.timezone('Europe/Stockholm')
    
    def get_all_active_bets(self) -> pd.DataFrame:
        """
        Get unified view of all active bets (Exact Score + SGPs)
        
        Returns:
            DataFrame with columns: type, id, match, league, prediction, odds, 
                                   ev, stake, status, match_date, kickoff_time
        """
        conn = sqlite3.connect(self.db_path)
        
        # Exact Score predictions
        exact_scores = pd.read_sql('''
            SELECT 
                'Exact Score' as type,
                id,
                home_team || ' vs ' || away_team as match,
                league,
                selection as prediction,
                odds,
                edge_percentage as ev,
                stake,
                status,
                match_date,
                kickoff_time,
                result,
                payout,
                profit_loss
            FROM football_opportunities
            WHERE status IN ('pending', 'live')
            ORDER BY match_date, kickoff_time
        ''', conn)
        
        # SGP predictions
        sgps = pd.read_sql('''
            SELECT 
                'SGP' as type,
                id,
                home_team || ' vs ' || away_team as match,
                league,
                parlay_description as prediction,
                bookmaker_odds as odds,
                ev_percentage as ev,
                stake,
                status,
                match_date,
                kickoff_time,
                outcome as result,
                payout,
                profit_loss
            FROM sgp_predictions
            WHERE status IN ('pending', 'live')
            ORDER BY match_date, kickoff_time
        ''', conn)
        
        conn.close()
        
        # Combine both
        all_bets = pd.concat([exact_scores, sgps], ignore_index=True)
        
        # Add live status indicator
        if not all_bets.empty:
            all_bets['live_status'] = all_bets.apply(self._calculate_live_status, axis=1)
            all_bets['minutes_to_kickoff'] = all_bets.apply(self._minutes_to_kickoff, axis=1)
        
        return all_bets
    
    def get_today_bets(self) -> pd.DataFrame:
        """Get all bets for matches playing today"""
        all_bets = self.get_all_active_bets()
        
        if all_bets.empty:
            return all_bets
        
        today = datetime.now(self.stockholm_tz).strftime('%Y-%m-%d')
        return all_bets[all_bets['match_date'] == today].copy()
    
    def get_live_bets(self) -> pd.DataFrame:
        """Get all bets for matches currently in play"""
        all_bets = self.get_all_active_bets()
        
        if all_bets.empty:
            return all_bets
        
        return all_bets[all_bets['live_status'] == 'LIVE'].copy()
    
    def get_upcoming_bets(self, hours: int = 3) -> pd.DataFrame:
        """Get bets for matches starting in next X hours"""
        all_bets = self.get_all_active_bets()
        
        if all_bets.empty:
            return all_bets
        
        return all_bets[
            (all_bets['live_status'] == 'UPCOMING') & 
            (all_bets['minutes_to_kickoff'] <= hours * 60)
        ].copy()
    
    def get_summary_stats(self) -> Dict[str, int]:
        """Get quick summary statistics"""
        all_bets = self.get_all_active_bets()
        today_bets = self.get_today_bets()
        live_bets = self.get_live_bets()
        
        return {
            'total_active': len(all_bets),
            'exact_score': len(all_bets[all_bets['type'] == 'Exact Score']) if not all_bets.empty else 0,
            'sgp': len(all_bets[all_bets['type'] == 'SGP']) if not all_bets.empty else 0,
            'today': len(today_bets),
            'live': len(live_bets),
            'total_stake': all_bets['stake'].sum() if not all_bets.empty else 0
        }
    
    def get_settled_today(self) -> pd.DataFrame:
        """Get all bets settled today (for daily recap)"""
        conn = sqlite3.connect(self.db_path)
        
        today = datetime.now(self.stockholm_tz).strftime('%Y-%m-%d')
        
        # Exact Score settled today
        exact_scores = pd.read_sql(f'''
            SELECT 
                'Exact Score' as type,
                id,
                home_team || ' vs ' || away_team as match,
                league,
                selection as prediction,
                odds,
                stake,
                result,
                payout,
                profit_loss
            FROM football_opportunities
            WHERE status = 'settled'
            AND DATE(settled_timestamp, 'unixepoch') = '{today}'
            ORDER BY settled_timestamp DESC
        ''', conn)
        
        # SGP settled today
        sgps = pd.read_sql(f'''
            SELECT 
                'SGP' as type,
                id,
                home_team || ' vs ' || away_team as match,
                league,
                parlay_description as prediction,
                bookmaker_odds as odds,
                stake,
                outcome as result,
                payout,
                profit_loss
            FROM sgp_predictions
            WHERE status = 'settled'
            AND DATE(settled_timestamp, 'unixepoch') = '{today}'
            ORDER BY settled_timestamp DESC
        ''', conn)
        
        conn.close()
        
        return pd.concat([exact_scores, sgps], ignore_index=True)
    
    def _calculate_live_status(self, row) -> str:
        """Calculate if match is LIVE, UPCOMING, or FINISHED"""
        try:
            match_datetime_str = f"{row['match_date']} {row['kickoff_time']}"
            match_time = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
            match_time = self.stockholm_tz.localize(match_time)
            now = datetime.now(self.stockholm_tz)
            
            # Match is live if started within last 2 hours
            if now >= match_time and now <= match_time + timedelta(hours=2):
                return 'LIVE'
            elif now < match_time:
                return 'UPCOMING'
            else:
                return 'FINISHED'
        except:
            return 'UNKNOWN'
    
    def _minutes_to_kickoff(self, row) -> int:
        """Calculate minutes until kickoff (negative if started)"""
        try:
            match_datetime_str = f"{row['match_date']} {row['kickoff_time']}"
            match_time = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
            match_time = self.stockholm_tz.localize(match_time)
            now = datetime.now(self.stockholm_tz)
            
            delta = (match_time - now).total_seconds() / 60
            return int(delta)
        except:
            return 999

    def format_bet_for_telegram(self, bet_row) -> str:
        """Format a single bet for Telegram display"""
        status_emoji = {
            'LIVE': '🔴',
            'UPCOMING': '⏰',
            'FINISHED': '✅'
        }
        
        emoji = status_emoji.get(bet_row['live_status'], '📋')
        type_emoji = '⚽' if bet_row['type'] == 'Exact Score' else '🎯'
        
        # Format time info
        if bet_row['live_status'] == 'LIVE':
            time_info = 'LIVE NOW'
        elif bet_row['live_status'] == 'UPCOMING':
            mins = bet_row['minutes_to_kickoff']
            if mins < 60:
                time_info = f'In {mins} min'
            else:
                hours = mins // 60
                time_info = f'In {hours}h {mins % 60}m'
        else:
            time_info = bet_row['kickoff_time']
        
        return (
            f"{emoji} {type_emoji} **{bet_row['match']}**\n"
            f"   {bet_row['prediction']}\n"
            f"   Odds: {bet_row['odds']:.2f} | EV: {bet_row['ev']:.1f}% | Stake: {bet_row['stake']:.0f} SEK\n"
            f"   {time_info} | {bet_row['league']}\n"
        )


if __name__ == '__main__':
    # Test the service
    service = BetStatusService()
    
    print("=== BET STATUS SERVICE TEST ===\n")
    
    stats = service.get_summary_stats()
    print("📊 Summary:")
    print(f"   Total active: {stats['total_active']}")
    print(f"   Exact Score: {stats['exact_score']}")
    print(f"   SGP: {stats['sgp']}")
    print(f"   Playing today: {stats['today']}")
    print(f"   Live now: {stats['live']}")
    print(f"   Total stake: {stats['total_stake']:.0f} SEK\n")
    
    today = service.get_today_bets()
    if not today.empty:
        print(f"📅 Today's bets ({len(today)}):")
        for _, bet in today.iterrows():
            print(service.format_bet_for_telegram(bet))
    else:
        print("📅 No bets today")
    
    print("\n✅ Service ready for dashboard and Telegram integration!")
