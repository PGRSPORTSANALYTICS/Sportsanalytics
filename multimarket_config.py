"""
MultiMarket Expansion v1.0 - Product Configuration (Dec 9, 2025)
================================================================
Defines products, market types, and filters for the expanded betting system.

Products:
- Value Singles (ML/AH/DC): Core subscription product
- Totals (Over/Under): Separate product with own limits
- BTTS (Both Teams To Score): Separate product with own limits
- Corners: Match and team corner markets
- ML Parlays: Multi-leg parlay product
- Multi-Match Parlays: Parlays built from L1/L2 singles

All products use Nova v2.0 trust tier framework.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class MarketType(Enum):
    ML = "ML"
    AH = "AH"
    DC = "DC"
    TOTALS = "TOTALS"
    BTTS = "BTTS"
    CORNERS = "CORNERS"
    DNB = "DNB"
    TEAM_TOTALS = "TEAM_TOTALS"
    SHOTS_TEAM = "SHOTS_TEAM"
    SHOTS_PLAYER = "SHOTS_PLAYER"
    CARDS_MATCH = "CARDS_MATCH"
    CARDS_TEAM = "CARDS_TEAM"
    CORNERS_HANDICAP = "CORNERS_HANDICAP"


class ProductType(Enum):
    VALUE_SINGLES = "VALUE_SINGLES"
    TOTALS = "TOTALS"
    BTTS = "BTTS"
    CORNERS = "CORNERS"
    SHOTS = "SHOTS"
    CARDS = "CARDS"
    CORNERS_HANDICAP = "CORNERS_HANDICAP"
    ML_PARLAYS = "ML_PARLAYS"
    MULTI_MATCH_PARLAYS = "MULTI_MATCH_PARLAYS"
    PROPS = "PROPS"


@dataclass
class ProductConfig:
    name: str
    max_per_day: int
    min_ev: float
    min_odds: float
    max_odds: float
    min_confidence: float
    market_types: List[str]
    l1_min_ev: float = 0.05
    l1_min_confidence: float = 0.55
    l2_min_ev: float = 0.02
    l2_min_confidence: float = 0.52
    l2_max_disagreement: float = 0.15
    l3_min_ev: float = 0.00
    l3_min_confidence: float = 0.50
    l3_max_disagreement: float = 0.25
    l3_min_daily_target: int = 5
    enabled: bool = True


PRODUCT_CONFIGS: Dict[str, ProductConfig] = {
    "VALUE_SINGLES": ProductConfig(
        name="Value Singles",
        max_per_day=20,
        min_ev=0.02,
        min_odds=1.40,
        max_odds=2.20,
        min_confidence=0.52,
        market_types=["ML", "AH", "DC", "DNB"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "TOTALS": ProductConfig(
        name="Totals (Over/Under)",
        max_per_day=10,
        min_ev=0.02,
        min_odds=1.50,
        max_odds=2.80,
        min_confidence=0.52,
        market_types=["TOTALS"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "BTTS": ProductConfig(
        name="BTTS (Both Teams To Score)",
        max_per_day=8,
        min_ev=0.02,
        min_odds=1.50,
        max_odds=2.80,
        min_confidence=0.52,
        market_types=["BTTS"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "CORNERS_MATCH": ProductConfig(
        name="Corners (Match Total)",
        max_per_day=6,
        min_ev=0.02,
        min_odds=1.60,
        max_odds=2.80,
        min_confidence=0.52,
        market_types=["CORNERS"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "CORNERS_TEAM": ProductConfig(
        name="Corners (Team)",
        max_per_day=4,
        min_ev=0.02,
        min_odds=1.60,
        max_odds=3.00,
        min_confidence=0.52,
        market_types=["CORNERS"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "ML_PARLAYS": ProductConfig(
        name="ML Parlays",
        max_per_day=5,
        min_ev=0.03,
        min_odds=3.00,
        max_odds=12.00,
        min_confidence=0.52,
        market_types=["ML", "DNB"],
    ),
    "MULTI_MATCH_PARLAYS": ProductConfig(
        name="Multi-Match Parlays",
        max_per_day=2,
        min_ev=0.03,
        min_odds=3.00,
        max_odds=10.00,
        min_confidence=0.52,
        market_types=["ML", "AH", "DC", "TOTALS", "BTTS"],
    ),
}


MARKET_TO_TYPE: Dict[str, MarketType] = {
    "HOME_WIN": MarketType.ML,
    "DRAW": MarketType.ML,
    "AWAY_WIN": MarketType.ML,
    "AH_HOME_-0.5": MarketType.AH,
    "AH_HOME_-1.0": MarketType.AH,
    "AH_HOME_-1.5": MarketType.AH,
    "AH_HOME_+0.5": MarketType.AH,
    "AH_HOME_+1.0": MarketType.AH,
    "AH_HOME_+1.5": MarketType.AH,
    "AH_AWAY_-0.5": MarketType.AH,
    "AH_AWAY_-1.0": MarketType.AH,
    "AH_AWAY_-1.5": MarketType.AH,
    "AH_AWAY_+0.5": MarketType.AH,
    "AH_AWAY_+1.0": MarketType.AH,
    "AH_AWAY_+1.5": MarketType.AH,
    "DC_HOME_DRAW": MarketType.DC,
    "DC_HOME_AWAY": MarketType.DC,
    "DC_DRAW_AWAY": MarketType.DC,
    "DNB_HOME": MarketType.DNB,
    "DNB_AWAY": MarketType.DNB,
    "FT_OVER_0_5": MarketType.TOTALS,
    "FT_UNDER_0_5": MarketType.TOTALS,
    "FT_OVER_1_5": MarketType.TOTALS,
    "FT_UNDER_1_5": MarketType.TOTALS,
    "FT_OVER_2_5": MarketType.TOTALS,
    "FT_UNDER_2_5": MarketType.TOTALS,
    "FT_OVER_3_5": MarketType.TOTALS,
    "FT_UNDER_3_5": MarketType.TOTALS,
    "FT_OVER_4_5": MarketType.TOTALS,
    "FT_UNDER_4_5": MarketType.TOTALS,
    "BTTS_YES": MarketType.BTTS,
    "BTTS_NO": MarketType.BTTS,
    "CORNERS_OVER_8_5": MarketType.CORNERS,
    "CORNERS_OVER_9_5": MarketType.CORNERS,
    "CORNERS_OVER_10_5": MarketType.CORNERS,
    "CORNERS_OVER_11_5": MarketType.CORNERS,
    "CORNERS_UNDER_8_5": MarketType.CORNERS,
    "CORNERS_UNDER_9_5": MarketType.CORNERS,
    "CORNERS_UNDER_10_5": MarketType.CORNERS,
    "CORNERS_UNDER_11_5": MarketType.CORNERS,
    "HOME_CORNERS_OVER_3_5": MarketType.CORNERS,
    "HOME_CORNERS_OVER_4_5": MarketType.CORNERS,
    "AWAY_CORNERS_OVER_3_5": MarketType.CORNERS,
    "AWAY_CORNERS_OVER_4_5": MarketType.CORNERS,
    "HOME_OVER_0_5": MarketType.TEAM_TOTALS,
    "HOME_OVER_1_5": MarketType.TEAM_TOTALS,
    "AWAY_OVER_0_5": MarketType.TEAM_TOTALS,
    "AWAY_OVER_1_5": MarketType.TEAM_TOTALS,
}


MARKET_LABELS: Dict[str, str] = {
    "HOME_WIN": "Home Win (ML)",
    "DRAW": "Draw (ML)",
    "AWAY_WIN": "Away Win (ML)",
    "AH_HOME_-0.5": "Home -0.5 (AH)",
    "AH_HOME_-1.0": "Home -1.0 (AH)",
    "AH_HOME_-1.5": "Home -1.5 (AH)",
    "AH_HOME_+0.5": "Home +0.5 (AH)",
    "AH_HOME_+1.0": "Home +1.0 (AH)",
    "AH_HOME_+1.5": "Home +1.5 (AH)",
    "AH_AWAY_-0.5": "Away -0.5 (AH)",
    "AH_AWAY_-1.0": "Away -1.0 (AH)",
    "AH_AWAY_-1.5": "Away -1.5 (AH)",
    "AH_AWAY_+0.5": "Away +0.5 (AH)",
    "AH_AWAY_+1.0": "Away +1.0 (AH)",
    "AH_AWAY_+1.5": "Away +1.5 (AH)",
    "DC_HOME_DRAW": "Home or Draw (DC)",
    "DC_HOME_AWAY": "Home or Away (DC)",
    "DC_DRAW_AWAY": "Draw or Away (DC)",
    "DNB_HOME": "Home (DNB)",
    "DNB_AWAY": "Away (DNB)",
    "FT_OVER_0_5": "Over 0.5 Goals",
    "FT_UNDER_0_5": "Under 0.5 Goals",
    "FT_OVER_1_5": "Over 1.5 Goals",
    "FT_UNDER_1_5": "Under 1.5 Goals",
    "FT_OVER_2_5": "Over 2.5 Goals",
    "FT_UNDER_2_5": "Under 2.5 Goals",
    "FT_OVER_3_5": "Over 3.5 Goals",
    "FT_UNDER_3_5": "Under 3.5 Goals",
    "FT_OVER_4_5": "Over 4.5 Goals",
    "FT_UNDER_4_5": "Under 4.5 Goals",
    "BTTS_YES": "BTTS Yes",
    "BTTS_NO": "BTTS No",
    "CORNERS_OVER_8_5": "Corners Over 8.5",
    "CORNERS_OVER_9_5": "Corners Over 9.5",
    "CORNERS_OVER_10_5": "Corners Over 10.5",
    "CORNERS_OVER_11_5": "Corners Over 11.5",
    "CORNERS_UNDER_8_5": "Corners Under 8.5",
    "CORNERS_UNDER_9_5": "Corners Under 9.5",
    "CORNERS_UNDER_10_5": "Corners Under 10.5",
    "CORNERS_UNDER_11_5": "Corners Under 11.5",
    "HOME_CORNERS_OVER_3_5": "Home Corners Over 3.5",
    "HOME_CORNERS_OVER_4_5": "Home Corners Over 4.5",
    "AWAY_CORNERS_OVER_3_5": "Away Corners Over 3.5",
    "AWAY_CORNERS_OVER_4_5": "Away Corners Over 4.5",
}


def get_market_type(market_key: str) -> Optional[MarketType]:
    return MARKET_TO_TYPE.get(market_key)


def get_market_label(market_key: str) -> str:
    return MARKET_LABELS.get(market_key, market_key)


def get_product_for_market(market_key: str) -> Optional[str]:
    market_type = get_market_type(market_key)
    if not market_type:
        return None
    
    type_str = market_type.value
    
    if type_str in ["ML", "AH", "DC", "DNB"]:
        return "VALUE_SINGLES"
    elif type_str == "TOTALS":
        return "TOTALS"
    elif type_str == "BTTS":
        return "BTTS"
    elif type_str == "CORNERS":
        return "CORNERS_MATCH"
    elif type_str == "TEAM_TOTALS":
        return "VALUE_SINGLES"
    
    return None


DAILY_TARGETS = {
    "VALUE_SINGLES": {"min": 5, "target": 10, "max": 15},
    "TOTALS": {"min": 3, "target": 6, "max": 10},
    "BTTS": {"min": 2, "target": 5, "max": 8},
    "CORNERS_MATCH": {"min": 2, "target": 4, "max": 6},
    "CORNERS_TEAM": {"min": 1, "target": 2, "max": 4},
    "ML_PARLAYS": {"min": 1, "target": 3, "max": 5},
    "MULTI_MATCH_PARLAYS": {"min": 0, "target": 1, "max": 2},
}


if __name__ == "__main__":
    print("=== MultiMarket Expansion v1.0 Configuration ===\n")
    
    for product_key, config in PRODUCT_CONFIGS.items():
        print(f"{config.name}:")
        print(f"  Max/Day: {config.max_per_day}")
        print(f"  Min EV: {config.min_ev:.0%}")
        print(f"  Odds: {config.min_odds}-{config.max_odds}")
        print(f"  Markets: {config.market_types}")
        print()
    
    print("Market Type Mappings:")
    for market, mtype in list(MARKET_TO_TYPE.items())[:10]:
        print(f"  {market} -> {mtype.value}")
