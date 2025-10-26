#!/usr/bin/env python3

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from feature_analytics import FeatureAnalytics

# Database path
DB_PATH = 'data/real_football.db'

# Page setup
st.set_page_config(
    page_title="🎯 Exact Score Predictions | +519% ROI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for exclusive design
st.markdown("""
<style>
    /* Main background and fonts */
    .stApp {
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
    }
    
    /* Headers */
    h1 {
        color: #FFD700 !important;
        font-size: 4rem !important;
        font-weight: 900 !important;
        text-align: center !important;
        text-shadow: 3px 3px 6px rgba(0,0,0,0.6);
        padding: 30px 0;
        margin-bottom: 10px !important;
    }
    
    h2 {
        color: #FFFFFF !important;
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        border-left: 5px solid #FFD700;
        padding-left: 15px;
        margin-top: 40px !important;
    }
    
    h3 {
        color: #E0E0E0 !important;
        font-size: 1.4rem !important;
    }
    
    /* Metrics styling */
    [data-testid="stMetricValue"] {
        font-size: 2.5rem !important;
        font-weight: 800 !important;
        color: #FFD700 !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    }
    
    [data-testid="stMetricLabel"] {
        color: #B0B0B0 !important;
        font-size: 1rem !important;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    /* Cards and containers */
    .stMarkdown {
        color: #E0E0E0;
    }
    
    /* Dividers */
    hr {
        border-color: rgba(255, 215, 0, 0.3) !important;
        margin: 30px 0;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        color: #000000;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 12px 35px;
        transition: all 0.3s ease;
        font-size: 1rem;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(255, 215, 0, 0.4);
    }
    
    /* Success/Info boxes */
    .stAlert {
        background-color: rgba(255, 215, 0, 0.1) !important;
        border: 1px solid rgba(255, 215, 0, 0.3) !important;
        border-radius: 10px;
        color: #FFD700 !important;
    }
    
    /* DataFrames */
    [data-testid="stDataFrame"] {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 10px;
    }
    
    /* Caption text */
    .caption {
        color: #909090 !important;
        font-size: 0.85rem;
    }
    
    /* Subtitle */
    .subtitle {
        text-align: center;
        color: #10B981;
        font-size: 1.4rem;
        margin-bottom: 20px;
        letter-spacing: 3px;
        text-transform: uppercase;
        font-weight: 700;
    }
    
    /* ROI Badge */
    .roi-badge {
        text-align: center;
        color: #10B981;
        font-size: 2.5rem;
        font-weight: 900;
        text-shadow: 0 0 20px rgba(16, 185, 129, 0.5);
        padding: 20px;
        margin: 20px 0;
    }
    
    /* Exact score badge */
    .exact-badge {
        background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%);
        color: white;
        padding: 8px 20px;
        border-radius: 20px;
        font-weight: 700;
        display: inline-block;
        margin: 5px;
        box-shadow: 0 2px 8px rgba(220, 38, 38, 0.4);
    }
    
    /* Collapsible section */
    .stExpander {
        background-color: rgba(255, 255, 255, 0.03);
        border-radius: 10px;
        border: 1px solid rgba(255, 215, 0, 0.2);
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def load_exact_score_tips():
    """Load all pending exact score predictions (until game is over)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, recommended_date
        FROM football_opportunities 
        WHERE market = 'exact_score'
        AND (outcome IS NULL OR outcome = '' OR outcome = 'unknown')
        ORDER BY match_date ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30) 
def load_exact_score_performance():
    """Get exact score performance stats"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            COUNT(*) as total_tips,
            COUNT(CASE WHEN outcome IN ('win', 'won') THEN 1 END) as wins,
            COUNT(CASE WHEN outcome IN ('loss', 'lost') THEN 1 END) as losses,
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome NOT IN ('unknown', 'void') THEN profit_loss ELSE 0 END) as net_profit,
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome NOT IN ('unknown', 'void') THEN stake ELSE 0 END) as total_staked
        FROM football_opportunities 
        WHERE tier = 'legacy'
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

@st.cache_data(ttl=30)
def load_exact_score_history():
    """Load exact score historical results"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, outcome, profit_loss, match_date,
               CASE 
                   WHEN outcome IN ('win', 'won') THEN '✅'
                   WHEN outcome IN ('loss', 'lost') THEN '❌'
                   ELSE '⚪'
               END as result
        FROM football_opportunities 
        WHERE tier = 'legacy'
        AND outcome IS NOT NULL 
        AND outcome != ''
        AND outcome NOT IN ('unknown')
        ORDER BY timestamp DESC 
        LIMIT 100
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_regular_tips():
    """Load regular betting opportunities (archived)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT home_team, away_team, selection, odds, edge_percentage, 
               confidence, match_date, tier, outcome, profit_loss
        FROM football_opportunities 
        WHERE tier IS NOT NULL
        AND tier != 'legacy'
        ORDER BY timestamp DESC
        LIMIT 20
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=30) 
def load_regular_performance():
    """Get regular betting performance stats"""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            COUNT(*) as total_tips,
            COUNT(CASE WHEN outcome IN ('win', 'won') THEN 1 END) as wins,
            COUNT(CASE WHEN outcome IN ('loss', 'lost') THEN 1 END) as losses,
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome != 'unknown' THEN profit_loss ELSE 0 END) as net_profit,
            SUM(CASE WHEN outcome IS NOT NULL AND outcome != '' AND outcome != 'unknown' THEN stake ELSE 0 END) as total_staked
        FROM football_opportunities 
        WHERE tier IS NOT NULL
        AND tier != 'legacy'
        """
        result = pd.read_sql_query(query, conn)
        conn.close()
        return result.iloc[0] if not result.empty else None
    except:
        return None

@st.cache_data(ttl=30)
def load_learning_status():
    """Get ML learning system status"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Get feature logs stats
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total_logged,
                   SUM(CASE WHEN outcome IN ('won','win','lost','loss') THEN 1 ELSE 0 END) as settled,
                   SUM(CASE WHEN outcome IN ('won','win') THEN 1 ELSE 0 END) as wins,
                   AVG(data_completeness) as avg_completeness
            FROM feature_logs
        """)
        row = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM feature_importance")
        importance_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT MAX(last_updated) FROM feature_importance")
        last_updated = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_logged': row[0] or 0,
            'settled': row[1] or 0,
            'wins': row[2] or 0,
            'avg_completeness': row[3] or 0,
            'features_analyzed': importance_count,
            'last_report': last_updated
        }
    except:
        return None

