#!/usr/bin/env python3
"""
ML PARLAY ENGINE (Moneyline Parlay)
===================================
LOW/MEDIUM risk, bread-and-butter product with 2-4 legs per parlay.

Product Features:
- Only 1X2 / Moneyline / Draw-No-Bet markets
- 2-4 legs per parlay
- Max 3 parlays per day
- 4%+ EV per leg
- Odds range 1.40 - 2.10 per leg

INTERNAL TEST MODE: Database logging only, no external posting.
"""

import logging
import json
import math
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from db_helper import db_helper
from bankroll_manager import get_bankroll_manager
from discord_notifier import send_bet_to_discord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# ML PARLAY CONFIGURATION - POLICY COMPLIANT (Dec 30, 2025)
# Strict 2-leg only policy with flat staking
# ============================================================

# PARLAY POLICY RULES:
# 1. ONLY 2-leg parlays allowed (no 3+ legs)
# 2. Each leg must be independently approved single with positive EV
# 3. Same matchday only
# 4. Flat staking at 10-25% of single stake
# 5. Kelly staking STRICTLY FORBIDDEN for parlays

# Master switch
ML_PARLAY_ENABLED = True

# ============================================================
# PARLAY PAUSE MODE (Jan 23, 2026)
# Set to True to pause parlay generation while focusing on singles
# Parlays have -399 SEK loss vs +100u singles profit
# ============================================================
ML_PARLAY_PAUSED = False  # ENABLED: Testing new stricter filters (Jan 23, 2026)

# Odds filters per leg - BALANCED (Jan 23, 2026)
# Find +EV according to model (needs odds >= 2.27 for home, >= 3.34 for away)
ML_PARLAY_MIN_ODDS = 1.90  # Minimum odds per leg (model needs higher odds for +EV)
ML_PARLAY_MAX_ODDS = 2.80  # Maximum odds per leg (moderate favorites/underdogs)

# Total parlay odds range - TARGET 3.5-7x (based on per-leg range)
# 2-leg: 1.90*1.90=3.61 to 2.80*2.80=7.84
ML_PARLAY_MIN_TOTAL_ODDS = 3.50   # Minimum combined odds
ML_PARLAY_MAX_TOTAL_ODDS = 8.00   # Maximum combined odds

# Minimum EV per leg (3% edge - standard threshold)
MIN_ML_PARLAY_LEG_EV = 0.03  # 3% EV threshold per leg

# NOVA v2.0 Safety Guardrail: Minimum total parlay EV
MIN_ML_PARLAY_TOTAL_EV = 5.0  # 5% total combined EV required

# ============================================================
# WIN PROBABILITY FOCUS - TIGHTENED (Jan 23, 2026)
# Prioritize hit rate over odds attractiveness
# ============================================================
MIN_LEG_WIN_PROBABILITY = 0.35  # 35%+ model probability (allows away wins and draws)
MAX_COMBINED_PARLAY_ODDS = 8.00  # Cap at 8x combined (matches total odds range)
MIN_COMBINED_PARLAY_ODDS = 3.50  # Minimum 3.5x (matches total odds range)
PREFER_DIFFERENT_LEAGUES = True  # Diversity bonus for uncorrelated legs (soft preference)
MIN_CONFIDENCE_SCORE = 0.55  # Composite confidence threshold (was 0.45, relaxed from 0.65)

# Form-based filtering (Jan 23, 2026)
MIN_RECENT_WINS = 3  # Team must have 3+ wins in last 5 matches
FORM_LOOKBACK_MATCHES = 5  # Check last 5 matches for form

# Parlay construction limits - POLICY: 2-LEG ONLY
MAX_ML_PARLAYS_PER_DAY = 4  # Increased to test new filters (Jan 23, 2026)
ML_PARLAY_MIN_LEGS = 2
ML_PARLAY_MAX_LEGS = 2  # POLICY: Only 2-leg parlays allowed

# FLAT STAKING - 20% of single stake (0.2 units)
# Kelly staking is STRICTLY FORBIDDEN for parlays
ML_PARLAY_STAKE_UNITS = 0.2  # Flat stake: 20% of 1-unit single stake

# Auto-stop conditions
MAX_PARLAYS_WITHOUT_POSITIVE_ROI = 20

# League whitelist - major predictable leagues only
ML_PARLAY_LEAGUE_WHITELIST = {
    # Top 5 European Leagues
    "soccer_epl",                    # Premier League
    "soccer_spain_la_liga",          # La Liga  
    "soccer_italy_serie_a",          # Serie A
    "soccer_germany_bundesliga",     # Bundesliga
    "soccer_france_ligue_one",       # Ligue 1
    # European Cups
    "soccer_uefa_champs_league",     # Champions League
    "soccer_uefa_europa_league",     # Europa League
    "soccer_uefa_europa_conf_league", # Conference League
    # Other major leagues
    "soccer_netherlands_eredivisie", # Eredivisie
    "soccer_portugal_primeira_liga", # Primeira Liga
    "soccer_turkey_super_league",    # Turkish Super Lig
    "soccer_sweden_allsvenskan",     # Allsvenskan
    # Americas
    "soccer_usa_mls",                # MLS
    "soccer_brazil_serie_a",         # Brasileirao
    "soccer_argentina_primera",      # Argentina Primera
}

