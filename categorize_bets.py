"""
Automatic Bet Categorization System
Runs daily to organize bets into: today, future, historical
"""
from datetime import datetime, timedelta
import pytz
from db_helper import db_helper

def categorize_all_bets():
    """Categorize all bets based on their match dates"""
    # Get Stockholm timezone
    stockholm_tz = pytz.timezone('Europe/Stockholm')
    now = datetime.now(stockholm_tz)
    today = now.date()
    
    print(f"📅 Categorizing bets for {today}")
    print("="*60)
    
    # Get all unsettled bets
    bets = db_helper.execute('''
        SELECT id, match_date, home_team, away_team, status
        FROM football_opportunities
        WHERE status != %s
    ''', ('settled',), fetch='all')
    print(f"📊 Found {len(bets)} unsettled bets to categorize\n")
    
    today_count = 0
    future_count = 0
    historical_count = 0
    
    for bet_id, match_date_str, home, away, status in bets:
        try:
            # Parse match date
            if 'T' in match_date_str:
                match_dt = datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
            else:
                match_dt = datetime.fromtimestamp(int(match_date_str)) if match_date_str.isdigit() else datetime.fromisoformat(match_date_str)
            
            match_date = match_dt.date()
            
            # Categorize
            if match_date < today:
                category = 'historical'
                historical_count += 1
            elif match_date == today:
                category = 'today'
                today_count += 1
            else:  # match_date > today
                category = 'future'
                future_count += 1
            
            # Update category
            db_helper.execute('''
                UPDATE football_opportunities
                SET bet_category = %s
                WHERE id = %s
            ''', (category, bet_id))
            
        except Exception as e:
            print(f"⚠️ Error processing {home} vs {away}: {e}")
            # Default to 'future' on error
            db_helper.execute('''
                UPDATE football_opportunities
                SET bet_category = %s
                WHERE id = %s
            ''', ('future', bet_id))
    
    # Also categorize settled bets as historical
    db_helper.execute('''
        UPDATE football_opportunities
        SET bet_category = %s
        WHERE status = %s
    ''', ('historical', 'settled'))
    
    print(f"✅ Categorization complete:")
    print(f"   📅 Today's bets: {today_count}")
    print(f"   📆 Future bets: {future_count}")
    print(f"   📜 Historical bets: {historical_count}")
    print(f"   ✅ Settled bets moved to historical")
    
    return today_count, future_count, historical_count

if __name__ == '__main__':
    categorize_all_bets()
