import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from db_helper import db_helper

logger = logging.getLogger(__name__)

OPPOSING_MARKETS = {
    'Home Win': ['Away Win', 'Draw'],
    'Away Win': ['Home Win', 'Draw'],
    'Draw': ['Home Win', 'Away Win'],
    'Over 2.5 Goals': ['Under 2.5 Goals'],
    'Under 2.5 Goals': ['Over 2.5 Goals'],
    'Over 3.5 Goals': ['Under 3.5 Goals'],
    'Under 3.5 Goals': ['Over 3.5 Goals'],
    'Over 1.5 Goals': ['Under 1.5 Goals'],
    'Under 1.5 Goals': ['Over 1.5 Goals'],
    'BTTS Yes': ['BTTS No'],
    'BTTS No': ['BTTS Yes'],
    'Draw No Bet - Home': ['Draw No Bet - Away'],
    'Draw No Bet - Away': ['Draw No Bet - Home'],
}

SMART_PICKS_ODDS_MIN = 1.70
SMART_PICKS_ODDS_MAX = 2.10
SMART_PICKS_ODDS_EXTENDED_MAX = 2.50

SMART_PICKS_ENABLED = False  # Stable 2.0 (Feb 19, 2026) - conflict filter disabled
MAX_PICKS_PER_MATCH = 2      # Stable 2.0 - allow up to 2 picks per match


def get_match_key(pick: dict) -> str:
    home = pick.get('home_team', '').strip().lower()
    away = pick.get('away_team', '').strip().lower()
    date = pick.get('match_date', '')
    return f"{home}|{away}|{date}"


def are_opposing(sel_a: str, sel_b: str) -> bool:
    a = sel_a.strip()
    b = sel_b.strip()
    opposites = OPPOSING_MARKETS.get(a, [])
    if b in opposites:
        return True
    opposites_b = OPPOSING_MARKETS.get(b, [])
    if a in opposites_b:
        return True
    if 'Over' in a and 'Under' in b:
        a_line = a.split()[-1] if a.split() else ''
        b_line = b.split()[-1] if b.split() else ''
        if a_line == b_line:
            return True
    if 'Under' in a and 'Over' in b:
        a_line = a.split()[-1] if a.split() else ''
        b_line = b.split()[-1] if b.split() else ''
        if a_line == b_line:
            return True
    if 'AH' in a and 'AH' in b and a != b:
        return True
    return False


def compute_smart_score(pick: dict) -> float:
    ev = float(pick.get('edge_percentage', 0) or 0)
    conf = float(pick.get('confidence', 0) or 0)
    odds = float(pick.get('odds', 0) or 0)

    ev_score = min(ev / 30.0, 1.0) * 40
    conf_score = min(conf / 100.0, 1.0) * 30

    if SMART_PICKS_ODDS_MIN <= odds <= SMART_PICKS_ODDS_MAX:
        odds_score = 30
    elif odds < SMART_PICKS_ODDS_MIN and odds >= 1.40:
        odds_score = 15
    elif odds > SMART_PICKS_ODDS_MAX and odds <= SMART_PICKS_ODDS_EXTENDED_MAX:
        odds_score = 20
    else:
        odds_score = 5

    trust = pick.get('trust_level', '')
    trust_bonus = 0
    if trust == 'L1_HIGH_TRUST':
        trust_bonus = 10
    elif trust == 'L2_MEDIUM_TRUST':
        trust_bonus = 5

    return ev_score + conf_score + odds_score + trust_bonus


def filter_smart_picks(picks: List[dict]) -> List[dict]:
    if not SMART_PICKS_ENABLED:
        for p in picks:
            p['_smart_score'] = compute_smart_score(p)

        match_groups: Dict[str, List[dict]] = {}
        for p in picks:
            key = get_match_key(p)
            match_groups.setdefault(key, []).append(p)

        result = []
        for match_key, group in match_groups.items():
            group.sort(key=lambda x: x['_smart_score'], reverse=True)
            result.extend(group[:MAX_PICKS_PER_MATCH])

        result.sort(key=lambda x: x.get('_smart_score', 0), reverse=True)
        return result

    match_groups: Dict[str, List[dict]] = {}
    for p in picks:
        key = get_match_key(p)
        match_groups.setdefault(key, []).append(p)

    smart_picks = []

    for match_key, group in match_groups.items():
        for p in group:
            p['_smart_score'] = compute_smart_score(p)

        group.sort(key=lambda x: x['_smart_score'], reverse=True)

        selected = []
        for candidate in group:
            has_conflict = False
            for existing in selected:
                if are_opposing(candidate.get('selection', ''), existing.get('selection', '')):
                    has_conflict = True
                    break
            if not has_conflict:
                selected.append(candidate)

        if selected:
            smart_picks.append(selected[0])

    smart_picks.sort(key=lambda x: x.get('_smart_score', 0), reverse=True)

    return smart_picks


def get_smart_picks_from_db(days_ahead: int = 7) -> List[dict]:
    rows = db_helper.execute('''
        SELECT id, home_team, away_team, league, market, selection, odds,
               edge_percentage, confidence, match_date, kickoff_utc, kickoff_epoch,
               trust_level, odds_by_bookmaker, best_odds_value, best_odds_bookmaker,
               avg_odds, fair_odds, status, result, mode
        FROM football_opportunities
        WHERE mode = 'PROD'
          AND status = 'pending'
          AND match_date >= CURRENT_DATE::text
        ORDER BY edge_percentage DESC
    ''', fetch='all')

    if not rows:
        return []

    picks = []
    for row in rows:
        pick = {
            'id': row[0],
            'home_team': row[1],
            'away_team': row[2],
            'league': row[3],
            'market': row[4],
            'selection': row[5],
            'odds': float(row[6]) if row[6] else 0,
            'edge_percentage': float(row[7]) if row[7] else 0,
            'confidence': int(row[8]) if row[8] else 0,
            'match_date': row[9],
            'kickoff_utc': row[10],
            'kickoff_epoch': row[11],
            'trust_level': row[12],
            'odds_by_bookmaker': row[13] if row[13] else {},
            'best_odds_value': float(row[14]) if row[14] else None,
            'best_odds_bookmaker': row[15],
            'avg_odds': float(row[16]) if row[16] else None,
            'fair_odds': float(row[17]) if row[17] else None,
            'status': row[18],
            'result': row[19],
            'mode': row[20],
        }
        picks.append(pick)

    return filter_smart_picks(picks)


def get_smart_picks_dataframe() -> pd.DataFrame:
    picks = get_smart_picks_from_db()
    if not picks:
        return pd.DataFrame()

    df = pd.DataFrame(picks)

    if 'kickoff_utc' in df.columns:
        df['kickoff_display'] = df['kickoff_utc'].apply(
            lambda x: x[:16].replace('T', ' ') if x else 'TBD'
        )

    if 'odds_by_bookmaker' in df.columns:
        def get_best_book(row):
            obs = row.get('odds_by_bookmaker')
            if isinstance(obs, str):
                try:
                    obs = json.loads(obs)
                except:
                    return ''
            if isinstance(obs, dict) and obs:
                best_book = max(obs, key=lambda k: obs[k])
                return f"{best_book} @ {obs[best_book]}"
            return ''
        df['best_bookmaker'] = df.apply(get_best_book, axis=1)

    return df
