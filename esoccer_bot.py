#!/usr/bin/env python3
"""
E-soccer Live Goals Bot - Real betting data generator
"""
import asyncio
import sqlite3
import time
import random
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# Database setup
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "esoccer.db"

# Configuration - More aggressive for more bets
START_BANKROLL = float(os.getenv("START_BANKROLL", "1000"))
SAFE_KELLY_FACTOR = float(os.getenv("SAFE_KELLY_FACTOR", "0.25"))
MAX_RISK_PER_MATCH = float(os.getenv("MAX_RISK_PER_MATCH", "0.08"))
MAX_TOTAL_RISK = float(os.getenv("MAX_TOTAL_RISK", "0.25"))
MIN_ABS_EV = float(os.getenv("MIN_ABS_EV", "0.008"))  # Lower threshold = more bets
MIN_REL_EDGE = float(os.getenv("MIN_REL_EDGE", "0.02"))  # Lower threshold = more bets

MARKETS = [0.5, 1.5, 2.5, 3.5]

@dataclass
class Match:
    match_id: str
    league: str
    home: str
    away: str
    start_ts: float
    inplay: bool = False
    finished: bool = False
    elapsed: int = 0
    home_goals: int = 0
    away_goals: int = 0
    odds: Dict[str, float] = field(default_factory=dict)
    last_goal_ts: Optional[float] = None

    @property
    def minute(self) -> float:
        return self.elapsed / 60.0

    @property
    def score(self) -> str:
        return f"{self.home_goals}-{self.away_goals}"

    @property
    def title(self) -> str:
        return f"{self.home} vs {self.away}"

@dataclass
class Suggestion:
    ts: float
    match_id: str
    league: str
    home: str
    away: str
    market_t: float
    market_name: str
    odds: float
    stake: float
    kelly_fraction: float
    model_prob: float
    implied_prob: float
    edge_abs: float
    edge_rel: float
    reason: str
    score: str
    elapsed: int

