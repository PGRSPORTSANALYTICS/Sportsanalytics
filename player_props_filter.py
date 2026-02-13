"""
Player Props Quality Filter
============================
Filters raw player props to keep only stable, high-quality betting candidates.

Quality Filters (all must pass):
1. Allowed markets only (4 basketball markets)
2. Odds range: 1.70-2.20
3. Deduplication: best odds per player+market+selection+line
4. Min 10+ historical games this season
5. Avg minutes >= 22 over last 10 games
6. Played >= 5 of last 7 games
7. Starter (25+ min) or rotation (15+ min) role
8. Not returning from injury
9. Not limited minutes last game
10. Projection requires 10+ recent game values
11. Positive EV only

Post-Filter Ranking (applied after quality pass):
1. Rank by edge descending
2. Max 2 props per player
3. Max 3 props per match
4. Remove projection diff < 1.0 stat unit
5. Keep top 15 by edge
6. Tag top 5 as Premium Picks
"""

import logging
from typing import Dict, List, Optional
from nba_stats_provider import get_player_stats, get_projection

logger = logging.getLogger(__name__)

ALLOWED_MARKETS = [
    'player_points',
    'player_rebounds',
    'player_assists',
    'player_points_rebounds_assists',
]

MIN_AVG_MINUTES = 22
MIN_GAMES_LAST_7 = 5
MIN_ODDS = 1.70
MAX_ODDS = 2.20
MIN_HISTORICAL_GAMES = 10
MIN_LAST_GAME_MINUTES = 15

MAX_PROPS_PER_PLAYER = 3
MAX_PROPS_PER_MATCH = 5
MIN_PROJECTION_DIFF = 1.0
MAX_FINAL_PROPS = 100
PREMIUM_COUNT = 10


def filter_quality_props(raw_props: List[Dict]) -> List[Dict]:
    logger.info(f"Filtering {len(raw_props)} raw props...")

    market_filtered = [p for p in raw_props if p.get('market') in ALLOWED_MARKETS]
    logger.info(f"  After market filter: {len(market_filtered)}")

    odds_filtered = [
        p for p in market_filtered
        if MIN_ODDS <= (p.get('odds') or 0) <= MAX_ODDS
    ]
    logger.info(f"  After odds filter ({MIN_ODDS}-{MAX_ODDS}): {len(odds_filtered)}")

    deduped = _deduplicate_props(odds_filtered)
    logger.info(f"  After dedup (best odds): {len(deduped)}")

    unique_players = list(set(p['player_name'] for p in deduped))
    logger.info(f"  Fetching stats for {len(unique_players)} unique players...")

    stats_cache = {}
    for name in unique_players:
        stats_cache[name] = get_player_stats(name)

    quality_props = []
    filtered_reasons = {
        'no_stats': 0, 'low_minutes': 0, 'few_games_7': 0,
        'few_games_total': 0, 'injury_return': 0, 'limited_last': 0,
        'not_rotation': 0, 'no_projection': 0, 'negative_ev': 0,
    }

    for prop in deduped:
        player_name = prop['player_name']
        stats = stats_cache.get(player_name)

        if not stats:
            filtered_reasons['no_stats'] += 1
            continue

        if stats['total_games'] < MIN_HISTORICAL_GAMES:
            filtered_reasons['few_games_total'] += 1
            continue

        if stats['avg_min_last_10'] < MIN_AVG_MINUTES:
            filtered_reasons['low_minutes'] += 1
            continue

        if stats['games_played_last_7'] < MIN_GAMES_LAST_7:
            filtered_reasons['few_games_7'] += 1
            continue

        if not (stats['is_starter'] or stats['is_rotation']):
            filtered_reasons['not_rotation'] += 1
            continue

        if stats['returning_from_injury']:
            filtered_reasons['injury_return'] += 1
            continue

        if stats['limited_last_game']:
            filtered_reasons['limited_last'] += 1
            continue

        line = prop.get('line')
        if line is None or line <= 0:
            filtered_reasons['no_projection'] += 1
            continue

        projection = get_projection(stats, prop['market'], line)
        if not projection:
            filtered_reasons['no_projection'] += 1
            continue

        selection = prop.get('selection', '').lower()
        odds = prop['odds']
        implied_prob = 1.0 / odds if odds > 0 else 0

        if 'over' in selection:
            model_prob = projection['hit_rate_over']
        elif 'under' in selection:
            model_prob = 1.0 - projection['hit_rate_over']
        else:
            continue

        if model_prob <= 0:
            model_prob = 0.01

        ev = (model_prob * odds - 1) * 100

        if ev <= 0:
            filtered_reasons['negative_ev'] += 1
            continue

        prop['model_prob'] = round(model_prob, 4)
        prop['edge_pct'] = round(ev, 1)
        prop['confidence'] = round(model_prob * 100, 1)
        prop['projected'] = projection['projected']
        prop['projection_diff'] = projection['diff']
        prop['hit_rate_over'] = projection['hit_rate_over']
        prop['games_over'] = projection['games_over']
        prop['games_total'] = projection['games_total']
        prop['consistency'] = projection['consistency']
        prop['avg_minutes'] = stats['avg_min_last_10']
        prop['games_last_7'] = stats['games_played_last_7']
        prop['is_starter'] = stats['is_starter']
        prop['quality_filtered'] = True

        quality_props.append(prop)

    logger.info(f"  Quality filter results: {len(quality_props)} passed (before ranking)")
    for reason, count in filtered_reasons.items():
        if count > 0:
            logger.info(f"    Filtered out - {reason}: {count}")

    ranked = _apply_ranking_rules(quality_props)
    return ranked


