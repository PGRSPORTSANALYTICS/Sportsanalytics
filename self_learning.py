#!/usr/bin/env python3
"""
Self-Learning AI Components for E-Soccer Betting Bot

This module implements advanced machine learning capabilities:
- Online Platt-style calibration that learns from bet results
- Player-specific goal rate learning with Laplace smoothing  
- Dynamic Kelly sizing based on calibration quality
- EWMA momentum smoothing for odds noise reduction
- Gamma priors + market calibration for advanced modeling
"""

import math
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, List

# Define Match class locally to avoid circular import
from dataclasses import dataclass, field
from typing import Dict

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

DB_PATH = Path("data/esoccer.db")

def poisson_pmf(k: int, mu: float) -> float:
    """Poisson probability mass function"""
    if mu <= 0:
        return 0.0 if k > 0 else 1.0
    return math.exp(-mu) * (mu ** k) / math.factorial(k)

def poisson_cdf(k: int, mu: float) -> float:
    """Poisson cumulative distribution function"""
    s = 0.0
    for i in range(max(0, k) + 1):
        s += poisson_pmf(i, mu)
    return min(1.0, s)

def poisson_sf(k: int, mu: float) -> float:
    """Poisson survival function P(X > k)"""
    return max(0.0, 1.0 - poisson_cdf(k, mu))

def invert_poisson_tail_for_mu(n_needed: int, target_prob: float, mu_low=1e-6, mu_high=20.0) -> float:
    """Find mu where P(X >= n_needed) ~= target_prob using bisection"""
    target_prob = min(max(target_prob, 1e-6), 1 - 1e-6)
    low, high = mu_low, mu_high
    for _ in range(40):
        mid = 0.5 * (low + high)
        p = poisson_sf(n_needed - 1, mid)
        if p > target_prob:
            high = mid
        else:
            low = mid
    return 0.5 * (low + high)

class EWMA:
    """Exponentially Weighted Moving Average for smoothing noisy odds"""
    def __init__(self, alpha: float = 0.4):
        self.alpha = alpha
        self.v: Optional[float] = None
        
    def update(self, x: float) -> float:
        if x is None:
            return self.v if self.v is not None else 0.0
        if self.v is None:
            self.v = x
        else:
            self.v = self.alpha * x + (1 - self.alpha) * self.v
        return self.v

class Calibrator:
    """Online Platt-style calibration on model probabilities.
    
    Uses logistic calibration: z = logit(p_model); z' = a*z + b → p_adj = sigmoid(z')
    Updates by SGD on log-loss when tickets settle (win/loss known).
    """
    
    def __init__(self, db_path: Path = DB_PATH, lr: float = 0.05, decay: float = 0.999):
        self.db_path = db_path
        self.a = 1.0
        self.b = 0.0
        self.lr = lr
        self.decay = decay
        self.brier_ewm = 0.20  # Exponential weighted mean of Brier scores
        self._init_db()
        self._load()
    
    def _init_db(self):
        """Initialize calibration database tables"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        
        # Create calibration table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS calibration (
                id INTEGER PRIMARY KEY CHECK (id=1),
                a REAL, b REAL, brier REAL, updated INTEGER
            )
        """)
        
        # Create training data table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS training_data (
                ts INTEGER, market_t REAL, elapsed INTEGER, goals_now INTEGER,
                odds REAL, p_implied REAL, p_model REAL, outcome INTEGER
            )
        """)
        
        con.commit()
        con.close()
    
    def _load(self):
        """Load calibration parameters from database"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        row = cur.execute("SELECT a, b, brier FROM calibration WHERE id=1").fetchone()
        con.close()
        if row:
            self.a, self.b, self.brier_ewm = map(float, row)
    
    @staticmethod
    def _sigmoid(x: float) -> float:
        """Sigmoid function with overflow protection"""
        return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))
    
    @staticmethod
    def _logit(p: float) -> float:
        """Logit function with boundary protection"""
        p = min(max(p, 1e-6), 1 - 1e-6)
        return math.log(p / (1 - p))
    
    def adjust(self, p_model: float) -> float:
        """Apply calibration to model probability"""
        z = self._logit(p_model)
        z2 = self.a * z + self.b
        return self._sigmoid(z2)
    
    def update(self, ts: int, market_t: float, elapsed: int, goals_now: int,
               odds: float, p_implied: float, p_model: float, outcome: int):
        """Update calibration parameters based on bet outcome"""
        # Save training example
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("INSERT INTO training_data VALUES (?,?,?,?,?,?,?,?)",
                    (int(ts), float(market_t), int(elapsed), int(goals_now), 
                     float(odds), float(p_implied), float(p_model), int(outcome)))
        con.commit()
        con.close()
        
        # Gradient step for calibration parameters
        z = self._logit(p_model)
        p_adjusted = self._sigmoid(self.a * z + self.b)
        error = (p_adjusted - outcome)
        
        # Gradients for a, b
        da = error * z
        db = error
        
        # Update with decayed learning rate
        self.lr *= self.decay
        self.a -= self.lr * da
        self.b -= self.lr * db
        
        # Update Brier score (measure of calibration quality)
        brier = (p_adjusted - outcome) ** 2
        self.brier_ewm = 0.95 * self.brier_ewm + 0.05 * brier
        
        # Persist to database
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO calibration (id,a,b,brier,updated) VALUES (1,?,?,?,?)",
                    (float(self.a), float(self.b), float(self.brier_ewm), int(time.time())))
        con.commit()
        con.close()

