"""
Unified League Registry - Single source of truth for all leagues
Maps The Odds API keys to API-Football IDs with metadata
"""

from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class LeagueConfig:
    """League configuration with dual API mapping"""
    name: str
    odds_api_key: str  # The Odds API sport key (e.g., 'soccer_epl')
    api_football_id: int  # API-Football league ID (e.g., 39)
    country: str
    tier: int  # 1=Premium, 2=Standard, 3=Value
    active: bool = True
    season: int = 2024  # Current season
    timezone: str = "Europe/London"  # For match scheduling


# Complete league registry - editable programmatically
LEAGUE_REGISTRY: List[LeagueConfig] = [
    # === EUROPEAN PREMIER TIER (Tier 1) ===
    LeagueConfig(
        name="Premier League",
        odds_api_key="soccer_epl",
        api_football_id=39,
        country="England",
        tier=1,
        timezone="Europe/London"
    ),
    LeagueConfig(
        name="La Liga",
        odds_api_key="soccer_spain_la_liga",
        api_football_id=140,
        country="Spain",
        tier=1,
        timezone="Europe/Madrid"
    ),
    LeagueConfig(
        name="Serie A",
        odds_api_key="soccer_italy_serie_a",
        api_football_id=135,
        country="Italy",
        tier=1,
        timezone="Europe/Rome"
    ),
    LeagueConfig(
        name="Bundesliga",
        odds_api_key="soccer_germany_bundesliga",
        api_football_id=78,
        country="Germany",
        tier=1,
        timezone="Europe/Berlin"
    ),
    LeagueConfig(
        name="Ligue 1",
        odds_api_key="soccer_france_ligue_one",
        api_football_id=61,
        country="France",
        tier=1,
        timezone="Europe/Paris"
    ),
    
    # === EUROPEAN SECONDARY TIER (Tier 2) ===
    LeagueConfig(
        name="English Championship",
        odds_api_key="soccer_efl_champ",
        api_football_id=40,
        country="England",
        tier=2,
        timezone="Europe/London"
    ),
    LeagueConfig(
        name="Eredivisie",
        odds_api_key="soccer_netherlands_eredivisie",
        api_football_id=88,
        country="Netherlands",
        tier=2,
        timezone="Europe/Amsterdam"
    ),
    LeagueConfig(
        name="Primeira Liga",
        odds_api_key="soccer_portugal_primeira_liga",
        api_football_id=94,
        country="Portugal",
        tier=2,
        timezone="Europe/Lisbon"
    ),
    LeagueConfig(
        name="Belgian First Division",
        odds_api_key="soccer_belgium_first_div",
        api_football_id=144,
        country="Belgium",
        tier=2,
        timezone="Europe/Brussels"
    ),
    LeagueConfig(
        name="Scottish Premiership",
        odds_api_key="soccer_scotland_premiership",
        api_football_id=179,
        country="Scotland",
        tier=2,
        timezone="Europe/London"
    ),
    
    # === EUROPEAN CUPS (Tier 1) ===
    LeagueConfig(
        name="Champions League",
        odds_api_key="soccer_uefa_champs_league",
        api_football_id=2,
        country="Europe",
        tier=1,
        timezone="Europe/London"
    ),
    LeagueConfig(
        name="Europa League",
        odds_api_key="soccer_uefa_europa_league",
        api_football_id=3,
        country="Europe",
        tier=1,
        timezone="Europe/London"
    ),
    LeagueConfig(
        name="Conference League",
        odds_api_key="soccer_uefa_conference_league",
        api_football_id=848,
        country="Europe",
        tier=2,
        timezone="Europe/London"
    ),
    
    # === LOWER TIER EUROPEAN LEAGUES (Tier 3) - HIGH VALUE TARGETS ===
    LeagueConfig(
        name="English League One",
        odds_api_key="soccer_england_league1",
        api_football_id=41,
        country="England",
        tier=3,
        timezone="Europe/London"
    ),
    LeagueConfig(
        name="English League Two",
        odds_api_key="soccer_england_league2",
        api_football_id=42,
        country="England",
        tier=3,
        timezone="Europe/London"
    ),
    LeagueConfig(
        name="German 2. Bundesliga",
        odds_api_key="soccer_germany_bundesliga2",
        api_football_id=79,
        country="Germany",
        tier=3,
        timezone="Europe/Berlin"
    ),
    LeagueConfig(
        name="Italian Serie B",
        odds_api_key="soccer_italy_serie_b",
        api_football_id=136,
        country="Italy",
        tier=3,
        timezone="Europe/Rome"
    ),
    LeagueConfig(
        name="Spanish Segunda Division",
        odds_api_key="soccer_spain_segunda_division",
        api_football_id=141,
        country="Spain",
        tier=3,
        timezone="Europe/Madrid"
    ),
    LeagueConfig(
        name="French Ligue 2",
        odds_api_key="soccer_france_ligue_two",
        api_football_id=62,
        country="France",
        tier=3,
        timezone="Europe/Paris"
    ),
    LeagueConfig(
        name="Dutch Eerste Divisie",
        odds_api_key="soccer_netherlands_eerste_divisie",
        api_football_id=89,
        country="Netherlands",
        tier=3,
        timezone="Europe/Amsterdam"
    ),
    LeagueConfig(
        name="Portuguese Segunda Liga",
        odds_api_key="soccer_portugal_segunda_liga",
        api_football_id=95,
        country="Portugal",
        tier=3,
        timezone="Europe/Lisbon"
    ),
    
    # === NORDIC & EASTERN EUROPE (Tier 3) ===
    LeagueConfig(
        name="Swedish Allsvenskan",
        odds_api_key="soccer_sweden_allsvenskan",
        api_football_id=113,
        country="Sweden",
        tier=3,
        timezone="Europe/Stockholm"
    ),
    LeagueConfig(
        name="Norwegian Eliteserien",
        odds_api_key="soccer_norway_eliteserien",
        api_football_id=103,
        country="Norway",
        tier=3,
        timezone="Europe/Oslo"
    ),
    LeagueConfig(
        name="Danish Superliga",
        odds_api_key="soccer_denmark_superliga",
        api_football_id=119,
        country="Denmark",
        tier=3,
        timezone="Europe/Copenhagen"
    ),
    LeagueConfig(
        name="Austrian Bundesliga",
        odds_api_key="soccer_austria_bundesliga",
        api_football_id=218,  # Note: Austrian Bundesliga ID is 218
        country="Austria",
        tier=3,
        timezone="Europe/Vienna"
    ),
    LeagueConfig(
        name="Swiss Super League",
        odds_api_key="soccer_switzerland_superleague",
        api_football_id=207,
        country="Switzerland",
        tier=3,
        timezone="Europe/Zurich"
    ),
    LeagueConfig(
        name="Greek Super League",
        odds_api_key="soccer_greece_super_league",
        api_football_id=197,
        country="Greece",
        tier=3,
        timezone="Europe/Athens"
    ),
    LeagueConfig(
        name="Polish Ekstraklasa",
        odds_api_key="soccer_poland_ekstraklasa",
        api_football_id=106,
        country="Poland",
        tier=3,
        timezone="Europe/Warsaw"
    ),
    LeagueConfig(
        name="Czech First League",
        odds_api_key="soccer_czech_liga",
        api_football_id=345,
        country="Czech Republic",
        tier=3,
        timezone="Europe/Prague"
    ),
    LeagueConfig(
        name="Turkish Super League",
        odds_api_key="soccer_turkey_super_league",
        api_football_id=203,
        country="Turkey",
        tier=2,
        timezone="Europe/Istanbul"
    ),
    LeagueConfig(
        name="Russian Premier League",
        odds_api_key="soccer_russia_premier_league",
        api_football_id=235,
        country="Russia",
        tier=3,
        timezone="Europe/Moscow"
    ),
    
    # === SOUTH AMERICA - WINTER LEAGUES (Tier 2) ===
    LeagueConfig(
        name="Brazilian Serie A",
        odds_api_key="soccer_brazil_campeonato",
        api_football_id=71,
        country="Brazil",
        tier=2,
        season=2024,
        timezone="America/Sao_Paulo"
    ),
    LeagueConfig(
        name="Argentinian Primera Division",
        odds_api_key="soccer_argentina_primera_division",
        api_football_id=128,
        country="Argentina",
        tier=2,
        timezone="America/Buenos_Aires"
    ),
    
    # === NORTH AMERICA (Tier 3) ===
    LeagueConfig(
        name="Major League Soccer",
        odds_api_key="soccer_usa_mls",
        api_football_id=253,
        country="USA",
        tier=3,
        timezone="America/New_York"
    ),
    LeagueConfig(
        name="Liga MX",
        odds_api_key="soccer_mexico_ligamx",
        api_football_id=262,
        country="Mexico",
        tier=3,
        timezone="America/Mexico_City"
    ),
    
    # === ASIA-PACIFIC - WINTER LEAGUES (Tier 3) ===
    LeagueConfig(
        name="Japanese J1 League",
        odds_api_key="soccer_japan_j_league",
        api_football_id=98,
        country="Japan",
        tier=3,
        season=2024,
        timezone="Asia/Tokyo"
    ),
    LeagueConfig(
        name="Korean K League 1",
        odds_api_key="soccer_korea_kleague1",
        api_football_id=292,
        country="South Korea",
        tier=3,
        timezone="Asia/Seoul"
    ),
    LeagueConfig(
        name="Australian A-League",
        odds_api_key="soccer_australia_aleague",
        api_football_id=188,
        country="Australia",
        tier=3,
        timezone="Australia/Sydney"
    ),
]


