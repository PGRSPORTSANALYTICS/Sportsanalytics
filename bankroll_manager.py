"""
Bankroll Manager - Centralized exposure control for all betting systems.

Prevents over-betting by tracking:
1. Current bankroll (starting + settled profits)
2. Pending exposure (sum of unsettled bet stakes)
3. Available funds (bankroll - pending exposure)

Ensures we never stake more than what's available.
"""

import os
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import create_engine, text


class BankrollManager:
    """Manages bankroll and exposure limits across all betting systems."""
    
    STARTING_BANKROLL = 10_000  # SEK
    MAX_DAILY_EXPOSURE_PCT = 0.80  # Max 80% of bankroll can be at risk
    DEFAULT_STAKE = 173  # SEK per bet (16 USD × 10.8)
    
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        self.engine = create_engine(self.database_url)
    
    def get_current_bankroll(self) -> float:
        """Calculate current bankroll: starting + all settled profits."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COALESCE(SUM(profit_loss), 0) as total_profit
                FROM bets
                WHERE LOWER(outcome) IN ('won', 'win', 'lost', 'loss', 'void', 'push')
            """))
            row = result.fetchone()
            total_profit = float(row[0]) if row else 0
        
        return self.STARTING_BANKROLL + total_profit
    
    def get_pending_exposure(self) -> float:
        """Get total stakes for all unsettled bets."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COALESCE(SUM(stake), 0) as pending_stakes
                FROM bets
                WHERE LOWER(COALESCE(outcome, '')) IN ('', 'pending', 'open')
                   OR outcome IS NULL
            """))
            row = result.fetchone()
            pending = float(row[0]) if row else 0
        
        return pending
    
    def get_today_exposure(self) -> float:
        """Get total stakes placed today (both pending and settled)."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COALESCE(SUM(stake), 0) as today_stakes
                FROM bets
                WHERE DATE(created_at) = CURRENT_DATE
            """))
            row = result.fetchone()
            today = float(row[0]) if row else 0
        
        return today
    
    def get_available_funds(self) -> float:
        """Calculate available funds: bankroll - pending exposure."""
        bankroll = self.get_current_bankroll()
        pending = self.get_pending_exposure()
        return max(0, bankroll - pending)
    
    def get_max_daily_exposure(self) -> float:
        """Maximum amount that can be staked in a single day."""
        bankroll = self.get_current_bankroll()
        return bankroll * self.MAX_DAILY_EXPOSURE_PCT
    
    def get_remaining_daily_budget(self) -> float:
        """How much more can be staked today."""
        max_daily = self.get_max_daily_exposure()
        today_exposure = self.get_today_exposure()
        return max(0, max_daily - today_exposure)
    
    def can_place_bet(self, stake: float = None) -> Tuple[bool, str]:
        """
        Check if a bet can be placed.
        
        Returns:
            (can_place: bool, reason: str)
        """
        stake = stake or self.DEFAULT_STAKE
        
        available = self.get_available_funds()
        daily_remaining = self.get_remaining_daily_budget()
        
        if stake > available:
            return False, f"Insufficient funds: {available:.0f} SEK available, need {stake:.0f} SEK"
        
        if stake > daily_remaining:
            return False, f"Daily limit reached: {daily_remaining:.0f} SEK remaining today"
        
        return True, "OK"
    
    def reserve_stake(self, stake: float = None) -> Tuple[bool, float, str]:
        """
        Attempt to reserve stake for a new bet.
        
        Returns:
            (success: bool, actual_stake: float, message: str)
        """
        stake = stake or self.DEFAULT_STAKE
        
        can_place, reason = self.can_place_bet(stake)
        
        if can_place:
            return True, stake, "Stake reserved"
        
        # Try reduced stake if funds are limited
        available = min(self.get_available_funds(), self.get_remaining_daily_budget())
        
        if available >= 100:  # Minimum stake threshold
            return True, available, f"Reduced stake to {available:.0f} SEK due to limits"
        
        return False, 0, reason
    
    def get_status(self) -> dict:
        """Get full bankroll status report."""
        bankroll = self.get_current_bankroll()
        pending = self.get_pending_exposure()
        available = self.get_available_funds()
        today_exposure = self.get_today_exposure()
        max_daily = self.get_max_daily_exposure()
        daily_remaining = self.get_remaining_daily_budget()
        
        return {
            "starting_bankroll": self.STARTING_BANKROLL,
            "current_bankroll": bankroll,
            "total_profit": bankroll - self.STARTING_BANKROLL,
            "pending_exposure": pending,
            "available_funds": available,
            "today_exposure": today_exposure,
            "max_daily_exposure": max_daily,
            "daily_remaining": daily_remaining,
            "exposure_pct": (pending / bankroll * 100) if bankroll > 0 else 0,
            "today_pct": (today_exposure / max_daily * 100) if max_daily > 0 else 0,
        }
    
    def print_status(self):
        """Print formatted bankroll status."""
        status = self.get_status()
        print("\n" + "="*50)
        print("💰 BANKROLL STATUS")
        print("="*50)
        print(f"Starting Bankroll:  {status['starting_bankroll']:,.0f} SEK")
        print(f"Current Bankroll:   {status['current_bankroll']:,.0f} SEK")
        print(f"Total Profit:       {status['total_profit']:+,.0f} SEK")
        print("-"*50)
        print(f"Pending Exposure:   {status['pending_exposure']:,.0f} SEK ({status['exposure_pct']:.1f}%)")
        print(f"Available Funds:    {status['available_funds']:,.0f} SEK")
        print("-"*50)
        print(f"Today's Exposure:   {status['today_exposure']:,.0f} SEK")
        print(f"Max Daily Limit:    {status['max_daily_exposure']:,.0f} SEK")
        print(f"Daily Remaining:    {status['daily_remaining']:,.0f} SEK ({status['today_pct']:.1f}% used)")
        print("="*50 + "\n")


# Singleton instance for easy import
_manager = None

def get_bankroll_manager() -> BankrollManager:
    """Get singleton BankrollManager instance."""
    global _manager
    if _manager is None:
        _manager = BankrollManager()
    return _manager


if __name__ == "__main__":
    manager = get_bankroll_manager()
    manager.print_status()
    
    # Test bet placement
    can_bet, reason = manager.can_place_bet(160)
    print(f"Can place 160 SEK bet: {can_bet} - {reason}")
