"""
Daily Analysis Engine - Content Generation for Discord
Generates post-match analysis and upcoming match teasers.
NO PICKS, NO ADVICE - Analysis only.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_ANALYTICS_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")

ALLOWED_MARKETS = ['Value Single']
ALLOWED_SELECTIONS = ['Over', 'Under', 'Home Win', 'Away Win', 'Draw', 'BTTS Yes', 'BTTS No', 'DNB']
ODDS_MIN = 1.70
ODDS_MAX = 2.30
HIGH_VISIBILITY_LEAGUES = [
    'Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1',
    'English Championship', 'Primeira Liga', 'Eredivisie',
    'Champions League', 'Europa League', 'FA Cup', 'Copa del Rey'
]


def get_db_connection():
    """Get database connection with retry logic."""
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


def get_settled_win() -> Optional[Dict]:
    """Find a suitable WIN for post-match analysis with actual score data."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT id, home_team, away_team, league, market, selection, odds,
                   outcome, actual_score, analysis, model_prob, match_date,
                   TO_TIMESTAMP(settled_timestamp) as settled_at
            FROM football_opportunities
            WHERE outcome = 'won'
              AND odds BETWEEN %s AND %s
              AND market = 'Value Single'
              AND settled_timestamp IS NOT NULL
              AND actual_score IS NOT NULL
              AND actual_score != ''
              AND actual_score != 'N/A'
              AND (
                  selection LIKE '%%Over%%' OR 
                  selection LIKE '%%Under%%' OR
                  selection LIKE '%%Win%%' OR
                  selection LIKE '%%BTTS%%' OR
                  selection LIKE '%%DNB%%' OR
                  selection = 'Draw'
              )
            ORDER BY 
                CASE WHEN league IN %s THEN 0 ELSE 1 END,
                settled_timestamp DESC
            LIMIT 1
        """, (ODDS_MIN, ODDS_MAX, tuple(HIGH_VISIBILITY_LEAGUES)))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        return dict(result) if result else None
    except Exception as e:
        print(f"Error getting settled win: {e}")
        return None


def get_settled_loss() -> Optional[Dict]:
    """Find a suitable LOSS for post-match analysis with actual score data."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT id, home_team, away_team, league, market, selection, odds,
                   outcome, actual_score, analysis, model_prob, match_date,
                   TO_TIMESTAMP(settled_timestamp) as settled_at
            FROM football_opportunities
            WHERE outcome = 'lost'
              AND odds BETWEEN %s AND %s
              AND market = 'Value Single'
              AND settled_timestamp IS NOT NULL
              AND actual_score IS NOT NULL
              AND actual_score != ''
              AND actual_score != 'N/A'
              AND (
                  selection LIKE '%%Over%%' OR 
                  selection LIKE '%%Under%%' OR
                  selection LIKE '%%Win%%' OR
                  selection LIKE '%%BTTS%%' OR
                  selection LIKE '%%DNB%%' OR
                  selection = 'Draw'
              )
            ORDER BY 
                CASE WHEN league IN %s THEN 0 ELSE 1 END,
                settled_timestamp DESC
            LIMIT 1
        """, (ODDS_MIN, ODDS_MAX, tuple(HIGH_VISIBILITY_LEAGUES)))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        return dict(result) if result else None
    except Exception as e:
        print(f"Error getting settled loss: {e}")
        return None


def get_upcoming_match() -> Optional[Dict]:
    """Find an upcoming match for the teaser (24-72 hours out)."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        now = datetime.utcnow()
        start_window = now + timedelta(hours=24)
        end_window = now + timedelta(hours=72)
        
        cur.execute("""
            SELECT DISTINCT ON (home_team, away_team)
                id, home_team, away_team, league, match_date, kickoff_utc,
                analysis, model_prob
            FROM football_opportunities
            WHERE outcome IS NULL
              AND match_date >= %s
              AND match_date <= %s
              AND league IN %s
            ORDER BY home_team, away_team, match_date
            LIMIT 10
        """, (start_window.strftime('%Y-%m-%d'), end_window.strftime('%Y-%m-%d'), 
              tuple(HIGH_VISIBILITY_LEAGUES)))
        
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        if results:
            return dict(results[0])
        return None
    except Exception as e:
        print(f"Error getting upcoming match: {e}")
        return None


def parse_analysis_json(analysis_str: str) -> Dict:
    """Parse the analysis JSON field."""
    try:
        if isinstance(analysis_str, dict):
            return analysis_str
        return json.loads(analysis_str) if analysis_str else {}
    except:
        return {}


def calculate_implied_prob(odds: float) -> float:
    """Calculate implied probability from decimal odds."""
    return round((1 / odds) * 100, 1) if odds > 0 else 0


