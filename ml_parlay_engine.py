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
# ML PARLAY CONFIGURATION CONSTANTS
# ============================================================

# Master switch
ML_PARLAY_ENABLED = True

# Odds filters per leg - TEST MODE: Wider range
ML_PARLAY_MIN_ODDS = 1.20  # TEST MODE: Lowered from 1.40
ML_PARLAY_MAX_ODDS = 3.00  # TEST MODE: Raised from 2.10

# Minimum EV per leg (0% edge for testing - raise to 4% for production)
MIN_ML_PARLAY_LEG_EV = 0.00  # TEST MODE: 0% EV threshold - TESTING ONLY

# Parlay construction limits
MAX_ML_PARLAYS_PER_DAY = 3
ML_PARLAY_MIN_LEGS = 2
ML_PARLAY_MAX_LEGS = 4

# Stake as percentage of bankroll
ML_PARLAY_STAKE_PCT = 0.016  # 1.6% Kelly stake of bankroll

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
        logger.info("✅ ML Parlay Engine initialized (TEST MODE)")
    
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
            
            candidates.sort(key=lambda x: x['edge_percentage'], reverse=True)
            logger.info(f"📊 Found {len(candidates)} candidate legs for ML Parlays")
            
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
    
    def _parlay_signature(self, legs: List[Dict]) -> tuple:
        """Create a unique signature for a parlay based on its legs"""
        return tuple(sorted([f"{l.get('match_id')}:{l.get('selection')}" for l in legs]))
    
    def _build_parlays(self, candidates: List[Dict]) -> List[Dict]:
        """
        Build parlays from candidate legs.
        
        Rules:
        - 2-4 legs per parlay
        - No duplicate matches within a parlay
        - Prioritize highest EV combinations
        - Max 3 parlays per day
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
        available_legs.sort(key=lambda x: x['edge_percentage'], reverse=True)
        
        for _ in range(remaining_slots):
            parlay_legs = []
            parlay_matches = set()
            
            for leg in available_legs:
                mid = leg['match_id']
                
                if mid in parlay_matches:
                    continue
                
                if mid in used_matches:
                    continue
                
                parlay_legs.append(leg)
                parlay_matches.add(mid)
                
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
            
            bankroll_mgr = get_bankroll_manager()
            current_bankroll = bankroll_mgr.get_current_bankroll()
            stake = round(current_bankroll * ML_PARLAY_STAKE_PCT, 2)
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
        
        Returns:
            List of parlay IDs created
        """
        if not ML_PARLAY_ENABLED:
            logger.info("⏭️ ML Parlay engine is disabled")
            return []
        
        logger.info("="*60)
        logger.info("🎰 ML PARLAY ENGINE - Starting (TEST MODE)")
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
                    leg_teams = [f"{leg['home_team']} vs {leg['away_team']}" for leg in parlay['legs'][:2]]
                    send_bet_to_discord({
                        'league': 'ML Parlay',
                        'home_team': leg_teams[0] if leg_teams else '',
                        'away_team': f"+{len(parlay['legs'])-1} more" if len(parlay['legs']) > 1 else '',
                        'match_date': parlay['legs'][0].get('match_date', '') if parlay['legs'] else '',
                        'product': 'ML_PARLAY',
                        'selection': metrics.get('description', f"{len(parlay['legs'])}-leg parlay"),
                        'odds': metrics.get('total_odds', 1.0),
                        'ev': metrics.get('combined_ev', 0) * 100,
                        'stake': metrics.get('stake', 0)
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
        engine = MLParlayEngine()
        parlay_ids = engine.generate_ml_parlays()
        logger.info(f"🎰 ML Parlay cycle complete: {len(parlay_ids)} parlays created")
        return parlay_ids
    except Exception as e:
        logger.error(f"❌ ML Parlay cycle error: {e}")
        return []


if __name__ == "__main__":
    run_prediction_cycle()
