"""
run_backtest.py

Kör din PGR-motor i BACKTEST-läge.
- Alla bets sparas med mode='BACKTEST'
- Dashboarden (som filtrerar på mode='PROD') påverkas inte
- Du kan ändå använda backtest-data för learning/analys
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import psycopg2
from psycopg2.extras import execute_values


# ========= CONFIG ========= #

BACKTEST_DAYS = 30
DEFAULT_STAKE = 100.0
PRODUCT_CODE = "VALUE_SINGLE"
DATABASE_URL = os.environ.get("DATABASE_URL")

SUPPORTED_PRODUCTS = ["VALUE_SINGLE", "EXACT_SCORE", "SGP"]

TABLE_MAPPING = {
    "VALUE_SINGLE": "football_opportunities",
    "EXACT_SCORE": "football_opportunities",
    "SGP": "sgp_predictions",
}


# ========= DB HELPERS ========= #

def get_db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in environment.")
    return psycopg2.connect(DATABASE_URL)


# ========= FIXTURE LOADER ========= #

def load_fixtures_for_range(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """
    Hämta matcher från API-Football för ett datumintervall.
    Använder samma källa som combined_sports_runner.py.
    
    Returns:
        Lista med dictionaries: fixture_id, home_team, away_team, kickoff, league
    """
    from league_config import LEAGUE_REGISTRY
    
    league_ids = []
    
    for league in LEAGUE_REGISTRY:
        if isinstance(league, dict):
            api_id = league.get("api_football_id") or league.get("league_id")
        else:
            api_id = (
                getattr(league, "api_football_id", None)
                or getattr(league, "league_id", None)
                or getattr(league, "id", None)
            )
        
        if api_id:
            league_ids.append(api_id)
    
    if not league_ids:
        league_ids = [39, 140, 135, 78, 61, 88, 94, 2, 3, 848]
    
    fixtures = []
    
    try:
        from api_football_client import APIFootballClient
        
        api_football_client = APIFootballClient()
        
        print(f"[BACKTEST] Fetching fixtures from {len(league_ids)} leagues...")
        print(f"[BACKTEST] Date range: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
        
        for league_id in league_ids:
            try:
                if hasattr(api_football_client, 'get_fixtures_for_league'):
                    league_fixtures = api_football_client.get_fixtures_for_league(
                        league_id=league_id,
                        start_date=start,
                        end_date=end,
                    )
                    fixtures.extend(league_fixtures)
                    print(f"[BACKTEST] League {league_id}: {len(league_fixtures)} fixtures")
                else:
                    current_year = start.year
                    current_season = current_year if start.month >= 7 else current_year - 1
                    
                    params = {
                        'league': league_id,
                        'season': current_season,
                        'from': start.strftime('%Y-%m-%d'),
                        'to': end.strftime('%Y-%m-%d'),
                    }
                    
                    cache_key = f"backtest_fixtures_{league_id}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
                    response = api_football_client._fetch_with_cache('fixtures', params, cache_key, ttl_hours=168)
                    
                    if not response:
                        continue
                    
                    for fixture in response:
                        fixture_info = fixture.get('fixture', {})
                        teams = fixture.get('teams', {})
                        league_info = fixture.get('league', {})
                        
                        kickoff_str = fixture_info.get('date', '')
                        kickoff = None
                        if kickoff_str:
                            try:
                                kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
                            except:
                                pass
                        
                        fixtures.append({
                            "fixture_id": fixture_info.get('id'),
                            "home_team": teams.get('home', {}).get('name', 'Unknown'),
                            "away_team": teams.get('away', {}).get('name', 'Unknown'),
                            "kickoff": kickoff,
                            "kickoff_str": kickoff_str,
                            "league": league_info.get('name', f'League {league_id}'),
                            "league_id": league_id,
                            "status": fixture_info.get('status', {}).get('short', 'NS'),
                            "home_score": fixture.get('goals', {}).get('home'),
                            "away_score": fixture.get('goals', {}).get('away'),
                        })
                    
                    print(f"[BACKTEST] League {league_id}: {len(response)} fixtures")
                
            except Exception as e:
                print(f"[BACKTEST] ⚠️ Error fetching league {league_id}: {e}")
                continue
        
        print(f"[BACKTEST] Total fixtures loaded: {len(fixtures)}")
        
    except ImportError as e:
        print(f"[BACKTEST] ⚠️ Import error: {e}")
        print("[BACKTEST] Falling back to database historical fixtures...")
        
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT DISTINCT home_team, away_team, match_date, kickoff_time, league
                FROM football_opportunities
                WHERE match_date BETWEEN %s AND %s
                  AND mode = 'PROD'
                ORDER BY match_date
            """, (start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')))
            
            for row in cur.fetchall():
                home_team, away_team, match_date, kickoff_time, league = row
                fixtures.append({
                    "fixture_id": f"{home_team}_{away_team}_{match_date}",
                    "home_team": home_team,
                    "away_team": away_team,
                    "kickoff": None,
                    "kickoff_str": f"{match_date}T{kickoff_time or '15:00'}:00Z",
                    "league": league or "Unknown",
                })
        finally:
            cur.close()
            conn.close()
    
    return fixtures


# ========= BET GENERATOR ========= #

def generate_backtest_bets_for_fixture(fixture: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generera backtest-bets för en match genom att anropa samma motor
    som används för riktiga bets.
    
    Args:
        fixture: Dict med fixture_id, home_team, away_team, kickoff, league
        
    Returns:
        Lista med bets: home_team, away_team, odds, stake, product, selection, ev, legs
    """
    bets = []
    
    home_team = fixture.get("home_team")
    away_team = fixture.get("away_team")
    league = fixture.get("league")
    kickoff = fixture.get("kickoff")
    kickoff_str = fixture.get("kickoff_str", "")
    fixture_id = fixture.get("fixture_id")
    
    match_date = ""
    kickoff_time = ""
    if kickoff:
        match_date = kickoff.strftime("%Y-%m-%d")
        kickoff_time = kickoff.strftime("%H:%M")
    elif kickoff_str:
        match_date = kickoff_str[:10] if len(kickoff_str) > 10 else ""
        kickoff_time = kickoff_str[11:16] if len(kickoff_str) > 16 else ""
    
    try:
        if PRODUCT_CODE == "VALUE_SINGLE":
            bets.extend(_generate_value_single_bets(fixture, home_team, away_team, league, match_date, kickoff_time))
        
        elif PRODUCT_CODE == "EXACT_SCORE":
            bets.extend(_generate_exact_score_bets(fixture, home_team, away_team, league, match_date, kickoff_time))
        
        elif PRODUCT_CODE == "SGP":
            bets.extend(_generate_sgp_bets(fixture, home_team, away_team, league, match_date, kickoff_time))
        
        else:
            print(f"[BACKTEST] ⚠️ Unknown product: {PRODUCT_CODE}")
    
    except Exception as e:
        print(f"[BACKTEST] ⚠️ Error generating bets for {home_team} vs {away_team}: {e}")
    
    return bets


def _generate_value_single_bets(fixture: Dict, home_team: str, away_team: str, 
                                 league: str, match_date: str, kickoff_time: str) -> List[Dict]:
    """Generate Value Singles bets using existing engine logic."""
    bets = []
    
    try:
        from real_football_champion import RealFootballChampion
        from value_singles_engine import ValueSinglesEngine
        
        champion = RealFootballChampion()
        engine = ValueSinglesEngine(champion=champion)
        
        match_dict = {
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "match_id": fixture.get("fixture_id"),
            "commence_time": fixture.get("kickoff_str", ""),
            "formatted_date": match_date,
            "formatted_time": kickoff_time,
        }
        
        odds_dict = champion.get_odds_for_match(match_dict) if hasattr(champion, "get_odds_for_match") else {}
        
        if not odds_dict:
            return bets
        
        lh, la = 1.5, 1.3
        try:
            if hasattr(champion, "analyze_team_form"):
                home_id = champion.get_team_id_by_name(home_team) if hasattr(champion, "get_team_id_by_name") else None
                away_id = champion.get_team_id_by_name(away_team) if hasattr(champion, "get_team_id_by_name") else None
                
                home_form = champion.analyze_team_form(home_team, home_id)
                away_form = champion.analyze_team_form(away_team, away_id)
                
                if home_form and away_form and hasattr(champion, "calculate_xg_edge"):
                    xg = champion.calculate_xg_edge(home_form, away_form, None)
                    lh = float(xg.get("home_xg", 1.5))
                    la = float(xg.get("away_xg", 1.3))
        except:
            pass
        
        probs = engine._build_single_markets(lh, la)
        
        for market_key, p_model in probs.items():
            odds = odds_dict.get(market_key)
            if odds is None or odds < 1.2:
                continue
            
            ev = engine._calc_ev(p_model, odds)
            if ev < engine.ev_threshold:
                continue
            
            confidence = int(min(100, max(0, 50 + ev * 250)))
            if confidence < engine.min_confidence:
                continue
            
            selection_text = _get_selection_text(market_key, home_team, away_team)
            
            stake = min(DEFAULT_STAKE * (1 + ev * 2), DEFAULT_STAKE * 2)
            
            bets.append({
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "match_date": match_date,
                "kickoff_time": kickoff_time,
                "market": market_key,
                "selection": selection_text,
                "odds": float(odds),
                "stake": float(stake),
                "ev": float(ev),
                "confidence": confidence,
                "product": "VALUE_SINGLE",
                "model_prob": float(p_model),
            })
        
    except ImportError as e:
        print(f"[BACKTEST] ⚠️ ValueSingles import error: {e}")
    except Exception as e:
        print(f"[BACKTEST] ⚠️ ValueSingles generation error: {e}")
    
    return bets


def _generate_exact_score_bets(fixture: Dict, home_team: str, away_team: str,
                                league: str, match_date: str, kickoff_time: str) -> List[Dict]:
    """Generate Exact Score bets using existing engine logic."""
    bets = []
    
    try:
        from exact_score_predictor import ExactScorePredictor
        
        predictor = ExactScorePredictor()
        
        match_dict = {
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "match_id": fixture.get("fixture_id"),
            "formatted_date": match_date,
            "formatted_time": kickoff_time,
        }
        
        predictions = predictor.predict_exact_score(match_dict) if hasattr(predictor, "predict_exact_score") else []
        
        for pred in predictions[:3]:
            bets.append({
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "match_date": match_date,
                "kickoff_time": kickoff_time,
                "market": "exact_score",
                "selection": pred.get("score", "1-1"),
                "odds": float(pred.get("odds", 10.0)),
                "stake": float(pred.get("stake", DEFAULT_STAKE)),
                "ev": float(pred.get("ev", 0.05)),
                "confidence": int(pred.get("confidence", 50)),
                "product": "EXACT_SCORE",
                "model_prob": float(pred.get("probability", 0.1)),
            })
        
    except ImportError:
        from scipy.stats import poisson
        
        lh, la = 1.5, 1.3
        
        for home_goals in range(5):
            for away_goals in range(5):
                prob = poisson.pmf(home_goals, lh) * poisson.pmf(away_goals, la)
                if prob < 0.03:
                    continue
                
                implied_odds = 1 / prob if prob > 0 else 50
                bookmaker_odds = implied_odds * 0.92
                ev = (prob * bookmaker_odds - 1)
                
                if ev > 0.03:
                    bets.append({
                        "home_team": home_team,
                        "away_team": away_team,
                        "league": league,
                        "match_date": match_date,
                        "kickoff_time": kickoff_time,
                        "market": "exact_score",
                        "selection": f"{home_goals}-{away_goals}",
                        "odds": round(bookmaker_odds, 2),
                        "stake": DEFAULT_STAKE,
                        "ev": round(ev, 4),
                        "confidence": int(min(100, 50 + ev * 200)),
                        "product": "EXACT_SCORE",
                        "model_prob": round(prob, 4),
                    })
    except Exception as e:
        print(f"[BACKTEST] ⚠️ ExactScore generation error: {e}")
    
    return bets


def _generate_sgp_bets(fixture: Dict, home_team: str, away_team: str,
                        league: str, match_date: str, kickoff_time: str) -> List[Dict]:
    """Generate SGP bets using existing engine logic."""
    bets = []
    
    try:
        from sgp_champion import SGPChampion
        
        champion = SGPChampion()
        
        match_dict = {
            "home_team": home_team,
            "away_team": away_team,
            "league": league,
            "match_id": fixture.get("fixture_id"),
            "formatted_date": match_date,
            "formatted_time": kickoff_time,
        }
        
        parlays = champion.generate_sgp_for_match(match_dict) if hasattr(champion, "generate_sgp_for_match") else []
        
        for parlay in parlays[:2]:
            legs = parlay.get("legs", [])
            legs_str = " + ".join([leg.get("selection", "") for leg in legs]) if isinstance(legs, list) else str(legs)
            
            bets.append({
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "match_date": match_date,
                "kickoff_time": kickoff_time,
                "legs": legs_str,
                "parlay_description": parlay.get("description", legs_str),
                "parlay_probability": float(parlay.get("probability", 0.1)),
                "fair_odds": float(parlay.get("fair_odds", 10.0)),
                "bookmaker_odds": float(parlay.get("bookmaker_odds", 8.0)),
                "ev_percentage": float(parlay.get("ev", 0.05)) * 100,
                "stake": float(parlay.get("stake", DEFAULT_STAKE)),
                "kelly_stake": float(parlay.get("kelly_stake", DEFAULT_STAKE * 0.5)),
                "product": "SGP",
            })
        
    except ImportError:
        from scipy.stats import poisson
        
        lh, la = 1.5, 1.3
        
        p_btts = 1 - poisson.pmf(0, lh) - poisson.pmf(0, la) + poisson.pmf(0, lh) * poisson.pmf(0, la)
        p_btts = 1 - (poisson.pmf(0, lh) + poisson.pmf(0, la) - poisson.pmf(0, lh) * poisson.pmf(0, la))
        p_over25 = 1 - sum(poisson.pmf(h, lh) * poisson.pmf(a, la) for h in range(3) for a in range(3-h))
        
        parlay_prob = p_btts * p_over25 * 0.85
        fair_odds = 1 / parlay_prob if parlay_prob > 0 else 20
        bookmaker_odds = fair_odds * 0.88
        ev = parlay_prob * bookmaker_odds - 1
        
        if ev > 0.03:
            bets.append({
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "match_date": match_date,
                "kickoff_time": kickoff_time,
                "legs": "BTTS Yes + Over 2.5 Goals",
                "parlay_description": f"{home_team} vs {away_team}: BTTS Yes + Over 2.5",
                "parlay_probability": round(parlay_prob, 4),
                "fair_odds": round(fair_odds, 2),
                "bookmaker_odds": round(bookmaker_odds, 2),
                "ev_percentage": round(ev * 100, 2),
                "stake": DEFAULT_STAKE,
                "kelly_stake": DEFAULT_STAKE * 0.5,
                "product": "SGP",
            })
    except Exception as e:
        print(f"[BACKTEST] ⚠️ SGP generation error: {e}")
    
    return bets


def _get_selection_text(market_key: str, home_team: str, away_team: str) -> str:
    """Convert market key to human-readable selection text."""
    return {
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
        "1H_OVER_0_5": "1H Over 0.5 Goals",
        "BTTS_YES": "BTTS Yes",
        "BTTS_NO": "BTTS No",
        "HOME_WIN": f"{home_team} Win",
        "DRAW": "Draw",
        "AWAY_WIN": f"{away_team} Win",
        "DC_HOME_DRAW": "Home or Draw",
        "DC_HOME_AWAY": "Home or Away",
        "DC_DRAW_AWAY": "Draw or Away",
        "DNB_HOME": f"DNB {home_team}",
        "DNB_AWAY": f"DNB {away_team}",
        "CORNERS_OVER_8_5": "Corners Over 8.5",
        "CORNERS_OVER_9_5": "Corners Over 9.5",
        "CORNERS_OVER_10_5": "Corners Over 10.5",
        "CORNERS_OVER_11_5": "Corners Over 11.5",
        "HOME_OVER_0_5": f"{home_team} Over 0.5 Goals",
        "HOME_OVER_1_5": f"{home_team} Over 1.5 Goals",
        "AWAY_OVER_0_5": f"{away_team} Over 0.5 Goals",
        "AWAY_OVER_1_5": f"{away_team} Over 1.5 Goals",
    }.get(market_key, market_key)


# ========= BET INSERTER ========= #

def insert_backtest_bets(bets: List[Dict[str, Any]]):
    """
    Sparar alla backtest-bets i rätt tabell beroende på produkt.
    Alla inserts sätter mode='BACKTEST'.
    """
    if not bets:
        return
    
    conn = get_db_conn()
    cur = conn.cursor()
    
    try:
        now = datetime.utcnow()
        timestamp = int(now.timestamp())
        
        football_bets = [b for b in bets if b.get("product") in ("VALUE_SINGLE", "EXACT_SCORE")]
        sgp_bets = [b for b in bets if b.get("product") == "SGP"]
        
        if football_bets:
            insert_sql = """
                INSERT INTO football_opportunities
                (timestamp, home_team, away_team, league, market, selection, odds, 
                 edge_percentage, confidence, stake, match_date, kickoff_time, 
                 status, mode, model_prob, tier, recommended_date)
                VALUES %s
                ON CONFLICT DO NOTHING
            """
            
            rows = []
            for b in football_bets:
                rows.append((
                    timestamp,
                    b.get("home_team"),
                    b.get("away_team"),
                    b.get("league"),
                    b.get("market", "Value Single"),
                    b.get("selection"),
                    float(b.get("odds", 0)),
                    float(b.get("ev", 0)) * 100,
                    int(b.get("confidence", 50)),
                    float(b.get("stake", DEFAULT_STAKE)),
                    b.get("match_date"),
                    b.get("kickoff_time"),
                    "pending",
                    "BACKTEST",
                    float(b.get("model_prob", 0)),
                    b.get("product", "VALUE_SINGLE").lower(),
                    now.strftime("%Y-%m-%d"),
                ))
            
            execute_values(cur, insert_sql, rows)
            print(f"[BACKTEST] Inserted {len(rows)} football bets")
        
        if sgp_bets:
            insert_sql = """
                INSERT INTO sgp_predictions
                (timestamp, home_team, away_team, league, match_date, kickoff_time,
                 legs, parlay_description, parlay_probability, fair_odds, bookmaker_odds,
                 ev_percentage, stake, kelly_stake, status, mode)
                VALUES %s
                ON CONFLICT DO NOTHING
            """
            
            rows = []
            for b in sgp_bets:
                rows.append((
                    timestamp,
                    b.get("home_team"),
                    b.get("away_team"),
                    b.get("league"),
                    b.get("match_date"),
                    b.get("kickoff_time"),
                    b.get("legs"),
                    b.get("parlay_description"),
                    float(b.get("parlay_probability", 0)),
                    float(b.get("fair_odds", 0)),
                    float(b.get("bookmaker_odds", 0)),
                    float(b.get("ev_percentage", 0)),
                    float(b.get("stake", DEFAULT_STAKE)),
                    float(b.get("kelly_stake", DEFAULT_STAKE * 0.5)),
                    "pending",
                    "BACKTEST",
                ))
            
            execute_values(cur, insert_sql, rows)
            print(f"[BACKTEST] Inserted {len(rows)} SGP bets")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"[BACKTEST] ❌ Insert error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ========= MAIN BACKTEST LOOP ========= #

def run_backtest(days: int = None, product: str = None, start_date: str = None, end_date: str = None):
    """
    Run backtest for a date range.
    
    Args:
        days: Number of days to backtest (default: BACKTEST_DAYS)
        product: Product code to backtest (default: PRODUCT_CODE)
        start_date: Start date string YYYY-MM-DD (overrides days)
        end_date: End date string YYYY-MM-DD (defaults to today)
    """
    global PRODUCT_CODE
    
    if product:
        if product not in SUPPORTED_PRODUCTS:
            print(f"[BACKTEST] ❌ Unsupported product: {product}")
            print(f"[BACKTEST] Supported: {SUPPORTED_PRODUCTS}")
            return
        PRODUCT_CODE = product
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end = datetime.utcnow()
    
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        days = days or BACKTEST_DAYS
        start = end - timedelta(days=days)
    
    print(f"[BACKTEST] {'='*60}")
    print(f"[BACKTEST] Running backtest for product={PRODUCT_CODE}")
    print(f"[BACKTEST] Date range: {start.date()} to {end.date()}")
    print(f"[BACKTEST] Target table: {TABLE_MAPPING.get(PRODUCT_CODE, 'unknown')}")
    print(f"[BACKTEST] {'='*60}")
    
    fixtures = load_fixtures_for_range(start, end)
    print(f"[BACKTEST] Loaded {len(fixtures)} fixtures in range.")
    
    if not fixtures:
        print("[BACKTEST] No fixtures found. Check API key or date range.")
        return
    
    total_bets = 0
    batch_size = 50
    batch_bets = []
    
    for i, fix in enumerate(fixtures, start=1):
        print(f"[BACKTEST] [{i}/{len(fixtures)}] {fix.get('home_team')} – {fix.get('away_team')} ({fix.get('league', 'N/A')})")
        
        bets = generate_backtest_bets_for_fixture(fix)
        
        for b in bets:
            b.setdefault("product", PRODUCT_CODE)
            b.setdefault("stake", DEFAULT_STAKE)
        
        batch_bets.extend(bets)
        
        if len(batch_bets) >= batch_size:
            insert_backtest_bets(batch_bets)
            total_bets += len(batch_bets)
            batch_bets = []
    
    if batch_bets:
        insert_backtest_bets(batch_bets)
        total_bets += len(batch_bets)
    
    print(f"[BACKTEST] {'='*60}")
    print(f"[BACKTEST] Done. Inserted {total_bets} BACKTEST bets.")
    print(f"[BACKTEST] {'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run PGR backtest")
    parser.add_argument("--days", type=int, default=BACKTEST_DAYS, help="Days to backtest")
    parser.add_argument("--product", type=str, default=PRODUCT_CODE, help="Product code")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD")
    
    args = parser.parse_args()
    
    run_backtest(
        days=args.days,
        product=args.product,
        start_date=args.start,
        end_date=args.end
    )