def _apply_ranking_rules(props: List[Dict]) -> List[Dict]:
    if not props:
        return props

    props.sort(key=lambda x: x.get('edge_pct', 0), reverse=True)
    logger.info(f"  Ranking: sorted {len(props)} by edge descending")

    player_counts = {}
    player_capped = []
    for p in props:
        name = p['player_name']
        player_counts[name] = player_counts.get(name, 0) + 1
        if player_counts[name] <= MAX_PROPS_PER_PLAYER:
            player_capped.append(p)
    removed_player = len(props) - len(player_capped)
    if removed_player:
        logger.info(f"  Ranking: removed {removed_player} (max {MAX_PROPS_PER_PLAYER}/player)")

    match_counts = {}
    match_capped = []
    for p in player_capped:
        match_key = f"{p.get('home_team','')}|{p.get('away_team','')}"
        match_counts[match_key] = match_counts.get(match_key, 0) + 1
        if match_counts[match_key] <= MAX_PROPS_PER_MATCH:
            match_capped.append(p)
    removed_match = len(player_capped) - len(match_capped)
    if removed_match:
        logger.info(f"  Ranking: removed {removed_match} (max {MAX_PROPS_PER_MATCH}/match)")

    filtered = [p for p in match_capped if abs(p.get('projection_diff', 0)) >= MIN_PROJECTION_DIFF]
    removed_diff = len(match_capped) - len(filtered)
    if removed_diff:
        logger.info(f"  Ranking: removed {removed_diff} with projection diff < {MIN_PROJECTION_DIFF}")

    final = filtered[:MAX_FINAL_PROPS]
    if len(filtered) > MAX_FINAL_PROPS:
        logger.info(f"  Ranking: capped to top {MAX_FINAL_PROPS} (was {len(filtered)})")

    for i, p in enumerate(final):
        if i < PREMIUM_COUNT:
            p['is_premium'] = True
        else:
            p['is_premium'] = False

    premium_count = sum(1 for p in final if p.get('is_premium'))
    logger.info(f"  Ranking complete: {len(final)} final props, {premium_count} Premium Picks")

    return final


def _deduplicate_props(props: List[Dict]) -> List[Dict]:
    best_map = {}
    for prop in props:
        key = f"{prop['player_name']}|{prop['market']}|{prop.get('selection','')}|{prop.get('line','')}"
        if key not in best_map or prop.get('odds', 0) > best_map[key].get('odds', 0):
            best_map[key] = prop
    return list(best_map.values())


def format_quality_props_table(props: List[Dict]) -> str:
    if not props:
        return "No quality props found."

    lines = [
        f"{'Match':<35} | {'Player':<20} | {'Market':<12} | {'Line':>5} | {'Odds':>5} | {'Proj':>5} | {'Edge':>6}",
        "-" * 105
    ]

    for p in props:
        match = f"{p.get('home_team','')} vs {p.get('away_team','')}"[:35]
        player = p['player_name'][:20]
        market = p['market'].replace('player_', '')[:12]
        line = f"{p.get('line', 0):.1f}"
        odds = f"{p.get('odds', 0):.2f}"
        proj = f"{p.get('projected', 0):.1f}"
        edge = f"{p.get('edge_pct', 0):+.1f}%"

        lines.append(f"{match:<35} | {player:<20} | {market:<12} | {line:>5} | {odds:>5} | {proj:>5} | {edge:>6}")

    return "\n".join(lines)
