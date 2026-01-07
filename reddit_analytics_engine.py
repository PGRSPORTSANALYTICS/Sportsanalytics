"""
Reddit Analytics Engine - Match Analysis for Reddit Content
Generates analytical breakdowns (Form vs H2H, tactical factors) for Reddit sharing.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor

DISCORD_REDDIT_WEBHOOK_URL = os.getenv("DISCORD_REDDIT_WEBHOOK_URL")

HIGH_VISIBILITY_LEAGUES = [
    'Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1',
    'English Championship', 'Primeira Liga', 'Eredivisie',
    'Champions League', 'Europa League', 'FA Cup', 'Copa del Rey',
    'Scottish Premiership', 'Belgian Pro League', 'Turkish Super Lig'
]


def get_db_connection():
    """Get database connection."""
    import time
    for attempt in range(3):
        try:
            conn = psycopg2.connect(
                os.getenv('DATABASE_URL'),
                connect_timeout=10,
                options='-c statement_timeout=30000'
            )
            return conn
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise e


def get_upcoming_matches(hours_ahead: int = 48, limit: int = 5) -> List[Dict]:
    """Get upcoming high-visibility matches with model data."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT DISTINCT ON (home_team, away_team)
                home_team, away_team, league, match_date,
                model_prob, odds, selection, analysis,
                edge_percentage, confidence
            FROM football_opportunities
            WHERE match_date::timestamp > NOW()
              AND match_date::timestamp < NOW() + INTERVAL '%s hours'
              AND market = 'Value Single'
              AND league IS NOT NULL
            ORDER BY home_team, away_team, 
                     CASE WHEN league IN %s THEN 0 ELSE 1 END,
                     match_date ASC
            LIMIT %s
        """, (hours_ahead, tuple(HIGH_VISIBILITY_LEAGUES), limit * 2))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        seen = set()
        unique = []
        for r in results:
            key = f"{r['home_team']}_{r['away_team']}"
            if key not in seen:
                seen.add(key)
                unique.append(dict(r))
                if len(unique) >= limit:
                    break
        
        return unique
    except Exception as e:
        print(f"Error getting upcoming matches: {e}")
        return []


def get_team_form(team_name: str) -> Dict:
    """Get recent form data for a team from historical bets."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                home_team, away_team, outcome, actual_score, match_date, selection
            FROM football_opportunities
            WHERE (home_team = %s OR away_team = %s)
              AND outcome IN ('won', 'lost')
              AND actual_score IS NOT NULL
              AND match_date::timestamp < NOW()
            ORDER BY match_date DESC
            LIMIT 10
        """, (team_name, team_name))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        wins = 0
        losses = 0
        goals_scored = 0
        goals_conceded = 0
        
        for r in results[:5]:
            try:
                score = r['actual_score']
                if '-' in str(score):
                    parts = score.split('-')
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                    
                    if r['home_team'] == team_name:
                        goals_scored += home_goals
                        goals_conceded += away_goals
                        if home_goals > away_goals:
                            wins += 1
                        elif home_goals < away_goals:
                            losses += 1
                    else:
                        goals_scored += away_goals
                        goals_conceded += home_goals
                        if away_goals > home_goals:
                            wins += 1
                        elif away_goals < home_goals:
                            losses += 1
            except:
                continue
        
        matches = min(5, len(results))
        return {
            'matches': matches,
            'wins': wins,
            'losses': losses,
            'draws': matches - wins - losses,
            'goals_scored': goals_scored,
            'goals_conceded': goals_conceded,
            'form_rating': 'Strong' if wins >= 3 else 'Average' if wins >= 2 else 'Weak'
        }
    except Exception as e:
        print(f"Error getting team form: {e}")
        return {'matches': 0, 'wins': 0, 'losses': 0, 'draws': 0, 'goals_scored': 0, 'goals_conceded': 0, 'form_rating': 'Unknown'}


def get_h2h_record(home_team: str, away_team: str) -> Dict:
    """Get head-to-head record between two teams."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                home_team, away_team, actual_score, match_date
            FROM football_opportunities
            WHERE ((home_team = %s AND away_team = %s) OR (home_team = %s AND away_team = %s))
              AND actual_score IS NOT NULL
              AND outcome IN ('won', 'lost')
            ORDER BY match_date DESC
            LIMIT 10
        """, (home_team, away_team, away_team, home_team))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        home_wins = 0
        away_wins = 0
        draws = 0
        
        for r in results:
            try:
                score = r['actual_score']
                if '-' in str(score):
                    parts = score.split('-')
                    hg = int(parts[0].strip())
                    ag = int(parts[1].strip())
                    
                    if r['home_team'] == home_team:
                        if hg > ag:
                            home_wins += 1
                        elif ag > hg:
                            away_wins += 1
                        else:
                            draws += 1
                    else:
                        if ag > hg:
                            home_wins += 1
                        elif hg > ag:
                            away_wins += 1
                        else:
                            draws += 1
            except:
                continue
        
        total = home_wins + away_wins + draws
        return {
            'total_matches': total,
            'home_wins': home_wins,
            'away_wins': away_wins,
            'draws': draws,
            'has_pattern': total >= 3 and (home_wins >= total * 0.6 or away_wins >= total * 0.6)
        }
    except Exception as e:
        print(f"Error getting H2H: {e}")
        return {'total_matches': 0, 'home_wins': 0, 'away_wins': 0, 'draws': 0, 'has_pattern': False}


def generate_match_analysis(match: Dict) -> str:
    """Generate Reddit-style analytical breakdown for a match."""
    home = match['home_team']
    away = match['away_team']
    league = match.get('league', 'Unknown League')
    
    home_form = get_team_form(home)
    away_form = get_team_form(away)
    h2h = get_h2h_record(home, away)
    
    match_date = match.get('match_date')
    if match_date:
        if isinstance(match_date, str):
            date_str = match_date
        else:
            date_str = match_date.strftime('%a %b %d, %H:%M UTC')
    else:
        date_str = "TBD"
    
    content = f"""**{home} vs {away}**
