import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

class HighlightsDetector:
    """Detects and returns highlight moments from prediction history."""
    
    def __init__(self, db_path: str = "data/real_football.db"):
        self.db_path = db_path
    
    def get_all_highlights(self) -> List[Dict[str, Any]]:
        """Get all highlight moments from the data."""
        highlights = []
        
        # Get historical data
        conn = sqlite3.connect(self.db_path)
        
        # Load settled predictions ordered by date
        query = """
        SELECT home_team, away_team, selection, odds, outcome, profit_loss, 
               match_date, timestamp, stake
        FROM football_opportunities 
        WHERE tier = 'legacy'
        AND outcome IS NOT NULL 
        AND outcome != ''
        AND outcome NOT IN ('unknown', 'void')
        ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty or len(df) < 2:
            return highlights
        
        # Add win flag
        df['is_win'] = df['outcome'].isin(['win', 'won'])
        
        # 1. WINNING STREAKS
        winning_streak_highlights = self._detect_winning_streaks(df)
        highlights.extend(winning_streak_highlights)
        
        # 2. ROI LIFTS
        roi_lift_highlights = self._detect_roi_lifts(df)
        highlights.extend(roi_lift_highlights)
        
        # 3. MILESTONE ACHIEVEMENTS
        milestone_highlights = self._detect_milestones(df)
        highlights.extend(milestone_highlights)
        
        # 4. BEST PERFORMANCES
        best_performance_highlights = self._detect_best_performances(df)
        highlights.extend(best_performance_highlights)
        
        # 5. PERFECT DAYS/WEEKS
        perfect_period_highlights = self._detect_perfect_periods(df)
        highlights.extend(perfect_period_highlights)
        
        # Sort by timestamp (most recent first)
        highlights.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return highlights[:10]  # Return top 10 most recent highlights
    
    def _detect_winning_streaks(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect winning streaks (3+, 5+, 7+ in a row)."""
        highlights = []
        
        current_streak = 0
        streak_start_idx = None
        
        for idx, row in df.iterrows():
            if row['is_win']:
                if current_streak == 0:
                    streak_start_idx = idx
                current_streak += 1
            else:
                # Streak ended
                if current_streak >= 3:
                    # Record this streak
                    emoji = "🔥" if current_streak >= 7 else "⚡" if current_streak >= 5 else "✨"
                    tier = "LEGENDARY" if current_streak >= 7 else "EPIC" if current_streak >= 5 else "GREAT"
                    
                    highlights.append({
                        'type': 'winning_streak',
                        'emoji': emoji,
                        'tier': tier,
                        'title': f"{current_streak} Wins in a Row!",
                        'description': f"{tier} winning streak - {current_streak} consecutive exact score hits",
                        'timestamp': row['timestamp'],
                        'value': current_streak
                    })
                
                current_streak = 0
                streak_start_idx = None
        
        # Check if we ended on a streak
        if current_streak >= 3:
            emoji = "🔥" if current_streak >= 7 else "⚡" if current_streak >= 5 else "✨"
            tier = "LEGENDARY" if current_streak >= 7 else "EPIC" if current_streak >= 5 else "GREAT"
            
            highlights.append({
                'type': 'winning_streak',
                'emoji': emoji,
                'tier': tier,
                'title': f"{current_streak} Wins in a Row!",
                'description': f"{tier} winning streak - {current_streak} consecutive exact score hits (ACTIVE!)",
                'timestamp': df.iloc[-1]['timestamp'],
                'value': current_streak,
                'active': True
            })
        
        return highlights
    
    def _detect_roi_lifts(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect significant ROI lifts (10%+, 25%+, 50%+)."""
        highlights = []
        
        if len(df) < 10:
            return highlights
        
        # Calculate rolling ROI
        df['cumulative_profit'] = df['profit_loss'].cumsum()
        df['cumulative_stake'] = df['stake'].cumsum()
        df['roi'] = (df['cumulative_profit'] / df['cumulative_stake'] * 100).fillna(0)
        
        # Look for significant jumps in 10-bet windows
        window_size = 10
        
        for i in range(window_size, len(df)):
            roi_before = df.iloc[i - window_size]['roi']
            roi_after = df.iloc[i]['roi']
            roi_change = roi_after - roi_before
            
            if roi_change >= 50:
                highlights.append({
                    'type': 'roi_lift',
                    'emoji': '🚀',
                    'tier': 'LEGENDARY',
                    'title': f'+{roi_change:.0f}% ROI Surge!',
                    'description': f'Massive ROI jump from {roi_before:.0f}% to {roi_after:.0f}% in {window_size} predictions',
                    'timestamp': df.iloc[i]['timestamp'],
                    'value': roi_change
                })
            elif roi_change >= 25:
                highlights.append({
                    'type': 'roi_lift',
                    'emoji': '📈',
                    'tier': 'EPIC',
                    'title': f'+{roi_change:.0f}% ROI Boost!',
                    'description': f'Strong ROI increase from {roi_before:.0f}% to {roi_after:.0f}% in {window_size} predictions',
                    'timestamp': df.iloc[i]['timestamp'],
                    'value': roi_change
                })
            elif roi_change >= 10:
                highlights.append({
                    'type': 'roi_lift',
                    'emoji': '💹',
                    'tier': 'GREAT',
                    'title': f'+{roi_change:.0f}% ROI Growth',
                    'description': f'Solid ROI improvement from {roi_before:.0f}% to {roi_after:.0f}% in {window_size} predictions',
                    'timestamp': df.iloc[i]['timestamp'],
                    'value': roi_change
                })
        
        return highlights
    
    def _detect_milestones(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect milestone achievements (10th win, 25th win, 50th prediction, etc.)."""
        highlights = []
        
        # Win milestones
        win_milestones = [5, 10, 15, 20, 25, 30, 40, 50]
        wins_df = df[df['is_win']].reset_index(drop=True)
        
        for milestone in win_milestones:
            if len(wins_df) >= milestone:
                row = wins_df.iloc[milestone - 1]
                highlights.append({
                    'type': 'milestone',
                    'emoji': '🏆',
                    'tier': 'MILESTONE',
                    'title': f'{milestone} Total Wins!',
                    'description': f'Milestone reached: {milestone} exact score predictions won',
                    'timestamp': row['timestamp'],
                    'value': milestone
                })
        
        # Prediction milestones
        pred_milestones = [50, 100, 150, 200, 250, 300, 400, 500]
        
        for milestone in pred_milestones:
            if len(df) >= milestone:
                row = df.iloc[milestone - 1]
                highlights.append({
                    'type': 'milestone',
                    'emoji': '🎯',
                    'tier': 'MILESTONE',
                    'title': f'{milestone} Predictions!',
                    'description': f'Milestone reached: {milestone} settled exact score predictions',
                    'timestamp': row['timestamp'],
                    'value': milestone
                })
        
        return highlights
    
    def _detect_best_performances(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect best single performances (highest odds won, biggest profit, etc.)."""
        highlights = []
        
        # Highest odds won
        wins_df = df[df['is_win']].copy()
        if not wins_df.empty:
            best_odds_row = wins_df.loc[wins_df['odds'].idxmax()]
            if best_odds_row['odds'] >= 10:
                highlights.append({
                    'type': 'best_performance',
                    'emoji': '💎',
                    'tier': 'EPIC',
                    'title': f'{best_odds_row["odds"]:.1f}x Odds Won!',
                    'description': f'Biggest odds win: {best_odds_row["selection"]} in {best_odds_row["home_team"]} vs {best_odds_row["away_team"]}',
                    'timestamp': best_odds_row['timestamp'],
                    'value': best_odds_row['odds']
                })
        
        # Biggest single profit
        if not df.empty:
            best_profit_row = df.loc[df['profit_loss'].idxmax()]
            if best_profit_row['profit_loss'] > 0:
                highlights.append({
                    'type': 'best_performance',
                    'emoji': '💰',
                    'tier': 'EPIC',
                    'title': f'+{best_profit_row["profit_loss"]:.0f} SEK Win!',
                    'description': f'Biggest single profit: {best_profit_row["selection"]} @ {best_profit_row["odds"]:.1f}x',
                    'timestamp': best_profit_row['timestamp'],
                    'value': best_profit_row['profit_loss']
                })
        
        return highlights
    
    def _detect_perfect_periods(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect perfect days/weeks (100% hit rate in a period)."""
        highlights = []
        
        if df.empty:
            return highlights
        
        # Convert timestamp to date
        df['date'] = pd.to_datetime(df['timestamp'], unit='s').dt.date
        
        # Check for perfect days (all predictions won, minimum 2 predictions)
        daily_stats = df.groupby('date').agg({
            'is_win': ['sum', 'count']
        })
        daily_stats.columns = ['wins', 'total']
        
        perfect_days = daily_stats[(daily_stats['wins'] == daily_stats['total']) & (daily_stats['total'] >= 2)]
        
        for date, stats in perfect_days.iterrows():
            # Get timestamp of last prediction on that day
            day_df = df[df['date'] == date]
            last_timestamp = day_df['timestamp'].max()
            
            highlights.append({
                'type': 'perfect_period',
                'emoji': '⭐',
                'tier': 'EPIC',
                'title': f'Perfect Day!',
                'description': f'{int(stats["total"])}/{int(stats["total"])} predictions won on {date}',
                'timestamp': last_timestamp,
                'value': stats['total']
            })
        
        return highlights
