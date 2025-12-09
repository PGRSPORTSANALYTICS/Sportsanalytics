"""
Market Router Configuration (Dec 9, 2025)
==========================================
Central configuration for market caps and per-market limits.
Ensures daily betting card is balanced across markets.

The router prevents spamming a single market (e.g., all Over 2.5 Goals)
and ensures portfolio diversification across market types.

MARKET_CAPS: Controls how many picks per product/market type
GLOBAL_DAILY_MAX_PICKS: Absolute cap across all products
"""

from typing import Dict, Any


MARKET_CAPS: Dict[str, Dict[str, Any]] = {
    "TOTALS": {
        "max_picks": 10,
        "per_market_caps": {
            "FT_OVER_2_5": 3,
            "FT_UNDER_2_5": 3,
            "FT_OVER_3_5": 2,
            "FT_UNDER_3_5": 2,
            "FT_OVER_1_5": 2,
            "FT_UNDER_1_5": 1,
            "FT_OVER_4_5": 1,
            "FT_UNDER_4_5": 1,
            "OTHER_TOTALS": 2,
        },
    },
    "BTTS": {
        "max_picks": 8,
        "per_market_caps": {
            "BTTS_YES": 5,
            "BTTS_NO": 3,
        },
    },
    "ML_AH": {
        "max_picks": 15,
        "per_market_caps": {
            "HOME_WIN": 4,
            "AWAY_WIN": 4,
            "DRAW": 2,
            "AH_HOME": 3,
            "AH_AWAY": 3,
            "DC_HOME_DRAW": 2,
            "DC_DRAW_AWAY": 2,
            "DC_HOME_AWAY": 1,
            "DNB_HOME": 2,
            "DNB_AWAY": 2,
            "OTHER_ML_AH": 2,
        },
    },
    "CORNERS_MATCH": {
        "max_picks": 6,
        "per_market_caps": {
            "CORNERS_OVER": 4,
            "CORNERS_UNDER": 2,
        },
    },
    "CORNERS_TEAM": {
        "max_picks": 4,
        "per_market_caps": {
            "HOME_CORNERS_OVER": 2,
            "AWAY_CORNERS_OVER": 2,
        },
    },
    "CORNERS_HANDICAP": {
        "max_picks": 6,
        "per_market_caps": {
            "CORNERS_HC_HOME": 3,
            "CORNERS_HC_AWAY": 3,
        },
    },
    "CARDS_MATCH": {
        "max_picks": 6,
        "per_market_caps": {
            "MATCH_CARDS_OVER": 4,
            "MATCH_CARDS_UNDER": 2,
            "BOOKING_POINTS_OVER": 2,
            "BOOKING_POINTS_UNDER": 1,
        },
    },
    "CARDS_TEAM": {
        "max_picks": 4,
        "per_market_caps": {
            "HOME_CARDS_OVER": 2,
            "AWAY_CARDS_OVER": 2,
        },
    },
    "SHOTS_TEAM": {
        "max_picks": 6,
        "per_market_caps": {
            "TEAM_SHOTS_OVER": 3,
            "TEAM_SHOTS_UNDER": 2,
            "HOME_SHOTS_OVER": 2,
            "AWAY_SHOTS_OVER": 2,
            "TEAM_SOT_OVER": 2,
            "TEAM_SOT_UNDER": 1,
        },
    },
    "VALUE_SINGLES": {
        "max_picks": 15,
        "per_market_caps": {
            "HOME_WIN": 4,
            "AWAY_WIN": 4,
            "DRAW": 2,
            "AH_HOME": 3,
            "AH_AWAY": 3,
            "DC_HOME_DRAW": 2,
            "DC_DRAW_AWAY": 2,
            "DNB_HOME": 2,
            "DNB_AWAY": 2,
            "OTHER": 3,
        },
    },
}

GLOBAL_DAILY_MAX_PICKS = 25


