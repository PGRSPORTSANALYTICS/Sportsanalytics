#!/usr/bin/env python3
"""
Platform Configuration
Controls which products are publicly visible vs running in background
"""

# Product visibility for paying subscribers
PUBLIC_PRODUCTS = {
    'exact_score': True,   # ✅ Live with real verified performance
    'sgp': False,          # ⏳ Data collection mode - add when 20+ live-odds settled
}

# Minimum settled predictions required before making product public
MIN_SETTLED_REQUIREMENTS = {
    'exact_score': 20,     # Already met (44 settled)
    'sgp_live_odds': 20,   # Need 20 settled with live odds before launch
}

# Launch timeline
LAUNCH_DATE = '2026-01-01'
SUBSCRIPTION_TIERS = {
    'basic': {
        'price_sek': 499,
        'products': ['exact_score'],
        'description': 'Exact score predictions with AI analysis'
    },
    'premium': {
        'price_sek': 999,
        'products': ['exact_score', 'sgp'],  # SGP added when ready
        'description': 'Exact scores + SGP parlays with live odds'
    }
}

def is_product_public(product_name: str) -> bool:
    """Check if product should be shown to subscribers"""
    return PUBLIC_PRODUCTS.get(product_name, False)

def get_public_products() -> list:
    """Get list of products available to subscribers"""
    return [k for k, v in PUBLIC_PRODUCTS.items() if v]

def is_ready_for_launch(product_name: str, settled_count: int) -> bool:
    """Check if product has enough data for honest launch"""
    min_required = MIN_SETTLED_REQUIREMENTS.get(product_name, 0)
    return settled_count >= min_required
