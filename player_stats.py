"""
Real Esoccer Battle Player Statistics Database
Data sourced from live rankings and performance tracking
"""

# Real player statistics from Esoccer Battle 8-minute matches
PLAYER_STATS = {
    # Top tier performers
    "goldfer": {
        "rank": 1,
        "points": 135,
        "matches": 62,
        "win_rate": 0.55,
        "loss_rate": 0.25,
        "draw_rate": 0.20,
        "goals_per_match": 2.61,
        "conceded_per_match": 1.82,
        "preferred_teams": ["Barcelona", "Real Madrid"],
        "style": "defensive",  # Low concession rate
        "form": "excellent"
    },
    
    "Samurai": {
        "rank": 2, 
        "points": 105,
        "matches": 64,
        "win_rate": 0.40,
        "loss_rate": 0.37,
        "draw_rate": 0.23,
        "goals_per_match": 3.1,
        "conceded_per_match": 3.1,
        "preferred_teams": ["Italy", "Juventus"],
        "style": "balanced",  # Equal goals for/against
        "form": "good"
    },
    
    "Cavempt": {
        "rank": 3,
        "points": 100,
        "matches": 62,
        "win_rate": 0.57,
        "loss_rate": 0.23,
        "draw_rate": 0.20,
        "goals_per_match": 3.29,
        "conceded_per_match": 2.28,
        "preferred_teams": ["Spain", "Barcelona"],
        "style": "attacking",  # High goal output
        "form": "very_good"
    },
    
    "Yakuza": {
        "rank": 4,
        "points": 120,
        "matches": 58,
        "win_rate": 0.69,  # Highest win rate!
        "loss_rate": 0.19,
        "draw_rate": 0.12,
        "goals_per_match": 2.83,
        "conceded_per_match": 1.51,  # Very defensive
        "preferred_teams": ["Liverpool", "England"],
        "style": "ultra_defensive",
        "form": "excellent"
    },
    
    "Venci": {
        "rank": 5,
        "points": 118,
        "matches": 55,
        "win_rate": 0.64,
        "loss_rate": 0.21,
        "draw_rate": 0.15,
        "goals_per_match": 5.55,  # HIGHEST SCORING!
        "conceded_per_match": 4.25,
        "preferred_teams": ["USA", "Newcastle United"],
        "style": "ultra_attacking",  # Very high scoring games
        "form": "excellent"
    },
    
    "Leolol_pepsi": {
        "rank": 6,
        "points": 110,
        "matches": 60,
        "win_rate": 0.58,
        "loss_rate": 0.25,
        "draw_rate": 0.17,
        "goals_per_match": 3.3,
        "conceded_per_match": 2.38,
        "preferred_teams": ["Newcastle", "Mexico"],
        "style": "attacking",
        "form": "very_good"
    },
    
    "Kray": {
        "rank": 7,
        "points": 124,
        "matches": 63,
        "win_rate": 0.52,
        "loss_rate": 0.30,
        "draw_rate": 0.18,
        "goals_per_match": 2.9,
        "conceded_per_match": 2.1,
        "preferred_teams": ["PSG", "France"],
        "style": "balanced",
        "form": "good"
    },
    
    "Romeo": {
        "rank": 8,
        "points": 108,
        "matches": 57,
        "win_rate": 0.60,
        "loss_rate": 0.23,
        "draw_rate": 0.17,
        "goals_per_match": 2.8,
        "conceded_per_match": 1.75,
        "preferred_teams": ["Atalanta", "Spain"],
        "style": "defensive",
        "form": "very_good"
    },
    
    "Matrix": {
        "rank": 9,
        "points": 105,
        "matches": 59,
        "win_rate": 0.58,
        "loss_rate": 0.25,
        "draw_rate": 0.17,
        "goals_per_match": 3.25,
        "conceded_per_match": 2.3,
        "preferred_teams": ["West Ham", "Manchester City"],
        "style": "attacking",
        "form": "very_good"
    },
    
    "Alexis": {
        "rank": 10,
        "points": 102,
        "matches": 61,
        "win_rate": 0.58,
        "loss_rate": 0.26,
        "draw_rate": 0.16,
        "goals_per_match": 3.38,
        "conceded_per_match": 2.32,
        "preferred_teams": ["Netherlands", "PSG"],
        "style": "attacking",
        "form": "very_good"
    }
}

def get_player_stats(player_name: str) -> dict:
    """Get statistics for a specific player"""
    return PLAYER_STATS.get(player_name, {})

def get_match_prediction(home_player: str, away_player: str) -> dict:
    """Predict match outcome based on player statistics"""
    home_stats = get_player_stats(home_player)
    away_stats = get_player_stats(away_player)
    
    if not home_stats or not away_stats:
        # Default prediction if player not found
        return {
            "expected_home_goals": 2.5,
            "expected_away_goals": 2.5,
            "expected_total_goals": 5.0,
            "home_win_prob": 0.45,
            "away_win_prob": 0.45,
            "draw_prob": 0.10
        }
    
    # Calculate expected goals based on player tendencies
    home_attack_strength = home_stats["goals_per_match"] / 3.0  # Normalize to strength
    away_attack_strength = away_stats["goals_per_match"] / 3.0
    
    home_defense_strength = 3.0 / home_stats["conceded_per_match"]  # Inverse for defense
    away_defense_strength = 3.0 / away_stats["conceded_per_match"]
    
    # Expected goals calculation
    expected_home_goals = home_attack_strength * (1 / away_defense_strength) * 2.5
    expected_away_goals = away_attack_strength * (1 / home_defense_strength) * 2.5
    expected_total_goals = expected_home_goals + expected_away_goals
    
    # Win probabilities based on player form and stats
    home_strength = home_stats["win_rate"] * 1.2 if home_stats.get("form") == "excellent" else home_stats["win_rate"]
    away_strength = away_stats["win_rate"] * 1.2 if away_stats.get("form") == "excellent" else away_stats["win_rate"]
    
    total_strength = home_strength + away_strength
    home_win_prob = home_strength / total_strength * 0.8  # 80% based on strength
    away_win_prob = away_strength / total_strength * 0.8
    draw_prob = 0.4 - (home_win_prob + away_win_prob - 0.8)  # Remainder
    
    # Normalize probabilities
    total_prob = home_win_prob + away_win_prob + draw_prob
    
    return {
        "expected_home_goals": round(expected_home_goals, 2),
        "expected_away_goals": round(expected_away_goals, 2),
        "expected_total_goals": round(expected_total_goals, 2),
        "home_win_prob": round(home_win_prob / total_prob, 3),
        "away_win_prob": round(away_win_prob / total_prob, 3),
        "draw_prob": round(draw_prob / total_prob, 3)
    }

def get_real_matchups() -> list:
    """Generate realistic matchups based on actual player pool"""
    players = list(PLAYER_STATS.keys())
    matchups = []
    
    # Create realistic matchups - avoid same player vs themselves
    import random
    random.shuffle(players)
    
    for i in range(0, len(players)-1, 2):
        home_player = players[i]
        away_player = players[i+1]
        
        # Use their preferred teams when available
        home_team = f"{PLAYER_STATS[home_player]['preferred_teams'][0]} ({home_player})"
        away_team = f"{PLAYER_STATS[away_player]['preferred_teams'][0]} ({away_player})"
        
        matchups.append((home_team, away_team))
    
    return matchups