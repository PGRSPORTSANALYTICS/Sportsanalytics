#!/usr/bin/env python3
"""
PARLAY ENGINE
=============
Builds 2-3 leg parlays from the best approved Value Singles.

Product Features:
- All markets: 1X2, Over/Under, BTTS, Double Chance
- 2-3 legs per parlay
- Max 3 parlays per day
- 3%+ EV per leg
- Uses approved Value Singles with real model probabilities

INTERNAL TEST MODE: Database logging only, no external posting.
"""

import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from db_helper import db_helper
from bankroll_manager import get_bankroll_manager
from discord_notifier import send_bet_to_discord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# PARLAY CONFIGURATION (Feb 6, 2026)
# Best bets from Value Singles → 2-3 leg parlays
# ============================================================

# PARLAY RULES:
# 1. 2-3 legs per parlay
# 2. Each leg must be an approved Value Single with positive EV
# 3. All markets allowed (1X2, Over/Under, BTTS, Double Chance)
# 4. Flat staking
# 5. Max 1 leg per match

ML_PARLAY_ENABLED = True
ML_PARLAY_PAUSED = False

# Odds filters per leg
ML_PARLAY_MIN_ODDS = 1.50
ML_PARLAY_MAX_ODDS = 3.00

# Minimum EV per leg (3% edge)
MIN_ML_PARLAY_LEG_EV = 0.03

# Minimum total parlay EV
MIN_ML_PARLAY_TOTAL_EV = 5.0

# Win probability
MIN_LEG_WIN_PROBABILITY = 0.35
MAX_COMBINED_PARLAY_ODDS = 15.00
MIN_COMBINED_PARLAY_ODDS = 3.00
PREFER_DIFFERENT_LEAGUES = True
MIN_CONFIDENCE_SCORE = 0.50

# Parlay construction limits
MAX_ML_PARLAYS_PER_DAY = 3
ML_PARLAY_MIN_LEGS = 2
ML_PARLAY_MAX_LEGS = 3

# FLAT STAKING - 20% of single stake (0.2 units)
ML_PARLAY_STAKE_UNITS = 0.2

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




