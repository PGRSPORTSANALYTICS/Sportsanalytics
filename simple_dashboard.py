#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# Removed ROI tracking system as requested

# Database path
DB_PATH = 'data/real_football.db'

def get_db_cache_key():
    """Generate cache key based on database modification time"""
    try:
        return f"db_cache_{os.path.getmtime(DB_PATH)}"
    except:
        return f"db_cache_{datetime.now().timestamp()}"

def confidence_to_stars(confidence):
    """Convert confidence score to stars"""
    if confidence >= 90: return "⭐⭐⭐⭐⭐"
    elif confidence >= 75: return "⭐⭐⭐⭐"
    elif confidence >= 60: return "⭐⭐⭐"
    elif confidence >= 45: return "⭐⭐"
    else: return "⭐"

# Page setup
st.set_page_config(
    page_title="🏆 Football Betting Dashboard",
    page_icon="🏆",
    layout="wide"
)

# Load data functions
@st.cache_data(ttl=10)
def load_current_opportunities(cache_key=None):
    """Get recent betting opportunities"""
    try:
        conn = sqlite3.connect(DB_PATH)
        thirty_min_ago = datetime.now().timestamp() - (30 * 60)
        query = f"""
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, stake, league, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as found_time,
               CASE 
                   WHEN outcome = 'win' THEN '✅ Win'
                   WHEN outcome = 'loss' THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 LIVE'
               END as status
        FROM football_opportunities 
        WHERE timestamp >= {thirty_min_ago}
        ORDER BY timestamp DESC 
        LIMIT 10
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=10)
def load_performance(cache_key=None):
    """Get betting performance stats"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome IN ('win', 'won') THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome IN ('loss', 'lost') THEN 1 ELSE 0 END) as losses,
            SUM(stake) as total_staked,
            SUM(profit_loss) as net_profit,
            AVG(CASE WHEN outcome IN ('win', 'won', 'loss', 'lost') THEN (profit_loss/stake)*100 END) as avg_roi
        FROM football_opportunities 
        WHERE outcome IS NOT NULL AND outcome != '' AND outcome != 'unknown'
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

