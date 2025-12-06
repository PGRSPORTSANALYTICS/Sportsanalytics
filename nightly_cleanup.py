#!/usr/bin/env python3
"""
Nightly Cleanup Script
Moves settled bets to historical table and generates daily report.
Run this every night after midnight to archive yesterday's bets.
"""

import os
from datetime import datetime, timedelta
from db_helper import DatabaseHelper

USD_TO_SEK = 10.8

class NightlyCleanup:
    def __init__(self):
        self.report_date = None
        self.stats = {
            'exact_score': {'won': 0, 'lost': 0, 'pending': 0, 'profit': 0, 'stake': 0},
            'sgp': {'won': 0, 'lost': 0, 'pending': 0, 'profit': 0, 'stake': 0},
            'basketball': {'won': 0, 'lost': 0, 'pending': 0, 'profit': 0, 'stake': 0},
            'ml_parlay': {'won': 0, 'lost': 0, 'pending': 0, 'profit': 0, 'stake': 0},
            'value_singles': {'won': 0, 'lost': 0, 'pending': 0, 'profit': 0, 'stake': 0}
        }
        
    def create_historical_table(self):
        """Create historical_bets table if it doesn't exist"""
        DatabaseHelper.execute("""
            CREATE TABLE IF NOT EXISTS historical_bets (
                id SERIAL PRIMARY KEY,
                original_id INTEGER,
                bet_type VARCHAR(50),
                match TEXT,
                league VARCHAR(255),
                market VARCHAR(100),
                selection TEXT,
                odds DECIMAL(10,2),
                stake_sek DECIMAL(10,2),
                ev_percentage DECIMAL(10,2),
                confidence DECIMAL(10,2),
                match_date TIMESTAMP,
                created_at TIMESTAMP,
                settled_at TIMESTAMP,
                outcome VARCHAR(20),
                profit_loss_sek DECIMAL(10,2),
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Historical bets table ready")
        
    def archive_exact_score_bets(self):
        """Archive settled exact score predictions"""
        rows = DatabaseHelper.execute("""
            SELECT id, match_id, market, selection, prob, ev, 
                   created_at, outcome, profit_loss
            FROM predictions 
            WHERE outcome IS NOT NULL AND outcome != ''
        """, fetch='all')
        
        if not rows:
            return 0
            
        archived = 0
        for row in rows:
            try:
                outcome = row[7] if row[7] else 'unknown'
                profit = float(row[8]) if row[8] else 0
                stake = 214  # Default stake in SEK
                
                if outcome.lower() == 'won':
                    self.stats['exact_score']['won'] += 1
                    self.stats['exact_score']['profit'] += profit
                elif outcome.lower() == 'lost':
                    self.stats['exact_score']['lost'] += 1
                    self.stats['exact_score']['profit'] -= stake
                    
                self.stats['exact_score']['stake'] += stake
                
                DatabaseHelper.execute("""
                    INSERT INTO historical_bets 
                    (original_id, bet_type, match, market, selection, odds, stake_sek, 
                     ev_percentage, created_at, outcome, profit_loss_sek)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row[0], 'exact_score', row[1], row[2], row[3], 
                      10.0, stake, float(row[5])*100 if row[5] else 0,
                      row[6], outcome, profit))
                      
                DatabaseHelper.execute("""
                    DELETE FROM predictions WHERE id = %s
                """, (row[0],))
                archived += 1
            except Exception as e:
                print(f"   ⚠️ Error archiving prediction {row[0]}: {e}")
                
        return archived
        
    def archive_sgp_bets(self):
        """Archive settled SGP predictions"""
        rows = DatabaseHelper.execute("""
            SELECT id, home_team, away_team, league, parlay_description, 
                   bookmaker_odds, stake, ev_percentage, match_date,
                   status, outcome, payout
            FROM sgp_predictions 
            WHERE status IN ('won', 'lost', 'settled')
        """, fetch='all')
        
        if not rows:
            return 0
            
        archived = 0
        for row in rows:
            try:
                status = row[9] if row[9] else 'unknown'
                stake = float(row[6]) if row[6] else 0
                payout = float(row[11]) if row[11] else 0
                odds = float(row[5]) if row[5] else 0
                
                if status == 'won':
                    self.stats['sgp']['won'] += 1
                    profit = payout - stake
                    self.stats['sgp']['profit'] += profit
                elif status in ('lost', 'settled'):
                    self.stats['sgp']['lost'] += 1
                    profit = -stake
                    self.stats['sgp']['profit'] -= stake
                else:
                    profit = 0
                    
                self.stats['sgp']['stake'] += stake
                
                match_name = f"{row[1]} vs {row[2]}"
                
                DatabaseHelper.execute("""
                    INSERT INTO historical_bets 
                    (original_id, bet_type, match, league, market, selection, odds, 
                     stake_sek, ev_percentage, match_date, outcome, profit_loss_sek)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row[0], 'sgp', match_name, row[3], 'SGP', row[4], 
                      odds, stake, float(row[7]) if row[7] else 0,
                      row[8], status, profit))
                      
                DatabaseHelper.execute("""
                    DELETE FROM sgp_predictions WHERE id = %s
                """, (row[0],))
                archived += 1
            except Exception as e:
                print(f"   ⚠️ Error archiving SGP {row[0]}: {e}")
                
        return archived
        
    def archive_basketball_bets(self):
        """Archive settled basketball predictions"""
        rows = DatabaseHelper.execute("""
            SELECT id, match, league, market, selection, odds, 
                   ev_percentage, confidence, commence_time, status, is_parlay
            FROM basketball_predictions 
            WHERE status IN ('won', 'lost')
        """, fetch='all')
        
        if not rows:
            return 0
            
        archived = 0
        for row in rows:
            try:
                status = row[9] if row[9] else 'unknown'
                odds = float(row[5]) if row[5] else 0
                stake = 214  # Default stake
                
                if status == 'won':
                    self.stats['basketball']['won'] += 1
                    profit = stake * (odds - 1)
                    self.stats['basketball']['profit'] += profit
                elif status == 'lost':
                    self.stats['basketball']['lost'] += 1
                    profit = -stake
                    self.stats['basketball']['profit'] -= stake
                else:
                    profit = 0
                    
                self.stats['basketball']['stake'] += stake
                
                DatabaseHelper.execute("""
                    INSERT INTO historical_bets 
                    (original_id, bet_type, match, league, market, selection, odds, 
                     stake_sek, ev_percentage, confidence, match_date, outcome, profit_loss_sek)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row[0], 'basketball', row[1], row[2], row[3], row[4], 
                      odds, stake, float(row[6]) if row[6] else 0,
                      float(row[7]) if row[7] else 0, row[8], status, profit))
                      
                DatabaseHelper.execute("""
                    DELETE FROM basketball_predictions WHERE id = %s
                """, (row[0],))
                archived += 1
            except Exception as e:
                print(f"   ⚠️ Error archiving basketball {row[0]}: {e}")
                
        return archived
        
    def archive_ml_parlays(self):
        """Archive settled ML parlay predictions"""
        rows = DatabaseHelper.execute("""
            SELECT id, parlay_description, status, 
                   total_odds, stake, combined_ev, match_date, potential_payout, profit_loss
            FROM ml_parlay_predictions 
            WHERE status IN ('won', 'lost')
        """, fetch='all')
        
        if not rows:
            return 0
            
        archived = 0
        for row in rows:
            try:
                status = row[2] if row[2] else 'unknown'
                stake = float(row[4]) if row[4] else 0
                odds = float(row[3]) if row[3] else 0
                profit_loss = float(row[8]) if row[8] else 0
                
                if status == 'won':
                    self.stats['ml_parlay']['won'] += 1
                    self.stats['ml_parlay']['profit'] += profit_loss
                elif status == 'lost':
                    self.stats['ml_parlay']['lost'] += 1
                    self.stats['ml_parlay']['profit'] += profit_loss
                    
                self.stats['ml_parlay']['stake'] += stake
                
                match_name = row[1] or 'ML Parlay'
                
                DatabaseHelper.execute("""
                    INSERT INTO historical_bets 
                    (original_id, bet_type, match, market, odds, 
                     stake_sek, ev_percentage, match_date, outcome, profit_loss_sek)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row[0], 'ml_parlay', match_name, 'ML Parlay', 
                      odds, stake, float(row[5])*100 if row[5] else 0,
                      row[6], status, profit_loss))
                      
                DatabaseHelper.execute("""
                    DELETE FROM ml_parlay_predictions WHERE id = %s
                """, (row[0],))
                archived += 1
            except Exception as e:
                print(f"   ⚠️ Error archiving ML parlay {row[0]}: {e}")
                
        return archived
        
    def count_pending(self):
        """Count pending bets across all tables"""
        exact = DatabaseHelper.execute("""
            SELECT COUNT(*) FROM predictions WHERE outcome IS NULL OR outcome = ''
        """, fetch='one')
        self.stats['exact_score']['pending'] = exact[0] if exact else 0
        
        sgp = DatabaseHelper.execute("""
            SELECT COUNT(*) FROM sgp_predictions WHERE status = 'pending'
        """, fetch='one')
        self.stats['sgp']['pending'] = sgp[0] if sgp else 0
        
        basket = DatabaseHelper.execute("""
            SELECT COUNT(*) FROM basketball_predictions WHERE status = 'pending'
        """, fetch='one')
        self.stats['basketball']['pending'] = basket[0] if basket else 0
        
        ml = DatabaseHelper.execute("""
            SELECT COUNT(*) FROM ml_parlay_predictions WHERE status = 'pending'
        """, fetch='one')
        self.stats['ml_parlay']['pending'] = ml[0] if ml else 0
        
    def generate_report(self, date_str=None):
        """Generate daily summary report"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            
        self.report_date = date_str
        
        report = []
        report.append("=" * 60)
        report.append(f"📊 PGR DAILY REPORT - {date_str}")
        report.append("=" * 60)
        report.append("")
        
        total_won = 0
        total_lost = 0
        total_profit = 0
        total_stake = 0
        
        for bet_type, stats in self.stats.items():
            if stats['won'] > 0 or stats['lost'] > 0 or stats['pending'] > 0:
                total = stats['won'] + stats['lost']
                hit_rate = (stats['won'] / total * 100) if total > 0 else 0
                roi = (stats['profit'] / stats['stake'] * 100) if stats['stake'] > 0 else 0
                
                name_map = {
                    'exact_score': '🎯 Exact Score',
                    'sgp': '🎲 SGP',
                    'basketball': '🏀 Basketball',
                    'ml_parlay': '📊 ML Parlay',
                    'value_singles': '💰 Value Singles'
                }
                
                report.append(f"{name_map.get(bet_type, bet_type)}")
                report.append(f"   Settled: {total} ({stats['won']}W / {stats['lost']}L)")
                report.append(f"   Hit Rate: {hit_rate:.1f}%")
                report.append(f"   P/L: {stats['profit']:+,.0f} SEK ({stats['profit']/USD_TO_SEK:+,.0f} USD)")
                report.append(f"   ROI: {roi:+.1f}%")
                report.append(f"   Pending: {stats['pending']}")
                report.append("")
                
                total_won += stats['won']
                total_lost += stats['lost']
                total_profit += stats['profit']
                total_stake += stats['stake']
        
        overall_hit = (total_won / (total_won + total_lost) * 100) if (total_won + total_lost) > 0 else 0
        overall_roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
        
        report.append("-" * 60)
        report.append("📈 OVERALL SUMMARY")
        report.append(f"   Total Settled: {total_won + total_lost} ({total_won}W / {total_lost}L)")
        report.append(f"   Overall Hit Rate: {overall_hit:.1f}%")
        report.append(f"   Total P/L: {total_profit:+,.0f} SEK ({total_profit/USD_TO_SEK:+,.0f} USD)")
        report.append(f"   Overall ROI: {overall_roi:+.1f}%")
        report.append(f"   Total Staked: {total_stake:,.0f} SEK ({total_stake/USD_TO_SEK:,.0f} USD)")
        report.append("")
        
        total_pending = sum(s['pending'] for s in self.stats.values())
        report.append(f"⏳ PENDING BETS: {total_pending}")
        report.append("=" * 60)
        
        return "\n".join(report)
        
    def save_daily_summary(self, report):
        """Save daily summary to database"""
        DatabaseHelper.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                id SERIAL PRIMARY KEY,
                report_date DATE UNIQUE,
                exact_score_won INTEGER DEFAULT 0,
                exact_score_lost INTEGER DEFAULT 0,
                exact_score_profit DECIMAL(10,2) DEFAULT 0,
                sgp_won INTEGER DEFAULT 0,
                sgp_lost INTEGER DEFAULT 0,
                sgp_profit DECIMAL(10,2) DEFAULT 0,
                basketball_won INTEGER DEFAULT 0,
                basketball_lost INTEGER DEFAULT 0,
                basketball_profit DECIMAL(10,2) DEFAULT 0,
                ml_parlay_won INTEGER DEFAULT 0,
                ml_parlay_lost INTEGER DEFAULT 0,
                ml_parlay_profit DECIMAL(10,2) DEFAULT 0,
                total_profit DECIMAL(10,2) DEFAULT 0,
                report_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        total_profit = sum(s['profit'] for s in self.stats.values())
        
        try:
            DatabaseHelper.execute("""
                INSERT INTO daily_reports 
                (report_date, exact_score_won, exact_score_lost, exact_score_profit,
                 sgp_won, sgp_lost, sgp_profit,
                 basketball_won, basketball_lost, basketball_profit,
                 ml_parlay_won, ml_parlay_lost, ml_parlay_profit,
                 total_profit, report_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_date) DO UPDATE SET
                    exact_score_won = EXCLUDED.exact_score_won,
                    exact_score_lost = EXCLUDED.exact_score_lost,
                    exact_score_profit = EXCLUDED.exact_score_profit,
                    sgp_won = EXCLUDED.sgp_won,
                    sgp_lost = EXCLUDED.sgp_lost,
                    sgp_profit = EXCLUDED.sgp_profit,
                    basketball_won = EXCLUDED.basketball_won,
                    basketball_lost = EXCLUDED.basketball_lost,
                    basketball_profit = EXCLUDED.basketball_profit,
                    ml_parlay_won = EXCLUDED.ml_parlay_won,
                    ml_parlay_lost = EXCLUDED.ml_parlay_lost,
                    ml_parlay_profit = EXCLUDED.ml_parlay_profit,
                    total_profit = EXCLUDED.total_profit,
                    report_text = EXCLUDED.report_text
            """, (self.report_date, 
                  self.stats['exact_score']['won'], self.stats['exact_score']['lost'], 
                  self.stats['exact_score']['profit'],
                  self.stats['sgp']['won'], self.stats['sgp']['lost'], 
                  self.stats['sgp']['profit'],
                  self.stats['basketball']['won'], self.stats['basketball']['lost'], 
                  self.stats['basketball']['profit'],
                  self.stats['ml_parlay']['won'], self.stats['ml_parlay']['lost'], 
                  self.stats['ml_parlay']['profit'],
                  total_profit, report))
            print(f"✅ Daily summary saved for {self.report_date}")
        except Exception as e:
            print(f"⚠️ Error saving daily summary: {e}")
            
    def run(self, date_str=None):
        """Run the full nightly cleanup process"""
        print("\n" + "=" * 60)
        print("🌙 PGR NIGHTLY CLEANUP")
        print("=" * 60)
        
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            
        print(f"\n📅 Processing: {date_str}")
        
        print("\n📦 Setting up historical table...")
        self.create_historical_table()
        
        print("\n🗄️ Archiving settled bets...")
        exact_archived = self.archive_exact_score_bets()
        print(f"   Exact Score: {exact_archived} bets archived")
        
        sgp_archived = self.archive_sgp_bets()
        print(f"   SGP: {sgp_archived} bets archived")
        
        basket_archived = self.archive_basketball_bets()
        print(f"   Basketball: {basket_archived} bets archived")
        
        ml_archived = self.archive_ml_parlays()
        print(f"   ML Parlay: {ml_archived} bets archived")
        
        print("\n📊 Counting pending bets...")
        self.count_pending()
        
        print("\n📝 Generating daily report...")
        report = self.generate_report(date_str)
        
        print("\n💾 Saving daily summary...")
        self.save_daily_summary(report)
        
        print("\n" + report)
        
        return report


def main():
    import sys
    
    date_arg = None
    if len(sys.argv) > 1:
        date_arg = sys.argv[1]
    
    cleanup = NightlyCleanup()
    cleanup.run(date_arg)


if __name__ == "__main__":
    main()
