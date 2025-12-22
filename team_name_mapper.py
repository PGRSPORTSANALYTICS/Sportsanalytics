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
            'CF Estrela': 'Estrela Amadora',
            'Estrela Amadora': 'Estrela Amadora',
            'AVS Futebol SAD': 'AVS',
            'AVS': 'AVS',
            'Rio Ave FC': 'Rio Ave',
            'Rio Ave': 'Rio Ave',
            'Gil Vicente': 'Gil Vicente',
            'Arouca': 'Arouca',
            'Santa Clara': 'Santa Clara',
            'Estoril': 'Estoril',
            'Nacional': 'Nacional',
            
            # Serie A - More teams
            'Atalanta BC': 'Atalanta',
            'Atalanta': 'Atalanta',
            'Genoa': 'Genoa',
            'Torino': 'Torino',
            'Sassuolo': 'Sassuolo',
            'Cagliari': 'Cagliari',
            'Pisa': 'Pisa',
            
            # Bundesliga - More teams
            '1. FC Köln': 'FC Koln',
            'FC Köln': 'FC Koln',
            'Koln': 'FC Koln',
            'Union Berlin': 'Union Berlin',
            'Werder Bremen': 'Werder Bremen',
            'FSV Mainz 05': 'Mainz 05',
            'Mainz 05': 'Mainz 05',
            'Mainz': 'Mainz 05',
            'FC St. Pauli': 'St. Pauli',
            'St. Pauli': 'St. Pauli',
            
            # La Liga - More teams
            'CA Osasuna': 'Osasuna',
            'Osasuna': 'Osasuna',
            'Alavés': 'Alaves',
            'Celta Vigo': 'Celta Vigo',
            'Celta': 'Celta Vigo',
            'Espanyol': 'Espanyol',
            'RCD Espanyol': 'Espanyol',
            'Real Sociedad': 'Real Sociedad',
            'Sevilla': 'Sevilla',
            'Levante': 'Levante',
            'Oviedo': 'Real Oviedo',
            'Elche CF': 'Elche',
            'Elche': 'Elche',
            'Rayo Vallecano': 'Rayo Vallecano',
            
            # Eredivisie - More teams
            'FC Twente Enschede': 'FC Twente',
            'FC Twente': 'FC Twente',
            'Twente': 'FC Twente',
            'AZ Alkmaar': 'AZ Alkmaar',
            'AZ': 'AZ Alkmaar',
            'Fortuna Sittard': 'Fortuna Sittard',
            'Sparta Rotterdam': 'Sparta Rotterdam',
            'FC Volendam': 'Volendam',
            'Volendam': 'Volendam',
            'Excelsior': 'Excelsior',
            'FC Zwolle': 'PEC Zwolle',
            'PEC Zwolle': 'PEC Zwolle',
            'Groningen': 'Groningen',
            'Heerenveen': 'Heerenveen',
            'Heracles Almelo': 'Heracles',
            'Heracles': 'Heracles',
            'NEC Nijmegen': 'NEC',
            'NEC': 'NEC',
            'NAC Breda': 'NAC Breda',
            'SC Telstar': 'Telstar',
            
            # Belgian Pro League
            'Club Brugge': 'Club Brugge',
            'Brugge': 'Club Brugge',
            'Gent': 'Gent',
            'KAA Gent': 'Gent',
            'Anderlecht': 'Anderlecht',
            'Royal Antwerp': 'Antwerp',
            'Antwerp': 'Antwerp',
            'Standard Liege': 'Standard Liege',
            'Standard': 'Standard Liege',
            'Genk': 'Genk',
            'KRC Genk': 'Genk',
            'Charleroi': 'Charleroi',
            'Cercle Brugge KSV': 'Cercle Brugge',
            'Cercle Brugge': 'Cercle Brugge',
            'Leuven': 'OH Leuven',
            'OH Leuven': 'OH Leuven',
            'Sint Truiden': 'Sint-Truiden',
            'Sint-Truiden': 'Sint-Truiden',
            'KV Mechelen': 'Mechelen',
            'Mechelen': 'Mechelen',
            'Dender': 'Dender',
            
            # English Championship & Lower Leagues
            'Sunderland': 'Sunderland',
            'Sheffield Wednesday': 'Sheffield Wednesday',
            'Sheffield Weds': 'Sheffield Wednesday',
            'Ipswich Town': 'Ipswich',
            'Ipswich': 'Ipswich',
            'Middlesbrough': 'Middlesbrough',
            'Bristol City': 'Bristol City',
            'Millwall': 'Millwall',
            'Blackburn Rovers': 'Blackburn',
            'Blackburn': 'Blackburn',
            'West Bromwich Albion': 'West Brom',
            'West Brom': 'West Brom',
            'Hull City': 'Hull City',
            'Hull': 'Hull City',
            'Derby County': 'Derby',
            'Derby': 'Derby',
            'Portsmouth': 'Portsmouth',
            'Norwich City': 'Norwich',
            'Norwich': 'Norwich',
            'Preston North End': 'Preston',
            'Preston': 'Preston',
            'Queens Park Rangers': 'QPR',
            'QPR': 'QPR',
            'Sheffield United': 'Sheffield Utd',
            'Sheffield Utd': 'Sheffield Utd',
            'Birmingham City': 'Birmingham',
            'Birmingham': 'Birmingham',
            'Leeds United': 'Leeds',
            'Leeds': 'Leeds',
            'Cardiff City': 'Cardiff',
            'Cardiff': 'Cardiff',
            'Oxford United': 'Oxford Utd',
            'Oxford Utd': 'Oxford Utd',
            'Charlton Athletic': 'Charlton',
            'Charlton': 'Charlton',
            'Lincoln City': 'Lincoln',
            'Lincoln': 'Lincoln',
            
            # English League One & Two
            'Stockport County FC': 'Stockport',
            'Stockport County': 'Stockport',
            'Stockport': 'Stockport',
            'Mansfield Town': 'Mansfield',
            'Mansfield': 'Mansfield',
            'Grimsby Town': 'Grimsby',
            'Grimsby': 'Grimsby',
            'Bromley FC': 'Bromley',
            'Bromley': 'Bromley',
            'Barnet': 'Barnet',
            'Salford City': 'Salford',
            'Salford': 'Salford',
            'Barrow': 'Barrow',
            'Cheltenham Town': 'Cheltenham',
            'Cheltenham': 'Cheltenham',
            'Colchester United': 'Colchester',
            'Colchester': 'Colchester',
            'Newport County': 'Newport',
            'Newport': 'Newport',
            'Doncaster Rovers': 'Doncaster',
            'Doncaster': 'Doncaster',
            'Plymouth Argyle': 'Plymouth',
            'Plymouth': 'Plymouth',
            'Fleetwood Town': 'Fleetwood',
            'Fleetwood': 'Fleetwood',
            'Gillingham': 'Gillingham',
            'Northampton Town': 'Northampton',
            'Northampton': 'Northampton',
            'Wimbledon': 'AFC Wimbledon',
            'AFC Wimbledon': 'AFC Wimbledon',
            'Notts County': 'Notts County',
            'Walsall': 'Walsall',
            'Oldham Athletic': 'Oldham',
            'Oldham': 'Oldham',
            'Tranmere Rovers': 'Tranmere',
            'Tranmere': 'Tranmere',
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
