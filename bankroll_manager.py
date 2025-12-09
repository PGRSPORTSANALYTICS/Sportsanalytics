"""
Bankroll Manager - Centralized exposure control for all betting systems.

Features:
1. Dynamic staking: 1.2% of current bankroll per bet
2. Unit system: 1 unit = 1% of bankroll (each bet = 1.2u)
3. Daily loss protection: Stop betting if daily loss ≥ 20% of bankroll
4. Exposure limits: Max 80% of bankroll at risk

Ensures smart money management and protects the bankroll.
"""

import os
from datetime import datetime
from typing import Optional, Tuple, Dict
from sqlalchemy import create_engine, text


class BankrollManager:
    """Manages bankroll and exposure limits across all betting systems."""
    
    STARTING_BANKROLL = 4_607  # SEK (adjusted to match actual: 13,294 - 8,687 profit)
    MAX_DAILY_EXPOSURE_PCT = 0.80  # Max 80% of bankroll can be at risk
    DAILY_LOSS_LIMIT_PCT = 0.20  # Stop betting if daily loss ≥ 20%
    
    STAKE_PCT = 0.012  # 1.2% of bankroll per bet (standard)
    EXACT_SCORE_STAKE_PCT = 0.006  # 0.6% for exact score (higher variance)
    BASE_UNIT_PCT = 0.01  # 1 unit = 1% of bankroll
    
    USD_TO_SEK = 10.8  # Conversion rate
    
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
    
    def get_dynamic_stake(self) -> float:
        """Calculate dynamic stake: 1.2% of current bankroll."""
        bankroll = self.get_current_bankroll()
        return bankroll * self.STAKE_PCT
    
    def get_exact_score_stake(self) -> float:
        """Fixed exact score stake: $5.5 USD = 59 SEK."""
        return 59.0  # Fixed $5.5 USD stake as requested
    
    def get_stake_units(self) -> float:
        """Get number of units per bet (1.2u = 1.2% / 1%)."""
        return self.STAKE_PCT / self.BASE_UNIT_PCT  # Always 1.2
    
    def get_unit_value(self) -> float:
        """Get value of 1 unit in SEK (1% of bankroll)."""
        bankroll = self.get_current_bankroll()
        return bankroll * self.BASE_UNIT_PCT
    
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
        """Get total stakes placed today across ALL bet tables."""
        total = 0.0
        with self.engine.connect() as conn:
            queries = [
                "SELECT COALESCE(SUM(stake), 0) FROM football_opportunities WHERE DATE(created_at) = CURRENT_DATE",
                "SELECT COALESCE(SUM(stake), 0) FROM sgp_predictions WHERE DATE(created_at) = CURRENT_DATE",
                "SELECT COALESCE(SUM(stake), 0) FROM ml_parlay_predictions WHERE DATE(timestamp) = CURRENT_DATE",
                "SELECT COALESCE(SUM(CASE WHEN bet_placed THEN 160 ELSE 0 END), 0) FROM basketball_predictions WHERE DATE(created_at) = CURRENT_DATE",
            ]
            for q in queries:
                try:
                    result = conn.execute(text(q))
                    row = result.fetchone()
                    total += float(row[0]) if row and row[0] else 0
                except:
                    pass
        return total
    
    def get_today_stake_breakdown(self) -> dict:
        """Get breakdown of today's stakes by product type."""
        breakdown = {
            'value_singles': 0.0,
            'parlays': 0.0, 
            'ml_parlays': 0.0,
            'basketball': 0.0,
            'total': 0.0
        }
        with self.engine.connect() as conn:
            try:
                result = conn.execute(text("SELECT COALESCE(SUM(stake), 0) FROM football_opportunities WHERE DATE(created_at) = CURRENT_DATE"))
                breakdown['value_singles'] = float(result.fetchone()[0] or 0)
            except: pass
            try:
                result = conn.execute(text("SELECT COALESCE(SUM(stake), 0) FROM sgp_predictions WHERE DATE(created_at) = CURRENT_DATE"))
                breakdown['parlays'] = float(result.fetchone()[0] or 0)
            except: pass
            try:
                result = conn.execute(text("SELECT COALESCE(SUM(stake), 0) FROM ml_parlay_predictions WHERE DATE(timestamp) = CURRENT_DATE"))
                breakdown['ml_parlays'] = float(result.fetchone()[0] or 0)
            except: pass
            try:
                result = conn.execute(text("SELECT COALESCE(SUM(CASE WHEN bet_placed THEN 160 ELSE 0 END), 0) FROM basketball_predictions WHERE DATE(created_at) = CURRENT_DATE"))
                breakdown['basketball'] = float(result.fetchone()[0] or 0)
            except: pass
        breakdown['total'] = sum([breakdown['value_singles'], breakdown['parlays'], breakdown['ml_parlays'], breakdown['basketball']])
        return breakdown
    
    def get_today_profit_loss(self) -> float:
        """Get today's total profit/loss from settled bets."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COALESCE(SUM(profit_loss), 0) as today_pl
                FROM bets
                WHERE DATE(created_at) = CURRENT_DATE
                  AND LOWER(outcome) IN ('won', 'win', 'lost', 'loss')
            """))
            row = result.fetchone()
            today_pl = float(row[0]) if row else 0
        
        return today_pl
    
    def is_daily_loss_limit_reached(self) -> Tuple[bool, float, float]:
        """
        Check if daily loss limit (20% of bankroll) has been reached.
        
        Returns:
            (limit_reached: bool, current_loss: float, limit_amount: float)
        """
        bankroll = self.get_current_bankroll()
        loss_limit = bankroll * self.DAILY_LOSS_LIMIT_PCT
        today_pl = self.get_today_profit_loss()
        
        if today_pl < 0 and abs(today_pl) >= loss_limit:
            return True, abs(today_pl), loss_limit
        
        return False, abs(min(0, today_pl)), loss_limit
    
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
        if stake is None:
            stake = self.get_dynamic_stake()
        
        limit_reached, current_loss, limit_amount = self.is_daily_loss_limit_reached()
        if limit_reached:
            return False, f"Daily loss limit reached: -{current_loss:.0f} SEK (limit: {limit_amount:.0f} SEK). No more bets today."
        
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
        if stake is None:
            stake = self.get_dynamic_stake()
        
        can_place, reason = self.can_place_bet(stake)
        
        if can_place:
            return True, stake, "Stake reserved"
        
        if "Daily loss limit reached" in reason:
            return False, 0, reason
        
        available = min(self.get_available_funds(), self.get_remaining_daily_budget())
        min_stake = self.get_current_bankroll() * 0.005  # Min 0.5% of bankroll
        
        if available >= min_stake:
            return True, available, f"Reduced stake to {available:.0f} SEK due to limits"
        
        return False, 0, reason
    
    def get_stake_info(self) -> Dict:
        """Get complete stake information for display."""
        bankroll = self.get_current_bankroll()
        stake_sek = self.get_dynamic_stake()
        stake_usd = stake_sek / self.USD_TO_SEK
        units = self.get_stake_units()
        unit_value_sek = self.get_unit_value()
        unit_value_usd = unit_value_sek / self.USD_TO_SEK
        
        return {
            "bankroll_sek": bankroll,
            "bankroll_usd": bankroll / self.USD_TO_SEK,
            "stake_sek": stake_sek,
            "stake_usd": stake_usd,
            "units": units,
            "unit_value_sek": unit_value_sek,
            "unit_value_usd": unit_value_usd,
            "stake_pct": self.STAKE_PCT * 100,
            "display_text": f"${stake_usd:.0f} ({units:.1f}u)"
        }
    
    def get_status(self) -> dict:
        """Get full bankroll status report."""
        bankroll = self.get_current_bankroll()
        pending = self.get_pending_exposure()
        available = self.get_available_funds()
        today_exposure = self.get_today_exposure()
        max_daily = self.get_max_daily_exposure()
        daily_remaining = self.get_remaining_daily_budget()
        today_pl = self.get_today_profit_loss()
        limit_reached, current_loss, loss_limit = self.is_daily_loss_limit_reached()
        stake_info = self.get_stake_info()
        
        return {
            "starting_bankroll": self.STARTING_BANKROLL,
            "current_bankroll": bankroll,
            "bankroll_usd": bankroll / self.USD_TO_SEK,
            "total_profit": bankroll - self.STARTING_BANKROLL,
            "pending_exposure": pending,
            "available_funds": available,
            "today_exposure": today_exposure,
            "max_daily_exposure": max_daily,
            "daily_remaining": daily_remaining,
            "exposure_pct": (pending / bankroll * 100) if bankroll > 0 else 0,
            "today_pct": (today_exposure / max_daily * 100) if max_daily > 0 else 0,
            "today_profit_loss": today_pl,
            "daily_loss_limit": loss_limit,
            "daily_loss_limit_reached": limit_reached,
            "dynamic_stake_sek": stake_info["stake_sek"],
            "dynamic_stake_usd": stake_info["stake_usd"],
            "stake_units": stake_info["units"],
            "stake_display": stake_info["display_text"],
        }
    
    def print_status(self):
        """Print formatted bankroll status."""
        status = self.get_status()
        print("\n" + "="*60)
        print("💰 BANKROLL STATUS")
        print("="*60)
        print(f"Starting Bankroll:  {status['starting_bankroll']:,.0f} SEK (${status['starting_bankroll']/self.USD_TO_SEK:,.0f} USD)")
        print(f"Current Bankroll:   {status['current_bankroll']:,.0f} SEK (${status['bankroll_usd']:,.0f} USD)")
        print(f"Total Profit:       {status['total_profit']:+,.0f} SEK")
        print("-"*60)
        print(f"📊 DYNAMIC STAKE (1.2% of bankroll):")
        print(f"   Stake per bet:   {status['dynamic_stake_sek']:.0f} SEK (${status['dynamic_stake_usd']:.0f} USD)")
        print(f"   Units per bet:   {status['stake_units']:.1f}u")
        print(f"   Display:         {status['stake_display']}")
        print("-"*60)
        print(f"Pending Exposure:   {status['pending_exposure']:,.0f} SEK ({status['exposure_pct']:.1f}%)")
        print(f"Available Funds:    {status['available_funds']:,.0f} SEK")
        print("-"*60)
        breakdown = self.get_today_stake_breakdown()
        print(f"📅 TODAY'S STAKING (1.6% Kelly):")
        print(f"   Value Singles:     {breakdown['value_singles']:,.0f} SEK")
        print(f"   Multi-Match:       {breakdown['parlays']:,.0f} SEK")
        print(f"   ML Parlays:        {breakdown['ml_parlays']:,.0f} SEK")
        print(f"   Basketball:        {breakdown['basketball']:,.0f} SEK")
        print(f"   ─────────────────────────────")
        print(f"   TOTAL STAKED:      {breakdown['total']:,.0f} SEK (${breakdown['total']/self.USD_TO_SEK:,.0f} USD)")
        print(f"   Today's P/L:       {status['today_profit_loss']:+,.0f} SEK")
        print(f"   Daily Loss Limit:  {status['daily_loss_limit']:,.0f} SEK (20% of bankroll)")
        if status['daily_loss_limit_reached']:
            print(f"   ⛔ DAILY LOSS LIMIT REACHED - NO MORE BETS TODAY")
        print("-"*60)
        print(f"Max Daily Limit:    {status['max_daily_exposure']:,.0f} SEK")
        print(f"Daily Remaining:    {status['daily_remaining']:,.0f} SEK ({status['today_pct']:.1f}% used)")
        print("="*60 + "\n")


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
    
    stake = manager.get_dynamic_stake()
    can_bet, reason = manager.can_place_bet(stake)
    print(f"Dynamic stake: {stake:.0f} SEK ({manager.get_stake_units():.1f}u)")
    print(f"Can place bet: {can_bet} - {reason}")