class PlayerModel:
    """Learns player-specific goal rates online with Laplace smoothing.
    
    Uses Bayesian updating: each player has a goal rate that gets updated
    as we observe their matches. Uses Laplace smoothing for robustness.
    """
    
    def __init__(self, db_path: Path = DB_PATH, mu0: float = 2.2, k: float = 8.0):
        self.db_path = db_path
        self.mu0 = mu0  # Prior mean goal rate
        self.k = k      # Prior strength (equivalent sample size)
        self._init_db()
    
    def _init_db(self):
        """Initialize player statistics database"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_learning (
                name TEXT PRIMARY KEY,
                matches INTEGER,
                total_goals REAL,
                updated INTEGER
            );
        """)
        con.commit()
        con.close()
    
    def _get_stats(self, name: str) -> Tuple[int, float]:
        """Get player's match count and total goals"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        row = cur.execute("SELECT matches, total_goals FROM player_learning WHERE name=?", 
                         (name,)).fetchone()
        con.close()
        if row:
            return int(row[0]), float(row[1])
        return 0, 0.0
    
    def _set_stats(self, name: str, matches: int, total_goals: float):
        """Update player's statistics"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO player_learning (name,matches,total_goals,updated) VALUES (?,?,?,?)",
                    (name, int(matches), float(total_goals), int(time.time())))
        con.commit()
        con.close()
    
    def update_from_match(self, home: str, away: str, total_goals: int):
        """Update both players' statistics from a completed match"""
        for player_name in (home, away):
            matches, goals = self._get_stats(player_name)
            self._set_stats(player_name, matches + 1, goals + total_goals)
    
    def get_goal_rate(self, name: str) -> float:
        """Get player's learned goal rate with Laplace smoothing"""
        matches, total_goals = self._get_stats(name)
        # Laplace smoothing: (observed + prior) / (count + prior_count)
        return (total_goals + self.k * self.mu0) / (max(1, matches) + self.k)
    
    def factor(self, home: str, away: str) -> float:
        """Get combined player factor relative to baseline"""
        home_rate = self.get_goal_rate(home)
        away_rate = self.get_goal_rate(away)
        combined_rate = (home_rate + away_rate) / 2.0
        return combined_rate / self.mu0