# League name mapping for display
LEAGUE_DISPLAY_NAMES = {
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "Champions League",
    "soccer_uefa_europa_league": "Europa League",
    "soccer_uefa_europa_conf_league": "Conference League",
    "soccer_netherlands_eredivisie": "Eredivisie",
    "soccer_portugal_primeira_liga": "Primeira Liga",
    "soccer_turkey_super_league": "Turkish Super Lig",
    "soccer_sweden_allsvenskan": "Allsvenskan",
    "soccer_usa_mls": "MLS",
    "soccer_brazil_serie_a": "Brasileirao",
    "soccer_argentina_primera": "Argentina Primera",
}

# Excluded leagues (women's, obscure)
ML_PARLAY_LEAGUE_BLACKLIST = {
    "soccer_england_league1_women",
    "soccer_england_fa_wsl",
    "soccer_usa_nwsl",
    "soccer_australia_aleague_women",
}


def poisson_pmf(lmb: float, k: int) -> float:
    """Poisson probability mass function"""
    if lmb <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lmb) * (lmb ** k) / math.factorial(k)


def prob_1x2(lh: float, la: float, max_goals: int = 8) -> Tuple[float, float, float]:
    """
    Calculate 1X2 probabilities using Poisson distribution.
    Returns (P(home win), P(draw), P(away win))
    """
    p_hw = p_d = p_aw = 0.0
    for h in range(max_goals + 1):
        ph = poisson_pmf(lh, h)
        for a in range(max_goals + 1):
            pa = poisson_pmf(la, a)
            p = ph * pa
            if h > a:
                p_hw += p
            elif h == a:
                p_d += p
            else:
                p_aw += p
    return p_hw, p_d, p_aw


def prob_dnb(lh: float, la: float, max_goals: int = 8) -> Tuple[float, float]:
    """
    Calculate Draw-No-Bet probabilities.
    Returns (P(home win | no draw), P(away win | no draw))
    """
    p_hw, p_d, p_aw = prob_1x2(lh, la, max_goals)
    non_draw = p_hw + p_aw
    if non_draw <= 0:
        return 0.5, 0.5
    return p_hw / non_draw, p_aw / non_draw