def get_market_cap_key(market_key: str, product: str) -> str:
    """
    Map a specific market_key to its cap category.
    
    Examples:
        FT_OVER_2_5 -> FT_OVER_2_5 (exact match for totals)
        AH_HOME_-0.5 -> AH_HOME
        HOME_CORNERS_OVER_3_5 -> HOME_CORNERS_OVER
        MATCH_CARDS_OVER_4_5 -> MATCH_CARDS_OVER
    """
    if not market_key:
        return "OTHER"
    
    mk = market_key.upper()
    
    if product == "TOTALS":
        if mk in ["FT_OVER_2_5", "FT_UNDER_2_5", "FT_OVER_3_5", "FT_UNDER_3_5",
                  "FT_OVER_1_5", "FT_UNDER_1_5", "FT_OVER_4_5", "FT_UNDER_4_5"]:
            return mk
        if "OVER" in mk:
            return "OTHER_TOTALS"
        if "UNDER" in mk:
            return "OTHER_TOTALS"
        return "OTHER_TOTALS"
    
    if product == "BTTS":
        if "BTTS_YES" in mk or mk == "BTTS_YES":
            return "BTTS_YES"
        if "BTTS_NO" in mk or mk == "BTTS_NO":
            return "BTTS_NO"
        return "BTTS_YES"
    
    if product in ["ML_AH", "VALUE_SINGLES"]:
        if mk == "HOME_WIN":
            return "HOME_WIN"
        if mk == "AWAY_WIN":
            return "AWAY_WIN"
        if mk == "DRAW":
            return "DRAW"
        if mk.startswith("AH_HOME"):
            return "AH_HOME"
        if mk.startswith("AH_AWAY"):
            return "AH_AWAY"
        if mk.startswith("DC_HOME_DRAW"):
            return "DC_HOME_DRAW"
        if mk.startswith("DC_DRAW_AWAY"):
            return "DC_DRAW_AWAY"
        if mk.startswith("DC_HOME_AWAY"):
            return "DC_HOME_AWAY"
        if mk.startswith("DNB_HOME"):
            return "DNB_HOME"
        if mk.startswith("DNB_AWAY"):
            return "DNB_AWAY"
        return "OTHER_ML_AH" if product == "ML_AH" else "OTHER"
    
    if product == "CORNERS_MATCH":
        if "OVER" in mk:
            return "CORNERS_OVER"
        if "UNDER" in mk:
            return "CORNERS_UNDER"
        return "CORNERS_OVER"
    
    if product == "CORNERS_TEAM":
        if "HOME" in mk:
            return "HOME_CORNERS_OVER"
        if "AWAY" in mk:
            return "AWAY_CORNERS_OVER"
        return "HOME_CORNERS_OVER"
    
    if product == "CORNERS_HANDICAP":
        if "HOME" in mk:
            return "CORNERS_HC_HOME"
        if "AWAY" in mk:
            return "CORNERS_HC_AWAY"
        return "CORNERS_HC_HOME"
    
    if product == "CARDS_MATCH":
        if "BOOKING" in mk:
            if "OVER" in mk:
                return "BOOKING_POINTS_OVER"
            return "BOOKING_POINTS_UNDER"
        if "OVER" in mk:
            return "MATCH_CARDS_OVER"
        if "UNDER" in mk:
            return "MATCH_CARDS_UNDER"
        return "MATCH_CARDS_OVER"
    
    if product == "CARDS_TEAM":
        if "HOME" in mk:
            return "HOME_CARDS_OVER"
        if "AWAY" in mk:
            return "AWAY_CARDS_OVER"
        return "HOME_CARDS_OVER"
    
    if product == "SHOTS_TEAM":
        if "SOT" in mk:
            if "OVER" in mk:
                return "TEAM_SOT_OVER"
            return "TEAM_SOT_UNDER"
        if "HOME" in mk:
            return "HOME_SHOTS_OVER"
        if "AWAY" in mk:
            return "AWAY_SHOTS_OVER"
        if "UNDER" in mk:
            return "TEAM_SHOTS_UNDER"
        return "TEAM_SHOTS_OVER"
    
    return "OTHER"


def map_product_to_router_category(product_type: str) -> str:
    """
    Map internal product types to router categories.
    
    The router uses slightly different category names to group
    related markets together.
    """
    product_upper = product_type.upper() if product_type else ""
    
    mapping = {
        "VALUE_SINGLES": "ML_AH",
        "TOTALS": "TOTALS",
        "BTTS": "BTTS",
        "CORNERS_MATCH": "CORNERS_MATCH",
        "CORNERS_TEAM": "CORNERS_TEAM",
        "CORNERS_HANDICAP": "CORNERS_HANDICAP",
        "CARDS_MATCH": "CARDS_MATCH",
        "CARDS_TEAM": "CARDS_TEAM",
        "SHOTS_TEAM": "SHOTS_TEAM",
        "SHOTS": "SHOTS_TEAM",
        "CARDS": "CARDS_MATCH",
        "CORNERS": "CORNERS_MATCH",
        "ML_AH": "ML_AH",
    }
    
    return mapping.get(product_upper, product_upper)


if __name__ == "__main__":
    print("=" * 60)
    print("MARKET ROUTER CONFIGURATION")
    print("=" * 60)
    print(f"\nGLOBAL_DAILY_MAX_PICKS: {GLOBAL_DAILY_MAX_PICKS}")
    print("\nMarket Caps by Product:")
    print("-" * 60)
    
    for product, config in MARKET_CAPS.items():
        print(f"\n{product}:")
        print(f"  Max Picks: {config['max_picks']}")
        print("  Per-Market Caps:")
        for market, cap in config.get("per_market_caps", {}).items():
            print(f"    {market}: {cap}")
    
    print("\n" + "=" * 60)
    print("Test Market Cap Key Mapping:")
    print("-" * 60)
    test_cases = [
        ("FT_OVER_2_5", "TOTALS"),
        ("AH_HOME_-0.5", "ML_AH"),
        ("BTTS_YES", "BTTS"),
        ("CORNERS_OVER_9_5", "CORNERS_MATCH"),
        ("MATCH_CARDS_OVER_4_5", "CARDS_MATCH"),
        ("TEAM_SHOTS_OVER_10_5", "SHOTS_TEAM"),
    ]
    for market_key, product in test_cases:
        cap_key = get_market_cap_key(market_key, product)
        print(f"  {market_key} ({product}) -> {cap_key}")