def format_post_match_analysis(bet: Dict, is_win: bool) -> str:
    """Format a post-match analysis post."""
    home = bet.get('home_team', 'Unknown')
    away = bet.get('away_team', 'Unknown')
    league = bet.get('league', 'Unknown League')
    selection = bet.get('selection', '')
    odds = float(bet.get('odds', 0))
    actual_score = bet.get('actual_score', 'N/A')
    match_date = bet.get('match_date', '')
    
    analysis_data = parse_analysis_json(bet.get('analysis', '{}'))
    model_prob = analysis_data.get('p_model', bet.get('model_prob', 0))
    if model_prob:
        model_prob = round(float(model_prob) * 100, 1)
    
    expected_home = analysis_data.get('expected_home_goals', 0)
    expected_away = analysis_data.get('expected_away_goals', 0)
    
    implied_prob = calculate_implied_prob(odds)
    
    result_label = "WIN" if is_win else "LOSS"
    
    market_type = "1X2"
    if 'Over' in selection or 'Under' in selection:
        market_type = "Over/Under"
    elif 'BTTS' in selection:
        market_type = "BTTS"
    elif 'DNB' in selection:
        market_type = "Draw No Bet"
    
    lines = [
        f"### Post-Match Analysis: {home} vs {away} — {market_type}",
        "",
        f"**Result: {result_label}**",
        "",
        "**Bet Context**",
        f"- Match: {home} vs {away} ({league})",
        f"- Date: {match_date}",
        f"- Market: {market_type}",
        f"- Selection: {selection}",
        f"- Odds: {odds:.2f}",
        f"- Implied Probability: {implied_prob}%",
        f"- Model Probability: {model_prob}%" if model_prob else "",
        f"- Stake: 1 unit (flat)",
        "",
        "**Pre-Match Reasoning**",
    ]
    
    if expected_home and expected_away:
        lines.append(f"The model projected {float(expected_home):.2f} expected goals for {home} and {float(expected_away):.2f} for {away}.")
    
    if model_prob and implied_prob:
        edge = round(model_prob - implied_prob, 1)
        if edge > 0:
            lines.append(f"This created a perceived edge of {edge}% over the market price.")
    
    lines.extend([
        "",
        "**What Happened in the Match**",
    ])
    
    if actual_score and actual_score != 'N/A' and '-' in str(actual_score):
        try:
            parts = str(actual_score).split('-')
            home_goals = int(parts[0].strip())
            away_goals = int(parts[1].strip())
            total_goals = home_goals + away_goals
            
            lines.append(f"Final Score: {home} {home_goals} - {away_goals} {away}")
            lines.append("")
            
            if home_goals > away_goals:
                lines.append(f"{home} secured the victory with a {home_goals}-{away_goals} scoreline.")
            elif away_goals > home_goals:
                lines.append(f"{away} came away with the win, finishing {away_goals}-{home_goals}.")
            else:
                lines.append(f"The match ended in a {home_goals}-{away_goals} draw.")
            
            if total_goals == 0:
                lines.append("A goalless affair with neither side finding the net.")
            elif total_goals <= 2:
                lines.append(f"A low-scoring contest with {total_goals} total goals.")
            elif total_goals >= 4:
                lines.append(f"An entertaining match with {total_goals} goals scored.")
            
            if 'Over' in selection or 'Under' in selection:
                threshold = 2.5
                if '3.5' in selection:
                    threshold = 3.5
                elif '1.5' in selection:
                    threshold = 1.5
                
                if 'Over' in selection:
                    if total_goals > threshold:
                        lines.append(f"The Over {threshold} selection landed as the match produced {total_goals} goals.")
                    else:
                        lines.append(f"The Over {threshold} selection missed with only {total_goals} goals scored.")
                else:
                    if total_goals < threshold:
                        lines.append(f"The Under {threshold} selection landed with {total_goals} goals staying below the line.")
                    else:
                        lines.append(f"The Under {threshold} selection missed as {total_goals} goals exceeded the threshold.")
            
            elif 'Win' in selection:
                if 'Home' in selection and home_goals > away_goals:
                    lines.append(f"The Home Win selection landed as {home} prevailed.")
                elif 'Away' in selection and away_goals > home_goals:
                    lines.append(f"The Away Win selection landed as {away} prevailed.")
                elif 'Home' in selection:
                    lines.append(f"The Home Win selection missed as {home} failed to secure victory.")
                else:
                    lines.append(f"The Away Win selection missed as {away} failed to secure victory.")
                    
        except Exception as e:
            lines.append(f"Final Score: {actual_score}")
            if is_win:
                lines.append("The selection landed as projected by the model.")
            else:
                lines.append("The selection did not land despite favorable pre-match indicators.")
    else:
        lines.append("Match data unavailable for detailed recap.")
    
    lines.extend([
        "",
        "**Evaluation**",
        "Process over outcome. The bet was placed based on:",
        "- Statistical edge identified pre-match",
        "- Model probability exceeding implied odds",
        "- Flat stake discipline maintained",
        "",
        "**Takeaway**",
    ])
    
    if is_win:
        lines.append("When edge exists and process is followed, wins confirm the methodology. No change to approach needed.")
    else:
        lines.append("Losses are part of the process. The decision was correct given pre-match information. Variance is expected in any probabilistic system.")
    
    return "\n".join([l for l in lines if l != "- Model Probability: %"])