*{league} — {date_str}*

━━━━━━━━━━━━━━━━━━━━

**📊 CURRENT FORM (Last 5)**

**{home}:** {home_form['wins']}W-{home_form['draws']}D-{home_form['losses']}L | {home_form['goals_scored']} scored, {home_form['goals_conceded']} conceded
→ Form rating: **{home_form['form_rating']}**

**{away}:** {away_form['wins']}W-{away_form['draws']}D-{away_form['losses']}L | {away_form['goals_scored']} scored, {away_form['goals_conceded']} conceded
→ Form rating: **{away_form['form_rating']}**

━━━━━━━━━━━━━━━━━━━━

**🔄 HEAD-TO-HEAD**
"""
    
    if h2h['total_matches'] > 0:
        content += f"""
Recent meetings: **{h2h['total_matches']}**
• {home} wins: {h2h['home_wins']}
• {away} wins: {h2h['away_wins']}
• Draws: {h2h['draws']}
"""
        if h2h['has_pattern']:
            if h2h['home_wins'] > h2h['away_wins']:
                content += f"\n⚠️ **Pattern detected:** {home} dominates this fixture historically"
            else:
                content += f"\n⚠️ **Pattern detected:** {away} has been a bogey team for {home}"
    else:
        content += "\nNo significant H2H data available\n"
    
    content += """
━━━━━━━━━━━━━━━━━━━━

**⚖️ FACTOR WEIGHTING**

"""
    
    form_advantage = None
    if home_form['wins'] > away_form['wins'] + 1:
        form_advantage = home
    elif away_form['wins'] > home_form['wins'] + 1:
        form_advantage = away
    
    h2h_advantage = None
    if h2h['has_pattern']:
        if h2h['home_wins'] > h2h['away_wins']:
            h2h_advantage = home
        else:
            h2h_advantage = away
    
    if form_advantage and h2h_advantage:
        if form_advantage == h2h_advantage:
            content += f"Both form AND H2H favor **{form_advantage}**. Strong signal.\n"
        else:
            content += f"**Conflicting signals:**\n• Form favors {form_advantage}\n• H2H favors {h2h_advantage}\n\nThis is where value can hide — markets often overweight recent form.\n"
    elif form_advantage:
        content += f"Form favors **{form_advantage}**, no clear H2H pattern.\nRecent form is the primary driver here.\n"
    elif h2h_advantage:
        content += f"H2H favors **{h2h_advantage}** despite balanced current form.\nPersistent matchup issues may be at play.\n"
    else:
        content += "No clear advantage either way. Evenly matched on paper.\n"
    
    content += """
━━━━━━━━━━━━━━━━━━━━

**📝 ANALYTICAL NOTES**

• Form weight: ~60-70% (short-term predictor)
• H2H weight: ~15-25% (higher if same manager/core squad)
• Other factors: ~10-20% (injuries, motivation, venue)

*This is analytical content for discussion purposes only.*
"""
    
    return content


def send_to_reddit_discord(content: str, title: str = "") -> bool:
    """Send analysis to Reddit Discord channel."""
    if not DISCORD_REDDIT_WEBHOOK_URL:
        print("No Reddit Discord webhook configured")
        return False
    
    try:
        embed = {
            "description": content[:4000],
            "color": 16744192,
            "footer": {"text": "PGR Match Analytics — For Reddit Discussion"}
        }
        
        if title:
            embed["title"] = title
        
        payload = {"embeds": [embed]}
        
        response = requests.post(
            DISCORD_REDDIT_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            print(f"Sent to Reddit Discord: {title}")
            return True
        else:
            print(f"Discord error: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error sending to Discord: {e}")
        return False


def generate_single_match_analysis(home_team: str, away_team: str) -> Optional[str]:
    """Generate analysis for a specific match by team names."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT home_team, away_team, league, match_date,
                   model_prob, odds, selection, analysis
            FROM football_opportunities
            WHERE (home_team ILIKE %s AND away_team ILIKE %s)
               OR (home_team ILIKE %s AND away_team ILIKE %s)
            ORDER BY match_date DESC
            LIMIT 1
        """, (f"%{home_team}%", f"%{away_team}%", f"%{away_team}%", f"%{home_team}%"))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return generate_match_analysis(dict(result))
        else:
            match = {
                'home_team': home_team,
                'away_team': away_team,
                'league': 'Unknown',
                'match_date': None
            }
            return generate_match_analysis(match)
    except Exception as e:
        print(f"Error: {e}")
        return None


def run_reddit_analytics(match_count: int = 3):
    """Generate and send match analytics for Reddit."""
    print(f"\n{'='*50}")
    print(f"REDDIT ANALYTICS ENGINE - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}\n")
    
    matches = get_upcoming_matches(hours_ahead=72, limit=match_count)
    
    if not matches:
        print("No upcoming matches found")
        return 0
    
    sent = 0
    for match in matches:
        analysis = generate_match_analysis(match)
        title = f"📊 {match['home_team']} vs {match['away_team']} — Form vs H2H Analysis"
        
        print(f"\n--- ANALYSIS: {match['home_team']} vs {match['away_team']} ---")
        print(analysis)
        
        if send_to_reddit_discord(analysis, title):
            sent += 1
    
    print(f"\nReddit Analytics Complete: {sent}/{len(matches)} analyses sent")
    return sent


if __name__ == "__main__":
    run_reddit_analytics(3)
