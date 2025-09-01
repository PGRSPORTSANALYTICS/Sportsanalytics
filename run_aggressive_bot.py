"""
🔥 AGGRESSIVE E-SOCCER BOT - CONTINUOUS BETTING ACTION
4+ games running with constant opportunities
"""

import asyncio
import time
from esoccer_scraper import RealEsoccerScraper
from aggressive_esoccer_betting import AggressiveEsoccerBetting
import sqlite3

class Match:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class AggressiveEsoccerBot:
    """Super aggressive e-soccer betting bot"""
    
    def __init__(self):
        self.scraper = RealEsoccerScraper()
        self.betting_system = AggressiveEsoccerBetting(bankroll=1000.0)
        self.bankroll = 1000.0
        
    async def run_continuous_betting(self):
        """🔥 Continuous aggressive betting loop"""
        print("🔥 AGGRESSIVE E-SOCCER BOT - CONTINUOUS ACTION STARTED!")
        print("🎯 Target: 4+ games running with constant betting opportunities")
        
        cycle = 0
        
        while True:
            cycle += 1
            print(f"\n🔄 AGGRESSIVE CYCLE #{cycle} - Scanning for opportunities...")
            
            try:
                # Get live e-soccer matches
                esoccer_data = self.scraper.get_esoccer_matches()
                
                if not esoccer_data:
                    print("⚠️ No matches found - waiting 30 seconds...")
                    await asyncio.sleep(30)
                    continue
                
                print(f"🎮 SCANNING {len(esoccer_data)} live e-soccer matches...")
                
                # Convert to match objects
                matches = []
                for match_data in esoccer_data:
                    match = Match(
                        match_id=match_data['match_id'],
                        home=match_data['home_team'],
                        away=match_data['away_team'],
                        league=match_data['league'],
                        elapsed=match_data.get('elapsed', 2),  # Default to 2 minutes
                        score=match_data.get('score', '0-0'),
                        home_goals=0,
                        away_goals=0,
                        odds={}
                    )
                    
                    # Apply odds from the match data
                    if 'odds' in match_data:
                        odds_data = match_data['odds']
                        
                        # Over/Under odds
                        if 'totals' in odds_data:
                            for line_key, odds_list in odds_data['totals'].items():
                                if odds_list:
                                    best_odds = max(item['odds'] for item in odds_list)
                                    match.odds[line_key] = best_odds
                        
                        # BTTS odds
                        if 'btts' in odds_data:
                            if 'yes' in odds_data['btts']:
                                match.odds['btts_yes'] = odds_data['btts']['yes']
                            if 'no' in odds_data['btts']:
                                match.odds['btts_no'] = odds_data['btts']['no']
                    
                    matches.append(match)
                
                # Find aggressive betting opportunities
                all_opportunities = []
                for match in matches:
                    opportunities = self.betting_system.find_aggressive_opportunities([match])
                    all_opportunities.extend(opportunities)
                
                if all_opportunities:
                    print(f"🔥 FOUND {len(all_opportunities)} AGGRESSIVE BETTING OPPORTUNITIES!")
                    
                    for bet in all_opportunities:
                        print(f"✅ PLACING BET: {bet.market} @ {bet.odds}")
                        print(f"   {bet.home} vs {bet.away}")
                        print(f"   Stake: ${bet.stake}, Edge: {bet.edge:.1%}")
                        print(f"   Reason: {bet.reason}")
                        
                        # Save bet to database (simplified)
                        try:
                            conn = sqlite3.connect('data/esoccer.db')
                            cur = conn.cursor()
                            
                            # Create tables if they don't exist
                            cur.execute("""
                                CREATE TABLE IF NOT EXISTS tickets (
                                    id TEXT PRIMARY KEY,
                                    open_ts INTEGER,
                                    match_id TEXT,
                                    league TEXT,
                                    home TEXT,
                                    away TEXT,
                                    market_t REAL,
                                    market_name TEXT,
                                    odds REAL,
                                    stake REAL,
                                    is_settled INTEGER,
                                    win INTEGER,
                                    close_ts INTEGER,
                                    pnl REAL
                                )
                            """)
                            
                            # Insert bet
                            bet_id = f"{bet.match_id}:{bet.market}:{int(time.time())}"
                            cur.execute("""
                                INSERT OR REPLACE INTO tickets
                                (id, open_ts, match_id, league, home, away, market_t, 
                                 market_name, odds, stake, is_settled, win, close_ts, pnl)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                bet_id, int(time.time()), bet.match_id, 
                                getattr(matches[0], 'league', 'E-soccer League'),
                                bet.home, bet.away, 0.0, bet.market, bet.odds, bet.stake,
                                0, None, None, 0.0
                            ))
                            
                            conn.commit()
                            conn.close()
                            
                        except Exception as e:
                            print(f"⚠️ Database error: {e}")
                    
                    # Update bankroll
                    total_stake = sum(bet.stake for bet in all_opportunities)
                    self.bankroll -= total_stake
                    self.betting_system.bankroll = self.bankroll
                    
                    print(f"💰 UPDATED BANKROLL: ${self.bankroll:.2f} (Risk: ${total_stake:.2f})")
                    
                else:
                    print("❌ NO AGGRESSIVE OPPORTUNITIES FOUND - system may need tuning")
                
                # Wait before next cycle
                print(f"⏱️ Waiting 60 seconds before next aggressive scan...")
                await asyncio.sleep(60)
                
            except Exception as e:
                print(f"❌ Error in aggressive betting cycle: {e}")
                await asyncio.sleep(30)

async def main():
    """Run the aggressive e-soccer betting bot"""
    bot = AggressiveEsoccerBot()
    await bot.run_continuous_betting()

if __name__ == "__main__":
    asyncio.run(main())