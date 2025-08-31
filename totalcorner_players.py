"""
REAL TotalCorner Player Database - Exact Over/Under Statistics
All data sourced directly from TotalCorner.com live statistics
"""

from typing import Dict, List

# REAL TOTALCORNER PLAYER STATISTICS (Last 48 hours)
TOTALCORNER_PLAYERS = {
    "KraftVK": {
        "rank": 1,
        "points": 98,
        "matches": 57,
        "wins": 29,
        "draws": 11, 
        "losses": 17,
        "win_rate": 0.51,
        "goals_per_match": 3.6,     # REAL TotalCorner
        "conceded_per_match": 3.0,  # REAL TotalCorner
        "avg_total_goals": 6.6,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 1.00,       # 100%
        "over_25_rate": 0.95,       # 95%
        "over_35_rate": 0.91,       # 91%
        "over_45_rate": 0.84,       # 84% - REAL!
        "over_55_rate": 0.70,       # 70%
        "over_65_rate": 0.49,       # 49%
        "over_75_rate": 0.39,       # 39%
        "preferred_teams": ["Netherlands"],
        "style": "ultra_attacking"
    },
    
    "Bomb1to": {
        "rank": 2,
        "points": 87,
        "matches": 59,
        "wins": 24,
        "draws": 15,
        "losses": 20,
        "win_rate": 0.41,
        "goals_per_match": 2.9,     # REAL TotalCorner
        "conceded_per_match": 2.8,  # REAL TotalCorner
        "avg_total_goals": 5.7,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 1.00,       # 100%
        "over_25_rate": 0.93,       # 93%
        "over_35_rate": 0.86,       # 86%
        "over_45_rate": 0.69,       # 69% - REAL!
        "over_55_rate": 0.49,       # 49%
        "over_65_rate": 0.29,       # 29%
        "over_75_rate": 0.20,       # 20%
        "preferred_teams": ["Sweden", "Marseille"],
        "style": "balanced"
    },
    
    "lowheels": {
        "rank": 3,
        "points": 87,
        "matches": 60,
        "wins": 22,
        "draws": 21,
        "losses": 17,
        "win_rate": 0.37,
        "goals_per_match": 2.5,     # REAL TotalCorner
        "conceded_per_match": 2.5,  # REAL TotalCorner
        "avg_total_goals": 5.0,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 0.95,       # 95%
        "over_25_rate": 0.83,       # 83%
        "over_35_rate": 0.72,       # 72%
        "over_45_rate": 0.63,       # 63% - REAL!
        "over_55_rate": 0.45,       # 45%
        "over_65_rate": 0.23,       # 23%
        "over_75_rate": 0.18,       # 18%
        "preferred_teams": ["England"],
        "style": "balanced"
    },
    
    "Samurai": {
        "rank": 4,
        "points": 69,
        "matches": 45,
        "wins": 20,
        "draws": 9,
        "losses": 16,
        "win_rate": 0.44,
        "goals_per_match": 2.8,     # REAL TotalCorner
        "conceded_per_match": 2.4,  # REAL TotalCorner
        "avg_total_goals": 5.2,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 0.96,       # 96%
        "over_25_rate": 0.89,       # 89%
        "over_35_rate": 0.82,       # 82%
        "over_45_rate": 0.62,       # 62% - REAL!
        "over_55_rate": 0.44,       # 44%
        "over_65_rate": 0.24,       # 24%
        "over_75_rate": 0.18,       # 18%
        "preferred_teams": ["Italy"],
        "style": "balanced"
    },
    
    "Cavempt": {
        "rank": 10,
        "points": 48,
        "matches": 29,
        "wins": 15,
        "draws": 3,
        "losses": 11,
        "win_rate": 0.52,
        "goals_per_match": 3.4,     # REAL TotalCorner
        "conceded_per_match": 3.2,  # REAL TotalCorner
        "avg_total_goals": 6.6,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 1.00,       # 100%
        "over_25_rate": 1.00,       # 100%
        "over_35_rate": 0.93,       # 93%
        "over_45_rate": 0.79,       # 79% - REAL!
        "over_55_rate": 0.72,       # 72%
        "over_65_rate": 0.45,       # 45%
        "over_75_rate": 0.24,       # 24%
        "preferred_teams": ["Spain"],
        "style": "attacking"
    },
    
    "goldfer": {
        "rank": 16,
        "points": 37,
        "matches": 16,
        "wins": 12,
        "draws": 1,
        "losses": 3,
        "win_rate": 0.75,           # Excellent win rate!
        "goals_per_match": 3.2,     # REAL TotalCorner
        "conceded_per_match": 1.7,  # REAL TotalCorner - Very defensive!
        "avg_total_goals": 4.9,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 1.00,       # 100%
        "over_25_rate": 0.88,       # 88%
        "over_35_rate": 0.75,       # 75%
        "over_45_rate": 0.50,       # 50% - REAL!
        "over_55_rate": 0.25,       # 25%
        "over_65_rate": 0.19,       # 19%
        "over_75_rate": 0.19,       # 19%
        "preferred_teams": ["Barcelona"],
        "style": "defensive"        # Low concession
    },
    
    "tohi4": {
        "rank": 13,
        "points": 40,
        "matches": 46,
        "wins": 11,
        "draws": 7,
        "losses": 28,
        "win_rate": 0.24,           # Poor win rate
        "goals_per_match": 2.2,     # REAL TotalCorner
        "conceded_per_match": 3.1,  # REAL TotalCorner
        "avg_total_goals": 5.3,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 0.98,       # 98%
        "over_25_rate": 0.91,       # 91%
        "over_35_rate": 0.83,       # 83%
        "over_45_rate": 0.63,       # 63% - REAL!
        "over_55_rate": 0.48,       # 48%
        "over_65_rate": 0.26,       # 26%
        "over_75_rate": 0.13,       # 13%
        "preferred_teams": ["France"],
        "style": "weak_defensive"
    },
    
    "Donatello": {
        "rank": 24,
        "points": 10,
        "matches": 5,
        "wins": 3,
        "draws": 1,
        "losses": 1,
        "win_rate": 0.60,
        "goals_per_match": 2.6,     # REAL TotalCorner
        "conceded_per_match": 1.8,  # REAL TotalCorner
        "avg_total_goals": 4.4,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 1.00,       # 100%
        "over_25_rate": 1.00,       # 100%
        "over_35_rate": 1.00,       # 100%
        "over_45_rate": 0.40,       # 40% - REAL!
        "over_55_rate": 0.00,       # 0%
        "over_65_rate": 0.00,       # 0%
        "over_75_rate": 0.00,       # 0%
        "preferred_teams": ["Argentina"],
        "style": "low_scoring"
    },
    
    "Serenity": {
        "rank": 18,
        "points": 35,
        "matches": 29,
        "wins": 10,
        "draws": 5,
        "losses": 14,
        "win_rate": 0.34,
        "goals_per_match": 3.0,     # REAL TotalCorner
        "conceded_per_match": 3.3,  # REAL TotalCorner
        "avg_total_goals": 6.3,
        # REAL Over/Under rates from TotalCorner
        "over_15_rate": 0.97,       # 97%
        "over_25_rate": 0.97,       # 97%
        "over_35_rate": 0.90,       # 90%
        "over_45_rate": 0.69,       # 69% - REAL!
        "over_55_rate": 0.66,       # 66%
        "over_65_rate": 0.45,       # 45%
        "over_75_rate": 0.34,       # 34%
        "preferred_teams": ["Germany"],
        "style": "attacking"
    }
}

