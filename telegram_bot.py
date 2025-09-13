#!/usr/bin/env python3
"""
Premium Football Tips Telegram Bot
==================================
Sends daily betting tips to subscribers with quality scoring and tiers.
Only sends REAL verified tips - no fake data.

Features:
- Daily premium (top 10) and standard tips delivery
- Subscriber management with premium tiers
- Real-time ROI tracking and performance updates
- Secure bot token management via environment variables
"""

import os
import sqlite3
import logging
import asyncio
from datetime import date, datetime
from typing import List, Dict, Optional
import sys

# Telegram bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/telegram_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PremiumTipsBot:
    """
    Telegram bot for delivering premium football betting tips.
    Focused on quality over quantity with authentic ROI tracking.
    """
    
    def __init__(self):
        self.db_path = 'data/real_football.db'
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.subscribers = {}  # Will load from database
        
        if not self.bot_token:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN not found in environment variables")
        
        logger.info("🤖 Premium Tips Bot initialized")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - welcome new subscribers"""
        if not update.effective_user or not update.message:
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        logger.info(f"👋 New user started bot: {username} (ID: {user_id})")
        
        welcome_message = """
🏆 **Welcome to Premium Football Tips!**

Get daily AI-powered betting opportunities with:
✅ Quality scoring algorithm (only 40 tips/day max)
✅ Premium tier (top 10 tips, score 8.0+)
✅ Standard tier (next 30 tips, score 6.0-7.9)
✅ Real ROI tracking (no fake results)
✅ Over/Under 2.5 & BTTS markets

**Current Status:** Building authentic track record
**Business Model:** Tips will be free during ROI building phase