class HeadToHeadModel:
    """Tracks and learns from head-to-head matchup patterns.
    
    Stores historical results between specific team pairings to identify:
    - Teams that consistently have high/low scoring games against each other
    - Matchup-specific scoring tendencies 
    - Head-to-head win/loss patterns
    - Defensive vs offensive matchup styles
    """
    
    def __init__(self, db_path: Path = DB_PATH, alpha: float = 0.1):
        self.db_path = db_path
        self.alpha = alpha  # Learning rate for exponential smoothing
        self._init_db()
    
    def _init_db(self):
        """Initialize head-to-head database table"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS head_to_head (
                matchup TEXT PRIMARY KEY,
                matches INTEGER,
                total_goals REAL,
                home_wins INTEGER,
                away_wins INTEGER,
                draws INTEGER,
                avg_goals REAL,
                updated INTEGER
            )
        """)
        con.commit()
        con.close()
    
    def _get_matchup_key(self, home: str, away: str) -> str:
        """Create consistent matchup key (always alphabetical order)"""
        teams = sorted([home.strip(), away.strip()])
        return f"{teams[0]} vs {teams[1]}"
    
    def _get_h2h_stats(self, matchup_key: str) -> dict:
        """Get head-to-head statistics for a matchup"""
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        row = cur.execute("""
            SELECT matches, total_goals, home_wins, away_wins, draws, avg_goals 
            FROM head_to_head WHERE matchup=?
        """, (matchup_key,)).fetchone()
        con.close()
        
        if row:
            return {
                'matches': int(row[0]),
                'total_goals': float(row[1]),
                'home_wins': int(row[2]),
                'away_wins': int(row[3]),
                'draws': int(row[4]),
                'avg_goals': float(row[5])
            }
        return {'matches': 0, 'total_goals': 0.0, 'home_wins': 0, 'away_wins': 0, 'draws': 0, 'avg_goals': 2.2}
    
    def update_from_match(self, home: str, away: str, home_goals: int, away_goals: int):
        """Update H2H statistics from a completed match"""
        matchup_key = self._get_matchup_key(home, away)
        stats = self._get_h2h_stats(matchup_key)
        
        # Update match count and total goals
        new_matches = stats['matches'] + 1
        total_goals = home_goals + away_goals
        new_total_goals = stats['total_goals'] + total_goals
        
        # Update win/loss/draw counts
        if home_goals > away_goals:
            new_home_wins = stats['home_wins'] + 1
            new_away_wins = stats['away_wins']
            new_draws = stats['draws']
        elif away_goals > home_goals:
            new_home_wins = stats['home_wins']
            new_away_wins = stats['away_wins'] + 1
            new_draws = stats['draws']
        else:
            new_home_wins = stats['home_wins']
            new_away_wins = stats['away_wins']
            new_draws = stats['draws'] + 1
        
        # Calculate new exponentially smoothed average
        if stats['matches'] == 0:
            new_avg_goals = float(total_goals)
        else:
            new_avg_goals = (1 - self.alpha) * stats['avg_goals'] + self.alpha * total_goals
        
        # Store updated statistics
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO head_to_head 
            (matchup, matches, total_goals, home_wins, away_wins, draws, avg_goals, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (matchup_key, new_matches, new_total_goals, new_home_wins, 
              new_away_wins, new_draws, new_avg_goals, int(time.time())))
        con.commit()
        con.close()
    
    def get_h2h_factor(self, home: str, away: str) -> float:
        """Get head-to-head adjustment factor for expected goals"""
        matchup_key = self._get_matchup_key(home, away)
        stats = self._get_h2h_stats(matchup_key)
        
        if stats['matches'] < 3:  # Need at least 3 matches for reliable H2H data
            return 1.0  # No adjustment
        
        # Return ratio of H2H average to baseline (2.2 goals per match)
        baseline = 2.2
        confidence = min(1.0, stats['matches'] / 10.0)  # More confidence with more matches
        h2h_factor = stats['avg_goals'] / baseline
        
        # Weighted blend: more H2H weight as confidence increases
        return (1 - confidence) * 1.0 + confidence * h2h_factor
    
    def get_matchup_tendency(self, home: str, away: str) -> str:
        """Get human-readable description of matchup tendency"""
        factor = self.get_h2h_factor(home, away)
        stats = self._get_h2h_stats(self._get_matchup_key(home, away))
        
        if stats['matches'] < 3:
            return "No H2H history"
        
        if factor > 1.2:
            return f"High-scoring ({stats['avg_goals']:.1f} avg goals)"
        elif factor < 0.8:
            return f"Low-scoring ({stats['avg_goals']:.1f} avg goals)"
        else:
            return f"Typical scoring ({stats['avg_goals']:.1f} avg goals)"