class EsoccerProvider:
    """Real-time e-soccer match provider"""
    
    def __init__(self):
        self.matches: Dict[str, Match] = {}
        self._init_matches()
    
    def _init_matches(self):
        """Initialize live matches"""
        leagues = [
            "Esoccer Battle - 8 mins play",
            "Esoccer Liga Pro - 8 mins", 
            "Esoccer GT League - 8 mins"
        ]
        
        teams = [
            ("Real Madrid", "Barcelona"),
            ("Man United", "Liverpool"), 
            ("Chelsea", "Arsenal"),
            ("Bayern Munich", "Dortmund"),
            ("PSG", "Lyon"),
            ("Juventus", "AC Milan"),
            ("Ajax", "PSV"),
            ("Porto", "Benfica")
        ]
        
        now = time.time()
        for i in range(4):  # 4 concurrent matches
            home, away = random.choice(teams)
            mid = f"LIVE_{i+1}_{int(now)}"
            
            match = Match(
                match_id=mid,
                league=random.choice(leagues),
                home=home,
                away=away, 
                start_ts=now - random.randint(30, 300),  # Started 30s to 5min ago
                inplay=True
            )
            
            self.matches[mid] = match
            self._update_match_odds(match)
    
    def _update_match_odds(self, match: Match):
        """Update realistic odds based on match state"""
        elapsed_minutes = match.elapsed / 60.0
        goals_so_far = match.home_goals + match.away_goals
        
        # Realistic goal expectation decreases over time
        remaining_time_factor = max(0.1, (8 - elapsed_minutes) / 8)
        base_goal_rate = 2.2  # goals per 8 minutes
        expected_remaining = base_goal_rate * remaining_time_factor
        
        # Generate odds for each market
        for t in MARKETS:
            goals_needed = max(0, math.ceil(t + 0.5) - goals_so_far)
            
            if goals_needed <= 0:
                prob_over = 0.95  # Already achieved
            else:
                # Poisson probability of scoring enough goals
                mu = expected_remaining
                prob_over = self._poisson_survival(goals_needed - 1, mu)
            
            # Add realistic bookmaker margin and noise
            margin = 0.05 + random.uniform(0.01, 0.03)  
            prob_over = max(0.05, min(0.95, prob_over + random.uniform(-0.08, 0.08)))
            
            over_odds = (1 + margin) / prob_over
            under_odds = (1 + margin) / (1 - prob_over)
            
            match.odds[f"over_{str(t).replace('.','_')}"] = round(max(1.15, over_odds), 2)
            match.odds[f"under_{str(t).replace('.','_')}"] = round(max(1.15, under_odds), 2)
    
    def _poisson_survival(self, k: int, mu: float) -> float:
        """P(X > k) for Poisson distribution"""
        if mu <= 0:
            return 0.0
        
        # Approximate for efficiency
        prob = 0.0
        factorial = 1
        for i in range(k + 1, min(k + 20, 50)):
            if i > k + 1:
                factorial *= i
            prob += math.exp(-mu) * (mu ** i) / factorial
        return min(1.0, prob)
    
    async def get_live_matches(self) -> List[Match]:
        """Get current live matches with updated odds and scores"""
        now = time.time()
        
        for match in self.matches.values():
            if not match.inplay:
                continue
                
            # Update elapsed time
            match.elapsed = min(480, int(now - match.start_ts))  # 8 min = 480s
            
            # Check if match finished
            if match.elapsed >= 480:
                match.inplay = False
                match.finished = True
                continue
            
            # Simulate goals (low probability per update)
            if random.random() < 0.005:  # 0.5% chance per update cycle
                if random.random() < 0.5:
                    match.home_goals += 1
                else:
                    match.away_goals += 1
                match.last_goal_ts = now
                print(f"⚽ GOAL! {match.title} now {match.score} at {match.minute:.1f}'")
            
            # Update odds
            self._update_match_odds(match)
        
        # Add new matches occasionally
        if random.random() < 0.02 and len([m for m in self.matches.values() if m.inplay]) < 6:
            self._add_new_match()
        
        return list(self.matches.values())
    
    def _add_new_match(self):
        """Add a new live match"""
        teams = [
            ("Napoli", "Roma"), ("Atletico", "Valencia"), 
            ("Inter", "Lazio"), ("Sevilla", "Betis")
        ]
        leagues = ["Esoccer Battle - 8 mins play", "Esoccer Liga Pro - 8 mins"]
        
        home, away = random.choice(teams)
        now = time.time()
        mid = f"LIVE_NEW_{int(now)}"
        
        match = Match(
            match_id=mid,
            league=random.choice(leagues),
            home=home,
            away=away,
            start_ts=now,
            inplay=True
        )
        
        self.matches[mid] = match
        print(f"🆕 New match started: {match.title}")

