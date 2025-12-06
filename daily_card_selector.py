"""
PGR Daily Betting Card Selector
Generates a daily betting card for subscribers based on EV-filtered predictions
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from db_helper import DatabaseHelper
import logging

logger = logging.getLogger(__name__)


class DailyCardSelector:
    """Generates daily betting cards using EV-based selection rules"""
    
    EV_TIER_A = (0.10, 0.20)
    EV_TIER_B = (0.05, 0.10)
    EV_TIER_C = (0.00, 0.05)
    
    SGP_VALID_ODDS = [(2.0, 3.0), (4.0, 5.0)]
    BASKETBALL_ODDS_RANGE = (1.40, 2.50)
    
    MAX_VALUE_SINGLES = 6
    MAX_SGP = 4
    MAX_BASKETBALL = 3
    
    def __init__(self):
        self.load_error = None
        self.value_singles = []
        self.sgp_bets = []
        self.basketball_bets = []
        
    def _get_ev_tier(self, ev: float) -> str:
        """Classify EV into tier A, B, or C"""
        if ev >= 0.10:
            return 'A'
        elif ev >= 0.05:
            return 'B'
        elif ev >= 0.00:
            return 'C'
        return 'X'
    
    def _is_valid_sgp_odds(self, odds: float) -> bool:
        """Check if SGP odds fall within valid ranges (2.0-3.0 or 4.0-5.0)"""
        for min_odds, max_odds in self.SGP_VALID_ODDS:
            if min_odds <= odds <= max_odds:
                return True
        return False
    
    def load_upcoming_bets(self) -> bool:
        """Load all upcoming bets from database for the next 24 hours"""
        if not os.getenv("DATABASE_URL"):
            self.load_error = "DATABASE_URL not configured"
            return False
        
        try:
            now = datetime.now()
            tomorrow = now + timedelta(hours=24)
            
            sgp_rows = DatabaseHelper.execute("""
                SELECT 
                    'SGP' as sport,
                    league,
                    'SGP' as market,
                    parlay_description as selection,
                    home_team || ' vs ' || away_team as matchup,
                    bookmaker_odds as odds,
                    ev_percentage / 100.0 as ev,
                    parlay_probability as confidence,
                    match_date as start_time,
                    status
                FROM sgp_predictions 
                WHERE status = 'pending'
                AND match_date_only >= CURRENT_DATE
                AND match_date_only <= CURRENT_DATE + INTERVAL '1 day'
            """, fetch='all')
            
            if sgp_rows:
                for row in sgp_rows:
                    ev = row[6] if row[6] else 0
                    odds = row[5] if row[5] else 0
                    
                    if ev < 0:
                        continue
                    if not self._is_valid_sgp_odds(odds):
                        continue
                    
                    self.sgp_bets.append({
                        'sport': 'Football',
                        'league': row[1] or 'Unknown',
                        'market': 'SGP',
                        'selection': row[3] or '',
                        'matchup': row[4] or '',
                        'odds': odds,
                        'ev': ev,
                        'confidence': row[7] if row[7] else 0,
                        'start_time': row[8] or '',
                        'tier': self._get_ev_tier(ev)
                    })
            
            basket_rows = DatabaseHelper.execute("""
                SELECT 
                    'Basketball' as sport,
                    league,
                    market,
                    selection,
                    match as matchup,
                    odds::float as odds,
                    ev_percentage::float / 100.0 as ev,
                    confidence::float / 100.0 as confidence,
                    commence_time as start_time,
                    status,
                    is_parlay
                FROM basketball_predictions 
                WHERE status = 'pending'
                AND commence_time >= NOW()
                AND commence_time <= NOW() + INTERVAL '24 hours'
                AND is_parlay = false
            """, fetch='all')
            
            if basket_rows:
                for row in basket_rows:
                    ev = row[6] if row[6] else 0
                    odds = row[5] if row[5] else 0
                    
                    if ev < 0:
                        continue
                    if odds < 1.40 and ev < 0.10:
                        continue
                    
                    self.basketball_bets.append({
                        'sport': 'Basketball',
                        'league': row[1] or 'NCAAB',
                        'market': row[2] or 'Unknown',
                        'selection': row[3] or '',
                        'matchup': row[4] or '',
                        'odds': odds,
                        'ev': ev,
                        'confidence': row[7] if row[7] else 0,
                        'start_time': row[8] or '',
                        'tier': self._get_ev_tier(ev)
                    })
            
            football_rows = DatabaseHelper.execute("""
                SELECT 
                    'Football' as sport,
                    league,
                    market,
                    selection,
                    home_team || ' vs ' || away_team as matchup,
                    odds as odds,
                    edge_percentage / 100.0 as ev,
                    confidence::float / 100.0 as confidence,
                    kickoff_time as start_time,
                    status
                FROM football_opportunities 
                WHERE status = 'pending'
                AND market NOT IN ('exact_score', 'correct_score')
                AND kickoff_time IS NOT NULL
            """, fetch='all')
            
            if football_rows:
                for row in football_rows:
                    ev = row[6] if row[6] else 0
                    odds = row[5] if row[5] else 0
                    
                    if ev < 0:
                        continue
                    if odds < 1.40 and ev < 0.10:
                        continue
                    
                    self.value_singles.append({
                        'sport': 'Football',
                        'league': row[1] or 'Unknown',
                        'market': row[2] or 'Unknown',
                        'selection': row[3] or '',
                        'matchup': row[4] or '',
                        'odds': odds,
                        'ev': ev,
                        'confidence': row[7] if row[7] else 0,
                        'start_time': row[8] or '',
                        'tier': self._get_ev_tier(ev)
                    })
            
            return True
            
        except Exception as e:
            self.load_error = str(e)
            logger.error(f"Error loading upcoming bets: {e}")
            return False
    
    def _sort_by_ev_tier(self, bets: List[Dict]) -> List[Dict]:
        """Sort bets by EV tier (A first, then B, then C) and within tier by EV descending"""
        tier_order = {'A': 0, 'B': 1, 'C': 2, 'X': 3}
        return sorted(bets, key=lambda x: (tier_order.get(x['tier'], 3), -x['ev']))
    
    def generate_daily_card(self) -> Dict[str, Any]:
        """Generate the daily betting card following selection rules"""
        if not self.load_upcoming_bets():
            return {
                'error': self.load_error,
                'value_singles': [],
                'sgp': [],
                'basketball': [],
                'summary': None
            }
        
        sorted_singles = self._sort_by_ev_tier(self.value_singles)[:self.MAX_VALUE_SINGLES]
        sorted_sgp = self._sort_by_ev_tier(self.sgp_bets)[:self.MAX_SGP]
        sorted_basketball = self._sort_by_ev_tier(self.basketball_bets)[:self.MAX_BASKETBALL]
        
        total_bets = len(sorted_singles) + len(sorted_sgp) + len(sorted_basketball)
        
        if total_bets == 0:
            return {
                'error': None,
                'value_singles': [],
                'sgp': [],
                'basketball': [],
                'summary': {
                    'message': 'No official value plays today based on current EV filters.',
                    'total_bets': 0
                }
            }
        
        summary = {
            'value_singles_count': len(sorted_singles),
            'sgp_count': len(sorted_sgp),
            'basketball_count': len(sorted_basketball),
            'total_bets': total_bets,
            'value_singles_avg_ev': sum(b['ev'] for b in sorted_singles) / len(sorted_singles) * 100 if sorted_singles else 0,
            'value_singles_avg_odds': sum(b['odds'] for b in sorted_singles) / len(sorted_singles) if sorted_singles else 0,
            'sgp_avg_ev': sum(b['ev'] for b in sorted_sgp) / len(sorted_sgp) * 100 if sorted_sgp else 0,
            'sgp_avg_odds': sum(b['odds'] for b in sorted_sgp) / len(sorted_sgp) if sorted_sgp else 0,
            'basketball_avg_ev': sum(b['ev'] for b in sorted_basketball) / len(sorted_basketball) * 100 if sorted_basketball else 0,
            'basketball_avg_odds': sum(b['odds'] for b in sorted_basketball) / len(sorted_basketball) if sorted_basketball else 0,
        }
        
        return {
            'error': None,
            'value_singles': sorted_singles,
            'sgp': sorted_sgp,
            'basketball': sorted_basketball,
            'summary': summary
        }
    
    def format_as_markdown(self) -> str:
        """Format the daily card as markdown"""
        card = self.generate_daily_card()
        
        if card['error']:
            return f"**Error:** {card['error']}"
        
        if card['summary'] and card['summary'].get('total_bets', 0) == 0:
            return card['summary'].get('message', 'No value plays today.')
        
        lines = ["# PGR Daily Betting Card", ""]
        
        if card['value_singles']:
            lines.append("## Value Singles")
            for bet in card['value_singles']:
                tier_badge = f"[Tier {bet['tier']}]"
                lines.append(
                    f"- {tier_badge} **{bet['league']}** – {bet['market']} – {bet['matchup']} "
                    f"– Odds: {bet['odds']:.2f} – EV: {bet['ev']*100:.1f}% – Conf: {bet['confidence']*100:.0f}%"
                )
            lines.append("")
        
        if card['sgp']:
            lines.append("## SGP Bets")
            for bet in card['sgp']:
                tier_badge = f"[Tier {bet['tier']}]"
                lines.append(
                    f"- {tier_badge} **{bet['league']}** – {bet['matchup']}\n"
                    f"  {bet['selection']}\n"
                    f"  Odds: {bet['odds']:.2f} – EV: {bet['ev']*100:.1f}%"
                )
            lines.append("")
        
        if card['basketball']:
            lines.append("## Basketball")
            for bet in card['basketball']:
                tier_badge = f"[Tier {bet['tier']}]"
                lines.append(
                    f"- {tier_badge} **{bet['league']}** – {bet['market']} – {bet['matchup']} "
                    f"– {bet['selection']} – Odds: {bet['odds']:.2f} – EV: {bet['ev']*100:.1f}%"
                )
            lines.append("")
        
        summary = card['summary']
        lines.append("---")
        lines.append("## Summary")
        lines.append(f"- **Value Singles:** {summary['value_singles_count']} bets "
                     f"(Avg EV: {summary['value_singles_avg_ev']:.1f}%, Avg Odds: {summary['value_singles_avg_odds']:.2f})")
        lines.append(f"- **SGP:** {summary['sgp_count']} bets "
                     f"(Avg EV: {summary['sgp_avg_ev']:.1f}%, Avg Odds: {summary['sgp_avg_odds']:.2f})")
        lines.append(f"- **Basketball:** {summary['basketball_count']} bets "
                     f"(Avg EV: {summary['basketball_avg_ev']:.1f}%, Avg Odds: {summary['basketball_avg_odds']:.2f})")
        lines.append(f"- **Total:** {summary['total_bets']} bets for today's card")
        
        return "\n".join(lines)


if __name__ == "__main__":
    selector = DailyCardSelector()
    print(selector.format_as_markdown())
