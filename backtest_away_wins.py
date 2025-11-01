"""
AWAY WINS BACKTEST: Simulate Away Win Predictions on Historical Matches
Tests if 0-2, 0-1, 1-2 would have worked on the same 159 settled matches
"""
import sqlite3
from typing import Dict, List

def backtest_away_wins():
    """Simulate away win predictions on historical settled matches"""
    conn = sqlite3.connect('data/real_football.db')
    cursor = conn.cursor()
    
    # Get ALL settled predictions with actual scores
    cursor.execute('''
        SELECT id, home_team, away_team, selection, result, odds, timestamp, match_date
        FROM football_opportunities
        WHERE result IS NOT NULL AND result != ''
        AND result NOT LIKE '%api-football%' = 0
        ORDER BY timestamp ASC
    ''')
    
    all_matches = cursor.fetchall()
    
    print(f"\n" + "="*70)
    print(f"⚽ AWAY WINS BACKTEST - Simulated Predictions")
    print(f"="*70)
    print(f"Analyzing {len(all_matches)} settled matches to see if away wins would have hit\n")
    
    if not all_matches:
        print("⚠️ No matches with actual scores found!")
        print("Run Smart Verifier first to get actual scores for settled matches\n")
        conn.close()
        return
    
    # Away win scores we want to test
    AWAY_WIN_SCORES = ['0-2', '0-1', '1-2']
    
    # Track what would have happened if we predicted away wins
    away_simulations = {
        '0-2': {'total': 0, 'won': 0, 'lost': 0},
        '0-1': {'total': 0, 'won': 0, 'lost': 0},
        '1-2': {'total': 0, 'won': 0, 'lost': 0}
    }
    
    # Also track what WAS actually predicted (home wins)
    home_predictions = {'total': 0, 'won': 0, 'lost': 0}
    
    # Analyze each match
    for match in all_matches:
        match_id, home_team, away_team, selection, result_raw, odds = match[:6]
        
        # Extract actual score from result (format: "2-1 (api-football)")
        actual_score = result_raw.replace(' (api-football)', '').strip()
        
        # Extract predicted score from selection (format: "Exact Score: 2-1")
        predicted_score = selection.replace('Exact Score: ', '').strip()
        
        # Determine if prediction won or lost
        prediction_won = (actual_score == predicted_score)
        
        # Track what was actually predicted
        home_predictions['total'] += 1
        if prediction_won:
            home_predictions['won'] += 1
        else:
            home_predictions['lost'] += 1
        
        # Simulate: What if we had predicted each away win score?
        for away_score in AWAY_WIN_SCORES:
            away_simulations[away_score]['total'] += 1
            
            # Check if this away score would have won
            if actual_score == away_score:
                away_simulations[away_score]['won'] += 1
            else:
                away_simulations[away_score]['lost'] += 1
    
    # Show results
    print(f"📊 ACTUAL HOME WIN PREDICTIONS (What we did):")
    print(f"="*70)
    home_wr = (home_predictions['won'] / home_predictions['total'] * 100) if home_predictions['total'] > 0 else 0
    print(f"   Total Bets: {home_predictions['total']}")
    print(f"   ✅ Wins: {home_predictions['won']}")
    print(f"   ❌ Losses: {home_predictions['lost']}")
    print(f"   📈 Hit Rate: {home_wr:.1f}%\n")
    
    print(f"🔄 SIMULATED AWAY WIN PREDICTIONS (What could have been):")
    print(f"="*70)
    print(f"{'Score':<10} {'Total':<10} {'Would Win':<12} {'Would Lose':<12} {'Hit Rate':<12} {'Assessment'}")
    print(f"-"*70)
    
    total_away_wins = 0
    total_away_bets = 0
    
    for score in AWAY_WIN_SCORES:
        stats = away_simulations[score]
        wr = (stats['won'] / stats['total'] * 100) if stats['total'] > 0 else 0
        
        total_away_wins += stats['won']
        total_away_bets += stats['total']
        
        # Assessment
        if wr > 60:
            assessment = "🏆 ELITE"
        elif wr > 25:
            assessment = "✅ STRONG"
        elif wr > 15:
            assessment = "💰 PROFITABLE"
        elif wr > 10:
            assessment = "⚠️ MARGINAL"
        else:
            assessment = "❌ WEAK"
        
        print(f"{score:<10} {stats['total']:<10} {stats['won']:<12} {stats['lost']:<12} {wr:<11.1f}% {assessment}")
    
    # Combined away win analysis
    combined_wr = (total_away_wins / total_away_bets * 100) if total_away_bets > 0 else 0
    print(f"-"*70)
    print(f"{'COMBINED':<10} {total_away_bets:<10} {total_away_wins:<12} {total_away_bets - total_away_wins:<12} {combined_wr:<11.1f}% {'📊 Overall'}")
    
    print(f"\n" + "="*70)
    print(f"🎯 KEY FINDINGS:")
    print(f"="*70)
    
    # Find best performing away score
    best_away_score = max(AWAY_WIN_SCORES, key=lambda s: away_simulations[s]['won'] / away_simulations[s]['total'] if away_simulations[s]['total'] > 0 else 0)
    best_wr = (away_simulations[best_away_score]['won'] / away_simulations[best_away_score]['total'] * 100)
    
    print(f"   🏆 Best Away Score: {best_away_score} ({best_wr:.1f}% win rate)")
    print(f"   📊 Average Away Win Rate: {combined_wr:.1f}%")
    print(f"   📈 Home Win Rate (actual): {home_wr:.1f}%")
    
    if combined_wr > home_wr:
        print(f"\n   ✅ AWAY WINS WOULD HAVE PERFORMED BETTER! (+{combined_wr - home_wr:.1f}%)")
    elif combined_wr < home_wr:
        print(f"\n   ⚠️ Away wins would have performed worse (-{home_wr - combined_wr:.1f}%)")
    else:
        print(f"\n   📊 Away wins would have performed similarly")
    
    # Strategic recommendation
    print(f"\n" + "="*70)
    print(f"💡 STRATEGIC RECOMMENDATION:")
    print(f"="*70)
    
    if combined_wr >= 15:
        print(f"   ✅ INCLUDE away wins in live predictions")
        print(f"   🎯 Expected combined hit rate: ~{(home_wr + combined_wr) / 2:.1f}%")
        print(f"   💰 Doubles the betting opportunities while maintaining quality")
    else:
        print(f"   ⚠️ Away wins need more selective filtering")
        print(f"   🔍 Consider higher confidence thresholds for away predictions")
    
    # Show some example matches
    print(f"\n📋 SAMPLE AWAY WIN OPPORTUNITIES THAT WERE MISSED:")
    print(f"="*70)
    
    cursor.execute('''
        SELECT home_team, away_team, selection, result, odds
        FROM football_opportunities
        WHERE result IS NOT NULL AND result != ''
        AND (result LIKE '0-2%' OR result LIKE '0-1%' OR result LIKE '1-2%')
        LIMIT 10
    ''')
    
    missed_opportunities = cursor.fetchall()
    
    if missed_opportunities:
        print(f"{'Home Team':<25} {'Away Team':<25} {'Predicted':<12} {'Actual':<12} {'Odds'}")
        print(f"-"*70)
        for match in missed_opportunities:
            home, away, selection, result, odds = match
            predicted = selection.replace('Exact Score: ', '').strip()
            actual = result.replace(' (api-football)', '').strip()
            print(f"{home:<25} {away:<25} {predicted:<12} {actual:<12} {odds:.2f}x")
        print(f"\n   ❌ These were LOSSES with home win predictions")
        print(f"   ✅ Would have been WINS with away win predictions!\n")
    else:
        print(f"   No clear away win misses found in data\n")
    
    conn.close()

if __name__ == '__main__':
    backtest_away_wins()