class GoalModel:
    """Advanced goal model combining prior + market calibration.
    
    Features:
    - Gamma prior over total 8-min goals
    - Market-implied mu estimation from live odds
    - EWMA smoothing to reduce noise
    - Player-based scaling factors
    """
    
    def __init__(self, total_secs: int = 480, player_factor_fn=None, h2h_factor_fn=None):
        self.total_secs = total_secs
        # E-SOCCER REALISTIC: λ ~ Gamma(α, β) with mean = α/β ≈ 4.8 goals per 8 min
        self.alpha = 3.0
        self.beta = self.alpha / 4.8  # More conservative (6.5 was too optimistic)
        # EWMA smoothers per (match_id, odds_key)
        self.ewma: Dict[Tuple[str, str], EWMA] = {}
        # Optional player factor callback
        self.player_factor_fn = player_factor_fn
        # Optional head-to-head factor callback
        self.h2h_factor_fn = h2h_factor_fn
    
    def _smooth_odds(self, key: Tuple[str, str], odds: float) -> float:
        """Apply EWMA smoothing to reduce odds noise"""
        if key not in self.ewma:
            self.ewma[key] = EWMA(alpha=0.35)
        return self.ewma[key].update(odds)
    
    @staticmethod
    def needed_goals_for_over(target: float, goals_now: int) -> int:
        """Calculate goals needed to win over bet"""
        threshold = math.floor(target) + 1  # for .5 lines
        return max(0, threshold - goals_now)
    
    def market_implied_mu(self, match: Match, target: float) -> Optional[float]:
        """Extract market-implied expected goals from live odds"""
        over_key = f"over_{str(target).replace('.', '_')}"
        odds = match.odds.get(over_key)
        if not odds:
            return None
        
        # Smooth odds to reduce noise
        key = (match.match_id, over_key)
        smoothed_odds = self._smooth_odds(key, float(odds))
        
        # Convert to probability
        p_over = 1.0 / max(1.001, smoothed_odds)
        
        # De-margin using under odds if available
        under_key = f"under_{str(target).replace('.', '_')}"
        under_odds = match.odds.get(under_key)
        if under_odds and under_odds > 1.0:
            p_under = 1.0 / float(under_odds)
            overround = p_over + p_under
            if overround > 1.02:  # Remove bookmaker margin
                p_over = p_over / overround
        
        # Invert Poisson tail to find implied mu
        goals_now = match.home_goals + match.away_goals
        n_needed = self.needed_goals_for_over(target, goals_now)
        if n_needed <= 0:
            return 10.0  # Bet already won
        
        mu = invert_poisson_tail_for_mu(n_needed, p_over)
        return min(12.0, max(1e-4, mu))
    
    def prior_mu_remaining(self, match: Match) -> float:
        """Calculate prior expectation of remaining goals"""
        goals_now = match.home_goals + match.away_goals
        frac_elapsed = min(1.0, match.elapsed / self.total_secs)
        
        # Bayesian update of Gamma prior
        alpha_post = self.alpha + goals_now
        beta_post = self.beta + max(1e-6, frac_elapsed)
        lambda_total_post = alpha_post / beta_post
        
        # Expected goals in remaining time
        rem_frac = max(0.0, 1.0 - frac_elapsed)
        mu_prior = max(1e-6, lambda_total_post * rem_frac)
        
        # Apply player-specific scaling if available
        if self.player_factor_fn:
            try:
                player_factor = self.player_factor_fn(match)
                mu_prior *= max(0.5, min(1.5, float(player_factor)))
            except Exception:
                pass
        
        # Apply head-to-head scaling if available
        if self.h2h_factor_fn:
            try:
                h2h_factor = self.h2h_factor_fn(match)
                mu_prior *= max(0.6, min(1.4, float(h2h_factor)))  # Slightly less variance than player factor
            except Exception:
                pass
        
        return mu_prior
    
    def mu_remaining(self, match: Match, calibration_target: float = 1.5) -> float:
        """Combine prior and market-implied mu with adaptive weighting"""
        mu_prior = self.prior_mu_remaining(match)
        mu_market = self.market_implied_mu(match, calibration_target)
        
        if mu_market is None:
            return mu_prior
        
        # Weight market more heavily as match progresses
        time_weight = 0.35 + 0.6 * (match.elapsed / self.total_secs)
        
        # Simple momentum: if odds are shortening, trust market more
        over_key = f"over_{str(calibration_target).replace('.', '_')}"
        raw_odds = match.odds.get(over_key, 0)
        smoothed_odds = self._smooth_odds((match.match_id, over_key), float(raw_odds)) if raw_odds else 0
        
        momentum_weight = 0.1 if smoothed_odds > raw_odds else 0.2
        total_weight = min(0.95, max(0.2, time_weight + momentum_weight))
        
        return total_weight * mu_market + (1 - total_weight) * mu_prior
    
    def prob_over(self, match: Match, target: float, mu_remaining: Optional[float] = None) -> float:
        """Calculate probability of over bet winning"""
        goals_now = match.home_goals + match.away_goals
        n_needed = self.needed_goals_for_over(target, goals_now)
        
        if n_needed <= 0:
            return 1.0
        
        if mu_remaining is None:
            mu_remaining = self.mu_remaining(match, max(1.5, target))
        
        return poisson_sf(n_needed - 1, mu_remaining)