class MLParlayEngine:
    """
    Parlay Engine
    
    Builds 2-3 leg parlays from the best approved Value Singles.
    All markets allowed: 1X2, Over/Under, BTTS, Double Chance.
    """
    
    def __init__(self):
        self._init_database()
        logger.info("✅ Parlay Engine initialized")
    
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
        Fetch approved Value Singles from DB as parlay candidate legs.
        All markets accepted: 1X2, Over/Under, BTTS, Double Chance.
        """
        candidates = []
        try:
            today = datetime.utcnow().strftime('%Y-%m-%d')
            tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            rows = db_helper.execute('''
                SELECT home_team, away_team, league, market, selection, odds, 
                       model_prob, edge_percentage, match_date, kickoff_time, match_id,
                       sim_probability, trust_level
                FROM football_opportunities
                WHERE match_date IN (%s, %s)
                  AND model_prob IS NOT NULL
                  AND model_prob >= %s
                  AND bet_placed = true
                  AND market IN ('Value Single')
                  AND odds >= %s AND odds <= %s
                  AND result IS NULL
            ''', (today, tomorrow, MIN_LEG_WIN_PROBABILITY, ML_PARLAY_MIN_ODDS, ML_PARLAY_MAX_ODDS), 
            fetch='all')
            
            if not rows:
                logger.info("📊 No Value Singles candidates found in DB")
                return []
            
            for row in rows:
                home_team, away_team, league, market, selection, odds, model_prob, edge_pct, match_date, kickoff_time, match_id, sim_prob, trust_level = row
                
                market_type, sel = self._classify_selection(selection)
                if not market_type:
                    continue
                
                implied_prob = 1.0 / odds if odds > 0 else 0
                edge = (model_prob - implied_prob) / implied_prob if implied_prob > 0 else 0
                
                if edge < MIN_ML_PARLAY_LEG_EV:
                    continue
                
                confidence = self._calculate_leg_confidence(model_prob, edge, odds)
                if confidence < MIN_CONFIDENCE_SCORE:
                    continue
                
                candidates.append({
                    'match_id': match_id or f"{home_team}_{away_team}_{match_date}",
                    'home_team': home_team,
                    'away_team': away_team,
                    'league': league,
                    'league_key': '',
                    'kickoff_time': kickoff_time or '',
                    'match_date': match_date,
                    'market_type': market_type,
                    'selection': sel,
                    'odds': float(odds),
                    'model_probability': float(model_prob),
                    'edge_percentage': float(edge * 100),
                    'confidence_score': float(confidence),
                    'source': 'value_singles_db'
                })
            
            logger.info(f"📊 Found {len(candidates)} parlay candidates from Value Singles")
            return candidates
            
        except Exception as e:
            logger.error(f"Error fetching parlay candidates: {e}")
            return []
    
    def _classify_selection(self, selection: str) -> Tuple[Optional[str], str]:
        """Classify a Value Singles selection into market type and normalized name."""
        if 'Home Win' in selection or selection == 'HOME':
            return '1X2', 'HOME'
        elif 'Away Win' in selection or selection == 'AWAY':
            return '1X2', 'AWAY'
        elif 'Draw' in selection or selection == 'DRAW':
            return '1X2', 'DRAW'
        elif 'Over' in selection:
            return 'TOTALS', selection
        elif 'Under' in selection:
            return 'TOTALS', selection
        elif 'BTTS Yes' in selection:
            return 'BTTS', 'BTTS_YES'
        elif 'BTTS No' in selection:
            return 'BTTS', 'BTTS_NO'
        elif 'DNB' in selection:
            return 'DNB', selection
        elif 'Double Chance' in selection:
            return 'DC', selection
        return None, selection
    
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
        Build 2-3 leg parlays from the best Value Singles candidates.
        Max 1 leg per match. Max 3 parlays per day.
        """
        existing = self._get_existing_parlays_today()
        remaining_slots = MAX_ML_PARLAYS_PER_DAY - existing
        
        if remaining_slots <= 0:
            logger.info(f"⏭️ Already created {existing} parlays today (max {MAX_ML_PARLAYS_PER_DAY})")
            return []
        
        if len(candidates) < ML_PARLAY_MIN_LEGS:
            logger.info(f"⏭️ Only {len(candidates)} candidates, need at least {ML_PARLAY_MIN_LEGS}")
            return []
        
        existing_signatures = self._get_existing_parlay_signatures()
        logger.info(f"📋 Found {len(existing_signatures)} existing parlay signatures")
        
        bets_in_pending = self._get_bets_in_pending_parlays()
        
        original_count = len(candidates)
        candidates = [c for c in candidates 
                     if f"{c['match_id']}:{c.get('market_type', 'h2h')}:{c['selection']}" not in bets_in_pending]
        filtered_count = original_count - len(candidates)
        if filtered_count > 0:
            logger.info(f"🚫 Filtered {filtered_count} candidates (already in pending parlays)")
        
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
        available_legs.sort(key=lambda x: (x.get('confidence_score', 0), x.get('model_probability', 0)), reverse=True)
        
        for _ in range(remaining_slots):
            parlay_legs = []
            parlay_matches = set()
            parlay_leagues = set()
            
            for leg in available_legs:
                mid = leg['match_id']
                league = leg.get('league', '')
                
                if mid in parlay_matches:
                    continue
                
                if mid in used_matches:
                    continue
                
                if PREFER_DIFFERENT_LEAGUES and league in parlay_leagues and len(parlay_legs) < ML_PARLAY_MAX_LEGS:
                    other_leagues_available = any(
                        l.get('league', '') not in parlay_leagues 
                        and l['match_id'] not in parlay_matches 
                        and l['match_id'] not in used_matches
                        for l in available_legs
                    )
                    if other_leagues_available:
                        continue
                
                parlay_legs.append(leg)
                parlay_matches.add(mid)
                parlay_leagues.add(league)
                
                if len(parlay_legs) >= ML_PARLAY_MAX_LEGS:
                    break
            
            if len(parlay_legs) >= ML_PARLAY_MIN_LEGS:
                sig = self._parlay_signature(parlay_legs)
                if sig in existing_signatures:
                    logger.info(f"⏭️ Skipping duplicate parlay")
                    used_matches.update(parlay_matches)
                    continue
                
                metrics = self._calculate_parlay_metrics(parlay_legs)
                if metrics['combined_ev'] < MIN_ML_PARLAY_TOTAL_EV:
                    logger.info(f"⏭️ Skipping parlay: combined EV {metrics['combined_ev']:.1f}% < {MIN_ML_PARLAY_TOTAL_EV}%")
                    used_matches.update(parlay_matches)
                    continue
                
                if metrics['total_odds'] > MAX_COMBINED_PARLAY_ODDS:
                    logger.info(f"⏭️ Skipping parlay: total odds {metrics['total_odds']:.2f} > {MAX_COMBINED_PARLAY_ODDS}")
                    used_matches.update(parlay_matches)
                    continue
                
                if metrics['total_odds'] < MIN_COMBINED_PARLAY_ODDS:
                    logger.info(f"⏭️ Skipping parlay: total odds {metrics['total_odds']:.2f} < {MIN_COMBINED_PARLAY_ODDS}")
                    used_matches.update(parlay_matches)
                    continue
                
                parlays.append({
                    'legs': parlay_legs,
                    'matches_used': parlay_matches
                })
                
                existing_signatures.add(sig)
                used_matches.update(parlay_matches)
            else:
                break
        
        logger.info(f"🎰 Built {len(parlays)} parlays from {len(candidates)} candidates")
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
                match_label = f"{leg['home_team']} vs {leg['away_team']}"
                if sel == 'HOME':
                    pick = f"{leg['home_team']} Win"
                elif sel == 'AWAY':
                    pick = f"{leg['away_team']} Win"
                elif sel == 'DRAW':
                    pick = f"{match_label} Draw"
                elif sel == 'BTTS_YES':
                    pick = f"{match_label} BTTS Yes"
                elif sel == 'BTTS_NO':
                    pick = f"{match_label} BTTS No"
                elif 'Over' in sel or 'Under' in sel:
                    pick = f"{match_label} {sel}"
                elif 'DNB' in sel:
                    pick = f"{match_label} {sel}"
                elif 'Double Chance' in sel:
                    pick = f"{match_label} {sel}"
                else:
                    pick = f"{match_label} {sel}"
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
            
            logger.info(f"✅ Saved Parlay {parlay_id}: {len(parlay['legs'])} legs @ {metrics['total_odds']:.2f}x, EV {metrics['combined_ev']:.1f}%")
            return parlay_id
            
        except Exception as e:
            logger.error(f"❌ Error saving parlay: {e}")
            return None
    
    def generate_ml_parlays(self) -> List[str]:
        """
        Main entry point: Build 2-3 leg parlays from best Value Singles.
        """
        if not ML_PARLAY_ENABLED:
            logger.info("⏭️ Parlay engine is disabled")
            return []
        
        should_stop, reason = self._check_auto_stop()
        if should_stop:
            logger.info(f"🚫 NO PARLAYS GENERATED: {reason}")
            return []
        
        logger.info("="*60)
        logger.info("🎰 PARLAY ENGINE - Building from best Value Singles")
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
        logger.info(f"✅ PARLAY ENGINE - Created {len(created_ids)} parlays")
        logger.info("="*60)
        
        return created_ids


def run_prediction_cycle():
    """Run a single parlay prediction cycle"""
    try:
        if ML_PARLAY_PAUSED:
            logger.info("⏸️ Parlays PAUSED")
            return []
        
        engine = MLParlayEngine()
        parlay_ids = engine.generate_ml_parlays()
        logger.info(f"🎰 Parlay cycle complete: {len(parlay_ids)} parlays created")
        return parlay_ids
    except Exception as e:
        logger.error(f"❌ Parlay cycle error: {e}")
        return []


if __name__ == "__main__":
    run_prediction_cycle()
