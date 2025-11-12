"""
Team ID mappings for API-Football
Maps common team names from The Odds API to API-Football team IDs
"""

# Premier League team IDs (season 2024/2025)
PREMIER_LEAGUE_TEAMS = {
    'Arsenal': 42,
    'Aston Villa': 66,
    'Bournemouth': 35,
    'Brentford': 55,
    'Brighton and Hove Albion': 51,
    'Brighton': 51,
    'Burnley': 44,
    'Chelsea': 49,
    'Crystal Palace': 52,
    'Everton': 45,
    'Fulham': 36,
    'Leeds United': 63,
    'Leeds': 63,
    'Leicester City': 46,
    'Liverpool': 40,
    'Manchester City': 50,
    'Manchester United': 33,
    'Newcastle United': 34,
    'Newcastle': 34,
    'Nottingham Forest': 65,
    'Southampton': 41,
    'Tottenham Hotspur': 47,
    'Tottenham': 47,
    'West Ham United': 48,
    'West Ham': 48,
    'Wolverhampton Wanderers': 39,
    'Wolves': 39,
}

# La Liga team IDs
LA_LIGA_TEAMS = {
    'Alavés': 720,
    'Athletic Bilbao': 531,
    'Atlético Madrid': 530,
    'Barcelona': 529,
    'Celta Vigo': 538,
    'Espanyol': 540,
    'Getafe': 546,
    'Girona': 547,
    'Las Palmas': 728,
    'Mallorca': 798,
    'Osasuna': 727,
    'CA Osasuna': 727,
    'Rayo Vallecano': 728,
    'Real Betis': 543,
    'Real Madrid': 541,
    'Real Sociedad': 548,
    'Sevilla': 536,
    'Valencia': 532,
    'Valladolid': 720,
    'Villarreal': 533,
}

# Serie A team IDs
SERIE_A_TEAMS = {
    'Atalanta BC': 499,
    'Atalanta': 499,
    'Bologna': 500,
    'Cagliari': 490,
    'Como': 512,
    'Empoli': 511,
    'Fiorentina': 502,
    'Genoa': 491,
    'Hellas Verona': 504,
    'Inter Milan': 505,
    'Inter': 505,
    'Juventus': 496,
    'Lazio': 487,
    'AC Milan': 489,
    'Milan': 489,
    'Monza': 1579,
    'Napoli': 492,
    'Parma': 488,
    'AS Roma': 497,
    'Roma': 497,
    'Salernitana': 514,
    'Sassuolo': 488,
    'Torino': 503,
    'Udinese': 494,
}

# Bundesliga team IDs  
BUNDESLIGA_TEAMS = {
    'Augsburg': 159,
    'Bayer Leverkusen': 168,
    'Bayern München': 157,
    'Bayern Munich': 157,
    'Borussia Dortmund': 165,
    'Borussia Mönchengladbach': 163,
    'Eintracht Frankfurt': 169,
    'Freiburg': 160,
    'Heidenheim': 172,
    'Hoffenheim': 164,
    'RB Leipzig': 173,
    'Mainz': 162,
    'St. Pauli': 192,
    'Union Berlin': 28,
    'VfB Stuttgart': 174,
    'Werder Bremen': 161,
    'Wolfsburg': 170,
}

# Ligue 1 team IDs
LIGUE_1_TEAMS = {
    'Angers': 77,
    'AJ Auxerre': 84,
    'Brest': 81,
    'Le Havre': 83,
    'Lens': 80,
    'Lille': 79,
    'Lyon': 85,
    'Marseille': 81,
    'Monaco': 91,
    'Montpellier': 82,
    'Nantes': 78,
    'Nice': 82,
    'Paris Saint Germain': 85,
    'PSG': 85,
    'Reims': 547,
    'Rennes': 99,
    'Saint-Étienne': 1063,
    'Strasbourg': 167,
    'Toulouse': 97,
}

# Champions League frequent teams
CHAMPIONS_LEAGUE_TEAMS = {
    'Club Brugge': 569,
    'Porto': 212,
    'Benfica': 211,
    'Celtic': 247,
    'Rangers': 247,
    'Shakhtar Donetsk': 553,
}

# Brazilian Serie A team IDs
BRAZIL_SERIE_A_TEAMS = {
    'Atletico Mineiro': 129,
    'Atletico-MG': 129,
    'Athletico Paranaense': 130,
    'Athletico-PR': 130,
    'Bahia': 134,
    'Botafogo': 125,
    'Corinthians': 131,
    'Cruzeiro': 132,
    'Cuiaba': 1207,
    'Flamengo': 127,
    'Fluminense': 124,
    'Fortaleza': 128,
    'Gremio': 136,
    'Internacional': 135,
    'Juventude': 1195,
    'Palmeiras': 126,
    'Red Bull Bragantino': 1217,
    'Bragantino': 1217,
    'Santos': 123,
    'Sao Paulo': 137,
    'Vasco da Gama': 139,
    'Vasco': 139,
}

# Japanese J1 League team IDs
JAPAN_J1_TEAMS = {
    'Avispa Fukuoka': 2803,
    'Cerezo Osaka': 280,
    'Consadole Sapporo': 283,
    'FC Tokyo': 281,
    'Gamba Osaka': 285,
    'Jubilo Iwata': 291,
    'Kashima Antlers': 292,
    'Kashiwa Reysol': 293,
    'Kawasaki Frontale': 294,
    'Kyoto Sanga': 6130,
    'Nagoya Grampus': 289,
    'Sanfrecce Hiroshima': 295,
    'Sapporo': 283,
    'Shonan Bellmare': 6128,
    'Tokyo Verdy': 6131,
    'Urawa Red Diamonds': 286,
    'Urawa Reds': 286,
    'Vissel Kobe': 290,
    'Yokohama F. Marinos': 284,
    'Yokohama FM': 284,
}

# Combine all mappings
ALL_TEAM_MAPPINGS = {}
ALL_TEAM_MAPPINGS.update(PREMIER_LEAGUE_TEAMS)
ALL_TEAM_MAPPINGS.update(LA_LIGA_TEAMS)
ALL_TEAM_MAPPINGS.update(SERIE_A_TEAMS)
ALL_TEAM_MAPPINGS.update(BUNDESLIGA_TEAMS)
ALL_TEAM_MAPPINGS.update(LIGUE_1_TEAMS)
ALL_TEAM_MAPPINGS.update(CHAMPIONS_LEAGUE_TEAMS)
ALL_TEAM_MAPPINGS.update(BRAZIL_SERIE_A_TEAMS)
ALL_TEAM_MAPPINGS.update(JAPAN_J1_TEAMS)


def get_team_id_from_mapping(team_name: str) -> int:
    """Get team ID from hardcoded mappings"""
    # Try exact match first
    if team_name in ALL_TEAM_MAPPINGS:
        return ALL_TEAM_MAPPINGS[team_name]
    
    # Try case-insensitive match
    for mapped_name, team_id in ALL_TEAM_MAPPINGS.items():
        if mapped_name.lower() == team_name.lower():
            return team_id
    
    # Try partial match
    team_lower = team_name.lower()
    for mapped_name, team_id in ALL_TEAM_MAPPINGS.items():
        if team_lower in mapped_name.lower() or mapped_name.lower() in team_lower:
            return team_id
    
    return None
