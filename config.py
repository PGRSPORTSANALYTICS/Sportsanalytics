# Configuration for Football Tips Platform
# User wants to sell tips, not auto-bet

# Feature flags
AUTO_BET_ENABLED = False  # Disable automated betting - focus on tips selling
TIPS_SELLING_MODE = True  # Enable tips selling features

# Quality thresholds
MIN_EDGE_PREMIUM = 20     # Minimum edge for premium tips
MIN_EDGE_STANDARD = 10    # Minimum edge for standard tips
DAILY_TIP_LIMIT = 40      # Maximum tips per day

# Result verification
USE_REAL_RESULTS = True   # Use real verification, no simulated results
