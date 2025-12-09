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
    "SHOTS_TEAM": ProductConfig(
        name="Team Shots (Over/Under)",
        max_per_day=6,
        min_ev=0.02,
        min_odds=1.60,
        max_odds=2.80,
        min_confidence=0.52,
        market_types=["SHOTS_TEAM"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "CARDS_MATCH": ProductConfig(
        name="Match Cards (Over/Under)",
        max_per_day=6,
        min_ev=0.02,
        min_odds=1.60,
        max_odds=2.80,
        min_confidence=0.52,
        market_types=["CARDS_MATCH"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "CARDS_TEAM": ProductConfig(
        name="Team Cards (Over/Under)",
        max_per_day=4,
        min_ev=0.02,
        min_odds=1.60,
        max_odds=3.00,
        min_confidence=0.52,
        market_types=["CARDS_TEAM"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "CORNERS_HANDICAP": ProductConfig(
        name="Corner Handicaps",
        max_per_day=6,
        min_ev=0.02,
        min_odds=1.70,
        max_odds=2.50,
        min_confidence=0.52,
        market_types=["CORNERS_HANDICAP"],
        l1_min_ev=0.05,
        l1_min_confidence=0.55,
        l2_min_ev=0.02,
        l2_min_confidence=0.52,
    ),
    "PROPS": ProductConfig(
        name="Player Props",
        max_per_day=4,
        min_ev=0.03,
        min_odds=1.70,
        max_odds=3.50,
        min_confidence=0.55,
        market_types=["SHOTS_PLAYER"],
        l1_min_ev=0.06,
        l1_min_confidence=0.58,
        l2_min_ev=0.03,
        l2_min_confidence=0.55,
        enabled=False,
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
    "TEAM_SHOTS_OVER_8_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_OVER_9_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_OVER_10_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_OVER_11_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_OVER_12_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_UNDER_8_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_UNDER_9_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_UNDER_10_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_UNDER_11_5": MarketType.SHOTS_TEAM,
    "TEAM_SHOTS_UNDER_12_5": MarketType.SHOTS_TEAM,
    "HOME_SHOTS_OVER_3_5": MarketType.SHOTS_TEAM,
    "HOME_SHOTS_OVER_4_5": MarketType.SHOTS_TEAM,
    "HOME_SHOTS_OVER_5_5": MarketType.SHOTS_TEAM,
    "AWAY_SHOTS_OVER_3_5": MarketType.SHOTS_TEAM,
    "AWAY_SHOTS_OVER_4_5": MarketType.SHOTS_TEAM,
    "AWAY_SHOTS_OVER_5_5": MarketType.SHOTS_TEAM,
    "TEAM_SOT_OVER_2_5": MarketType.SHOTS_TEAM,
    "TEAM_SOT_OVER_3_5": MarketType.SHOTS_TEAM,
    "TEAM_SOT_OVER_4_5": MarketType.SHOTS_TEAM,
    "TEAM_SOT_UNDER_2_5": MarketType.SHOTS_TEAM,
    "TEAM_SOT_UNDER_3_5": MarketType.SHOTS_TEAM,
    "TEAM_SOT_UNDER_4_5": MarketType.SHOTS_TEAM,
    "HOME_SOT_OVER_1_5": MarketType.SHOTS_TEAM,
    "HOME_SOT_OVER_2_5": MarketType.SHOTS_TEAM,
    "AWAY_SOT_OVER_1_5": MarketType.SHOTS_TEAM,
    "AWAY_SOT_OVER_2_5": MarketType.SHOTS_TEAM,
    "MATCH_CARDS_OVER_2_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_OVER_3_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_OVER_4_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_OVER_5_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_OVER_6_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_UNDER_2_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_UNDER_3_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_UNDER_4_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_UNDER_5_5": MarketType.CARDS_MATCH,
    "MATCH_CARDS_UNDER_6_5": MarketType.CARDS_MATCH,
    "BOOKING_POINTS_OVER_30_5": MarketType.CARDS_MATCH,
    "BOOKING_POINTS_OVER_40_5": MarketType.CARDS_MATCH,
    "BOOKING_POINTS_OVER_50_5": MarketType.CARDS_MATCH,
    "BOOKING_POINTS_UNDER_30_5": MarketType.CARDS_MATCH,
    "BOOKING_POINTS_UNDER_40_5": MarketType.CARDS_MATCH,
    "BOOKING_POINTS_UNDER_50_5": MarketType.CARDS_MATCH,
    "HOME_CARDS_OVER_0_5": MarketType.CARDS_TEAM,
    "HOME_CARDS_OVER_1_5": MarketType.CARDS_TEAM,
    "HOME_CARDS_OVER_2_5": MarketType.CARDS_TEAM,
    "AWAY_CARDS_OVER_0_5": MarketType.CARDS_TEAM,
    "AWAY_CARDS_OVER_1_5": MarketType.CARDS_TEAM,
    "AWAY_CARDS_OVER_2_5": MarketType.CARDS_TEAM,
    "CORNERS_HC_HOME_-0_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_HOME_-1_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_HOME_-2_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_HOME_+0_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_HOME_+1_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_HOME_+2_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_AWAY_-0_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_AWAY_-1_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_AWAY_-2_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_AWAY_+0_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_AWAY_+1_5": MarketType.CORNERS_HANDICAP,
    "CORNERS_HC_AWAY_+2_5": MarketType.CORNERS_HANDICAP,
    "PLAYER_SHOTS_OVER_0_5": MarketType.SHOTS_PLAYER,
    "PLAYER_SHOTS_OVER_1_5": MarketType.SHOTS_PLAYER,
    "PLAYER_SHOTS_OVER_2_5": MarketType.SHOTS_PLAYER,
    "PLAYER_SOT_OVER_0_5": MarketType.SHOTS_PLAYER,
    "PLAYER_SOT_OVER_1_5": MarketType.SHOTS_PLAYER,
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
    "TEAM_SHOTS_OVER_8_5": "Team Shots Over 8.5",
    "TEAM_SHOTS_OVER_9_5": "Team Shots Over 9.5",
    "TEAM_SHOTS_OVER_10_5": "Team Shots Over 10.5",
    "TEAM_SHOTS_OVER_11_5": "Team Shots Over 11.5",
    "TEAM_SHOTS_OVER_12_5": "Team Shots Over 12.5",
    "TEAM_SHOTS_UNDER_8_5": "Team Shots Under 8.5",
    "TEAM_SHOTS_UNDER_9_5": "Team Shots Under 9.5",
    "TEAM_SHOTS_UNDER_10_5": "Team Shots Under 10.5",
    "TEAM_SHOTS_UNDER_11_5": "Team Shots Under 11.5",
    "TEAM_SHOTS_UNDER_12_5": "Team Shots Under 12.5",
    "HOME_SHOTS_OVER_3_5": "Home Shots Over 3.5",
    "HOME_SHOTS_OVER_4_5": "Home Shots Over 4.5",
    "HOME_SHOTS_OVER_5_5": "Home Shots Over 5.5",
    "AWAY_SHOTS_OVER_3_5": "Away Shots Over 3.5",
    "AWAY_SHOTS_OVER_4_5": "Away Shots Over 4.5",
    "AWAY_SHOTS_OVER_5_5": "Away Shots Over 5.5",
    "TEAM_SOT_OVER_2_5": "Shots on Target Over 2.5",
    "TEAM_SOT_OVER_3_5": "Shots on Target Over 3.5",
    "TEAM_SOT_OVER_4_5": "Shots on Target Over 4.5",
    "TEAM_SOT_UNDER_2_5": "Shots on Target Under 2.5",
    "TEAM_SOT_UNDER_3_5": "Shots on Target Under 3.5",
    "TEAM_SOT_UNDER_4_5": "Shots on Target Under 4.5",
    "HOME_SOT_OVER_1_5": "Home SOT Over 1.5",
    "HOME_SOT_OVER_2_5": "Home SOT Over 2.5",
    "AWAY_SOT_OVER_1_5": "Away SOT Over 1.5",
    "AWAY_SOT_OVER_2_5": "Away SOT Over 2.5",
    "MATCH_CARDS_OVER_2_5": "Match Cards Over 2.5",
    "MATCH_CARDS_OVER_3_5": "Match Cards Over 3.5",
    "MATCH_CARDS_OVER_4_5": "Match Cards Over 4.5",
    "MATCH_CARDS_OVER_5_5": "Match Cards Over 5.5",
    "MATCH_CARDS_OVER_6_5": "Match Cards Over 6.5",
    "MATCH_CARDS_UNDER_2_5": "Match Cards Under 2.5",
    "MATCH_CARDS_UNDER_3_5": "Match Cards Under 3.5",
    "MATCH_CARDS_UNDER_4_5": "Match Cards Under 4.5",
    "MATCH_CARDS_UNDER_5_5": "Match Cards Under 5.5",
    "MATCH_CARDS_UNDER_6_5": "Match Cards Under 6.5",
    "BOOKING_POINTS_OVER_30_5": "Booking Pts Over 30.5",
    "BOOKING_POINTS_OVER_40_5": "Booking Pts Over 40.5",
    "BOOKING_POINTS_OVER_50_5": "Booking Pts Over 50.5",
    "BOOKING_POINTS_UNDER_30_5": "Booking Pts Under 30.5",
    "BOOKING_POINTS_UNDER_40_5": "Booking Pts Under 40.5",
    "BOOKING_POINTS_UNDER_50_5": "Booking Pts Under 50.5",
    "HOME_CARDS_OVER_0_5": "Home Cards Over 0.5",
    "HOME_CARDS_OVER_1_5": "Home Cards Over 1.5",
    "HOME_CARDS_OVER_2_5": "Home Cards Over 2.5",
    "AWAY_CARDS_OVER_0_5": "Away Cards Over 0.5",
    "AWAY_CARDS_OVER_1_5": "Away Cards Over 1.5",
    "AWAY_CARDS_OVER_2_5": "Away Cards Over 2.5",
    "CORNERS_HC_HOME_-0_5": "Home Corners -0.5",
    "CORNERS_HC_HOME_-1_5": "Home Corners -1.5",
    "CORNERS_HC_HOME_-2_5": "Home Corners -2.5",
    "CORNERS_HC_HOME_+0_5": "Home Corners +0.5",
    "CORNERS_HC_HOME_+1_5": "Home Corners +1.5",
    "CORNERS_HC_HOME_+2_5": "Home Corners +2.5",
    "CORNERS_HC_AWAY_-0_5": "Away Corners -0.5",
    "CORNERS_HC_AWAY_-1_5": "Away Corners -1.5",
    "CORNERS_HC_AWAY_-2_5": "Away Corners -2.5",
    "CORNERS_HC_AWAY_+0_5": "Away Corners +0.5",
    "CORNERS_HC_AWAY_+1_5": "Away Corners +1.5",
    "CORNERS_HC_AWAY_+2_5": "Away Corners +2.5",
    "PLAYER_SHOTS_OVER_0_5": "Player Shots Over 0.5",
    "PLAYER_SHOTS_OVER_1_5": "Player Shots Over 1.5",
    "PLAYER_SHOTS_OVER_2_5": "Player Shots Over 2.5",
    "PLAYER_SOT_OVER_0_5": "Player SOT Over 0.5",
    "PLAYER_SOT_OVER_1_5": "Player SOT Over 1.5",
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
    elif type_str == "SHOTS_TEAM":
        return "SHOTS_TEAM"
    elif type_str == "SHOTS_PLAYER":
        return "PROPS"
    elif type_str == "CARDS_MATCH":
        return "CARDS_MATCH"
    elif type_str == "CARDS_TEAM":
        return "CARDS_TEAM"
    elif type_str == "CORNERS_HANDICAP":
        return "CORNERS_HANDICAP"
    
    return None


DAILY_TARGETS = {
    "VALUE_SINGLES": {"min": 5, "target": 10, "max": 15},
    "TOTALS": {"min": 3, "target": 6, "max": 10},
    "BTTS": {"min": 2, "target": 5, "max": 8},
    "CORNERS_MATCH": {"min": 2, "target": 4, "max": 6},
    "CORNERS_TEAM": {"min": 1, "target": 2, "max": 4},
    "SHOTS_TEAM": {"min": 1, "target": 4, "max": 6},
    "CARDS_MATCH": {"min": 1, "target": 4, "max": 6},
    "CARDS_TEAM": {"min": 0, "target": 2, "max": 4},
    "CORNERS_HANDICAP": {"min": 1, "target": 3, "max": 6},
    "PROPS": {"min": 0, "target": 2, "max": 4},
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