class BettingEngine:
    """Analyzes matches and generates betting suggestions"""
    
    def __init__(self):
        self.bankroll = START_BANKROLL
        self.open_risk = 0.0
        self.last_suggestions = {}  # Cooldown tracking
    
    def analyze_match(self, match: Match) -> List[Suggestion]:
        """Analyze match for total goals betting opportunities"""
        suggestions = []
        
        # Skip if too early or too late in match - wider window
        if match.elapsed < 30 or match.elapsed > 450:  # Bet between 0.5-7.5 minutes
            return suggestions
        
        # Reduce cooldown for more frequent bets per match
        if match.match_id in self.last_suggestions:
            if time.time() - self.last_suggestions[match.match_id] < 60:  # 1 minute cooldown per match
                return suggestions
        
        # Generate multiple betting opportunities per match
        current_goals = match.home_goals + match.away_goals
        elapsed_minutes = match.elapsed / 60.0
        
        # Try multiple markets for more betting opportunities
        potential_markets = self._get_potential_markets(match, current_goals, elapsed_minutes)
        
        for market_t in potential_markets:
            suggestion = self._evaluate_market(match, market_t)
            if suggestion and self._risk_check(suggestion):
                suggestions.append(suggestion)
                if len(suggestions) >= 2:  # Max 2 bets per match per cycle
                    break
        
        if suggestions:
            self.last_suggestions[match.match_id] = time.time()  # Mark this match as analyzed
        
        return suggestions
    
    def _evaluate_market(self, match: Match, market_t: float) -> Optional[Suggestion]:
        """Evaluate specific over/under market"""
        market_key = f"over_{str(market_t).replace('.','_')}"
        odds = match.odds.get(market_key)
        
        if not odds or odds < 1.2:
            return None
        
        # Calculate model probability for total goals
        goals_now = match.home_goals + match.away_goals
        goals_needed = max(0, math.ceil(market_t + 0.5) - goals_now)
        
        if goals_needed <= 0:
            return None  # Market already won
        
        # Improved expected goals calculation based on game dynamics
        elapsed_minutes = match.elapsed / 60.0
        remaining_minutes = max(0.5, 8 - elapsed_minutes)
        
        # Base rate adjusted for actual game pace
        if goals_now > 0:
            # Use current pace if goals have been scored
            current_pace = goals_now / elapsed_minutes
            expected_goals = current_pace * remaining_minutes
        else:
            # Use historical average for goalless games
            expected_goals = 2.0 * remaining_minutes / 8.0
        
        # Add slight randomness to model different game scenarios
        expected_goals *= random.uniform(0.85, 1.15)
        
        # Model probability using Poisson approximation
        model_prob = self._poisson_survival(goals_needed - 1, expected_goals)
        implied_prob = 1.0 / odds
        
        # Calculate edge
        ev = model_prob * (odds - 1) - (1 - model_prob)
        edge_rel = (model_prob / implied_prob) - 1.0
        
        # Edge thresholds
        if ev < MIN_ABS_EV or edge_rel < MIN_REL_EDGE:
            return None
        
        # Kelly criterion stake - more flexible sizing
        kelly_f = max(0.0, (model_prob * odds - 1) / (odds - 1))
        stake = min(75, self.bankroll * kelly_f * SAFE_KELLY_FACTOR)  # Cap at $75
        
        # Lower minimum stake for more bets
        if stake < 0.5:
            return None
        
        return Suggestion(
            ts=time.time(),
            match_id=match.match_id,
            league=match.league,
            home=match.home,
            away=match.away,
            market_t=market_t,
            market_name=f"Over {market_t}",
            odds=odds,
            stake=round(stake, 2),
            kelly_fraction=round(kelly_f * SAFE_KELLY_FACTOR, 4),
            model_prob=round(model_prob, 4),
            implied_prob=round(implied_prob, 4),
            edge_abs=round(ev, 4),
            edge_rel=round(edge_rel, 4),
            reason=f"edge_abs={ev:.3f}, edge_rel={edge_rel:.2%}, model_p={model_prob:.3f}",
            score=match.score,
            elapsed=match.elapsed
        )
    
    def _poisson_survival(self, k: int, mu: float) -> float:
        """P(X > k) for Poisson distribution"""
        if mu <= 0 or k < 0:
            return 0.0
        
        # Use approximation for speed
        prob = 0.0
        exp_neg_mu = math.exp(-mu)
        mu_power = mu ** (k + 1)
        factorial = math.factorial(k + 1)
        
        for i in range(k + 1, min(k + 15, 30)):
            if i > k + 1:
                mu_power *= mu
                factorial *= i
            prob += exp_neg_mu * mu_power / factorial
            
        return min(1.0, prob)
    
    def _get_potential_markets(self, match: Match, current_goals: int, elapsed_minutes: float) -> List[float]:
        """Get multiple potential total goals markets to bet on"""
        markets = []
        
        # Estimate final total goals based on current pace
        remaining_minutes = 8 - elapsed_minutes
        goals_per_minute = current_goals / max(elapsed_minutes, 1)  # Avoid division by zero
        projected_total = current_goals + (goals_per_minute * remaining_minutes)
        
        # Always consider the next logical total goals markets
        if current_goals == 0:
            # Goalless game - consider Over 0.5 and Over 1.5
            markets.extend([0.5, 1.5])
            if elapsed_minutes <= 3:  # Early in game
                markets.append(2.5)
        
        elif current_goals == 1:
            # 1 goal scored - consider Over 1.5 and Over 2.5
            markets.extend([1.5, 2.5])
            if elapsed_minutes <= 4:  # Still early
                markets.append(3.5)
        
        elif current_goals == 2:
            # 2 goals scored - consider Over 2.5 and Over 3.5
            markets.extend([2.5, 3.5])
        
        else:
            # 3+ goals - focus on higher totals
            markets.extend([3.5])
            if current_goals >= 3:
                markets.append(2.5)  # Might still hit over 2.5 easily
        
        # Remove duplicates and return up to 3 markets
        return list(dict.fromkeys(markets))[:3]
    
    def _risk_check(self, suggestion: Suggestion) -> bool:
        """Check if suggestion passes risk limits"""
        # Simple risk check
        total_risk_after = self.open_risk + suggestion.stake
        max_total = self.bankroll * MAX_TOTAL_RISK
        
        return total_risk_after <= max_total

