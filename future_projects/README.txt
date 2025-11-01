SGP AI - Same Game Parlay Pricing Engine
========================================

Saved for future development when exact score platform has stable cash flow.

What it does:
- Prices multi-leg parlays using copula correlation modeling
- Kelly Criterion stake calculator
- FastAPI backend with simple UI

Potential revenue models:
1. B2B API service ($500-2000/month per client)
2. Affiliate marketing (drive traffic to sportsbooks)
3. Personal betting (if model accurate)

Why saved for later:
- Current focus: Get exact score platform to 354 bets and validate performance
- Need stable revenue first before diversifying
- SGP requires expensive data feeds and longer validation time

To use in future:
1. Create new Replit project
2. Install: pip install fastapi uvicorn numpy
3. Run: uvicorn sgp_ai_parlay_pricer:app --host 0.0.0.0 --port 8000

Decision made: November 1, 2025