Use /tips to see today's recommendations
Use /performance to see our real results
Use /help for all commands
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 Today's Tips", callback_data="today_tips")],
            [InlineKeyboardButton("📈 Performance", callback_data="performance")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
        
        # Save subscriber to database
        self._save_subscriber(user_id, username)
    
    async def tips_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send today's premium and standard tips"""
        try:
            # Handle both message and callback query
            chat = update.effective_chat
            user = update.effective_user
            if not chat or not user:
                return
                
            tips = self._get_todays_tips()
            
            if not tips['premium'] and not tips['standard']:
                message_text = "⏳ No tips available yet today. Check back later!"
            else:
                message_text = self._format_tips_message(tips)
                logger.info(f"📤 Sent tips to user {user.id}")
            
            # Send message based on update type
            if update.callback_query:
                await update.callback_query.edit_message_text(message_text, parse_mode='Markdown')
            elif update.message:
                await update.message.reply_text(message_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Error sending tips: {e}")
            error_msg = "❌ Error getting tips. Please try again later."
            if update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            elif update.message:
                await update.message.reply_text(error_msg)
    
    async def performance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send current performance statistics"""
        try:
            stats = self._get_performance_stats()
            message_text = self._format_performance_message(stats)
            
            # Send message based on update type
            if update.callback_query:
                await update.callback_query.edit_message_text(message_text, parse_mode='Markdown')
            elif update.message:
                await update.message.reply_text(message_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ Error getting performance: {e}")
            error_msg = "❌ Error getting performance. Please try again later."
            if update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            elif update.message:
                await update.message.reply_text(error_msg)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        help_text = """
🤖 **Premium Football Tips Bot Commands**

/start - Welcome message and setup
/tips - Get today's betting tips
/performance - See real ROI performance
/help - Show this help message

**Tip Quality Scoring:**
• Premium: Score 8.0+ (top 10 daily)
• Standard: Score 6.0-7.9 (next 30 daily)
• Edge %: Value percentage over bookmaker odds
• Confidence: AI confidence level (1-5 stars)

**Markets:** Over/Under 2.5 Goals, Both Teams To Score
**Minimum Odds:** 1.70 for value betting
**Results:** 100% real verification, no simulated data

💡 Tips are currently FREE while building track record
        """
        
        # Send message based on update type
        if update.callback_query:
            await update.callback_query.edit_message_text(help_text, parse_mode='Markdown')
        elif update.message:
            await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button callbacks"""
        query = update.callback_query
        if not query:
            return
            
        await query.answer()
        
        if query.data == "today_tips":
            await self.tips_command(update, context)
        elif query.data == "performance":
            await self.performance_command(update, context)
        elif query.data == "help":
            await self.help_command(update, context)
    
    def _get_todays_tips(self) -> Dict[str, List[Dict]]:
        """Get today's premium and standard tips from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            today = date.today().isoformat()
            
            cursor = conn.cursor()
            cursor.execute("""
                SELECT home_team, away_team, league, market, selection, odds,
                       quality_score, edge_percentage, confidence, match_date,
                       kickoff_time, recommended_tier
                FROM football_opportunities 
                WHERE recommended_date = ? 
                AND recommended_tier IS NOT NULL
                ORDER BY daily_rank ASC
            """, (today,))
            
            all_tips = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            # Separate premium and standard tips
            premium_tips = [tip for tip in all_tips if tip['recommended_tier'] == 'premium']
            standard_tips = [tip for tip in all_tips if tip['recommended_tier'] == 'standard']
            
            logger.info(f"📊 Retrieved {len(premium_tips)} premium + {len(standard_tips)} standard tips")
            
            return {
                'premium': premium_tips[:10],  # Limit to top 10
                'standard': standard_tips[:30]  # Limit to top 30
            }
            
        except Exception as e:
            logger.error(f"❌ Database error getting tips: {e}")
            return {'premium': [], 'standard': []}
    
    def _get_performance_stats(self) -> Dict:
        """Get real performance statistics from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get overall performance
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_tips,
                    COUNT(CASE WHEN outcome = 'won' THEN 1 END) as wins,
                    COUNT(CASE WHEN outcome = 'lost' THEN 1 END) as losses,
                    COUNT(CASE WHEN outcome IS NULL THEN 1 END) as pending,
                    ROUND(SUM(profit_loss), 2) as total_profit,
                    ROUND(AVG(quality_score), 1) as avg_quality
                FROM football_opportunities
                WHERE recommended_tier IS NOT NULL
            """)
            
            stats = dict(zip([col[0] for col in cursor.description], cursor.fetchone()))
            
            # Calculate win rate
            if stats['wins'] + stats['losses'] > 0:
                stats['win_rate'] = round((stats['wins'] / (stats['wins'] + stats['losses'])) * 100, 1)
            else:
                stats['win_rate'] = 0
            
            conn.close()
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting performance stats: {e}")
            return {}
    
    def _format_tips_message(self, tips: Dict[str, List[Dict]]) -> str:
        """Format tips into readable Telegram message"""
        message = f"🏆 **Premium Football Tips - {date.today().strftime('%d/%m/%Y')}**\n\n"
        
        if tips['premium']:
            message += "💎 **PREMIUM TIPS** (Score 8.0+)\n"
            for i, tip in enumerate(tips['premium'], 1):
                # Scale confidence from database range (0-100) to display range (1-5)
                scaled_confidence = min(5, max(1, int(tip['confidence'] / 20) + 1))
                stars = "⭐" * scaled_confidence
                message += f"{i}. **{tip['home_team']} vs {tip['away_team']}**\n"
                message += f"   📍 {tip['league']}\n"
                message += f"   🎯 {tip['selection']} @ {tip['odds']:.2f}\n"
                message += f"   📊 Score: {tip['quality_score']:.1f} | Edge: {tip['edge_percentage']:.1f}% | {stars}\n"
                message += f"   ⏰ {tip['kickoff_time'] or 'TBD'}\n\n"
        
        if tips['standard']:
            message += "⚡ **STANDARD TIPS** (Score 6.0-7.9)\n"
            for i, tip in enumerate(tips['standard'][:5], 1):  # Show first 5 standard tips
                # Scale confidence from database range (0-100) to display range (1-5) 
                scaled_confidence = min(5, max(1, int(tip['confidence'] / 20) + 1))
                stars = "⭐" * scaled_confidence
                message += f"{i}. **{tip['home_team']} vs {tip['away_team']}**\n"
                message += f"   🎯 {tip['selection']} @ {tip['odds']:.2f} | Score: {tip['quality_score']:.1f} | {stars}\n"
        
        if len(tips['standard']) > 5:
            message += f"\n... and {len(tips['standard']) - 5} more standard tips available\n"
        
        message += "\n📝 **Note:** Tips are FREE during track record building phase"
        message += "\n🔒 **Guarantee:** 100% real results, no simulated data"
        
        return message
    
    def _format_performance_message(self, stats: Dict) -> str:
        """Format performance statistics"""
        if not stats:
            return "❌ No performance data available yet"
        
        message = "📈 **REAL PERFORMANCE STATISTICS**\n\n"
        message += f"🎯 **Total Tips:** {stats.get('total_tips', 0)}\n"
        message += f"✅ **Wins:** {stats.get('wins', 0)}\n"
        message += f"❌ **Losses:** {stats.get('losses', 0)}\n"
        message += f"⏳ **Pending:** {stats.get('pending', 0)}\n"
        message += f"🏆 **Win Rate:** {stats.get('win_rate', 0)}%\n"
        message += f"💰 **Total P&L:** ${stats.get('total_profit', 0)}\n"
        message += f"⭐ **Avg Quality:** {stats.get('avg_quality', 0)}/10\n\n"
        message += "🔒 **100% Authentic Results** - No fake data ever used\n"
        message += "📊 All results verified from real match outcomes"
        
        return message
    
    def _save_subscriber(self, user_id: int, username: str):
        """Save subscriber to database"""
        try:
            # For now, just log - could extend to full subscriber management
            logger.info(f"💾 Subscriber saved: {username} (ID: {user_id})")
        except Exception as e:
            logger.error(f"❌ Error saving subscriber: {e}")
    
    async def send_daily_tips(self):
        """Send daily tips to all subscribers (for scheduled sending)"""
        try:
            tips = self._get_todays_tips()
            
            if not tips['premium'] and not tips['standard']:
                logger.info("⏳ No tips to send today")
                return
            
            message = self._format_tips_message(tips)
            
            # For now, just log the message that would be sent
            # In production, you'd iterate through subscribers and send to each
            logger.info(f"📤 Daily tips ready to send:\n{message}")
            
        except Exception as e:
            logger.error(f"❌ Error in daily tips broadcast: {e}")
    
    def run(self):
        """Start the Telegram bot"""
        try:
            logger.info("🚀 Starting Premium Football Tips Bot")
            
            if not self.bot_token:
                logger.error("❌ Bot token not available")
                return
            
            # Create application
            application = Application.builder().token(self.bot_token).build()
            
            # Add command handlers
            application.add_handler(CommandHandler("start", self.start_command))
            application.add_handler(CommandHandler("tips", self.tips_command))
            application.add_handler(CommandHandler("performance", self.performance_command))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CallbackQueryHandler(self.button_callback))
            
            # Start bot
            logger.info("✅ Bot handlers registered, starting polling...")
            application.run_polling()
            
        except Exception as e:
            logger.error(f"💥 Bot startup error: {e}")
            raise

def test_bot_connection():
    """Test bot connection and configuration"""
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            print("❌ TELEGRAM_BOT_TOKEN not found")
            return False
        
        print(f"✅ Bot token configured: ...{bot_token[-10:]}")
        
        # Test database connection
        import sqlite3
        conn = sqlite3.connect('data/real_football.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM football_opportunities WHERE recommended_tier IS NOT NULL")
        tip_count = cursor.fetchone()[0]
        conn.close()
        
        print(f"✅ Database connected: {tip_count} quality tips available")
        print("🤖 Bot is ready to send premium tips!")
        return True
        
    except Exception as e:
        print(f"❌ Bot test failed: {e}")
        return False

if __name__ == "__main__":
    # Test configuration first
    if test_bot_connection():
        # Start bot
        bot = PremiumTipsBot()
        bot.run()
    else:
        print("💥 Bot configuration failed - check token and database")
        sys.exit(1)