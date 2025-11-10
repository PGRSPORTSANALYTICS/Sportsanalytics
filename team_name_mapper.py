"""
Team Name Mapper
Standardizes team names across different data sources
Critical for combining FBref, Understat, Odds API data
"""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class TeamNameMapper:
    """
    Maps team names between different APIs and sources
    Each source uses slightly different team names
    """
    
    def __init__(self):
        # Mapping: Odds API name -> Standard name
        # NOTE: Keep canonical names simple to avoid breaking Understat/FBref integrations
        self.standardized_names = {
            # Premier League
            'Manchester City': 'Manchester City',
            'Man City': 'Manchester City',
            'Arsenal': 'Arsenal',
            'Liverpool': 'Liverpool',
            'Chelsea': 'Chelsea',
            'Manchester United': 'Manchester United',
            'Man Utd': 'Manchester United',
            'Man United': 'Manchester United',
            'Tottenham': 'Tottenham',
            'Tottenham Hotspur': 'Tottenham',
            'Spurs': 'Tottenham',
            'Newcastle': 'Newcastle United',
            'Newcastle United': 'Newcastle United',
            'West Ham': 'West Ham United',
            'West Ham United': 'West Ham United',
            'Wolverhampton': 'Wolverhampton',
            'Wolverhampton Wanderers': 'Wolverhampton',
            'Wolves': 'Wolverhampton',
            'Brighton': 'Brighton',
            'Brighton and Hove Albion': 'Brighton',
            'Brighton & Hove Albion': 'Brighton',
            'Nottingham Forest': 'Nottingham Forest',
            'Forest': 'Nottingham Forest',
            'Leicester': 'Leicester City',
            'Leicester City': 'Leicester City',
            'Crystal Palace': 'Crystal Palace',
            'Everton': 'Everton',
            'Brentford': 'Brentford',
            'Fulham': 'Fulham',
            'Bournemouth': 'Bournemouth',
            'AFC Bournemouth': 'Bournemouth',
            
            # La Liga - CRITICAL FIXES for 226 pending SGPs
            'Real Madrid': 'Real Madrid',
            'Barcelona': 'Barcelona',
            'Atletico Madrid': 'Atletico Madrid',
            'Atlético Madrid': 'Atletico Madrid',
            'Athletic Bilbao': 'Athletic Club',
            'Athletic Club': 'Athletic Club',
            'Athletic de Bilbao': 'Athletic Club',
            'Real Betis': 'Real Betis',
            'Betis': 'Real Betis',
            'Valencia': 'Valencia',
            'Mallorca': 'Mallorca',
            'Getafe': 'Getafe',
            'Alaves': 'Alaves',
            'Deportivo Alaves': 'Alaves',
            'Oviedo': 'Real Oviedo',
            'Real Oviedo': 'Real Oviedo',
            
            # Bundesliga
            'Bayern Munich': 'Bayern Munich',
            'Bayern München': 'Bayern Munich',
            'Bayern': 'Bayern Munich',
            'Borussia Dortmund': 'Dortmund',
            'Dortmund': 'Dortmund',
            'VfB Stuttgart': 'VfB Stuttgart',
            'Stuttgart': 'VfB Stuttgart',
            'Augsburg': 'Augsburg',
            
            # Serie A
            'Inter': 'Inter',
            'Inter Milan': 'Inter',
            'AC Milan': 'Milan',
            'Milan': 'Milan',
            'Juventus': 'Juventus',
            'AS Roma': 'AS Roma',
            'Roma': 'AS Roma',
            'Napoli': 'Napoli',
            'Bologna': 'Bologna',
            'Udinese': 'Udinese',
            
            # Ligue 1
            'Paris Saint Germain': 'Paris S-G',
            'PSG': 'Paris S-G',
            'Paris Saint-Germain': 'Paris S-G',
            'Marseille': 'Marseille',
            'Lyon': 'Lyon',
            
            # Eredivisie - CRITICAL FIX for case sensitivity
            'Ajax': 'Ajax',
            'Ajax Amsterdam': 'Ajax',
            'PSV': 'PSV Eindhoven',
            'PSV Eindhoven': 'PSV Eindhoven',
            'Feyenoord': 'Feyenoord',
            'Feyenoord Rotterdam': 'Feyenoord',
            'GO Ahead Eagles': 'Go Ahead Eagles',
            'Go Ahead Eagles': 'Go Ahead Eagles',
            
            # Primeira Liga
            'Benfica': 'Benfica',
            'Porto': 'Porto',
            'FC Porto': 'Porto',
            'Sporting': 'Sporting CP',
            'Sporting CP': 'Sporting CP',
            'Sporting Lisbon': 'Sporting CP',
            'Braga': 'Braga',
            'Moreirense': 'Moreirense FC',
            'Moreirense FC': 'Moreirense FC',
        }
        
        # FBref specific variations
        self.fbref_variations = {
            'Manchester City': 'Manchester City',
            'Arsenal': 'Arsenal',
            'Liverpool': 'Liverpool',
            'Manchester Utd': 'Manchester United',
            'Tottenham': 'Tottenham',
        }
        
        # Understat specific variations
        self.understat_variations = {
            'Manchester_City': 'Manchester City',
            'Manchester_United': 'Manchester United',
            'Tottenham': 'Tottenham',
            'Newcastle_United': 'Newcastle United',
        }
    
    def standardize(self, team_name: str) -> str:
        """
        Convert any team name to standardized form
        
        Args:
            team_name: Team name from any source
            
        Returns:
            Standardized team name
        """
        # Try direct lookup
        if team_name in self.standardized_names:
            return self.standardized_names[team_name]
        
        # Try case-insensitive lookup
        for key, value in self.standardized_names.items():
            if key.lower() == team_name.lower():
                return value
        
        # Return as-is if no mapping found
        logger.warning(f"No standardization found for: {team_name}")
        return team_name
    
    def to_fbref(self, team_name: str) -> str:
        """Convert to FBref format"""
        standard = self.standardize(team_name)
        return self.fbref_variations.get(standard, standard)
    
    def to_understat(self, team_name: str) -> str:
        """Convert to Understat format (uses underscores)"""
        standard = self.standardize(team_name)
        
        # Check if we have specific mapping
        for key, value in self.understat_variations.items():
            if value == standard:
                return key
        
        # Default: replace spaces with underscores
        return standard.replace(' ', '_')
    
    def add_mapping(self, team_name: str, standard_name: str):
        """Add custom team mapping"""
        self.standardized_names[team_name] = standard_name
        logger.info(f"Added mapping: {team_name} -> {standard_name}")


if __name__ == '__main__':
    mapper = TeamNameMapper()
    
    print("="*80)
    print("TEAM NAME MAPPER TEST")
    print("="*80)
    
    test_names = [
        'Man City',
        'Manchester United',
        'Tottenham Hotspur',
        'Paris Saint Germain',
        'Bayern München'
    ]
    
    print("\n🔄 Testing name standardization:")
    for name in test_names:
        standard = mapper.standardize(name)
        fbref = mapper.to_fbref(name)
        understat = mapper.to_understat(name)
        
        print(f"\n   {name}")
        print(f"   → Standard: {standard}")
        print(f"   → FBref: {fbref}")
        print(f"   → Understat: {understat}")
    
    print("\n" + "="*80)
    print("✅ Name mapping ensures compatibility across all data sources")