def format_upcoming_teaser(match: Dict) -> str:
    """Format an upcoming match teaser (NO PICK, NO ODDS)."""
    home = match.get('home_team', 'Unknown')
    away = match.get('away_team', 'Unknown')
    league = match.get('league', 'Unknown League')
    match_date = match.get('match_date', '')
    
    analysis_data = parse_analysis_json(match.get('analysis', '{}'))
    expected_home = analysis_data.get('expected_home_goals', 0)
    expected_away = analysis_data.get('expected_away_goals', 0)
    
    lines = [
        f"### Match on the Radar: {home} vs {away}",
        "",
        f"**{league}** — {match_date}",
        "",
        "**Why This Match Is Interesting**",
        f"A {league} fixture between {home} and {away} presents several analytical dimensions worth examining.",
        "",
        "**Tactical & Situational Factors**",
        "- League positioning and recent form trajectories",
        "- Head-to-head historical patterns",
        "- Squad availability and rotation considerations",
        "- Home/away performance differentials",
        "",
        "**Questions the Data Is Trying to Answer**",
    ]
    
    if expected_home and expected_away:
        total_xg = float(expected_home) + float(expected_away)
        lines.append(f"- Will the match tempo align with the projected {total_xg:.1f} combined xG?")
    
    lines.extend([
        "- How do recent form trends translate to match probability?",
        "- Are there value discrepancies between model output and market consensus?",
        "- Does historical H2H data suggest predictable patterns?",
        "",
        "**Why Matches Like This Are Monitored**",
        "High-visibility league fixtures with clear statistical profiles allow for meaningful model validation. These matches help refine probability calibration over time.",
        "",
        "*This is the type of match where process matters more than prediction.*"
    ])
    
    return "\n".join(lines)


def generate_daily_analysis() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Generate all three daily analysis posts."""
    win_post = None
    loss_post = None
    teaser_post = None
    
    win_bet = get_settled_win()
    if win_bet:
        win_post = format_post_match_analysis(win_bet, is_win=True)
        print(f"Generated WIN analysis: {win_bet.get('home_team')} vs {win_bet.get('away_team')}")
    else:
        print("No suitable WIN found for analysis")
    
    loss_bet = get_settled_loss()
    if loss_bet:
        loss_post = format_post_match_analysis(loss_bet, is_win=False)
        print(f"Generated LOSS analysis: {loss_bet.get('home_team')} vs {loss_bet.get('away_team')}")
    else:
        print("No suitable LOSS found for analysis")
    
    upcoming = get_upcoming_match()
    if upcoming:
        teaser_post = format_upcoming_teaser(upcoming)
        print(f"Generated TEASER: {upcoming.get('home_team')} vs {upcoming.get('away_team')}")
    else:
        print("No suitable upcoming match found for teaser")
    
    return win_post, loss_post, teaser_post


def send_to_discord(content: str, title: str = "") -> bool:
    """Send content to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        print("No Discord webhook configured")
        return False
    
    try:
        embed = {
            "description": content[:4000],
            "color": 3447003,
            "footer": {"text": "PGR Sports Analytics — Analysis Only"}
        }
        
        if title:
            embed["title"] = title
        
        payload = {"embeds": [embed]}
        
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            print(f"Sent to Discord: {title}")
            return True
        else:
            print(f"Discord error: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error sending to Discord: {e}")
        return False


def run_daily_analysis():
    """Run the daily analysis generation and send to Discord."""
    print(f"\n{'='*50}")
    print(f"DAILY ANALYSIS ENGINE - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*50}\n")
    
    win_post, loss_post, teaser_post = generate_daily_analysis()
    
    posts_generated = 0
    
    if win_post:
        print("\n--- WIN ANALYSIS ---")
        print(win_post)
        print()
        send_to_discord(win_post, "Post-Match Analysis (WIN)")
        posts_generated += 1
    
    if loss_post:
        print("\n--- LOSS ANALYSIS ---")
        print(loss_post)
        print()
        send_to_discord(loss_post, "Post-Match Analysis (LOSS)")
        posts_generated += 1
    
    if teaser_post:
        print("\n--- UPCOMING MATCH TEASER ---")
        print(teaser_post)
        print()
        send_to_discord(teaser_post, "Match on the Radar")
        posts_generated += 1
    
    print(f"\nDaily Analysis Complete: {posts_generated}/3 posts generated")
    return posts_generated


if __name__ == "__main__":
    run_daily_analysis()