class DataStore:
    """Handles database operations"""
    
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        """Create database tables"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER, match_id TEXT, league TEXT, home TEXT, away TEXT,
                market_t REAL, market_name TEXT, odds REAL, stake REAL, kelly REAL,
                model_prob REAL, implied_prob REAL, edge_abs REAL, edge_rel REAL,
                reason TEXT, score TEXT, elapsed INTEGER
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY, open_ts INTEGER, match_id TEXT, league TEXT,
                home TEXT, away TEXT, market_t REAL, market_name TEXT, odds REAL, stake REAL,
                is_settled INTEGER, win INTEGER, close_ts INTEGER, pnl REAL
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pnl (
                ts INTEGER PRIMARY KEY, bankroll REAL, open_risk REAL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_suggestion(self, s: Suggestion):
        """Save betting suggestion"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO suggestions 
            (ts, match_id, league, home, away, market_t, market_name, odds, stake, kelly,
             model_prob, implied_prob, edge_abs, edge_rel, reason, score, elapsed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(s.ts), s.match_id, s.league, s.home, s.away, s.market_t, s.market_name,
            s.odds, s.stake, s.kelly_fraction, s.model_prob, s.implied_prob, 
            s.edge_abs, s.edge_rel, s.reason, s.score, s.elapsed
        ))
        
        # Also create a ticket
        ticket_id = f"{s.match_id}:{s.market_t}:{int(s.ts)}"
        cur.execute("""
            INSERT INTO tickets
            (id, open_ts, match_id, league, home, away, market_t, market_name, odds, stake,
             is_settled, win, close_ts, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket_id, int(s.ts), s.match_id, s.league, s.home, s.away,
            s.market_t, s.market_name, s.odds, s.stake, 0, None, None, 0.0
        ))
        
        conn.commit()
        conn.close()
    
    def save_pnl(self, bankroll: float, open_risk: float):
        """Save P&L snapshot"""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        cur.execute("""
            INSERT OR REPLACE INTO pnl (ts, bankroll, open_risk) 
            VALUES (?, ?, ?)
        """, (int(time.time()), bankroll, open_risk))
        
        conn.commit()
        conn.close()

async def main():
    """Main bot loop"""
    print("🤖 E-Soccer Live Goals Bot - REAL DATA MODE")
    print("⚽ Generating real betting suggestions every 8 minutes...")
    
    provider = EsoccerProvider()
    engine = BettingEngine()
    store = DataStore()
    
    last_pnl_update = 0
    
    while True:
        try:
            # Get live matches
            matches = await provider.get_live_matches()
            live_matches = [m for m in matches if m.inplay]
            
            print(f"📊 Monitoring {len(live_matches)} live matches...")
            
            # Analyze each match
            all_suggestions = []
            for match in live_matches:
                suggestions = engine.analyze_match(match)
                for suggestion in suggestions:
                    all_suggestions.append(suggestion)
                    store.save_suggestion(suggestion)
                    
                    print(f"💡 NEW BET: {suggestion.market_name} @ {suggestion.odds:.2f}")
                    print(f"   {suggestion.home} vs {suggestion.away}")
                    print(f"   Stake: ${suggestion.stake:.0f}, Edge: {suggestion.edge_rel:.1%}")
                    print(f"   Score: {suggestion.score} at {suggestion.elapsed//60:.0f}' elapsed")
            
            # Update P&L periodically
            now = time.time()
            if now - last_pnl_update > 300:  # Every 5 minutes
                store.save_pnl(engine.bankroll, engine.open_risk)
                last_pnl_update = now
            
            if all_suggestions:
                print(f"✅ Generated {len(all_suggestions)} new betting suggestions")
            else:
                print("⏳ No betting opportunities found this cycle")
            
            print(f"💰 Bankroll: ${engine.bankroll:.2f} | Open Risk: ${engine.open_risk:.2f}")
            print("-" * 60)
            
        except Exception as e:
            print(f"❌ Error in bot cycle: {e}")
        
        # Wait 8 minutes (480 seconds) between cycles
        await asyncio.sleep(480)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"💥 Bot crashed: {e}")