class SelfLearner:
    """Main integration class for all self-learning components"""
    
    def __init__(self, safe_kelly_base: float = 0.25):
        self.calibrator = Calibrator(DB_PATH)
        self.player_model = PlayerModel(DB_PATH)
        self.h2h_model = HeadToHeadModel(DB_PATH)
        self.goal_model = GoalModel(
            player_factor_fn=self._player_factor,
            h2h_factor_fn=self._h2h_factor
        )
        self.safe_kelly_base = safe_kelly_base
        self._kelly_multiplier = safe_kelly_base
    
    def _player_factor(self, match: Match) -> float:
        """Player factor callback for GoalModel"""
        try:
            return self.player_model.factor(match.home, match.away)
        except Exception:
            return 1.0
    
    def _h2h_factor(self, match: Match) -> float:
        """Head-to-head factor callback for GoalModel"""
        try:
            return self.h2h_model.get_h2h_factor(match.home, match.away)
        except Exception:
            return 1.0
    
    def get_dynamic_kelly(self) -> float:
        """Adaptive Kelly sizing based on calibration quality"""
        brier = self.calibrator.brier_ewm
        
        if brier > 0.24:  # Poor calibration → be conservative
            multiplier = self.safe_kelly_base * 0.6
        elif brier < 0.18:  # Good calibration → be more aggressive
            multiplier = self.safe_kelly_base * 1.25
        else:
            multiplier = self.safe_kelly_base
        
        self._kelly_multiplier = min(0.5, max(0.1, multiplier))
        return self._kelly_multiplier
    
    def get_calibrated_probability(self, match: Match, target: float) -> float:
        """Get calibrated probability for over bet"""
        raw_prob = self.goal_model.prob_over(match, target)
        return self.calibrator.adjust(raw_prob)
    
    def update_from_settlement(self, match: Match, target: float, won: bool):
        """Update all learning components when a bet settles"""
        # Update calibrator
        goals_now = match.home_goals + match.away_goals
        odds = match.odds.get(f"over_{str(target).replace('.', '_')}", 0)
        p_implied = 1.0 / odds if odds > 1 else 0
        p_model = self.goal_model.prob_over(match, target)
        
        self.calibrator.update(
            ts=int(time.time()),
            market_t=target,
            elapsed=match.elapsed,
            goals_now=goals_now,
            odds=odds,
            p_implied=p_implied,
            p_model=p_model,
            outcome=1 if won else 0
        )
        
        # Update player model and H2H model when match finishes
        if match.finished:
            total_goals = match.home_goals + match.away_goals
            self.player_model.update_from_match(match.home, match.away, total_goals)
            # Update head-to-head statistics with individual goal counts
            self.h2h_model.update_from_match(match.home, match.away, match.home_goals, match.away_goals)

    def import_historical_data(self, historical_matches: List[Dict]):
        """Import historical match data to pre-train learning models"""
        imported_count = 0
        
        print("📚 Importing historical data for AI learning...")
        
        for match_data in historical_matches:
            try:
                # Update player statistics
                home_player = match_data.get('home_player', match_data.get('home', ''))
                away_player = match_data.get('away_player', match_data.get('away', ''))
                total_goals = match_data['total_goals']
                home_goals = match_data['home_goals']
                away_goals = match_data['away_goals']
                
                # Clean player names (remove team prefix if present)
                if '(' in home_player and ')' in home_player:
                    home_player = home_player.split('(')[-1].replace(')', '')
                if '(' in away_player and ')' in away_player:
                    away_player = away_player.split('(')[-1].replace(')', '')
                
                # Update player learning model
                self.player_model.update_from_match(home_player, away_player, total_goals)
                
                # Update head-to-head learning model  
                self.h2h_model.update_from_match(home_player, away_player, home_goals, away_goals)
                
                imported_count += 1
                
            except Exception as e:
                print(f"⚠️ Error importing match {match_data.get('match_id', 'unknown')}: {e}")
                continue
        
        print(f"✅ Successfully imported {imported_count} historical matches")
        return imported_count
    
    def get_learning_stats(self) -> Dict:
        """Get current learning statistics for dashboard"""
        return {
            'calibration_a': self.calibrator.a,
            'calibration_b': self.calibrator.b,
            'brier_score': self.calibrator.brier_ewm,
            'kelly_multiplier': self._kelly_multiplier,
            'learning_quality': 'Excellent' if self.calibrator.brier_ewm < 0.18 
                               else 'Good' if self.calibrator.brier_ewm < 0.24 
                               else 'Learning'
        }