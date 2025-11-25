"""
Bet Status Service - Unified monitoring for Exact Score, SGP, and Women's 1X2 predictions
Provides real-time bet tracking for dashboard and Telegram bot
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pytz
from db_connection import DatabaseConnection


def normalize_result(raw_result: Optional[str]) -> str:
    """
    Normalize all possible result variants to: WON, LOST, PENDING, VOID.
    Supports English and Swedish terminology.
    """
    if raw_result is None:
        return "PENDING"

    s = raw_result.strip().lower()

    win_keywords = [
        "won", "win", "wins", "winner",
        "vinst", "vunnit", "vinna", "green",
        "success"
    ]

    loss_keywords = [
        "lost", "loss", "förlust",
        "förlorat", "red"
    ]

    void_keywords = [
        "void", "push", "refunded",
        "money back", "pushed", "voided",
        "tie", "draw", "oavgjort"
    ]

    if any(k in s for k in win_keywords):
        return "WON"
    if any(k in s for k in loss_keywords):
        return "LOST"
    if any(k in s for k in void_keywords):
        return "VOID"

    if s in ["pending", "open", "not settled", "running", "live", ""]:
        return "PENDING"

    return "PENDING"


class BetStatusService:
    """Centralized service for monitoring all bets across all products"""
    
    def __init__(self):
        self.stockholm_tz = pytz.timezone('Europe/Stockholm')
    
    def get_all_active_bets(self) -> pd.DataFrame:
        """
        Get unified view of all active bets (Exact Score + SGP + Women's 1X2)
        
        Returns:
            DataFrame with columns: type, id, match, league, prediction, odds, 
                                   ev, stake, status, match_date, kickoff_time
        """
        with DatabaseConnection.get_connection() as conn:
            # Exact Score predictions
            exact_scores = pd.read_sql('''
            SELECT 
                'Exact Score' as type,
                id,
                home_team || ' vs ' || away_team as match,
                league,
                REPLACE(selection, 'Exact Score: ', '') as prediction,
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
            
            # Women's 1X2 predictions
            women_1x2 = pd.read_sql('''
            SELECT 
                'Women 1X2' as type,
                id,
                home_team || ' vs ' || away_team as match,
                league,
                selection as prediction,
                odds,
                ev_percentage as ev,
                stake,
                status,
                TO_CHAR(match_date, 'YYYY-MM-DD') as match_date,
                TO_CHAR(kickoff_time, 'HH24:MI:SS') as kickoff_time,
                outcome as result,
                CASE 
                    WHEN outcome = 'win' THEN (odds - 1) * stake
                    ELSE 0
                END as payout,
                profit_loss
            FROM women_match_winner_predictions
                WHERE status IN ('pending', 'live')
                ORDER BY match_date, kickoff_time
            ''', conn)
            
            # Combine all three
            all_bets = pd.concat([exact_scores, sgps, women_1x2], ignore_index=True)
            
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
        
        # Calculate separate stakes for each product
        exact_score_stake = 0
        sgp_stake = 0
        women_1x2_stake = 0
        
        if not all_bets.empty:
            exact_score_bets = all_bets[all_bets['type'] == 'Exact Score']
            sgp_bets = all_bets[all_bets['type'] == 'SGP']
            women_1x2_bets = all_bets[all_bets['type'] == 'Women 1X2']
            
            exact_score_stake = exact_score_bets['stake'].sum() if not exact_score_bets.empty else 0
            sgp_stake = sgp_bets['stake'].sum() if not sgp_bets.empty else 0
            women_1x2_stake = women_1x2_bets['stake'].sum() if not women_1x2_bets.empty else 0
        
        return {
            'total_active': len(all_bets),
            'exact_score': len(all_bets[all_bets['type'] == 'Exact Score']) if not all_bets.empty else 0,
            'sgp': len(all_bets[all_bets['type'] == 'SGP']) if not all_bets.empty else 0,
            'women_1x2': len(all_bets[all_bets['type'] == 'Women 1X2']) if not all_bets.empty else 0,
            'today': len(today_bets),
            'live': len(live_bets),
            'exact_score_stake': exact_score_stake,
            'sgp_stake': sgp_stake,
            'women_1x2_stake': women_1x2_stake,
            'total_stake': exact_score_stake + sgp_stake + women_1x2_stake
        }
    
    def get_settled_today(self) -> pd.DataFrame:
        """Get all bets settled today (for daily recap)"""
        with DatabaseConnection.get_connection() as conn:
            today = datetime.now(self.stockholm_tz).strftime('%Y-%m-%d')
            
            # Exact Score settled today
            exact_scores = pd.read_sql(f'''
                SELECT 
                    'Exact Score' as type,
                    id,
                    home_team || ' vs ' || away_team as match,
                    league,
                    REPLACE(selection, 'Exact Score: ', '') as prediction,
                    odds,
                    stake,
                    result,
                    payout,
                    profit_loss
                FROM football_opportunities
                WHERE status = 'settled'
                AND DATE(TO_TIMESTAMP(settled_timestamp)) = '{today}'
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
                AND DATE(TO_TIMESTAMP(settled_timestamp)) = '{today}'
                ORDER BY settled_timestamp DESC
            ''', conn)
            
            # Women's 1X2 settled today
            women_1x2 = pd.read_sql(f'''
                SELECT 
                    'Women 1X2' as type,
                    id,
                    home_team || ' vs ' || away_team as match,
                    league,
                    selection as prediction,
                    odds,
                    stake,
                    outcome as result,
                    CASE 
                        WHEN outcome = 'win' THEN (odds - 1) * stake
                        ELSE 0
                    END as payout,
                    profit_loss
                FROM women_match_winner_predictions
                WHERE status = 'settled'
                AND DATE(TO_TIMESTAMP(settled_timestamp)) = '{today}'
                ORDER BY settled_timestamp DESC
            ''', conn)
            
            return pd.concat([exact_scores, sgps, women_1x2], ignore_index=True)
    
    def _calculate_live_status(self, row) -> str:
        """Calculate if match is LIVE, UPCOMING, or FINISHED"""
        try:
            kickoff = row['kickoff_time']
            
            # Handle ISO format with timezone (2025-11-06T20:00:00Z)
            if 'T' in kickoff:
                match_time = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
            else:
                # Handle simple format (HH:MM)
                match_datetime_str = f"{row['match_date']} {kickoff}"
                match_time = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
                match_time = self.stockholm_tz.localize(match_time)
            
            now = datetime.now(pytz.UTC)
            
            # Match is live if started within last 2 hours
            if now >= match_time and now <= match_time + timedelta(hours=2):
                return 'LIVE'
            elif now < match_time:
                return 'UPCOMING'
            else:
                return 'FINISHED'
        except Exception as e:
            return 'UNKNOWN'
    
    def _minutes_to_kickoff(self, row) -> int:
        """Calculate minutes until kickoff (negative if started)"""
        try:
            kickoff = row['kickoff_time']
            
            # Handle ISO format with timezone (2025-11-06T20:00:00Z)
            if 'T' in kickoff:
                match_time = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
            else:
                # Handle simple format (HH:MM)
                match_datetime_str = f"{row['match_date']} {kickoff}"
                match_time = datetime.strptime(match_datetime_str, '%Y-%m-%d %H:%M')
                match_time = self.stockholm_tz.localize(match_time)
            
            now = datetime.now(pytz.UTC)
            
            delta = (match_time - now).total_seconds() / 60
            return int(delta)
        except Exception as e:
            return 999

    def get_women_1x2_performance(self) -> Dict:
        """Get performance stats for women's 1X2 predictions (PROD mode only)"""
        with DatabaseConnection.get_connection() as conn:
        
        try:
            # Get all settled women's 1X2 bets (PROD mode only)
            query = '''
                SELECT 
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                    SUM(stake) as total_staked,
                    SUM(profit_loss) as total_profit
                FROM women_match_winner_predictions
                WHERE status = 'settled'
                AND outcome IS NOT NULL
                AND mode = 'PROD'
            '''
            
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty or df.iloc[0]['total_bets'] == 0:
                return {
                    'total_bets': 0,
                    'wins': 0,
                    'losses': 0,
                    'hit_rate': 0.0,
                    'roi': 0.0,
                    'total_profit': 0.0,
                    'total_staked': 0.0
                }
            
            row = df.iloc[0]
            total_bets = int(row['total_bets'] or 0)
            wins = int(row['wins'] or 0)
            losses = int(row['losses'] or 0)
            total_staked = float(row['total_staked'] or 0)
            total_profit = float(row['total_profit'] or 0)
            
            hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
            roi = (total_profit / total_staked * 100) if total_staked > 0 else 0
            
            return {
                'total_bets': total_bets,
                'wins': wins,
                'losses': losses,
                'hit_rate': hit_rate,
                'roi': roi,
                'total_profit': total_profit,
                'total_staked': total_staked
            }
            
        except Exception as e:
            conn.close()
            return {
                'total_bets': 0,
                'wins': 0,
                'losses': 0,
                'hit_rate': 0.0,
                'roi': 0.0,
                'total_profit': 0.0,
                'total_staked': 0.0,
                'error': str(e)
            }

    def format_bet_for_telegram(self, bet_row) -> str:
        """Format a single bet for Telegram display"""
        status_emoji = {
            'LIVE': '🔴',
            'UPCOMING': '⏰',
            'FINISHED': '✅'
        }
        
        emoji = status_emoji.get(bet_row['live_status'], '📋')
        
        # Type-specific emoji
        if bet_row['type'] == 'Exact Score':
            type_emoji = '⚽'
        elif bet_row['type'] == 'SGP':
            type_emoji = '🎯'
        else:  # Women 1X2
            type_emoji = '👩⚽'
        
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