@st.cache_data(ttl=10)
def load_recent_bets(cache_key=None):
    """Get recent betting history"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, stake, outcome, profit_loss,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time
        FROM football_opportunities 
        ORDER BY timestamp DESC 
        LIMIT 20
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

# Main Dashboard
st.title("🏆 Premium Football Tips Platform")
st.markdown("**AI-Powered Quality Tips with Daily Limits & ROI Focus**")

# === TOP RECOMMENDED TIPS SECTION ===
col1, col2 = st.columns([3, 1])
with col1:
    st.header("🌟 Today's Recommended Tips")
with col2:
    if st.button("🔄 Refresh Data", help="Force refresh from database"):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=10)
def load_recommended_tips(cache_key=None):
    """Load today's recommended tips with quality scoring"""
    try:
        from datetime import date
        today = date.today().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        
        # Get premium tips (top 10)
        premium_query = """
        SELECT home_team, away_team, league, selection, odds, edge_percentage, 
               confidence, quality_score, daily_rank, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as discovered
        FROM football_opportunities 
        WHERE recommended_date = ? AND recommended_tier = 'premium'
        ORDER BY daily_rank ASC
        """
        premium_df = pd.read_sql_query(premium_query, conn, params=[today])
        
        # Get standard tips (next 30)
        standard_query = """
        SELECT home_team, away_team, league, selection, odds, edge_percentage, 
               confidence, quality_score, daily_rank, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as discovered
        FROM football_opportunities 
        WHERE recommended_date = ? AND recommended_tier = 'standard'
        ORDER BY daily_rank ASC
        """
        standard_df = pd.read_sql_query(standard_query, conn, params=[today])
        
        conn.close()
        return premium_df, standard_df
    except Exception as e:
        st.error(f"Error loading recommended tips: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Load tips with cache-busting
cache_key = get_db_cache_key()
premium_tips, standard_tips = load_recommended_tips(cache_key)


# Display daily tip usage metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("🌟 Premium Tips", f"{len(premium_tips)}/10", "High-Quality Picks")
with col2:
    st.metric("⭐ Standard Tips", f"{len(standard_tips)}/30", "Good Value Picks")
with col3:
    total_tips = len(premium_tips) + len(standard_tips)
    st.metric("📊 Total Daily Tips", f"{total_tips}/40", "Daily Limit Applied")
with col4:
    if not premium_tips.empty:
        avg_score = premium_tips['quality_score'].mean()
        st.metric("🎯 Avg Quality Score", f"{avg_score:.1f}/100", "AI Confidence")

# Premium Tips Section
if not premium_tips.empty:
    st.subheader("🌟 Premium Tips (Top 10)")
    st.success("**Highest quality opportunities with the best ROI potential**")
    
    for idx, tip in premium_tips.iterrows():
        with st.expander(f"#{tip['daily_rank']} {tip['home_team']} vs {tip['away_team']} - {tip['selection']} ({tip['quality_score']:.1f} pts)", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**🏟️ Match:** {tip['home_team']} vs {tip['away_team']}")
                st.write(f"**🏆 League:** {tip['league']}")
                st.write(f"**⚽ Bet:** {tip['selection']}")
                
            with col2:
                st.write(f"**📊 Odds:** {tip['odds']:.2f}")
                st.write(f"**📈 Edge:** {tip['edge_percentage']:.1f}%")
                st.write(f"**🎯 Confidence:** {tip['confidence']}%")
                
            with col3:
                st.write(f"**⭐ Quality Score:** {tip['quality_score']:.1f}/100")
                st.write(f"**🗓️ Match Date:** {tip['match_date']}")
                st.write(f"**⏰ Kickoff:** {tip['kickoff_time']}")
                
            # Quality indicators
            if tip['quality_score'] >= 85:
                st.success("🔥 **EXCEPTIONAL QUALITY** - Highest recommendation level")
            elif tip['quality_score'] >= 80:
                st.info("✨ **HIGH QUALITY** - Strong recommendation")
            else:
                st.warning("⚡ **GOOD QUALITY** - Solid opportunity")

else:
    st.info("🔍 **Generating today's premium tips...** Check back shortly for the top 10 recommendations")

# Standard Tips Section (collapsed by default)
if not standard_tips.empty:
    st.subheader("⭐ Standard Tips (Next 30)")
    
    with st.expander(f"View {len(standard_tips)} Standard Quality Tips", expanded=False):
        st.info("**Good value opportunities - solid picks with decent ROI potential**")
        
        # Display as table for standard tips
        display_standard = standard_tips[['daily_rank', 'home_team', 'away_team', 'league', 'selection', 
                                        'odds', 'edge_percentage', 'confidence', 'quality_score']].copy()
        display_standard.columns = ['Rank', 'Home', 'Away', 'League', 'Bet', 'Odds', 'Edge %', 'Confidence', 'Score']
        
        # Format the data
        display_standard['Odds'] = display_standard['Odds'].round(2)
        display_standard['Edge %'] = display_standard['Edge %'].round(1)
        display_standard['Score'] = display_standard['Score'].round(1)
        
        # Color coding by quality score
        def highlight_quality(row):
            score = row['Score']
            if score >= 80:
                return ['background-color: #d4edda'] * len(row)  # Green for high quality
            elif score >= 70:
                return ['background-color: #fff3cd'] * len(row)  # Yellow for medium quality
            else:
                return ['background-color: #f8f9fa'] * len(row)  # Light gray for standard quality
        
        styled_standard = display_standard.style.apply(highlight_quality, axis=1)
        st.dataframe(styled_standard, width='stretch')

st.markdown("---")

# === EXACT SCORE PREDICTIONS SECTION ===
st.header("🎯 Exact Score Predictions")

@st.cache_data(ttl=30)
def get_exact_score_predictions():
    """Get today's exact score predictions"""
    try:
        conn = sqlite3.connect(DB_PATH)
        from datetime import date
        today = date.today().isoformat()
        
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, stake, league, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as found_time,
               quality_score, analysis,
               CASE 
                   WHEN outcome = 'win' OR outcome = 'won' THEN '✅ Win'
                   WHEN outcome = 'loss' OR outcome = 'lost' THEN '❌ Loss' 
                   WHEN outcome = 'void' THEN '⚪ Void'
                   ELSE '🔥 LIVE'
               END as status
        FROM football_opportunities 
        WHERE market = 'exact_score' AND recommended_date = ?
        ORDER BY timestamp DESC
        """
        df = pd.read_sql_query(query, conn, params=[today])
        conn.close()
        return df
    except Exception as e:
        print(f"Error loading exact scores: {e}")
        return pd.DataFrame()

exact_scores = get_exact_score_predictions()

if not exact_scores.empty:
    st.success(f"🎯 **{len(exact_scores)} Exact Score Predictions for Today** - Special AI predictions with higher payouts")
    
    for idx, prediction in exact_scores.iterrows():
        # Parse analysis for exact score details
        try:
            analysis_str = str(prediction['analysis']) if pd.notna(prediction['analysis']) and prediction['analysis'] else '{}'
            analysis = json.loads(analysis_str)
            exact_score_analysis = analysis.get('exact_score_analysis', {})
            predicted_score = exact_score_analysis.get('predicted_score', 'Unknown')
            probability = exact_score_analysis.get('probability', 0) * 100  # Convert to percentage
            reasoning = exact_score_analysis.get('reasoning', 'AI-based prediction')
        except:
            predicted_score = 'Unknown'
            probability = 0
            reasoning = 'AI-based prediction'
        
        with st.expander(f"🎯 {prediction['home_team']} vs {prediction['away_team']} - Score: {predicted_score} | Status: {prediction['status']}", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**🏟️ Match:** {prediction['home_team']} vs {prediction['away_team']}")
                st.write(f"**🏆 League:** {prediction['league']}")
                st.write(f"**🎯 Predicted Score:** {predicted_score}")
                st.write(f"**🎲 Probability:** {probability:.1f}%")
                
            with col2:
                st.write(f"**📊 Odds:** {prediction['odds']:.2f}")
                st.write(f"**📈 Edge:** {prediction['edge_percentage']:.1f}%")
                st.write(f"**🎯 Confidence:** {prediction['confidence']}%")
                st.write(f"**💰 Stake:** ${prediction['stake']:.2f}")
                
            with col3:
                st.write(f"**⭐ Quality Score:** {prediction['quality_score']:.1f}/100")
                st.write(f"**🗓️ Match Date:** {prediction['match_date']}")
                st.write(f"**⏰ Kickoff:** {prediction['kickoff_time']}")
                st.write(f"**📊 Status:** {prediction['status']}")
            
            # AI Reasoning
            st.info(f"🧠 **AI Analysis:** {reasoning}")
            
            # Payout calculation
            potential_payout = prediction['stake'] * prediction['odds']
            potential_profit = potential_payout - prediction['stake']
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💰 Potential Payout", f"${potential_payout:.2f}")
            with col2:
                st.metric("💵 Potential Profit", f"${potential_profit:.2f}")
            with col3:
                st.metric("🎯 Return on Investment", f"{((potential_profit / prediction['stake']) * 100):.1f}%")
                
            # Special exact score indicator
            if prediction['odds'] >= 10:
                st.warning("🚀 **HIGH ODDS EXACT SCORE** - Big payout potential but higher risk")
            elif prediction['odds'] >= 6:
                st.info("⭐ **MEDIUM ODDS EXACT SCORE** - Good balance of risk and reward")
            else:
                st.success("✅ **CONSERVATIVE EXACT SCORE** - Lower risk, solid prediction")

else:
    st.info("🎯 **Exact Score Predictions** - Today's special predictions will appear here")
    st.caption("🤖 AI analyzes matches and selects the 2 best games for exact score predictions")

st.markdown("---")

# === TIPS SELLING DASHBOARD ===
st.header("💡 Tips Analytics & Performance")

st.success("🎯 **Tips Selling Mode Active** - Focus on quality recommendations with verified ROI tracking")

# Show tips-focused statistics
@st.cache_data(ttl=30)
def get_tips_stats():
    try:
        conn = sqlite3.connect('data/real_football.db')
        cursor = conn.cursor()
        
        # Get stats for tips selling (today's tips)
        from datetime import date
        today = date.today().isoformat()
        
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as total_tips,
                COUNT(CASE WHEN recommended_tier = 'premium' THEN 1 END) as premium_tips,
                COUNT(CASE WHEN recommended_tier = 'standard' THEN 1 END) as standard_tips,
                ROUND(AVG(CASE WHEN recommended_tier IS NOT NULL THEN quality_score END), 1) as avg_quality
            FROM football_opportunities
            WHERE recommended_date = ?
        """, (today,))
        
        stats = cursor.fetchone()
        conn.close()
        return stats
    except:
        return (0, 0, 0, 0)

tips_stats = get_tips_stats()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("📊 Total Tips Today", tips_stats[0], f"Max 40/day")
with col2:
    st.metric("🌟 Premium Tips", tips_stats[1], f"Top quality")
with col3:
    st.metric("⭐ Standard Tips", tips_stats[2], f"Good value")
with col4:
    avg_quality = tips_stats[3] if tips_stats[3] else 0
    st.metric("🎯 Avg Quality Score", f"{avg_quality}/100", f"AI confidence")

# Tips Selling Mode - No auto-betting controls needed
st.info("🎯 **Tips Selling Mode Active** - Focus on quality tip recommendations instead of auto-betting.")

st.markdown("---")

# === WINS & LOSSES TRACKING ===
st.header("🏆 Betting Performance & Results")

# Get performance stats
@st.cache_data(ttl=30)
def get_wins_losses_stats():
    """Get current wins/losses performance stats"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            COUNT(*) as total_tips,
            COUNT(CASE WHEN outcome IN ('won', 'win') THEN 1 END) as wins,
            COUNT(CASE WHEN outcome IN ('lost', 'loss') THEN 1 END) as losses,
            COUNT(CASE WHEN outcome IS NULL OR outcome = '' THEN 1 END) as pending,
            SUM(CASE WHEN outcome IN ('won', 'win') THEN profit_loss ELSE 0 END) as win_profit,
            SUM(CASE WHEN outcome IN ('lost', 'loss') THEN profit_loss ELSE 0 END) as loss_amount,
            SUM(profit_loss) as total_profit,
            ROUND(AVG(quality_score), 1) as avg_quality
        FROM football_opportunities 
        WHERE recommended_tier IS NOT NULL
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except Exception as e:
        st.error(f"Error loading performance: {e}")
        return None

perf_stats = get_wins_losses_stats()

if perf_stats is not None:
    # Calculate win rate
    completed_tips = perf_stats['wins'] + perf_stats['losses']
    win_rate = (perf_stats['wins'] / completed_tips * 100) if completed_tips > 0 else 0
    
    # Performance Summary Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "📊 Total Tips", 
            int(perf_stats['total_tips']),
            "Quality recommendations"
        )
    
    with col2:
        st.metric(
            "✅ Wins", 
            int(perf_stats['wins']),
            f"{win_rate:.1f}% win rate"
        )
    
    with col3:
        st.metric(
            "❌ Losses", 
            int(perf_stats['losses']),
            f"{completed_tips} completed"
        )
    
    with col4:
        profit_color = "normal" if perf_stats['total_profit'] >= 0 else "inverse"
        st.metric(
            "💰 Total P&L", 
            f"${perf_stats['total_profit']:.2f}",
            delta_color=profit_color
        )
    
    with col5:
        st.metric(
            "⭐ Avg Quality", 
            f"{perf_stats['avg_quality']:.1f}/100",
            "AI confidence"
        )
    
    # Win Rate Progress Bar
    st.subheader("📈 Performance Overview")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Win rate visualization
        if win_rate >= 60:
            win_status = "Excellent"
            win_color = "success"
        elif win_rate >= 55:
            win_status = "Good"
            win_color = "info"
        elif win_rate >= 50:
            win_status = "Average"
            win_color = "warning"
        else:
            win_status = "Building"
            win_color = "error"
        
        if win_color == "success":
            st.success(f"🎯 **Win Rate: {win_rate:.1f}%** ({win_status})")
        elif win_color == "info":
            st.info(f"🎯 **Win Rate: {win_rate:.1f}%** ({win_status})")
        elif win_color == "warning":
            st.warning(f"🎯 **Win Rate: {win_rate:.1f}%** ({win_status})")
        else:
            st.error(f"🎯 **Win Rate: {win_rate:.1f}%** ({win_status})")
        
        # Progress bar for win rate
        st.progress(min(win_rate / 100, 1.0))
    
    with col2:
        # Profit analysis
        if perf_stats['total_profit'] > 0:
            st.success(f"💰 **Profitable: +${perf_stats['total_profit']:.2f}**")
            roi_percent = (perf_stats['total_profit'] / (completed_tips * 5)) * 100 if completed_tips > 0 else 0
            st.info(f"📊 ROI: {roi_percent:.1f}% (${perf_stats['total_profit']:.2f} profit on ${completed_tips * 5:.2f} stakes)")
        elif perf_stats['total_profit'] == 0:
            st.info(f"📊 **Break Even: ${perf_stats['total_profit']:.2f}**")
        else:
            st.error(f"📉 **Loss: ${perf_stats['total_profit']:.2f}**")
            st.info("🔄 Building authentic track record...")
else:
    st.warning("⚠️ Unable to load performance data")

# Recent Wins and Losses Display
st.subheader("🎯 Recent Results")

@st.cache_data(ttl=30)
def get_recent_results():
    """Get recent wins and losses"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Get recent wins
        wins_query = """
        SELECT home_team, away_team, selection, odds, stake, profit_loss,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time
        FROM football_opportunities 
        WHERE outcome IN ('won', 'win')
        ORDER BY timestamp DESC 
        LIMIT 10
        """
        wins_df = pd.read_sql_query(wins_query, conn)
        
        # Get recent losses
        losses_query = """
        SELECT home_team, away_team, selection, odds, stake, profit_loss,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time
        FROM football_opportunities 
        WHERE outcome IN ('lost', 'loss')
        ORDER BY timestamp DESC 
        LIMIT 10
        """
        losses_df = pd.read_sql_query(losses_query, conn)
        
        conn.close()
        return wins_df, losses_df
    except Exception as e:
        st.error(f"Error loading recent results: {e}")
        return pd.DataFrame(), pd.DataFrame()

wins_df, losses_df = get_recent_results()

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### ✅ **Recent WINS**")
    if not wins_df.empty:
        for _, win in wins_df.head(5).iterrows():
            profit = win['profit_loss']
            st.success(f"""
            **🎉 {win['selection']}** @ {win['odds']:.2f}  
            ⚽ {win['home_team']} vs {win['away_team']}  
            💰 **+${profit:.2f}** profit (${win['stake']:.2f} stake)  
            🕒 {win['bet_time']}
            """)
    else:
        st.info("🔄 Recent wins will appear here")

with col2:
    st.markdown("#### ❌ **Recent LOSSES**")
    if not losses_df.empty:
        for _, loss in losses_df.head(5).iterrows():
            loss_amount = abs(loss['profit_loss'])
            st.error(f"""
            **❌ {loss['selection']}** @ {loss['odds']:.2f}  
            ⚽ {loss['home_team']} vs {loss['away_team']}  
            💸 **-${loss_amount:.2f}** loss (${loss['stake']:.2f} stake)  
            🕒 {loss['bet_time']}
            """)
    else:
        st.info("🔄 Recent losses will appear here")

st.markdown("---")

# Update bet outcomes section
st.subheader("🎯 Update Bet Results")

@st.cache_data(ttl=10)
def load_pending_bets():
    """Get pending tips awaiting results"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT id, home_team, away_team, selection, odds, stake, 
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time
        FROM football_opportunities 
        WHERE (outcome IS NULL OR outcome = '' OR outcome = 'pending')
        AND recommended_tier IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 20
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=10)
def load_finished_bets():
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT home_team, away_team, selection, odds, stake, outcome, profit_loss,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time
        FROM football_opportunities 
        WHERE outcome IS NOT NULL AND outcome != ''
        ORDER BY timestamp DESC
        LIMIT 50
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

pending_bets = load_pending_bets()

if not pending_bets.empty:
    st.warning(f"⚠️ {len(pending_bets)} old bets pending results - tips selling mode focuses on new recommendations")
else:
    st.success("🎉 No pending bets! All results are up to date.")

st.markdown("---")

# === ALL AI OPPORTUNITIES ===
st.header("🤖 All AI Opportunities")

@st.cache_data(ttl=30)
def load_all_ai_opportunities():
    """Load all AI-generated opportunities for manual review"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT home_team, away_team, league, selection, odds, edge_percentage, 
               confidence, analysis, match_date, kickoff_time,
               datetime(timestamp, 'unixepoch', 'localtime') as found_time
        FROM football_opportunities 
        WHERE status = 'pending'
        AND edge_percentage >= 5
        ORDER BY edge_percentage DESC, confidence DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error loading AI opportunities: {e}")
        return pd.DataFrame()

ai_opportunities = load_all_ai_opportunities()

if not ai_opportunities.empty:
    st.success(f"🎯 **{len(ai_opportunities)} AI opportunities found** - All betting chances discovered by the AI system")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Opportunities", len(ai_opportunities))
    with col2:
        avg_edge = ai_opportunities['edge_percentage'].mean()
        st.metric("Avg Edge", f"{avg_edge:.1f}%")
    with col3:
        high_edge = len(ai_opportunities[ai_opportunities['edge_percentage'] >= 15])
        st.metric("High Edge (15%+)", high_edge)
    with col4:
        high_conf = len(ai_opportunities[ai_opportunities['confidence'] >= 80])
        st.metric("High Confidence", high_conf)
    
    # Filter controls for AI opportunities
    col1, col2 = st.columns(2)
    with col1:
        leagues = ['All'] + list(ai_opportunities['league'].unique())
        selected_league_ai = st.selectbox("League Filter", leagues, key="ai_league")
    with col2:
        bet_types = ['All'] + list(ai_opportunities['selection'].unique())
        selected_bet_ai = st.selectbox("Bet Type", bet_types, key="ai_bet")
    
    # Apply filters
    filtered_ai = ai_opportunities.copy()
    if isinstance(filtered_ai, pd.Series):
        filtered_ai = filtered_ai.to_frame().T
    
    if selected_league_ai != 'All':
        filtered_ai = filtered_ai[filtered_ai['league'] == selected_league_ai]
    if selected_bet_ai != 'All':
        filtered_ai = filtered_ai[filtered_ai['selection'] == selected_bet_ai]
    
    # Ensure it's a DataFrame after filtering
    if isinstance(filtered_ai, pd.Series):
        filtered_ai = filtered_ai.to_frame().T
    
    # Display AI opportunities table
    if isinstance(filtered_ai, pd.DataFrame) and not filtered_ai.empty:
        st.subheader(f"📊 AI Opportunities ({len(filtered_ai)} matches filters)")
        
        display_ai = filtered_ai[['found_time', 'home_team', 'away_team', 'league', 'selection', 
                                 'odds', 'edge_percentage', 'confidence']].copy()
        if isinstance(display_ai, pd.Series):
            display_ai = display_ai.to_frame().T
        # Ensure it's a DataFrame before setting columns
        if isinstance(display_ai, pd.DataFrame):
            display_ai.columns = ['Discovered', 'Home', 'Away', 'League', 'Bet', 'Odds', 'Edge %', 'Confidence']
        
        # Format the data
        display_ai['Odds'] = display_ai['Odds'].round(2)
        display_ai['Edge %'] = display_ai['Edge %'].round(1)
        
        # Color coding by edge percentage
        def highlight_edge(row):
            edge = row['Edge %']
            if edge >= 20:
                return ['background-color: #d4edda'] * len(row)  # Green for high edge
            elif edge >= 10:
                return ['background-color: #fff3cd'] * len(row)  # Yellow for medium edge
            else:
                return ['background-color: #f8f9fa'] * len(row)  # Light gray for low edge
        
        # Ensure we have a DataFrame for styling
        if isinstance(display_ai, pd.DataFrame) and not display_ai.empty:
            styled_ai = display_ai.style.apply(highlight_edge, axis=1)
        else:
            styled_ai = display_ai
        st.dataframe(styled_ai, width='stretch')
        
    
    else:
        st.warning("No opportunities match your filters")

else:
    st.info("🔍 **AI is scanning for opportunities...** New opportunities will appear here as the AI discovers them")

# === PERFORMANCE SUMMARY ===
st.header("📊 Performance Summary")

perf = load_performance()

if perf is not None and perf['total_bets'] > 0:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Bets", int(perf['total_bets']))
        
    with col2:
        win_rate = (perf['wins'] / (perf['wins'] + perf['losses']) * 100) if (perf['wins'] + perf['losses']) > 0 else 0
        st.metric("Win Rate", f"{win_rate:.1f}%")
        
    with col3:
        st.metric("Net Profit", f"${perf['net_profit']:.2f}")
        
    with col4:
        roi = perf['avg_roi'] if pd.notna(perf['avg_roi']) else 0
        st.metric("Avg ROI", f"{roi:.1f}%")
        
    # Profit/Loss Chart
    recent = load_recent_bets()
    if isinstance(recent, pd.DataFrame) and not recent.empty and 'profit_loss' in recent.columns:
        completed = recent[recent['outcome'].notna() & recent['profit_loss'].notna()].copy()
        if isinstance(completed, pd.Series):
            completed = completed.to_frame().T
        if isinstance(completed, pd.DataFrame) and not completed.empty:
            completed['cumulative_profit'] = completed['profit_loss'].fillna(0).cumsum()
            
            fig = px.line(completed, y='cumulative_profit', 
                         title="Profit Over Time",
                         labels={'cumulative_profit': 'Cumulative Profit ($)'})
            fig.update_traces(line_color='#00cc44')
            st.plotly_chart(fig, use_column_width=True)

else:
    st.info("📈 Performance tracking will appear after placing bets")

# === CURRENT BETTING ACTIVITY ===
st.header("📊 Current Betting Activity")

@st.cache_data(ttl=60)
def load_historical_bets():
    """Get all historical betting data with filters"""
    try:
        conn = sqlite3.connect('data/real_football.db')
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, confidence,
               stake, outcome, profit_loss, league, match_date, kickoff_time, status,
               datetime(timestamp, 'unixepoch', 'localtime') as bet_time,
               DATE(datetime(timestamp, 'unixepoch', 'localtime')) as bet_date
        FROM football_opportunities 
        WHERE status = 'placed'
        ORDER BY timestamp DESC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

historical_bets = load_historical_bets()

if not historical_bets.empty:
    # Filter controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Outcome filter
        outcome_options = ['All', 'Pending'] + list(historical_bets['outcome'].dropna().unique())
        selected_outcome = st.selectbox("Filter by Result", outcome_options)
    
    with col2:
        # League filter
        league_options = ['All'] + list(historical_bets['league'].dropna().unique())
        selected_league = st.selectbox("Filter by League", league_options)
    
    with col3:
        # Show count
        show_count = st.selectbox("Show", [20, 50, 100, "All"])
    
    # Apply filters
    filtered_bets = historical_bets.copy()
    
    if selected_outcome == 'Pending':
        filtered_bets = filtered_bets[filtered_bets['outcome'].isna()]
    elif selected_outcome != 'All':
        filtered_bets = filtered_bets[filtered_bets['outcome'] == selected_outcome]
    
    if selected_league != 'All':
        filtered_bets = filtered_bets[filtered_bets['league'] == selected_league]
    
    if show_count != "All":
        if isinstance(filtered_bets, pd.DataFrame):
            filtered_bets = filtered_bets.head(int(show_count))
        elif isinstance(filtered_bets, pd.Series):
            filtered_bets = filtered_bets.head(int(show_count)).to_frame().T
    
    # === WIN/TOTAL RATIO PROMINENTLY DISPLAYED ===
    completed_bets = historical_bets[historical_bets['outcome'].notna()]
    # Only count PLACED bets without outcomes as truly pending
    placed_bets = historical_bets[historical_bets['status'] == 'placed']
    if isinstance(placed_bets, pd.Series):
        placed_bets = placed_bets.to_frame().T
    pending_count = len(placed_bets[placed_bets['outcome'].isna()]) if isinstance(placed_bets, pd.DataFrame) else 0
    
    if not completed_bets.empty:
        wins = len(completed_bets[completed_bets['outcome'] == 'win'])
        losses = len(completed_bets[completed_bets['outcome'] == 'loss'])
        voids = len(completed_bets[completed_bets['outcome'] == 'void'])
        total_decided = wins + losses
        
        # Prominent Win/Total display
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("🎯 Win/Total", f"{wins}/{total_decided}", 
                     f"{(wins/total_decided*100):.1f}% win rate" if total_decided > 0 else "No completed bets")
        
        with col2:
            st.metric("✅ Wins", wins, f"${completed_bets[completed_bets['outcome'] == 'win']['profit_loss'].sum():.2f}")
        
        with col3:
            st.metric("❌ Losses", losses, f"${completed_bets[completed_bets['outcome'] == 'loss']['profit_loss'].sum():.2f}")
        
        with col4:
            total_profit = completed_bets['profit_loss'].sum()
            st.metric("💰 Net P&L", f"${total_profit:.2f}")
        
        with col5:
            st.metric("⏳ Pending", pending_count)
    
    # Filter controls
    st.subheader("🔍 Filter & Search")
    
    # Display current betting table
    st.subheader("📊 Current Bets & Results")
    
    display_df = filtered_bets[['bet_time', 'home_team', 'away_team', 'selection', 
                               'odds', 'edge_percentage', 'stake', 'outcome', 'profit_loss']].copy()
    if isinstance(display_df, pd.Series):
        display_df = display_df.to_frame().T
    # Ensure it's a DataFrame before setting columns
    if isinstance(display_df, pd.DataFrame):
        display_df.columns = ['Date', 'Home Team', 'Away Team', 'Bet', 'Odds', 
                             'Edge %', 'Stake $', 'Result', 'P&L $']
    
    # Format numbers
    display_df['Odds'] = display_df['Odds'].round(2)
    display_df['Edge %'] = display_df['Edge %'].round(1)
    display_df['Stake $'] = display_df['Stake $'].round(2)
    display_df['P&L $'] = display_df['P&L $'].round(2)
    
    # Color coding function
    def highlight_results(row):
        if pd.isna(row['Result']):
            return ['background-color: #fff3cd'] * len(row)  # Yellow for pending
        elif row['Result'] == 'win':
            return ['background-color: #d4edda'] * len(row)  # Green for wins
        elif row['Result'] == 'loss':
            return ['background-color: #f8d7da'] * len(row)  # Red for losses
        else:
            return ['background-color: #f0f0f0'] * len(row)  # Gray for void
    
    # Ensure we have a DataFrame for styling
    if isinstance(display_df, pd.DataFrame) and not display_df.empty:
        styled_df = display_df.style.apply(highlight_results, axis=1)
    else:
        styled_df = display_df
    st.dataframe(styled_df, width='stretch')
    
    # Monthly performance breakdown
    if not completed_bets.empty:
        st.subheader("📅 Monthly Performance Breakdown")
        
        completed_copy = completed_bets.copy()
        if isinstance(completed_copy, pd.Series):
            completed_copy = completed_copy.to_frame().T
        # Ensure proper datetime conversion and dt accessor usage
        if isinstance(completed_copy, pd.DataFrame) and not completed_copy.empty:
            completed_copy['month'] = pd.to_datetime(completed_copy['bet_time']).dt.strftime('%Y-%m')
        else:
            completed_copy['month'] = ''
        
        monthly_stats = completed_copy.groupby('month').agg({
            'outcome': 'count',
            'profit_loss': 'sum',
            'stake': 'sum'
        }).round(2)
        
        monthly_stats.columns = ['Total Bets', 'Net P&L ($)', 'Total Staked ($)']
        monthly_stats['ROI %'] = ((monthly_stats['Net P&L ($)'] / monthly_stats['Total Staked ($)']) * 100).round(1)
        
        # Add win/loss breakdown
        for month in monthly_stats.index:
            month_data = completed_copy[completed_copy['month'] == month]
            wins_month = len(month_data[month_data['outcome'] == 'win'])
            losses_month = len(month_data[month_data['outcome'] == 'loss'])
            monthly_stats.loc[month, 'Win/Loss'] = f"{wins_month}/{wins_month + losses_month}"
        
        st.dataframe(monthly_stats, width='stretch')

else:
    st.info("📝 Current betting activity will appear here after placing bets")


# Auto-refresh
st.markdown("---")
st.caption("🔄 Dashboard refreshes automatically every 30 seconds")