def get_active_leagues(tier: Optional[int] = None) -> List[LeagueConfig]:
    """Get all active leagues, optionally filtered by tier"""
    leagues = [league for league in LEAGUE_REGISTRY if league.active]
    if tier is not None:
        leagues = [league for league in leagues if league.tier == tier]
    return leagues


def get_odds_api_keys() -> List[str]:
    """Get list of all active Odds API sport keys"""
    return [league.odds_api_key for league in LEAGUE_REGISTRY if league.active]


def get_api_football_ids() -> List[int]:
    """Get list of all active API-Football league IDs"""
    return [league.api_football_id for league in LEAGUE_REGISTRY if league.active]


def odds_key_to_api_football_id(odds_key: str) -> Optional[int]:
    """Map Odds API key to API-Football ID"""
    for league in LEAGUE_REGISTRY:
        if league.odds_api_key == odds_key and league.active:
            return league.api_football_id
    return None


def api_football_id_to_odds_key(api_id: int) -> Optional[str]:
    """Map API-Football ID to Odds API key"""
    for league in LEAGUE_REGISTRY:
        if league.api_football_id == api_id and league.active:
            return league.odds_api_key
    return None


def get_league_by_odds_key(odds_key: str) -> Optional[LeagueConfig]:
    """Get full league config by Odds API key"""
    for league in LEAGUE_REGISTRY:
        if league.odds_api_key == odds_key and league.active:
            return league
    return None


