"""
College Basketball Dashboard
Displays NCAAB value picks from the database
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from db_connection import DatabaseConnection

st.set_page_config(
    page_title="College Basketball Value Picks",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #FF6B35;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .sub-header {
        text-align: center;
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .pick-card {
        background: #f8f9fa;
        border-left: 4px solid #FF6B35;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 5px;
    }
    .parlay-card {
        background: #fff3e0;
        border-left: 4px solid #ff9800;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🏀 College Basketball Value Picks</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">NCAAB • Consensus-Based Value Detection</div>', unsafe_allow_html=True)


@st.cache_data(ttl=120)
def get_ncaab_picks():
    """Fetch all NCAAB picks from database"""
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    match,
                    market,
                    selection,
                    odds,
                    probability,
                    ev_percentage,
                    confidence,
                    bookmaker,
                    is_parlay,
                    parlay_legs,
                    commence_time,
                    created_at
                FROM basketball_predictions
                WHERE status = 'pending'
                ORDER BY ev_percentage DESC, confidence DESC
            """
            df = pd.read_sql(query, conn)
            return df
    except Exception as e:
        st.error(f"Error loading picks: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_stats():
    """Get overall stats"""
    try:
        with DatabaseConnection.get_connection() as conn:
            query = """
                SELECT 
                    COUNT(*) as total_picks,
                    AVG(ev_percentage) as avg_ev,
                    AVG(confidence) as avg_conf,
                    COUNT(CASE WHEN is_parlay THEN 1 END) as parlay_count
                FROM basketball_predictions
                WHERE status = 'pending'
            """
            result = pd.read_sql(query, conn)
            return result.iloc[0] if not result.empty else None
    except:
        return None


picks_df = get_ncaab_picks()
stats = get_stats()

if stats is not None:
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{int(stats['total_picks'])}</div>
            <div class="metric-label">Total Picks</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['avg_ev']:.1f}%</div>
            <div class="metric-label">Avg EV</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['avg_conf']:.1f}%</div>
            <div class="metric-label">Avg Confidence</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{int(stats['parlay_count'])}</div>
            <div class="metric-label">Parlays</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 All Picks", "🎯 Singles Only", "🔥 Parlays Only"])

with tab1:
    if picks_df.empty:
        st.info("🏀 No picks available yet. The engine will generate picks every 2 hours.")
    else:
        singles = picks_df[~picks_df['is_parlay']]
        parlays = picks_df[picks_df['is_parlay']]
        
        if not singles.empty:
            st.subheader("🎯 Value Singles")
            for idx, row in singles.head(15).iterrows():
                st.markdown(f"""
                <div class="pick-card">
                    <strong>{row['match']}</strong><br>
                    <span style="color: #FF6B35; font-weight: 600;">{row['market']}: {row['selection']}</span><br>
                    <small>
                        Odds: {row['odds']:.2f} | EV: <strong>{row['ev_percentage']:.1f}%</strong> | 
                        Confidence: {row['confidence']:.1f}% | Book: {row['bookmaker']}
                    </small>
                </div>
                """, unsafe_allow_html=True)
        
        if not parlays.empty:
            st.subheader("🔥 Multi-Game Parlays")
            for idx, row in parlays.head(10).iterrows():
                st.markdown(f"""
                <div class="parlay-card">
                    <strong>{row['match']}</strong><br>
                    <span style="color: #ff9800; font-weight: 600;">{row['market']}</span><br>
                    <span style="font-size: 0.9rem;">{row['selection']}</span><br>
                    <small>
                        Combined Odds: {row['odds']:.2f} | EV: <strong>{row['ev_percentage']:.1f}%</strong> | 
                        Min Confidence: {row['confidence']:.1f}%
                    </small>
                </div>
                """, unsafe_allow_html=True)

with tab2:
    singles_only = picks_df[~picks_df['is_parlay']]
    if singles_only.empty:
        st.info("No singles available")
    else:
        st.dataframe(
            singles_only[['match', 'market', 'selection', 'odds', 'ev_percentage', 'confidence', 'bookmaker']],
            use_container_width=True,
            hide_index=True
        )

with tab3:
    parlays_only = picks_df[picks_df['is_parlay']]
    if parlays_only.empty:
        st.info("No parlays available")
    else:
        st.dataframe(
            parlays_only[['match', 'market', 'selection', 'odds', 'ev_percentage', 'confidence', 'parlay_legs']],
            use_container_width=True,
            hide_index=True
        )

st.markdown("---")
st.caption("🏀 Data updates every 2 hours | Powered by The Odds API consensus devigging")

if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()
