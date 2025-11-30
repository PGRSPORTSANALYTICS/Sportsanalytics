#!/usr/bin/env python3
"""
Simple Telegram Broadcast System
Sends predictions directly via Telegram Bot API
"""

import os
import requests
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBroadcaster:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN not set")
        
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.db_path = 'data/real_football.db'
        logger.info("✅ Telegram broadcaster initialized")
    
    def send_message(self, chat_id: str, text: str) -> bool:
        """Send a message to a Telegram chat"""
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send message to {chat_id}: {e}")
            return False
    
    def get_subscribers(self) -> List[str]:
        """Get all subscriber chat IDs from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_subscribers (
                    chat_id TEXT PRIMARY KEY,
                    username TEXT,
                    subscribed_at INTEGER,
                    is_channel INTEGER DEFAULT 0,
                    channel_type TEXT
                )
            ''')
            
            cursor.execute('SELECT chat_id FROM telegram_subscribers WHERE is_channel = 0')
            subscribers = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            return subscribers
        except Exception as e:
            logger.error(f"❌ Failed to get subscribers: {e}")
            return []
    
    def get_channel(self, channel_type: str = 'exact_score') -> Optional[str]:
        """Get configured channel ID for specific type (exact_score or sgp)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT chat_id FROM telegram_subscribers 
                WHERE is_channel = 1 AND channel_type = ? 
                LIMIT 1
            ''', (channel_type,))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Failed to get channel: {e}")
            return None
    
    def set_channel(self, channel_id: str, channel_name: str = "Channel", channel_type: str = 'exact_score') -> bool:
        """Set the broadcast channel for specific type (exact_score or sgp)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove old channel of this type if exists
            cursor.execute('DELETE FROM telegram_subscribers WHERE is_channel = 1 AND channel_type = ?', (channel_type,))
            
            # Add new channel
            cursor.execute('''
                INSERT INTO telegram_subscribers (chat_id, username, subscribed_at, is_channel, channel_type)
                VALUES (?, ?, ?, 1, ?)
            ''', (channel_id, channel_name, int(datetime.now().timestamp()), channel_type))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ {channel_type.upper()} channel set: {channel_name} ({channel_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to set channel: {e}")
            return False
    
    def add_subscriber(self, chat_id: str, username: str = "Unknown") -> bool:
        """Add a new subscriber"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO telegram_subscribers (chat_id, username, subscribed_at, is_channel)
                VALUES (?, ?, ?, 0)
            ''', (chat_id, username, int(datetime.now().timestamp())))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Added subscriber: {username} ({chat_id})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to add subscriber: {e}")
            return False
    
    def broadcast_prediction(self, prediction: Dict, prediction_type: str = 'exact_score') -> int:
        """Broadcast a prediction to appropriate channel based on type (ONLY TODAY'S MATCHES)
        
        Args:
            prediction: Prediction dict
            prediction_type: 'exact_score' or 'sgp'
        """
        # Filter: Only broadcast if match is playing TODAY
        match_date_raw = prediction.get('match_date') or prediction.get('datetime') or prediction.get('kickoff_time')
        
        if match_date_raw:
            try:
                # Parse multiple date formats with robust fallback
                from datetime import datetime
                import re
                
                # Normalize the date string
                date_str = str(match_date_raw).strip()
                
                # Try multiple parsing strategies
                dt = None
                
                # Strategy 1: ISO format with Z (2025-11-01T13:00:45Z)
                if 'Z' in date_str:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                # Strategy 2: ISO format with timezone (2025-11-01T13:00:45+00:00)
                elif '+' in date_str or date_str.count('-') > 2:
                    dt = datetime.fromisoformat(date_str)
                # Strategy 3: Naive ISO format (2025-11-01T13:00:45)
                elif 'T' in date_str:
                    dt = datetime.fromisoformat(date_str)
                # Strategy 4: Date only (2025-11-01)
                elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                    dt = datetime.fromisoformat(date_str)
                else:
                    # Last resort: try direct parse
                    dt = datetime.fromisoformat(date_str)
                
                match_date = dt.date()
                today = datetime.now().date()
                
                if match_date != today:
                    logger.info(f"🔕 Skipping broadcast - Match plays on {match_date}, not today ({today})")
                    return 0
            except Exception as e:
                logger.error(f"❌ Failed to parse match date '{match_date_raw}': {e}")
                logger.error(f"   Prediction will NOT be broadcast - fix date format!")
                return 0
        else:
            logger.warning(f"⚠️ No match date found in prediction - skipping broadcast")
            return 0
        
        # Format message based on prediction type
        if prediction_type == 'sgp':
            message = self._format_sgp_prediction(prediction)
        else:
            message = self._format_prediction(prediction)
        
        subscribers = self.get_subscribers()
        channel_id = self.get_channel(channel_type=prediction_type)
        
        success_count = 0
        
        # Send to appropriate channel first (public visibility)
        if channel_id:
            if self.send_message(channel_id, message):
                logger.info(f"📢 Posted {prediction_type.upper()} to channel: {channel_id}")
                success_count += 1
            else:
                logger.warning(f"⚠️ Failed to post to channel: {channel_id}")
        else:
            logger.warning(f"⚠️ No {prediction_type.upper()} channel configured")
        
        # Send to individual subscribers
        if not subscribers:
            logger.warning("⚠️ No individual subscribers")
        else:
            for chat_id in subscribers:
                if self.send_message(chat_id, message):
                    success_count += 1
        
        total_targets = (1 if channel_id else 0) + len(subscribers)
        logger.info(f"📤 Broadcasted {prediction_type.upper()} to {success_count}/{total_targets} targets")
        return success_count
    
    def _get_live_stats(self) -> Dict:
        """Get live ROI and performance stats from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN outcome IN ('won', 'win') THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome IN ('lost', 'loss') THEN 1 ELSE 0 END) as losses,
                    SUM(stake) as total_staked,
                    SUM(CASE WHEN outcome IN ('won', 'win') THEN stake * (odds - 1) ELSE -stake END) as net_profit
                FROM football_opportunities 
                WHERE market = 'exact_score'
                AND outcome IS NOT NULL
            ''')
            
            result = cursor.fetchone()
            conn.close()
            
            total = result[0] or 0
            wins = result[1] or 0
            staked = result[3] or 1
            profit = result[4] or 0
            
            win_rate = (wins / total * 100) if total > 0 else 0
            roi = (profit / staked * 100) if staked > 0 else 0
            
            return {
                'total': total,
                'wins': wins,
                'win_rate': win_rate,
                'profit': profit,
                'roi': roi
            }
        except Exception as e:
            logger.error(f"❌ Failed to get live stats: {e}")
            return {'total': 0, 'wins': 0, 'win_rate': 0, 'profit': 0, 'roi': 0}
    
    def _escape_markdown(self, text: str) -> str:
        """Escape Markdown special characters for Telegram"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    def _generate_analysis_from_json(self, analysis_json, home_team: str, away_team: str, predicted_score: str) -> str:
        """Generate human-readable analysis from JSON"""
        import json
        try:
            if not analysis_json:
                return ""
            
            analysis = analysis_json if isinstance(analysis_json, dict) else json.loads(analysis_json)
            parts = []
            
            parts.append(f"WHY {predicted_score}?")
            
            xg = analysis.get('xg_prediction', {})
            if xg.get('home_xg', 0) > 0:
                parts.append(f"xG: {home_team} {xg['home_xg']:.1f}, {away_team} {xg['away_xg']:.1f}")
            
            home_form = analysis.get('home_form', {})
            if home_form.get('matches_played', 0) > 0:
                parts.append(f"{home_team}: {home_form['win_rate']:.0f}% WR, {home_form['goals_per_game']:.1f} goals/game")
            
            away_form = analysis.get('away_form', {})
            if away_form.get('matches_played', 0) > 0:
                parts.append(f"{away_team}: {away_form['win_rate']:.0f}% WR, {away_form['goals_per_game']:.1f} goals/game")
            
            h2h = analysis.get('h2h', {})
            if h2h.get('matches_played', 0) >= 3:
                parts.append(f"H2H: {h2h['avg_total_goals']:.1f} avg goals ({h2h['matches_played']} games)")
            
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Failed to generate analysis: {e}")
            return ""
    
    def _format_prediction(self, prediction: Dict) -> str:
        """Format prediction as Telegram message"""
        from datetime import datetime
        import pytz
        
        home = prediction['home_team']
        away = prediction['away_team']
        score = prediction['selection'].replace('Exact Score: ', '')
        odds = prediction['odds']
        confidence = prediction.get('confidence', 'N/A')
        stake = prediction.get('stake', 173)  # 16 USD × 10.8
        
        analysis_text = ""
        if prediction.get('analysis_json'):
            analysis_text = self._generate_analysis_from_json(
                prediction['analysis_json'],
                home,
                away,
                score
            )
        
        # Get live performance stats
        stats = self._get_live_stats()
        
        league = prediction.get('league', 'N/A')
        
        # Parse kickoff time from match_date field
        match_date_raw = prediction.get('match_date') or prediction.get('datetime') or prediction.get('kickoff_time')
        if match_date_raw:
            try:
                # Parse ISO format: 2025-11-01T13:00:45Z
                dt = datetime.fromisoformat(match_date_raw.replace('Z', '+00:00'))
                # Convert to Stockholm time (CET/CEST)
                stockholm_tz = pytz.timezone('Europe/Stockholm')
                dt_stockholm = dt.astimezone(stockholm_tz)
                
                # Format: "Sat Nov 2, 15:00" for easy reading
                match_time = dt_stockholm.strftime('%a %b %d, %H:%M')
            except:
                match_time = match_date_raw
        else:
            match_time = 'TBA'
        
        message = f"""⚽ NEW EXACT SCORE PREDICTION

{home} vs {away}
Predicted Score: {score}
Odds: {odds}x
Confidence: {confidence}/100
Recommended Stake: {stake} SEK

Potential Return: {int(stake * odds)} SEK
Profit: {int(stake * (odds - 1))} SEK

⏰ KICKOFF: {match_time}
🏆 League: {league}

{analysis_text}

📊 LIVE PERFORMANCE
{stats['wins']}/{stats['total']} wins ({stats['win_rate']:.1f}%)
Total Profit: {stats['profit']:.0f} SEK ({stats['roi']:.1f}% ROI)
Target: 20-25% WR, +100-200% ROI
"""
        return message
    
    def _format_sgp_legs_telegram(self, legs_str: str) -> str:
        """Format SGP legs for Telegram (Bet365 style - clean and hierarchical)"""
        if not legs_str or '|' not in legs_str:
            return legs_str
        
        leg_parts = legs_str.split('|')
        formatted = []
        
        for i, leg in enumerate(leg_parts, 1):
            leg = leg.strip()
            
            # Bet365-style format: Main selection on top, market type below
            if 'OVER_UNDER_GOALS' in leg:
                threshold = leg.split('(')[1].split(')')[0]
                if 'OVER' in leg and 'UNDER' not in leg:
                    formatted.append(f"✓ Over {threshold} Goals\n    Match Goals Total")
                else:
                    formatted.append(f"✓ Under {threshold} Goals\n    Match Goals Total")
                    
            elif 'BTTS' in leg:
                if 'YES' in leg:
                    formatted.append("✓ Both Teams to Score - Yes\n    Both Teams to Score")
                else:
                    formatted.append("✓ Both Teams to Score - No\n    Both Teams to Score")
                    
            elif 'HOME_TEAM_CORNERS' in leg:
                threshold = leg.split('(')[1].split(')')[0]
                direction = 'Over' if 'OVER' in leg else 'Under'
                formatted.append(f"✓ Home Team {direction} {threshold} Corners\n    Team 1 Corners")
                
            elif 'AWAY_TEAM_CORNERS' in leg:
                threshold = leg.split('(')[1].split(')')[0]
                direction = 'Over' if 'OVER' in leg else 'Under'
                formatted.append(f"✓ Away Team {direction} {threshold} Corners\n    Team 2 Corners")
                
            elif 'HOME_TEAM_SHOTS' in leg:
                threshold = leg.split('(')[1].split(')')[0]
                direction = 'Over' if 'OVER' in leg else 'Under'
                formatted.append(f"✓ Home Team {direction} {threshold} Shots\n    Team 1 Total Shots")
                
            elif 'AWAY_TEAM_SHOTS' in leg:
                threshold = leg.split('(')[1].split(')')[0]
                direction = 'Over' if 'OVER' in leg else 'Under'
                formatted.append(f"✓ Away Team {direction} {threshold} Shots\n    Team 2 Total Shots")
                
            elif 'CORNERS' in leg and 'TEAM' not in leg:
                threshold = leg.split('(')[1].split(')')[0]
                direction = 'Over' if 'OVER' in leg else 'Under'
                formatted.append(f"✓ {direction} {threshold} Match Corners\n    Total Match Corners")
                
            elif 'MATCH_RESULT' in leg:
                if 'HOME' in leg:
                    formatted.append("✓ Home Team to Win\n    Match Result")
                elif 'AWAY' in leg:
                    formatted.append("✓ Away Team to Win\n    Match Result")
                else:
                    formatted.append("✓ Draw\n    Match Result")
                    
            elif 'FIRST_HALF' in leg or '1H' in leg:
                threshold = leg.split('(')[1].split(')')[0]
                direction = 'Over' if 'OVER' in leg else 'Under'
                formatted.append(f"✓ 1st Half {direction} {threshold} Goals\n    First Half Goals")
                
            else:
                formatted.append(f"✓ {leg}")
        
        return '\n\n'.join(formatted)
    
    def _format_sgp_prediction(self, prediction: Dict) -> str:
        """Format SGP prediction as Telegram message"""
        from datetime import datetime
        import pytz
        
        home = prediction['home_team']
        away = prediction['away_team']
        
        # Use legs for clear formatting, fallback to description
        legs = prediction.get('legs', '')
        if legs:
            parlay_text = self._format_sgp_legs_telegram(legs)
        else:
            parlay_text = prediction.get('parlay_description', 'SGP')
        
        odds = prediction.get('bookmaker_odds', prediction.get('odds', 0))
        ev = prediction.get('ev_percentage', 0)
        stake = prediction.get('stake', 173)  # 16 USD × 10.8
        
        league = prediction.get('league', 'N/A')
        
        # Parse kickoff time
        match_date_raw = prediction.get('match_date') or prediction.get('datetime') or prediction.get('kickoff_time')
        if match_date_raw:
            try:
                dt = datetime.fromisoformat(match_date_raw.replace('Z', '+00:00'))
                stockholm_tz = pytz.timezone('Europe/Stockholm')
                dt_stockholm = dt.astimezone(stockholm_tz)
                match_time = dt_stockholm.strftime('%a %b %d, %H:%M')
            except:
                match_time = match_date_raw
        else:
            match_time = 'TBA'
        
        message = f"""🎲 NEW SGP PREDICTION

{home} vs {away}

📋 PARLAY:
{parlay_text}

💰 Odds: {odds:.1f}x
📈 Expected Value: {ev:+.1f}%
💵 Recommended Stake: {stake} SEK

Potential Return: {int(stake * odds)} SEK
Profit: {int(stake * (odds - 1))} SEK

⏰ KICKOFF: {match_time}
🏆 League: {league}

🎯 Smart parlay combining correlated markets for maximum value!
"""
        return message
    
    def _format_result(self, result: Dict) -> str:
        """Format settled result as Telegram message"""
        home = result['home_team']
        away = result['away_team']
        predicted = result['predicted_score']
        actual = result['actual_score']
        outcome = result['outcome']
        stake = result['stake']
        odds = result['odds']
        profit = result.get('profit_loss', 0)
        
        # Get updated performance stats
        stats = self._get_live_stats()
        
        if outcome in ('won', 'win'):
            emoji = "✅"
            status = "WIN!"
            result_line = f"Profit: +{int(profit)} SEK"
        else:
            emoji = "❌"
            status = "LOSS"
            result_line = f"Loss: {int(profit)} SEK"
        
        message = f"""{emoji} RESULT: {status}

{home} vs {away}
Predicted: {predicted}
Actual Score: {actual}

Stake: {stake} SEK
Odds: {odds}x
{result_line}

League: {result.get('league', 'N/A')}

📊 UPDATED PERFORMANCE
{stats['wins']}/{stats['total']} wins ({stats['win_rate']:.1f}%)
Total Profit: {stats['profit']:.0f} SEK ({stats['roi']:.1f}% ROI)
"""
        return message
    
    def broadcast_result(self, result: Dict, result_type: str = 'exact_score') -> int:
        """Broadcast a settled result to appropriate channel based on type
        
        Args:
            result: Result dict
            result_type: 'exact_score' or 'sgp'
        """
        message = self._format_result(result)
        subscribers = self.get_subscribers()
        channel_id = self.get_channel(channel_type=result_type)
        
        success_count = 0
        
        # Send to appropriate channel first (public visibility)
        if channel_id:
            if self.send_message(channel_id, message):
                logger.info(f"📢 Posted {result_type.upper()} result to channel: {channel_id}")
                success_count += 1
            else:
                logger.warning(f"⚠️ Failed to post result to channel: {channel_id}")
        
        # Send to individual subscribers
        if not subscribers:
            logger.warning("⚠️ No individual subscribers")
        else:
            for chat_id in subscribers:
                if self.send_message(chat_id, message):
                    success_count += 1
        
        total_targets = (1 if channel_id else 0) + len(subscribers)
        logger.info(f"📤 Broadcasted {result_type.upper()} result to {success_count}/{total_targets} targets")
        return success_count
    
    def get_todays_predictions(self) -> List[Dict]:
        """Get today's predictions from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT home_team, away_team, selection, odds, confidence, 
                       stake, match_date, kickoff_time, league
                FROM football_opportunities
                WHERE DATE(datetime(timestamp, 'unixepoch')) = ?
                AND outcome IS NULL
                ORDER BY timestamp DESC
            ''', (today,))
            
            predictions = []
            for row in cursor.fetchall():
                match_datetime = f"{row[6]} {row[7]}" if row[6] and row[7] else "TBA"
                predictions.append({
                    'home_team': row[0],
                    'away_team': row[1],
                    'selection': row[2],
                    'odds': row[3],
                    'confidence': row[4],
                    'stake': row[5],
                    'datetime': match_datetime,
                    'league': row[8]
                })
            
            conn.close()
            return predictions
            
        except Exception as e:
            logger.error(f"❌ Failed to get predictions: {e}")
            return []


def main():
    """Test the broadcaster"""
    broadcaster = TelegramBroadcaster()
    
    predictions = broadcaster.get_todays_predictions()
    logger.info(f"Found {len(predictions)} predictions today")
    
    for pred in predictions:
        broadcaster.broadcast_prediction(pred)


if __name__ == '__main__':
    main()