def get_league_by_api_football_id(api_id: int) -> Optional[LeagueConfig]:
    """Get full league config by API-Football ID"""
    for league in LEAGUE_REGISTRY:
        if league.api_football_id == api_id and league.active:
            return league
    return None


def add_league(league: LeagueConfig) -> bool:
    """Add new league to registry (deduplicates by odds_key)"""
    # Check for duplicates
    for existing in LEAGUE_REGISTRY:
        if existing.odds_api_key == league.odds_api_key:
            # Update existing
            LEAGUE_REGISTRY.remove(existing)
            LEAGUE_REGISTRY.append(league)
            return True
    
    # Add new
    LEAGUE_REGISTRY.append(league)
    return True


def get_winter_leagues() -> List[LeagueConfig]:
    """Get leagues currently in their active season (winter leagues for Northern Hemisphere)"""
    winter_countries = ["Brazil", "Argentina", "Japan", "South Korea", "Australia", "USA", "Mexico"]
    return [league for league in LEAGUE_REGISTRY if league.country in winter_countries and league.active]


if __name__ == "__main__":
    print("🌍 LEAGUE REGISTRY STATUS")
    print("=" * 60)
    
    active = get_active_leagues()
    print(f"\n✅ Active Leagues: {len(active)}")
    
    for tier in [1, 2, 3]:
        tier_leagues = get_active_leagues(tier=tier)
        print(f"\n📊 Tier {tier}: {len(tier_leagues)} leagues")
        for league in tier_leagues:
            print(f"   • {league.name} ({league.country})")
    
    winter = get_winter_leagues()
    print(f"\n❄️ Winter Leagues (24/7 Coverage): {len(winter)}")
    for league in winter:
        print(f"   • {league.name} - {league.timezone}")