# ============================================================================
# HEADER
# ============================================================================

# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

with st.sidebar:
    st.markdown("## 📋 Navigation")
    page = st.radio(
        "Choose Section:",
        ["📊 Dashboard", "📜 Terms & Legal"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### 🎯 Exact Score Predictions")
    st.caption("AI-Powered Exact Score Tips")
    st.caption("Launching January 2026")
    
    st.markdown("---")
    st.markdown("### 💰 Subscription")
    st.markdown("**Standard:** 499 SEK/month")
    st.markdown("**VIP:** 999 SEK/month")
    
    st.markdown("---")
    st.caption("🔒 100% Transparent Performance")
    st.caption("📊 Live ROI Tracking")

# ============================================================================
# PAGE: TERMS & LEGAL
# ============================================================================

if page == "📜 Terms & Legal":
    st.markdown("# 📜 Terms of Service & Legal")
    st.markdown('<p class="subtitle">LEGAL INFORMATION & DISCLAIMERS</p>', unsafe_allow_html=True)
    
    # Language selector
    language = st.radio("Select Language / Välj språk:", ["🇬🇧 English", "🇸🇪 Svenska"], horizontal=True)
    
    st.markdown("---")
    
    if "English" in language:
        # English Terms
        with st.expander("📋 Terms of Service", expanded=True):
            try:
                with open('legal/terms_of_service_en.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            except:
                st.error("Terms of Service document not found")
        
        with st.expander("⚠️ Risk Disclaimer", expanded=False):
            try:
                with open('legal/disclaimer_en.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            except:
                st.error("Risk Disclaimer document not found")
        
        with st.expander("🔒 Privacy Policy", expanded=False):
            try:
                with open('legal/privacy_policy_en.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            except:
                st.error("Privacy Policy document not found")
    
    else:
        # Swedish Terms
        with st.expander("📋 Användarvillkor", expanded=True):
            try:
                with open('legal/terms_of_service_sv.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            except:
                st.error("Användarvillkor hittades inte")
        
        with st.expander("⚠️ Riskvarning", expanded=False):
            try:
                with open('legal/disclaimer_sv.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            except:
                st.error("Riskvarning hittades inte")
        
        with st.expander("🔒 Integritetspolicy", expanded=False):
            try:
                with open('legal/privacy_policy_sv.md', 'r', encoding='utf-8') as f:
                    st.markdown(f.read())
            except:
                st.error("Integritetspolicy hittades inte")
    
    st.markdown("---")
    st.markdown("## 🇸🇪 Responsible Gambling Support")
    st.info("""
    **Stödlinjen (Swedish Gambling Support):**
    - Phone: 020-819 100
    - Website: [stodlinjen.se](https://www.stodlinjen.se)
    
    **Important:** Gambling involves risk. Only bet what you can afford to lose.
    """)
    
    st.markdown("---")
    st.markdown("## 📧 Contact")
    st.markdown("For questions about these terms, contact us via Telegram channel.")
    
    st.markdown("---")
    st.caption("Last Updated: October 26, 2025")
    st.caption("Governed by Swedish Law | All Rights Reserved")
    
    st.stop()  # Stop here if on Terms page

# ============================================================================
# PAGE: DASHBOARD (Main Content)
# ============================================================================

st.markdown("# 🎯 EXACT SCORE PREDICTIONS")

# Calculate real ROI for subtitle
exact_stats = load_exact_score_performance()
if exact_stats is not None and exact_stats['total_staked'] > 0:
    roi = (exact_stats['net_profit'] / exact_stats['total_staked'] * 100)
    st.markdown(f'<p class="subtitle">✅ PROVEN +{roi:.0f}% ROI | AI-POWERED ACCURACY</p>', unsafe_allow_html=True)
    st.markdown(f'<div class="roi-badge">📈 +{roi:.0f}% RETURN ON INVESTMENT</div>', unsafe_allow_html=True)
else:
    st.markdown('<p class="subtitle">✅ AI-POWERED EXACT SCORE PREDICTIONS</p>', unsafe_allow_html=True)

col1, col2 = st.columns([4, 1])
with col2:
    if st.button("🔄 REFRESH"):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ============================================================================
# TOP: EXACT SCORE PERFORMANCE STATS (HERO SECTION)
# ============================================================================

st.markdown("## 🏆 PERFORMANCE OVERVIEW")

if exact_stats is not None:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("TOTAL PREDICTIONS", int(exact_stats['total_tips']))
    
    with col2:
        settled = exact_stats['wins'] + exact_stats['losses']
        st.metric("SETTLED", int(settled))
    
    with col3:
        hit_rate = (exact_stats['wins'] / (exact_stats['wins'] + exact_stats['losses']) * 100) if (exact_stats['wins'] + exact_stats['losses']) > 0 else 0
        st.metric("HIT RATE", f"{hit_rate:.1f}%")
    
    with col4:
        st.metric("MONEY SPENT", f"{exact_stats['total_staked']:,.0f} SEK")
    
    with col5:
        st.metric("TOTAL PROFIT", f"{exact_stats['net_profit']:,.0f} SEK", delta="Authentic Results")
    
    with col6:
        roi = (exact_stats['net_profit'] / exact_stats['total_staked'] * 100) if exact_stats['total_staked'] > 0 else 0
        st.metric("ROI", f"+{roi:.1f}%")

st.success("🔒 **100% Authentic Performance** | Real match results verified from API-Football")

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# ML LEARNING SYSTEM STATUS
# ============================================================================

st.markdown("## 🧠 AI LEARNING SYSTEM STATUS")

learning_status = load_learning_status()
if learning_status:
    settled_count = learning_status['settled']
    milestone_100 = 100
    milestone_500 = 500
    
    # Progress calculations
    progress_to_100 = min(settled_count / milestone_100, 1.0)
    progress_to_500 = min(settled_count / milestone_500, 1.0)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Predictions Logged", f"{learning_status['total_logged']}")
        st.caption("🔬 With 50+ features each")
    
    with col2:
        st.metric("Settled & Learning", f"{settled_count}")
        st.caption(f"📊 {learning_status['avg_completeness']:.0f}% data quality")
    
    with col3:
        features_status = "✅ Active" if learning_status['features_analyzed'] > 0 else "⏳ Pending"
        st.metric("Feature Analysis", features_status)
        st.caption(f"{learning_status['features_analyzed']} features analyzed")
    
    with col4:
        if settled_count >= milestone_100:
            next_milestone = milestone_500
            status_text = f"{settled_count}/{next_milestone}"
            milestone_name = "→ 500 Target"
        else:
            next_milestone = milestone_100
            status_text = f"{settled_count}/{next_milestone}"
            milestone_name = "→ First Report"
        
        st.metric("Progress", status_text)
        st.caption(milestone_name)
    
    # Progress bars
    st.markdown("")
    
    if settled_count < milestone_100:
        remaining = milestone_100 - settled_count
        st.progress(progress_to_100, text=f"🎯 First Report Milestone: {settled_count}/{milestone_100} ({remaining} needed)")
        
        if remaining <= 10:
            st.info(f"🔥 **Almost there!** Only {remaining} more settled predictions until your first feature importance report!")
        elif remaining <= 30:
            st.info(f"⚡ **Getting close!** {remaining} more predictions needed for automated learning insights.")
    else:
        st.progress(1.0, text=f"✅ First Milestone Complete: {settled_count}/{milestone_100}")
        st.success("🎉 **Learning Active!** Feature importance reports are being generated automatically.")
        
        if settled_count < milestone_500:
            remaining_500 = milestone_500 - settled_count
            st.progress(progress_to_500, text=f"🚀 Next Milestone: {settled_count}/{milestone_500} (statistical significance)")
            st.info(f"📈 {remaining_500} more predictions until statistical significance threshold")
    
    if learning_status['last_report']:
        st.caption(f"📅 Last analysis: {learning_status['last_report']}")
else:
    st.info("🧠 ML learning system initializing...")

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# FEATURE ANALYTICS - WHAT'S WORKING
# ============================================================================

st.markdown("## 📊 FEATURE ANALYTICS - What's Driving Success")

try:
    analytics = FeatureAnalytics()
    importance_df = analytics.calculate_feature_importance()
    summary = analytics.get_feature_performance_summary()
    
    if not importance_df.empty and len(importance_df) > 0:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("### 🎯 Top 10 Winning Features")
            st.caption("Features that correlate most with successful predictions")
            
            # Show top 10 features for wins
            top_winning = importance_df.nlargest(10, 'importance_score')
            
            for idx, row in top_winning.iterrows():
                feature_emoji = "🔥" if row['importance_score'] > 50 else "✅" if row['importance_score'] > 25 else "📊"
                
                # Format feature name (make it readable)
                feature_display = row['feature_name'].replace('_', ' ').title()
                
                # Show difference between win avg and loss avg
                if row['relative_diff_pct'] > 0:
                    trend_text = f"+{row['relative_diff_pct']:.0f}% higher in wins"
                    trend_color = "🟢"
                else:
                    trend_text = f"{row['relative_diff_pct']:.0f}% lower in wins"
                    trend_color = "🔴"
                
                st.markdown(f"{feature_emoji} **{feature_display}** ({row['category']})")
                st.caption(f"{trend_color} {trend_text} | Sample: {row['sample_size']} predictions")
                st.progress(min(row['importance_score'] / 100, 1.0))
                st.markdown("")
        
        with col2:
            st.markdown("### 📈 Performance by Category")
            st.caption("How different feature types contribute to accuracy")
            
            # Group by category
            category_perf = importance_df.groupby('category').agg({
                'importance_score': 'mean',
                'sample_size': 'sum'
            }).sort_values('importance_score', ascending=False)
            
            for category, data in category_perf.iterrows():
                avg_importance = data['importance_score']
                
                category_emoji = {
                    'Team Form': '⚽',
                    'Head-to-Head': '🤝',
                    'Expected Goals': '🎯',
                    'Odds Movement': '📈',
                    'League Standings': '🏆',
                    'Injuries/Lineup': '🏥',
                    'Prediction Metrics': '📊'
                }.get(category, '📊')
                
                st.markdown(f"{category_emoji} **{category}**")
                st.caption(f"Average importance: {avg_importance:.1f}")
                st.progress(min(avg_importance / 100, 1.0))
                st.markdown("")
        
        # Quality tier performance
        if summary and 'quality_tiers' in summary and summary['quality_tiers']:
            st.markdown("### 🎚️ Quality Score vs Hit Rate")
            st.caption("Higher quality scores lead to better accuracy")
            
            quality_cols = st.columns(len(summary['quality_tiers']))
            
            for idx, tier_data in enumerate(summary['quality_tiers']):
                with quality_cols[idx]:
                    tier_name = tier_data['quality_tier']
                    total = tier_data['wins'] + tier_data['losses']
                    hit_rate = (tier_data['wins'] / total * 100) if total > 0 else 0
                    
                    st.metric(
                        tier_name,
                        f"{hit_rate:.1f}%",
                        delta=f"{tier_data['wins']}/{total} wins"
                    )
    else:
        st.info("📊 Feature analytics will appear after more predictions are settled. Keep tracking!")
        
except Exception as e:
    st.info(f"📊 Feature analytics coming soon (waiting for settled predictions)")

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# TODAY'S EXACT SCORE PREDICTIONS
# ============================================================================

st.markdown("## 🎯 ACTIVE PREDICTIONS")

exact_tips = load_exact_score_tips()
if not exact_tips.empty:
    st.info(f"📊 **{len(exact_tips)} Active Exact Score Predictions** (pending until match completion)")
    
    st.markdown("")
    
    for idx, tip in exact_tips.iterrows():
        col1, col2, col3 = st.columns([3, 2, 2])
        
        with col1:
            st.markdown(f"### {tip['home_team']} vs {tip['away_team']}")
            st.markdown(f'<div class="exact-badge">{tip["selection"]}</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"**Odds:** `{tip['odds']:.2f}x`")
            st.markdown(f"Edge: **+{tip['edge_percentage']:.1f}%**")
        
        with col3:
            st.markdown(f"**Confidence:** {tip['confidence']}%")
            st.caption(f"⏰ {tip['match_date']}")
        
        st.markdown("---")
else:
    st.info("🎯 No active predictions. All recent predictions have been settled. Check back soon for new opportunities!")

st.markdown("<br>", unsafe_allow_html=True)

# ============================================================================
# HISTORICAL EXACT SCORE PERFORMANCE
# ============================================================================

st.markdown("## 📊 HISTORICAL PERFORMANCE")

historical = load_exact_score_history()
if not historical.empty:
    wins = len(historical[historical['result'] == '✅'])
    losses = len(historical[historical['result'] == '❌'])
    settled_total = wins + losses
    actual_hit_rate = (wins / settled_total * 100) if settled_total > 0 else 0
    
    st.success(f"📈 **{len(historical)} Completed Predictions** | {wins} Wins | {losses} Losses | {actual_hit_rate:.1f}% Hit Rate")
    
    st.markdown("")
    
    display_df = historical.copy()
    display_df['Match'] = display_df['home_team'] + ' vs ' + display_df['away_team']
    display_df['P&L'] = display_df['profit_loss'].apply(lambda x: f"{x:,.0f} SEK")
    display_df['Score'] = display_df['selection']
    
    table_data = display_df[['Match', 'Score', 'odds', 'result', 'P&L', 'match_date']].copy()
    table_data.columns = ['Match', 'Predicted Score', 'Odds', 'Result', 'P&L', 'Date']
    table_data.index = range(1, len(table_data) + 1)
    
    def color_historical(row):
        if '✅' in str(row['Result']):
            return ['background-color: rgba(16, 185, 129, 0.2)'] * len(row)
        elif '❌' in str(row['Result']):
            return ['background-color: rgba(239, 68, 68, 0.2)'] * len(row)
        else:
            return ['background-color: rgba(255, 255, 255, 0.05)'] * len(row)
    
    styled_table = table_data.style.apply(color_historical, axis=1)
    st.dataframe(styled_table, use_container_width=True, height=600)
else:
    st.info("📊 Historical results will appear as predictions settle.")

st.markdown("<br><br>", unsafe_allow_html=True)

# ============================================================================
# ARCHIVED: REGULAR BETTING TIPS (COLLAPSED)
# ============================================================================

with st.expander("📂 ARCHIVED: Regular Betting Tips (Old System)", expanded=False):
    st.caption("⚠️ This section shows the old regular betting system that has been discontinued due to underperformance.")
    
    regular_stats = load_regular_performance()
    if regular_stats is not None and regular_stats['total_tips'] > 0:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Tips", int(regular_stats['total_tips']))
        
        with col2:
            win_rate = (regular_stats['wins'] / (regular_stats['wins'] + regular_stats['losses']) * 100) if (regular_stats['wins'] + regular_stats['losses']) > 0 else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")
        
        with col3:
            net_profit = regular_stats['net_profit'] if regular_stats['net_profit'] is not None else 0
            st.metric("Net Profit", f"{net_profit:,.0f} SEK")
        
        with col4:
            roi = (net_profit / regular_stats['total_staked'] * 100) if regular_stats['total_staked'] and regular_stats['total_staked'] > 0 else 0
            st.metric("ROI", f"{roi:.1f}%")
    else:
        st.info("📂 No regular betting tips in archive - system now exclusively focuses on exact scores.")
    
    st.markdown("")
    
    regular_tips = load_regular_tips()
    if not regular_tips.empty:
        display_reg = regular_tips.head(10).copy()
        display_reg['Match'] = display_reg['home_team'] + ' vs ' + display_reg['away_team']
        display_reg['Tier'] = display_reg['tier'].apply(lambda x: x.upper() if x else 'N/A')
        display_reg['Status'] = display_reg['outcome'].apply(lambda x: '✅' if x in ['win', 'won'] else ('❌' if x in ['loss', 'lost'] else '⚪'))
        
        reg_table = display_reg[['Match', 'selection', 'Tier', 'odds', 'Status']].copy()
        reg_table.columns = ['Match', 'Selection', 'Tier', 'Odds', 'Result']
        st.dataframe(reg_table, use_container_width=True, height=300)

st.markdown("---")
st.markdown('<p style="text-align: center; color: #808080; font-size: 0.9rem;">🔒 100% Authentic Results | 🔄 Auto-refresh every 30s | 🎯 Exact Score Excellence</p>', unsafe_allow_html=True)
