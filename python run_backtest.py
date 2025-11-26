from db.bets import insert_bet
from algos.sgp import generate_sgp_bets
from datetime import datetime, timedelta

# Exempel: backtesta 30 dagar bakåt
start = datetime.now() - timedelta(days=30)
end = datetime.now()

fixtures = load_fixtures_for_range(start, end)

for fixture in fixtures:
    sgp_suggestions = generate_sgp_bets(fixture)

    for bet in sgp_suggestions:
        insert_bet(
            home_team=bet.home,
            away_team=bet.away,
            stake=bet.stake,
            odds=bet.odds,
            product="SGP",
            legs=bet.legs,
            result="PENDING",
            mode="BACKTEST",       # 💥 SUPER VIKTIGT
        )