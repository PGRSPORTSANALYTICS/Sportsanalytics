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
                'text': text,
                'parse_mode': 'Markdown'
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
                    is_channel INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('SELECT chat_id FROM telegram_subscribers WHERE is_channel = 0')
            subscribers = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            return subscribers
        except Exception as e:
            logger.error(f"❌ Failed to get subscribers: {e}")
            return []
    
    def get_channel(self) -> Optional[str]:
        """Get configured channel ID (if any)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT chat_id FROM telegram_subscribers WHERE is_channel = 1 LIMIT 1')
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Failed to get channel: {e}")
            return None
    
    def set_channel(self, channel_id: str, channel_name: str = "Channel") -> bool:
        """Set the broadcast channel"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove old channel if exists
            cursor.execute('DELETE FROM telegram_subscribers WHERE is_channel = 1')
            
            # Add new channel
            cursor.execute('''
                INSERT INTO telegram_subscribers (chat_id, username, subscribed_at, is_channel)
                VALUES (?, ?, ?, 1)
            ''', (channel_id, channel_name, int(datetime.now().timestamp())))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Channel set: {channel_name} ({channel_id})")
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
    
    def broadcast_prediction(self, prediction: Dict) -> int:
        """Broadcast a prediction to all subscribers AND channel"""
        message = self._format_prediction(prediction)
        subscribers = self.get_subscribers()
        channel_id = self.get_channel()
        
        success_count = 0
        
        # Send to channel first (public visibility)
        if channel_id:
            if self.send_message(channel_id, message):
                logger.info(f"📢 Posted to channel: {channel_id}")
                success_count += 1
            else:
                logger.warning(f"⚠️ Failed to post to channel: {channel_id}")
        
        # Send to individual subscribers
        if not subscribers:
            logger.warning("⚠️ No individual subscribers")
        else:
            for chat_id in subscribers:
                if self.send_message(chat_id, message):
                    success_count += 1
        
        total_targets = (1 if channel_id else 0) + len(subscribers)
        logger.info(f"📤 Broadcasted to {success_count}/{total_targets} targets")
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
    
    def _format_prediction(self, prediction: Dict) -> str:
        """Format prediction as Telegram message"""
        home = prediction['home_team']
        away = prediction['away_team']
        score = prediction['selection'].replace('Exact Score: ', '')
        odds = prediction['odds']
        confidence = prediction.get('confidence', 'N/A')
        stake = prediction.get('stake', 160)
        analysis = prediction.get('analysis', '')
        
        # Get live performance stats
        stats = self._get_live_stats()
        
        message = f"""🎯 **NEW EXACT SCORE PREDICTION**

⚽ **{home} vs {away}**
📊 Predicted Score: **{score}**
💰 Odds: **{odds}x**
🎯 Confidence: {confidence}/100
💵 Recommended Stake: {stake} SEK

🚀 Potential Return: **{int(stake * odds)} SEK**
📈 Profit: **{int(stake * (odds - 1))} SEK**

⏰ Match Time: {prediction.get('datetime', 'TBA')}
🏆 League: {prediction.get('league', 'N/A')}

{analysis}

📊 **LIVE SYSTEM PERFORMANCE**
✅ {stats['wins']}/{stats['total']} wins ({stats['win_rate']:.1f}%)
💰 Total Profit: {stats['profit']:.0f} SEK ({stats['roi']:.1f}% ROI)
🎯 Target: 20-25% WR, +100-200% ROI
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
            emoji = "🎉"
            status = "**WIN!**"
            result_line = f"💰 Profit: **+{int(profit)} SEK**"
        else:
            emoji = "❌"
            status = "**LOSS**"
            result_line = f"💸 Loss: **{int(profit)} SEK**"
        
        message = f"""{emoji} **RESULT: {status}**

⚽ **{home} vs {away}**
📊 Predicted: **{predicted}**
🎯 Actual Score: **{actual}**

💰 Stake: {stake} SEK
📈 Odds: {odds}x
{result_line}

🏆 League: {result.get('league', 'N/A')}

📊 **UPDATED SYSTEM STATS**
✅ {stats['wins']}/{stats['total']} wins ({stats['win_rate']:.1f}%)
💰 Total Profit: {stats['profit']:.0f} SEK ({stats['roi']:.1f}% ROI)
"""
        return message
    
    def broadcast_result(self, result: Dict) -> int:
        """Broadcast a settled result to all subscribers AND channel"""
        message = self._format_result(result)
        subscribers = self.get_subscribers()
        channel_id = self.get_channel()
        
        success_count = 0
        
        # Send to channel first (public visibility)
        if channel_id:
            if self.send_message(channel_id, message):
                logger.info(f"📢 Posted result to channel: {channel_id}")
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
        logger.info(f"📤 Broadcasted result to {success_count}/{total_targets} targets")
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