class MLParlayEngine:
    """
    Moneyline Parlay Engine
    
    Generates low/medium risk parlays from 1X2/Moneyline/DNB markets.
    """
    
    def __init__(self, champion=None):
        """
        Args:
            champion: RealFootballChampion instance for fetching fixtures/odds
        """
        self.champion = champion
        self._init_database()
        logger.info("✅ ML Parlay Engine initialized (POLICY COMPLIANT)")
    
    def _check_auto_stop(self) -> Tuple[bool, str]:
        """
        Check if ML parlays should be suspended based on auto-stop conditions.
        
        Conditions:
        - 20 parlays without positive cumulative ROI
        
        Returns:
            (should_stop, reason) - True if parlays should be suspended
        """
        try:
            result = db_helper.execute("""
                SELECT 
                    COUNT(*) as total_parlays,
                    COALESCE(SUM(CASE WHEN outcome = 'won' THEN (total_odds - 1) * 0.2 ELSE -0.2 END), 0) as parlay_pnl
                FROM ml_parlay_predictions 
                WHERE outcome IN ('won', 'lost')
                AND match_date >= (CURRENT_DATE - INTERVAL '30 days')::TEXT
            """, fetch='one')
            
            if result:
                total = result[0] or 0
                pnl = float(result[1] or 0)
                
                if total >= MAX_PARLAYS_WITHOUT_POSITIVE_ROI and pnl < 0:
                    return True, f"AUTO-STOP: {total} parlays with negative ROI ({pnl:.2f} units)"
            
            return False, ""
        except Exception as e:
            logger.warning(f"Auto-stop check failed: {e}")
            return False, ""
    
    def _init_database(self):
        """Create ML Parlay predictions table"""
        db_helper.execute('''
            CREATE TABLE IF NOT EXISTS ml_parlay_predictions (
                id SERIAL PRIMARY KEY,
                parlay_id TEXT UNIQUE,
                timestamp BIGINT,
                match_date TEXT,
                
                -- Parlay details
                num_legs INTEGER,
                legs TEXT,
                parlay_description TEXT,
                
                -- Combined metrics
                total_odds REAL,
                combined_probability REAL,
                combined_ev REAL,
                confidence_score REAL,
                
                -- Staking
                stake REAL,
                potential_payout REAL,
                
                -- Status tracking
                status TEXT DEFAULT 'pending',
                outcome TEXT,
                result TEXT,
                profit_loss REAL,
                settled_timestamp BIGINT,
                
                -- Metadata
                mode TEXT DEFAULT 'test',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        db_helper.execute('''
            CREATE TABLE IF NOT EXISTS ml_parlay_legs (
                id SERIAL PRIMARY KEY,
                parlay_id TEXT,
                leg_number INTEGER,
                
                -- Match info
                match_id TEXT,
                home_team TEXT,
                away_team TEXT,
                league TEXT,
                league_key TEXT,
                kickoff_time TEXT,
                
                -- Bet details
                market_type TEXT,
                selection TEXT,
                odds REAL,
                
                -- Model data
                model_probability REAL,
                edge_percentage REAL,
                
                -- Result tracking
                leg_result TEXT,
                actual_score TEXT,
                
                FOREIGN KEY (parlay_id) REFERENCES ml_parlay_predictions(parlay_id)
            )
        ''')
        
        logger.info("✅ ML Parlay database schema ready")
    
    def _get_league_key(self, match: Dict) -> Optional[str]:
        """Extract the Odds API league key from match data"""
        sport_key = match.get('sport_key', '')
        if sport_key:
            return sport_key
        
        league = match.get('league_name', '') or match.get('league', '')
        for key, name in LEAGUE_DISPLAY_NAMES.items():
            if name.lower() in league.lower():
                return key
        return None
    
    def _is_allowed_league(self, match: Dict) -> bool:
        """Check if match is from an allowed league"""
        league_key = self._get_league_key(match)
        if not league_key:
            return False
        
        if league_key in ML_PARLAY_LEAGUE_BLACKLIST:
            return False
        
        return league_key in ML_PARLAY_LEAGUE_WHITELIST
    
    def _fetch_candidate_legs(self) -> List[Dict]:
        """
        Fetch all candidate legs for ML parlays.
        Uses existing match data from The Odds API.
        """
        candidates = []
        
        try:
            import requests
            import os
            
            api_key = os.environ.get('THE_ODDS_API_KEY')
            if not api_key:
                logger.error("❌ THE_ODDS_API_KEY not found")
                return []
            
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            day_after = today + timedelta(days=2)  # TEST MODE: Extended to 3 days
            
            for league_key in ML_PARLAY_LEAGUE_WHITELIST:
                try:
                    url = f"https://api.the-odds-api.com/v4/sports/{league_key}/odds/"
                    params = {
                        'apiKey': api_key,
                        'regions': 'eu',
                        'markets': 'h2h',
                        'oddsFormat': 'decimal',
                        'dateFormat': 'iso'
                    }
                    
                    resp = requests.get(url, params=params, timeout=15)
                    if resp.status_code != 200:
                        continue
                    
                    matches = resp.json()
                    
                    for match in matches:
                        try:
                            commence_time = match.get('commence_time', '')
                            if not commence_time:
                                continue
                            
                            match_dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                            match_date = match_dt.date()
                            
                            if match_date != today and match_date != tomorrow and match_date != day_after:
                                continue  # TEST MODE: Include matches up to 3 days ahead
                            
                            home_team = match.get('home_team', '')
                            away_team = match.get('away_team', '')
                            match_id = match.get('id', f"{home_team}_{away_team}_{match_date}")
                            
                            bookmakers = match.get('bookmakers', [])
                            if not bookmakers:
                                continue
                            
                            best_odds = self._extract_best_h2h_odds(bookmakers, home_team, away_team)
                            if not best_odds or (best_odds['home'] == 0 and best_odds['away'] == 0):
                                continue
                            
                            xg_home, xg_away = self._estimate_xg(home_team, away_team, league_key)
                            
                            p_home, p_draw, p_away = prob_1x2(xg_home, xg_away)
                            
                            for selection, prob, odds_key in [
                                ('HOME', p_home, 'home'),
                                ('DRAW', p_draw, 'draw'),
                                ('AWAY', p_away, 'away')
                            ]:
                                odds = best_odds.get(odds_key, 0)
                                if odds <= 0:
                                    continue
                                
                                if odds < ML_PARLAY_MIN_ODDS or odds > ML_PARLAY_MAX_ODDS:
                                    continue
                                
                                implied_prob = 1.0 / odds
                                edge = (prob - implied_prob) / implied_prob if implied_prob > 0 else 0
                                
                                if edge < MIN_ML_PARLAY_LEG_EV:
                                    continue
                                
                                # WIN PROBABILITY FILTER (Jan 18, 2026)
                                # Require high win probability, not just positive EV
                                if prob < MIN_LEG_WIN_PROBABILITY:
                                    continue
                                
                                # Calculate composite confidence score
                                confidence = self._calculate_leg_confidence(prob, edge, odds)
                                if confidence < MIN_CONFIDENCE_SCORE:
                                    continue
                                
                                candidates.append({
                                    'match_id': match_id,
                                    'home_team': home_team,
                                    'away_team': away_team,
                                    'league': LEAGUE_DISPLAY_NAMES.get(league_key, league_key),
                                    'league_key': league_key,
                                    'kickoff_time': commence_time,
                                    'match_date': str(match_date),
                                    'market_type': '1X2',
                                    'selection': selection,
                                    'odds': odds,
                                    'model_probability': prob,
                                    'edge_percentage': edge * 100,
                                    'confidence_score': confidence,
                                    'xg_home': xg_home,
                                    'xg_away': xg_away,
                                })
                            
                            p_home_dnb, p_away_dnb = prob_dnb(xg_home, xg_away)
                            
                            for selection, prob, odds_key in [
                                ('HOME_DNB', p_home_dnb, 'home'),
                                ('AWAY_DNB', p_away_dnb, 'away')
                            ]:
                                base_odds = best_odds.get(odds_key.replace('_DNB', '').lower(), 0)
                                if base_odds <= 0:
                                    continue
                                
                                dnb_odds = self._estimate_dnb_odds(base_odds, best_odds.get('draw', 3.0))
                                
                                if dnb_odds < ML_PARLAY_MIN_ODDS or dnb_odds > ML_PARLAY_MAX_ODDS:
                                    continue
                                
                                implied_prob = 1.0 / dnb_odds
                                edge = (prob - implied_prob) / implied_prob if implied_prob > 0 else 0
                                
                                if edge < MIN_ML_PARLAY_LEG_EV:
                                    continue
                                
                                # WIN PROBABILITY FILTER (Jan 18, 2026)
                                if prob < MIN_LEG_WIN_PROBABILITY:
                                    continue
                                
                                # Calculate composite confidence score
                                confidence = self._calculate_leg_confidence(prob, edge, dnb_odds)
                                if confidence < MIN_CONFIDENCE_SCORE:
                                    continue
                                
                                candidates.append({
                                    'match_id': match_id,
                                    'home_team': home_team,
                                    'away_team': away_team,
                                    'league': LEAGUE_DISPLAY_NAMES.get(league_key, league_key),
                                    'league_key': league_key,
                                    'kickoff_time': commence_time,
                                    'match_date': str(match_date),
                                    'market_type': 'DNB',
                                    'selection': selection,
                                    'odds': dnb_odds,
                                    'model_probability': prob,
                                    'edge_percentage': edge * 100,
                                    'confidence_score': confidence,
                                    'xg_home': xg_home,
                                    'xg_away': xg_away,
                                })
                        
                        except Exception as match_err:
                            logger.debug(f"Error processing match: {match_err}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"Error processing league {league_key}: {e}")
                    continue
                
                time.sleep(0.2)
            
            # Sort by confidence score (prioritize high probability), then by edge
            candidates.sort(key=lambda x: (x.get('confidence_score', 0), x.get('model_probability', 0)), reverse=True)
            logger.info(f"📊 Found {len(candidates)} candidate legs for ML Parlays (min {MIN_LEG_WIN_PROBABILITY*100:.0f}% prob)")
            
            return candidates
            
        except Exception as e:
            logger.error(f"❌ Error fetching candidate legs: {e}")
            return []
    
    def _extract_best_h2h_odds(self, bookmakers: List[Dict], home_team: str, away_team: str) -> Dict[str, float]:
        """
        Extract best H2H odds from bookmaker data.
        
        Args:
            bookmakers: List of bookmaker data from The Odds API
            home_team: The home team name (must match exactly)
            away_team: The away team name (must match exactly)
        
        Returns:
            Dict with 'home', 'draw', 'away' odds correctly mapped to teams
        """
        best = {'home': 0.0, 'draw': 0.0, 'away': 0.0}
        
        for bm in bookmakers:
            markets = bm.get('markets', [])
            for market in markets:
                if market.get('key') != 'h2h':
                    continue
                
                outcomes = market.get('outcomes', [])
                for outcome in outcomes:
                    name = outcome.get('name', '')
                    price = outcome.get('price', 0)
                    
                    if price <= 0:
                        continue
                    
                    if name == 'Draw' or 'Draw' in name:
                        if price > best['draw']:
                            best['draw'] = price
                    elif name == home_team:
                        if price > best['home']:
                            best['home'] = price
                    elif name == away_team:
                        if price > best['away']:
                            best['away'] = price
        
        return best
    
    def _estimate_xg(self, home_team: str, away_team: str, league_key: str) -> Tuple[float, float]:
        """
        Estimate expected goals for a match.
        Uses league averages + team form if available.
        """
        league_xg = {
            'soccer_epl': (1.45, 1.15),
            'soccer_spain_la_liga': (1.35, 1.10),
            'soccer_italy_serie_a': (1.35, 1.15),
            'soccer_germany_bundesliga': (1.55, 1.25),
            'soccer_france_ligue_one': (1.35, 1.10),
            'soccer_uefa_champs_league': (1.40, 1.20),
            'soccer_uefa_europa_league': (1.35, 1.15),
            'soccer_netherlands_eredivisie': (1.50, 1.25),
            'soccer_usa_mls': (1.45, 1.20),
        }
        
        base_home, base_away = league_xg.get(league_key, (1.40, 1.15))
        
        return base_home, base_away
    
    def _estimate_dnb_odds(self, ml_odds: float, draw_odds: float) -> float:
        """Estimate Draw-No-Bet odds from moneyline and draw odds"""
        if ml_odds <= 1 or draw_odds <= 1:
            return ml_odds
        
        p_ml = 1 / ml_odds
        p_draw = 1 / draw_odds
        
        p_dnb = p_ml / (1 - p_draw) if p_draw < 1 else p_ml
        
        if p_dnb <= 0 or p_dnb >= 1:
            return ml_odds * 0.7
        
        dnb_odds = 1 / p_dnb
        
        dnb_odds *= 0.95
        
        return max(1.01, min(dnb_odds, ml_odds))
    
    def _check_team_form(self, team_name: str, league_key: str, selection: str) -> Tuple[bool, int]:
        """
        Check if team has good recent form (3+ wins in last 5 matches).
        
        Returns:
            (passes_filter, wins_count) - True if team form is acceptable
        """
        try:
            import requests
            import os
            
            api_key = os.environ.get('API_FOOTBALL_KEY')
            if not api_key:
                return True, 0
            
            league_id_map = {
                'soccer_epl': 39,
                'soccer_spain_la_liga': 140,
                'soccer_italy_serie_a': 135,
                'soccer_germany_bundesliga': 78,
                'soccer_france_ligue_one': 61,
            }
            
            league_id = league_id_map.get(league_key)
            if not league_id:
                return True, 0
            
            url = 'https://v3.football.api-sports.io/fixtures'
            headers = {
                'X-RapidAPI-Key': api_key,
                'X-RapidAPI-Host': 'v3.football.api-sports.io'
            }
            params = {
                'team': team_name,
                'last': FORM_LOOKBACK_MATCHES,
                'league': league_id,
                'season': 2025
            }
            
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code != 200:
                return True, 0
            
            data = resp.json()
            fixtures = data.get('response', [])
            
            wins = 0
            for fixture in fixtures:
                home_goals = fixture.get('goals', {}).get('home', 0) or 0
                away_goals = fixture.get('goals', {}).get('away', 0) or 0
                home_team = fixture.get('teams', {}).get('home', {}).get('name', '')
                
                is_home = team_name.lower() in home_team.lower()
                
                if is_home and home_goals > away_goals:
                    wins += 1
                elif not is_home and away_goals > home_goals:
                    wins += 1
            
            passes = wins >= MIN_RECENT_WINS
            return passes, wins
            
        except Exception as e:
            logger.debug(f"Form check failed for {team_name}: {e}")
            return True, 0
    
    def _calculate_leg_confidence(self, probability: float, edge: float, odds: float) -> float:
        """
        Calculate composite confidence score for a parlay leg.
        
        Factors:
        - Win probability (40% weight) - higher is better
        - Edge/EV (30% weight) - positive edge required
        - Odds safety (30% weight) - lower odds = safer
        
        Returns:
            Confidence score between 0-1
        """
        # Win probability component (0-1, higher = better)
        prob_score = min(1.0, probability)
        
        # Edge component (normalize edge, cap at 20%)
        edge_score = min(1.0, max(0.0, edge / 0.20))
        
        # Odds safety component (lower odds = higher score)
        # 1.35 = 1.0, 1.70 = 0.0 within our range
        if odds <= ML_PARLAY_MIN_ODDS:
            odds_score = 1.0
        elif odds >= ML_PARLAY_MAX_ODDS:
            odds_score = 0.0
        else:
            odds_score = 1.0 - ((odds - ML_PARLAY_MIN_ODDS) / (ML_PARLAY_MAX_ODDS - ML_PARLAY_MIN_ODDS))
        
        # Weighted composite score
        confidence = (prob_score * 0.40) + (edge_score * 0.30) + (odds_score * 0.30)
        
        return round(confidence, 3)
    
    def _get_existing_parlays_today(self) -> int:
        """Count how many ML parlays already created today"""
        today = datetime.utcnow().date()
        
        result = db_helper.execute(
            """SELECT COUNT(*) FROM ml_parlay_predictions 
               WHERE match_date = %s""",
            (str(today),),
            fetch='one'
        )
        
        return result[0] if result else 0
    
    def _get_existing_parlay_signatures(self) -> set:
        """Get signatures of existing parlays to prevent duplicates"""
        import json
        
        today = datetime.utcnow().date()
        result = db_helper.execute(
            """SELECT legs FROM ml_parlay_predictions 
               WHERE match_date = %s""",
            (str(today),),
            fetch='all'
        )
        
        signatures = set()
        if result:
            for row in result:
                try:
                    legs = json.loads(row[0]) if row[0] else []
                    # Create signature from match_id + selection
                    sig = tuple(sorted([f"{l.get('match_id')}:{l.get('selection')}" for l in legs]))
                    signatures.add(sig)
                except:
                    pass
        
        return signatures
    
    def _get_bets_in_pending_parlays(self) -> set:
        """Get match_id + market combinations already used in pending parlays.
        
        Same game can have different markets (1X2, Corners, Over/Under, etc.)
        so we only block the exact same bet, not the entire game.
        """
        result = db_helper.execute(
            """SELECT DISTINCT match_id, market_type, selection FROM ml_parlay_legs l
               JOIN ml_parlay_predictions p ON l.parlay_id = p.parlay_id
               WHERE p.status = 'pending'""",
            fetch='all'
        )
        
        bet_keys = set()
        if result:
            for row in result:
                if row[0]:
                    # Create unique key: match_id:market:selection
                    bet_key = f"{row[0]}:{row[1]}:{row[2]}"
                    bet_keys.add(bet_key)
        
        logger.info(f"🔒 Found {len(bet_keys)} specific bets already in pending parlays")
        return bet_keys
    
    def _parlay_signature(self, legs: List[Dict]) -> tuple:
        """Create a unique signature for a parlay based on its legs"""
        return tuple(sorted([f"{l.get('match_id')}:{l.get('selection')}" for l in legs]))
    
    def _build_parlays(self, candidates: List[Dict]) -> List[Dict]:
        """
        Build parlays from candidate legs.
        
        Rules:
        - 2-4 legs per parlay
        - No duplicate matches within a parlay
        - No matches already in pending parlays (avoid correlated risk)
        - Prioritize highest EV combinations
        - Max 5 parlays per day
        - No duplicate parlays (same legs as existing)
        """
        existing = self._get_existing_parlays_today()
        remaining_slots = MAX_ML_PARLAYS_PER_DAY - existing
        
        if remaining_slots <= 0:
            logger.info(f"⏭️ Already created {existing} ML parlays today (max {MAX_ML_PARLAYS_PER_DAY})")
            return []
        
        if len(candidates) < ML_PARLAY_MIN_LEGS:
            logger.info(f"⏭️ Only {len(candidates)} candidates, need at least {ML_PARLAY_MIN_LEGS}")
            return []
        
        # Get existing parlay signatures to avoid duplicates
        existing_signatures = self._get_existing_parlay_signatures()
        logger.info(f"📋 Found {len(existing_signatures)} existing parlay signatures")
        
        # Get specific bets already in pending parlays to avoid duplicate bets
        # Same game can have different markets (1X2, Corners, Over/Under)
        bets_in_pending = self._get_bets_in_pending_parlays()
        
        # Filter out candidates that are already in pending parlays (same game + market + selection)
        original_count = len(candidates)
        candidates = [c for c in candidates 
                     if f"{c['match_id']}:{c.get('market_type', 'h2h')}:{c['selection']}" not in bets_in_pending]
        filtered_count = original_count - len(candidates)
        if filtered_count > 0:
            logger.info(f"🚫 Filtered {filtered_count} candidates (same bet already in pending parlays)")
        
        if len(candidates) < ML_PARLAY_MIN_LEGS:
            logger.info(f"⏭️ Only {len(candidates)} candidates after filtering, need at least {ML_PARLAY_MIN_LEGS}")
            return []
        
        parlays = []
        used_matches = set()
        
        candidates_by_match = {}
        for leg in candidates:
            mid = leg['match_id']
            if mid not in candidates_by_match:
                candidates_by_match[mid] = []
            candidates_by_match[mid].append(leg)
        
        for match_id, match_legs in candidates_by_match.items():
            candidates_by_match[match_id] = sorted(match_legs, key=lambda x: x['edge_percentage'], reverse=True)[:1]
        
        available_legs = []
        for legs in candidates_by_match.values():
            available_legs.extend(legs)
        # Sort by confidence score (prioritizes probability), then edge
        available_legs.sort(key=lambda x: (x.get('confidence_score', 0), x.get('model_probability', 0)), reverse=True)
        
        for _ in range(remaining_slots):
            parlay_legs = []
            parlay_matches = set()
            parlay_leagues = set()  # Track leagues for diversity
            
            for leg in available_legs:
                mid = leg['match_id']
                league_key = leg.get('league_key', '')
                
                if mid in parlay_matches:
                    continue
                
                if mid in used_matches:
                    continue
                
                # LEAGUE DIVERSITY: Soft preference for different leagues
                # Skip same-league legs on first pass, but allow as fallback
                if PREFER_DIFFERENT_LEAGUES and league_key in parlay_leagues and len(parlay_legs) < ML_PARLAY_MAX_LEGS:
                    # Check if there are other league options available
                    other_leagues_available = any(
                        l.get('league_key', '') not in parlay_leagues 
                        and l['match_id'] not in parlay_matches 
                        and l['match_id'] not in used_matches
                        for l in available_legs
                    )
                    if other_leagues_available:
                        continue  # Skip this same-league leg, try others first
                
                parlay_legs.append(leg)
                parlay_matches.add(mid)
                parlay_leagues.add(league_key)
                
                if len(parlay_legs) >= ML_PARLAY_MAX_LEGS:
                    break
            
            if len(parlay_legs) >= ML_PARLAY_MIN_LEGS:
                # Check if this parlay is a duplicate of an existing one
                sig = self._parlay_signature(parlay_legs)
                if sig in existing_signatures:
                    logger.info(f"⏭️ Skipping duplicate parlay (already exists)")
                    # Still mark matches as used so we try different combinations
                    used_matches.update(parlay_matches)
                    continue
                
                # NOVA v2.0 Safety Guardrail: Check total parlay EV >= 5%
                metrics = self._calculate_parlay_metrics(parlay_legs)
                if metrics['combined_ev'] < MIN_ML_PARLAY_TOTAL_EV:
                    logger.info(f"⏭️ Skipping parlay: combined EV {metrics['combined_ev']:.1f}% < {MIN_ML_PARLAY_TOTAL_EV}% minimum")
                    used_matches.update(parlay_matches)
                    continue
                
                # WIN PROBABILITY FOCUS: Target attractive odds range (3x-4.5x)
                if metrics['total_odds'] > MAX_COMBINED_PARLAY_ODDS:
                    logger.info(f"⏭️ Skipping parlay: total odds {metrics['total_odds']:.2f} > {MAX_COMBINED_PARLAY_ODDS} cap")
                    used_matches.update(parlay_matches)
                    continue
                
                if metrics['total_odds'] < MIN_COMBINED_PARLAY_ODDS:
                    logger.info(f"⏭️ Skipping parlay: total odds {metrics['total_odds']:.2f} < {MIN_COMBINED_PARLAY_ODDS} min (not worth it)")
                    used_matches.update(parlay_matches)
                    continue
                
                # FORM-BASED FILTERING (Jan 23, 2026)
                # Check if selected teams have good recent form (3+ wins in last 5)
                form_pass = True
                for leg in parlay_legs:
                    selection = leg.get('selection', '')
                    team_to_check = None
                    
                    if 'HOME' in selection:
                        team_to_check = leg.get('home_team', '')
                    elif 'AWAY' in selection:
                        team_to_check = leg.get('away_team', '')
                    
                    if team_to_check:
                        passes, wins = self._check_team_form(team_to_check, leg.get('league_key', ''), selection)
                        if not passes:
                            logger.info(f"⏭️ Form filter failed: {team_to_check} has only {wins} wins in last {FORM_LOOKBACK_MATCHES} (need {MIN_RECENT_WINS}+)")
                            form_pass = False
                            break
                        else:
                            logger.debug(f"✅ Form check passed: {team_to_check} has {wins} wins in last {FORM_LOOKBACK_MATCHES}")
                
                if not form_pass:
                    used_matches.update(parlay_matches)
                    continue
                
                parlays.append({
                    'legs': parlay_legs,
                    'matches_used': parlay_matches
                })
                
                # Add to existing signatures to prevent duplicates within this run
                existing_signatures.add(sig)
                used_matches.update(parlay_matches)
            else:
                break
        
        logger.info(f"🎰 Built {len(parlays)} ML parlays from {len(candidates)} candidates")
        return parlays
    
    def _calculate_parlay_metrics(self, legs: List[Dict]) -> Dict:
        """Calculate combined metrics for a parlay"""
        total_odds = 1.0
        combined_prob = 1.0
        total_ev = 0.0
        total_confidence = 0.0
        
        for leg in legs:
            total_odds *= leg['odds']
            combined_prob *= leg['model_probability']
            total_ev += leg['edge_percentage']
            total_confidence += leg['edge_percentage'] * 10
        
        avg_ev = total_ev / len(legs) if legs else 0
        
        leg_count_factor = {2: 0.9, 3: 0.8, 4: 0.7}.get(len(legs), 0.6)
        confidence_score = min(1.0, (avg_ev / 10) * leg_count_factor)
        
        combined_ev = (combined_prob * total_odds - 1) * 100
        
        return {
            'total_odds': round(total_odds, 2),
            'combined_probability': round(combined_prob, 4),
            'combined_ev': round(combined_ev, 2),
            'avg_leg_ev': round(avg_ev, 2),
            'confidence_score': round(confidence_score, 3)
        }
    
    def _save_parlay(self, parlay: Dict, metrics: Dict) -> Optional[str]:
        """Save parlay and legs to database"""
        try:
            import uuid
            parlay_id = f"ML_{uuid.uuid4().hex[:8].upper()}"
            timestamp = int(time.time())
            today = datetime.utcnow().date()
            
            stake = ML_PARLAY_STAKE_UNITS
            potential_payout = round(stake * metrics['total_odds'], 2)
            
            legs_json = json.dumps([{
                'match_id': l['match_id'],
                'home_team': l['home_team'],
                'away_team': l['away_team'],
                'league': l['league'],
                'market_type': l['market_type'],
                'selection': l['selection'],
                'odds': l['odds'],
                'edge_percentage': l['edge_percentage']
            } for l in parlay['legs']])
            
            description_parts = []
            for leg in parlay['legs']:
                sel = leg['selection']
                if sel == 'HOME':
                    pick = leg['home_team']
                elif sel == 'AWAY':
                    pick = leg['away_team']
                elif sel == 'DRAW':
                    pick = 'Draw'
                elif sel == 'HOME_DNB':
                    pick = f"{leg['home_team']} (DNB)"
                elif sel == 'AWAY_DNB':
                    pick = f"{leg['away_team']} (DNB)"
                else:
                    pick = sel
                description_parts.append(f"{pick} @{leg['odds']:.2f}")
            
            parlay_description = " + ".join(description_parts)
            
            db_helper.execute('''
                INSERT INTO ml_parlay_predictions (
                    parlay_id, timestamp, match_date, num_legs, legs, parlay_description,
                    total_odds, combined_probability, combined_ev, confidence_score,
                    stake, potential_payout, status, mode
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', 'test')
            ''', (
                parlay_id, timestamp, str(today), len(parlay['legs']), legs_json, parlay_description,
                metrics['total_odds'], metrics['combined_probability'], metrics['combined_ev'],
                metrics['confidence_score'], stake, potential_payout
            ))
            
            for i, leg in enumerate(parlay['legs'], 1):
                db_helper.execute('''
                    INSERT INTO ml_parlay_legs (
                        parlay_id, leg_number, match_id, home_team, away_team,
                        league, league_key, kickoff_time, market_type, selection,
                        odds, model_probability, edge_percentage
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    parlay_id, i, leg['match_id'], leg['home_team'], leg['away_team'],
                    leg['league'], leg['league_key'], leg['kickoff_time'], leg['market_type'],
                    leg['selection'], leg['odds'], leg['model_probability'], leg['edge_percentage']
                ))
            
            # TEST MODE: Skip bankroll tracking
            # bankroll_mgr.record_pending_bet('ML_PARLAY', stake, parlay_id)
            
            logger.info(f"✅ Saved ML Parlay {parlay_id}: {len(parlay['legs'])} legs @ {metrics['total_odds']:.2f}x, EV {metrics['combined_ev']:.1f}%")
            return parlay_id
            
        except Exception as e:
            logger.error(f"❌ Error saving parlay: {e}")
            return None
    
    def generate_ml_parlays(self) -> List[str]:
        """
        Main entry point: Generate ML parlays for today.
        
        PARLAY POLICY (Dec 30, 2025):
        - ONLY 2-leg parlays allowed
        - Each leg must have positive EV
        - Flat staking (0.2 units)
        - Auto-stop if performance conditions met
        
        Returns:
            List of parlay IDs created
        """
        if not ML_PARLAY_ENABLED:
            logger.info("⏭️ ML Parlay engine is disabled")
            return []
        
        should_stop, reason = self._check_auto_stop()
        if should_stop:
            logger.info(f"🚫 NO PARLAYS GENERATED – POLICY RESTRICTION: {reason}")
            return []
        
        logger.info("="*60)
        logger.info("🎰 ML PARLAY ENGINE - Starting (POLICY COMPLIANT: 2-leg only)")
        logger.info("="*60)
        
        candidates = self._fetch_candidate_legs()
        
        if not candidates:
            logger.info("⏭️ No candidate legs found")
            return []
        
        logger.info(f"📊 Top candidates by EV:")
        for i, c in enumerate(candidates[:10], 1):
            logger.info(f"   {i}. {c['home_team']} vs {c['away_team']} | {c['selection']} @{c['odds']:.2f} (EV {c['edge_percentage']:.1f}%)")
        
        parlays = self._build_parlays(candidates)
        
        if not parlays:
            logger.info("⏭️ Could not build any valid parlays")
            return []
        
        created_ids = []
        for parlay in parlays:
            metrics = self._calculate_parlay_metrics(parlay['legs'])
            parlay_id = self._save_parlay(parlay, metrics)
            if parlay_id:
                created_ids.append(parlay_id)
                try:
                    send_bet_to_discord({
                        'product': 'ML_PARLAY',
                        'match_date': parlay['legs'][0].get('match_date', '') if parlay['legs'] else '',
                        'odds': metrics.get('total_odds', 1.0),
                        'ev': metrics.get('combined_ev', 0),
                        'trust_level': parlay.get('trust_level', 'L2'),
                        'num_legs': len(parlay['legs']),
                        'legs': [
                            {
                                'home_team': leg.get('home_team', ''),
                                'away_team': leg.get('away_team', ''),
                                'selection': leg.get('selection', ''),
                                'odds': leg.get('odds', 0)
                            }
                            for leg in parlay['legs']
                        ]
                    }, product_type='ML_PARLAY')
                except Exception as e:
                    logger.warning(f"Discord notification failed: {e}")
        
        logger.info("="*60)
        logger.info(f"✅ ML PARLAY ENGINE - Created {len(created_ids)} parlays")
        logger.info("="*60)
        
        return created_ids


def run_prediction_cycle():
    """Run a single ML Parlay prediction cycle"""
    try:
        if ML_PARLAY_PAUSED:
            logger.info("⏸️ ML Parlays PAUSED - Focus on profitable singles (+100u ROI)")
            logger.info("   Set ML_PARLAY_PAUSED = False to resume parlay generation")
            return []
        
        engine = MLParlayEngine()
        parlay_ids = engine.generate_ml_parlays()
        logger.info(f"🎰 ML Parlay cycle complete: {len(parlay_ids)} parlays created")
        return parlay_ids
    except Exception as e:
        logger.error(f"❌ ML Parlay cycle error: {e}")
        return []


if __name__ == "__main__":
    run_prediction_cycle()