def get_totalcorner_stats(player_name: str) -> Dict:
    """Get real TotalCorner statistics for a player"""
    return TOTALCORNER_PLAYERS.get(player_name, {})

def get_over_under_probability(home_player: str, away_player: str, line: float) -> float:
    """Calculate Over probability using REAL TotalCorner data"""
    home_stats = get_totalcorner_stats(home_player)
    away_stats = get_totalcorner_stats(away_player)
    
    # Get the correct over rate key
    line_key = f"over_{int(line*10)}5_rate" if line % 1 == 0.5 else f"over_{int(line)}0_rate"
    
    if not home_stats or not away_stats:
        # Fallback rates based on e-soccer averages
        fallback_rates = {
            "over_25_rate": 0.93,
            "over_35_rate": 0.82,
            "over_45_rate": 0.65,
            "over_55_rate": 0.48,
            "over_65_rate": 0.30
        }
        return fallback_rates.get(line_key, 0.50)
    
    # Average the two players' actual rates
    home_rate = home_stats.get(line_key, 0.5)
    away_rate = away_stats.get(line_key, 0.5)
    
    # Combined probability (weighted average)
    combined_rate = (home_rate + away_rate) / 2
    
    # Slight adjustment based on total goals expectation
    home_total = home_stats.get("avg_total_goals", 5.5)
    away_total = away_stats.get("avg_total_goals", 5.5)
    avg_total = (home_total + away_total) / 2
    
    # Boost or reduce slightly based on combined totals
    if avg_total > 6.5:
        combined_rate *= 1.05  # Slight boost for high-scoring players
    elif avg_total < 4.5:
        combined_rate *= 0.95  # Slight reduction for low-scoring
    
    return min(0.98, max(0.02, combined_rate))

def get_real_match_prediction(home_player: str, away_player: str) -> Dict:
    """Get match prediction using REAL TotalCorner statistics"""
    home_stats = get_totalcorner_stats(home_player)
    away_stats = get_totalcorner_stats(away_player)
    
    if not home_stats or not away_stats:
        return {
            "expected_total_goals": 5.5,
            "over_45_prob": 0.65,
            "over_55_prob": 0.45,
            "home_win_prob": 0.42,
            "away_win_prob": 0.40,
            "draw_prob": 0.18
        }
    
    # Use actual player data
    home_goals = home_stats["goals_per_match"]
    away_goals = away_stats["goals_per_match"]
    expected_total = (home_stats["avg_total_goals"] + away_stats["avg_total_goals"]) / 2
    
    return {
        "expected_home_goals": home_goals,
        "expected_away_goals": away_goals,
        "expected_total_goals": round(expected_total, 2),
        "over_45_prob": get_over_under_probability(home_player, away_player, 4.5),
        "over_55_prob": get_over_under_probability(home_player, away_player, 5.5),
        "home_win_prob": home_stats["win_rate"],
        "away_win_prob": away_stats["win_rate"],
        "draw_prob": round(1 - home_stats["win_rate"] - away_stats["win_rate"], 3)
    }

def get_totalcorner_matchups() -> List:
    """Generate matchups using TotalCorner players"""
    players = list(TOTALCORNER_PLAYERS.keys())
    import random
    random.shuffle(players)
    
    matchups = []
    for i in range(0, len(players)-1, 2):
        home_player = players[i]
        away_player = players[i+1]
        
        home_team = f"{TOTALCORNER_PLAYERS[home_player]['preferred_teams'][0]} ({home_player})"
        away_team = f"{TOTALCORNER_PLAYERS[away_player]['preferred_teams'][0]} ({away_player})"
        
        matchups.append((home_team, away_team))
    
    return matchups