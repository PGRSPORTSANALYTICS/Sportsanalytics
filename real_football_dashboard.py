import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import time
import os
import json
from datetime import datetime, timezone
import pytz
from pathlib import Path

# Page configuration
st.set_page_config(
    page_title="Real Football Champion Dashboard",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

class RealFootballDataLoader:
    """Data loader for Real Football Champion system"""
    
    def __init__(self):
        self.db_path = "data/real_football.db"
        self.ensure_database()
    
    def ensure_database(self):
        """Ensure database exists"""
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(self.db_path):
            # Database will be created by the main system
            pass
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def get_all_opportunities(self):
        """Get all betting opportunities"""
        try:
            conn = self.get_connection()
            query = """
                SELECT * FROM football_opportunities 
                ORDER BY timestamp DESC
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            if not df.empty:
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
                # Parse analysis JSON safely
                def safe_parse_json(x):
                    try:
                        return json.loads(x) if x and x != 'null' else {}
                    except:
                        return {}
                
                df['analysis_parsed'] = df['analysis'].apply(safe_parse_json)
            
            return df
        except Exception as e:
            print(f"Database error: {e}")  # For debugging
            # Return empty DataFrame with proper columns
            return pd.DataFrame({
                'timestamp': [],
                'home_team': [],
                'away_team': [],
                'league': [],
                'selection': [],
                'odds': [],
                'edge_percentage': [],
                'confidence': [],
                'stake': [],
                'status': [],
                'analysis_parsed': []
            })
    
    def get_recent_opportunities(self, limit=20):
        """Get recent opportunities"""
        df = self.get_all_opportunities()
        return df.head(limit) if not df.empty else df
    
    def get_stats_summary(self):
        """Get summary statistics"""
        df = self.get_all_opportunities()
        
        if df.empty:
            return {
                'total_opportunities': 0,
                'avg_edge': 0,
                'avg_confidence': 0,
                'avg_stake': 0,
                'total_stake': 0,
                'leagues_covered': 0,
                'top_market': 'None',
                'pending_count': 0
            }
        
        stats = {
            'total_opportunities': len(df),
            'avg_edge': df['edge_percentage'].mean(),
            'avg_confidence': df['confidence'].mean(),
            'avg_stake': df['stake'].mean(),
            'total_stake': df['stake'].sum(),
            'leagues_covered': df['league'].nunique(),
            'top_market': df['market'].mode().iloc[0] if not df['market'].mode().empty else 'None',
            'pending_count': len(df[df['status'] == 'pending'])
        }
        
        return stats

# Initialize data loader (no caching to see live data)
def get_data_loader():
    return RealFootballDataLoader()

data_loader = get_data_loader()

# Auto-refresh functionality  
auto_refresh = st.sidebar.checkbox("Auto Refresh (10 sec)", value=True)
if auto_refresh:
    time.sleep(10)
    st.rerun()

# Manual refresh button
if st.sidebar.button("🔄 Refresh Now"):
    st.rerun()

# Main dashboard
st.title("🏆 Real Football Champion Dashboard")
st.markdown("**Advanced Analytics & Pre-Match Betting Opportunities**")
st.markdown("---")

# Get current data
stats = data_loader.get_stats_summary()
recent_opportunities = data_loader.get_recent_opportunities(limit=15)

# Key metrics row
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "🎯 Total Opportunities",
        stats['total_opportunities'],
        f"+{stats['pending_count']} pending"
    )

with col2:
    st.metric(
        "📈 Average Edge",
        f"{stats['avg_edge']:.1f}%",
        "Mathematical advantage"
    )

with col3:
    st.metric(
        "🎯 Avg Confidence",
        f"{stats['avg_confidence']:.0f}/100",
        "AI confidence score"
    )

with col4:
    st.metric(
        "💰 Total Stakes",
        f"${stats['total_stake']:.2f}",
        f"${stats['avg_stake']:.2f} avg"
    )

with col5:
    st.metric(
        "⚽ Leagues",
        stats['leagues_covered'],
        f"Top: {stats['top_market']}"
    )

st.markdown("---")

# Main content tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Live Opportunities", 
    "📊 Analysis Dashboard",
    "⚽ Team Analytics", 
    "📋 Full History"
])

with tab1:
    st.header("🎯 Current Betting Opportunities")
    
    if recent_opportunities.empty:
        st.info("🔍 No opportunities found yet. System is analyzing upcoming matches...")
        st.markdown("**Status:** Real Football Champion is scanning for:")
        st.markdown("- Premier League fixtures")
        st.markdown("- La Liga matches") 
        st.markdown("- Serie A games")
        st.markdown("- Bundesliga matches")
        st.markdown("- Champions League")
        st.markdown("- Europa League")
    else:
        st.success(f"✅ Found {len(recent_opportunities)} opportunities!")
        
        # Display top opportunities
        for idx, row in recent_opportunities.head(10).iterrows():
            with st.expander(f"🎯 {row['home_team']} vs {row['away_team']} - {row['selection']} @ {row['odds']:.2f}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Edge", f"{row['edge_percentage']:.1f}%")
                    st.metric("Confidence", f"{row['confidence']}/100")
                    st.metric("Stake", f"${row['stake']:.2f}")
                
                with col2:
                    st.write("**Match Details:**")
                    st.write(f"🏟️ {row['home_team']} vs {row['away_team']}")
                    st.write(f"🏆 {row['league']}")
                    st.write(f"🎯 {row['market']}: {row['selection']}")
                    st.write(f"📊 Odds: {row['odds']:.2f}")
                
                with col3:
                    try:
                        if hasattr(row, 'analysis_parsed') and row['analysis_parsed']:
                            analysis = row['analysis_parsed']
                            st.write("**xG Analysis:**")
                            if isinstance(analysis, dict) and 'xg_prediction' in analysis:
                                xg = analysis['xg_prediction']
                                if isinstance(xg, dict):
                                    st.write(f"🏠 Home xG: {xg.get('home_xg', 0):.1f}")
                                    st.write(f"✈️ Away xG: {xg.get('away_xg', 0):.1f}")
                                    st.write(f"⚽ Total xG: {xg.get('total_xg', 0):.1f}")
                    except Exception as e:
                        st.write("**xG Analysis:** Processing...")

with tab2:
    st.header("📊 Analysis Dashboard")
    
    if not recent_opportunities.empty:
        # Edge distribution
        fig_edge = px.histogram(
            recent_opportunities, 
            x='edge_percentage',
            title="📈 Edge Distribution",
            nbins=20
        )
        fig_edge.update_layout(
            xaxis_title="Edge Percentage (%)",
            yaxis_title="Number of Opportunities"
        )
        st.plotly_chart(fig_edge, use_container_width=True)
        
        # Confidence vs Edge scatter
        fig_scatter = px.scatter(
            recent_opportunities,
            x='confidence',
            y='edge_percentage',
            size='stake',
            color='league',
            title="🎯 Confidence vs Edge Analysis",
            hover_data=['home_team', 'away_team', 'selection']
        )
        fig_scatter.update_layout(
            xaxis_title="Confidence Score",
            yaxis_title="Edge Percentage (%)"
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
        
        # Market distribution
        market_counts = recent_opportunities['selection'].value_counts()
        fig_pie = px.pie(
            values=market_counts.values,
            names=market_counts.index,
            title="🎯 Market Distribution"
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # League analysis
        league_stats = recent_opportunities.groupby('league').agg({
            'edge_percentage': 'mean',
            'confidence': 'mean',
            'stake': 'sum'
        }).round(2)
        
        st.subheader("🏆 League Performance")
        st.dataframe(league_stats, use_container_width=True)
    
    else:
        st.info("📊 Analysis will appear when opportunities are found")

with tab3:
    st.header("⚽ Team Analytics")
    
    if not recent_opportunities.empty:
        # Team frequency
        home_teams = recent_opportunities['home_team'].value_counts()
        away_teams = recent_opportunities['away_team'].value_counts()
        all_teams = pd.concat([home_teams, away_teams]).groupby(level=0).sum().sort_values(ascending=False)
        
        st.subheader("🎯 Most Analyzed Teams")
        fig_teams = px.bar(
            x=all_teams.head(15).index,
            y=all_teams.head(15).values,
            title="Teams with Most Opportunities"
        )
        fig_teams.update_layout(
            xaxis_title="Team",
            yaxis_title="Number of Opportunities"
        )
        st.plotly_chart(fig_teams, use_container_width=True)
        
        # xG analysis if available
        xg_data = []
        for idx, row in recent_opportunities.iterrows():
            try:
                if isinstance(row['analysis_parsed'], dict) and 'xg_prediction' in row['analysis_parsed']:
                    xg = row['analysis_parsed']['xg_prediction']
                    if isinstance(xg, dict):
                        xg_data.append({
                            'match': f"{row['home_team']} vs {row['away_team']}",
                            'home_xg': xg.get('home_xg', 0),
                            'away_xg': xg.get('away_xg', 0),
                            'total_xg': xg.get('total_xg', 0)
                        })
            except Exception:
                continue
        
        if xg_data:
            xg_df = pd.DataFrame(xg_data)
            
            st.subheader("🧠 xG Analysis")
            fig_xg = px.scatter(
                xg_df,
                x='home_xg',
                y='away_xg',
                size='total_xg',
                hover_data=['match'],
                title="Expected Goals Analysis"
            )
            fig_xg.update_layout(
                xaxis_title="Home Team xG",
                yaxis_title="Away Team xG"
            )
            st.plotly_chart(fig_xg, use_container_width=True)
    
    else:
        st.info("⚽ Team analytics will appear when opportunities are found")

with tab4:
    st.header("📋 Complete Opportunity History")
    
    if not recent_opportunities.empty:
        # Show all opportunities in a table
        display_df = recent_opportunities[['home_team', 'away_team', 'league', 
                                        'selection', 'odds', 'edge_percentage', 'confidence', 
                                        'stake', 'status']].copy()
        if 'datetime' in recent_opportunities.columns:
            display_df['datetime'] = recent_opportunities['datetime'].dt.strftime('%Y-%m-%d %H:%M')
            # Reorder columns to put datetime first
            cols = ['datetime'] + [col for col in display_df.columns if col != 'datetime']
            display_df = display_df[cols]
        
        st.dataframe(display_df, use_container_width=True)
        
        # Export functionality
        if st.button("📥 Export Opportunities"):
            try:
                export_dir = Path("exports")
                export_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"football_opportunities_{timestamp}.csv"
                
                display_df.to_csv(export_dir / filename, index=False)
                st.success(f"✅ Exported to exports/{filename}")
            except Exception as e:
                st.error(f"❌ Export failed: {e}")
    
    else:
        st.info("📋 Opportunity history will appear here")

# Footer with status
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**🏆 Real Football Champion**")
with col2:
    st.markdown(f"**📊 Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
with col3:
    st.markdown(f"**⚽ System Status:** {'🟢 Active' if stats['total_opportunities'] > 0 else '🟡 Scanning'}")