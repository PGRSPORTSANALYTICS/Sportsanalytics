# pgr_analytics.py
"""
PGR Advanced Analytics & Backtesting Module
Historical analysis, strategy backtesting, and performance insights
"""

from typing import Optional, List, Dict, Literal
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import streamlit as st

from pgr_theme import PGR_COLORS
from pgr_components import section_title


def inject_analytics_css():
    """Inject CSS for analytics components"""
    st.markdown(
        f"""
        <style>
        .pgr-analytics-card {{
            background: {PGR_COLORS["bg_alt"]};
            border: 1px solid {PGR_COLORS["border"]};
            border-radius: 12px;
            padding: 1.25rem;
            margin-bottom: 1rem;
        }}
        
        .pgr-analytics-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid {PGR_COLORS["border"]};
        }}
        
        .pgr-analytics-title {{
            font-size: 1rem;
            font-weight: 600;
            color: {PGR_COLORS["text"]};
        }}
        
        .pgr-analytics-subtitle {{
            font-size: 0.75rem;
            color: {PGR_COLORS["muted"]};
        }}
        
        .pgr-stat-row {{
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid {PGR_COLORS["border"]};
        }}
        
        .pgr-stat-row:last-child {{
            border-bottom: none;
        }}
        
        .pgr-stat-label {{
            color: {PGR_COLORS["muted"]};
            font-size: 0.85rem;
        }}
        
        .pgr-stat-value {{
            font-weight: 600;
            color: {PGR_COLORS["text"]};
        }}
        
        .pgr-stat-value.positive {{
            color: {PGR_COLORS["accent"]};
        }}
        
        .pgr-stat-value.negative {{
            color: {PGR_COLORS["danger"]};
        }}
        
        .pgr-progress-bar {{
            background: {PGR_COLORS["border"]};
            border-radius: 4px;
            height: 8px;
            overflow: hidden;
            margin-top: 0.5rem;
        }}
        
        .pgr-progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}
        
        .pgr-backtest-result {{
            background: linear-gradient(135deg, {PGR_COLORS["bg_alt"]} 0%, {PGR_COLORS["bg"]} 100%);
            border: 1px solid {PGR_COLORS["border"]};
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
        }}
        
        .pgr-backtest-roi {{
            font-size: 2.5rem;
            font-weight: 700;
            margin: 0.5rem 0;
        }}
        
        .pgr-insight-badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin: 0.25rem;
        }}
        
        .pgr-insight-badge.good {{
            background: rgba(0, 245, 157, 0.15);
            color: {PGR_COLORS["accent"]};
            border: 1px solid {PGR_COLORS["accent"]};
        }}
        
        .pgr-insight-badge.warning {{
            background: rgba(255, 181, 71, 0.15);
            color: {PGR_COLORS["warning"]};
            border: 1px solid {PGR_COLORS["warning"]};
        }}
        
        .pgr-insight-badge.bad {{
            background: rgba(255, 75, 107, 0.15);
            color: {PGR_COLORS["danger"]};
            border: 1px solid {PGR_COLORS["danger"]};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def performance_breakdown(
    df: pd.DataFrame,
    group_by: str = "product",
    title: str = "Performance Breakdown",
):
    """
    Show performance breakdown by category
    df should have: group_by column, 'won', 'stake', 'profit', 'odds'
    """
    section_title(title, icon="📊")
    
    if df.empty:
        st.caption("No data available")
        return
    
    grouped = df.groupby(group_by).agg({
        'won': ['sum', 'count'],
        'profit': 'sum',
        'stake': 'sum',
        'odds': 'mean',
    }).reset_index()
    
    grouped.columns = [group_by, 'wins', 'total', 'profit', 'staked', 'avg_odds']
    grouped['hit_rate'] = (grouped['wins'] / grouped['total'] * 100).round(1)
    grouped['roi'] = (grouped['profit'] / grouped['staked'] * 100).round(1)
    
    for _, row in grouped.iterrows():
        roi_class = "positive" if row['roi'] >= 0 else "negative"
        roi_color = PGR_COLORS["accent"] if row['roi'] >= 0 else PGR_COLORS["danger"]
        
        st.markdown(
            f"""
            <div class="pgr-analytics-card">
                <div class="pgr-analytics-header">
                    <div>
                        <div class="pgr-analytics-title">{row[group_by]}</div>
                        <div class="pgr-analytics-subtitle">{int(row['total'])} bets | Avg odds: {row['avg_odds']:.2f}</div>
                    </div>
                    <span class="pgr-stat-value {roi_class}">{row['roi']:+.1f}% ROI</span>
                </div>
                <div class="pgr-stat-row">
                    <span class="pgr-stat-label">Hit Rate</span>
                    <span class="pgr-stat-value">{row['hit_rate']:.1f}%</span>
                </div>
                <div class="pgr-progress-bar">
                    <div class="pgr-progress-fill" style="width: {min(row['hit_rate'], 100)}%; background: {roi_color};"></div>
                </div>
                <div class="pgr-stat-row" style="margin-top: 0.75rem;">
                    <span class="pgr-stat-label">Profit</span>
                    <span class="pgr-stat-value {roi_class}">{row['profit']:+,.0f} SEK</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def odds_range_analysis(
    df: pd.DataFrame,
    ranges: List[tuple] = [(1.0, 3.0), (3.0, 6.0), (6.0, 10.0), (10.0, 50.0)],
):
    """Analyze performance by odds ranges"""
    section_title("Performance by Odds Range", icon="🎰")
    
    if df.empty:
        st.caption("No data available")
        return
    
    results = []
    for low, high in ranges:
        mask = (df['odds'] >= low) & (df['odds'] < high)
        subset = df[mask]
        
        if len(subset) > 0:
            wins = subset['won'].sum()
            total = len(subset)
            profit = subset['profit'].sum()
            staked = subset['stake'].sum()
            
            results.append({
                'range': f"{low:.0f}-{high:.0f}x",
                'bets': total,
                'wins': wins,
                'hit_rate': wins / total * 100,
                'roi': profit / staked * 100 if staked > 0 else 0,
                'profit': profit,
            })
    
    cols = st.columns(len(results))
    for i, r in enumerate(results):
        with cols[i]:
            roi_color = PGR_COLORS["accent"] if r['roi'] >= 0 else PGR_COLORS["danger"]
            st.markdown(
                f"""
                <div class="pgr-analytics-card" style="text-align: center;">
                    <div style="font-size: 1.25rem; font-weight: 700; color: {PGR_COLORS["text"]};">{r['range']}</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]}; margin-bottom: 0.5rem;">{r['bets']} bets</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: {roi_color};">{r['roi']:+.1f}%</div>
                    <div style="font-size: 0.7rem; color: {PGR_COLORS["muted"]};">ROI</div>
                    <div style="margin-top: 0.5rem; font-size: 0.85rem;">Hit: {r['hit_rate']:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def streak_analysis(df: pd.DataFrame):
    """Analyze winning and losing streaks"""
    section_title("Streak Analysis", icon="🔥")
    
    if df.empty or 'won' not in df.columns:
        st.caption("No data available")
        return
    
    wins = df['won'].values
    
    current_streak = 0
    current_type = None
    max_win_streak = 0
    max_loss_streak = 0
    temp_streak = 0
    prev = None
    
    for w in wins:
        if prev is None:
            temp_streak = 1
            prev = w
        elif w == prev:
            temp_streak += 1
        else:
            if prev:
                max_win_streak = max(max_win_streak, temp_streak)
            else:
                max_loss_streak = max(max_loss_streak, temp_streak)
            temp_streak = 1
            prev = w
    
    if prev:
        max_win_streak = max(max_win_streak, temp_streak)
        current_streak = temp_streak
        current_type = "win"
    else:
        max_loss_streak = max(max_loss_streak, temp_streak)
        current_streak = temp_streak
        current_type = "loss"
    
    cols = st.columns(3)
    
    with cols[0]:
        st.markdown(
            f"""
            <div class="pgr-analytics-card" style="text-align: center;">
                <div style="font-size: 0.8rem; color: {PGR_COLORS["muted"]};">Current Streak</div>
                <div style="font-size: 2rem; font-weight: 700; color: {PGR_COLORS["accent"] if current_type == "win" else PGR_COLORS["danger"]};">
                    {current_streak}{"W" if current_type == "win" else "L"}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with cols[1]:
        st.markdown(
            f"""
            <div class="pgr-analytics-card" style="text-align: center;">
                <div style="font-size: 0.8rem; color: {PGR_COLORS["muted"]};">Best Win Streak</div>
                <div style="font-size: 2rem; font-weight: 700; color: {PGR_COLORS["accent"]};">
                    {max_win_streak}W
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with cols[2]:
        st.markdown(
            f"""
            <div class="pgr-analytics-card" style="text-align: center;">
                <div style="font-size: 0.8rem; color: {PGR_COLORS["muted"]};">Worst Loss Streak</div>
                <div style="font-size: 2rem; font-weight: 700; color: {PGR_COLORS["danger"]};">
                    {max_loss_streak}L
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def backtest_results(
    total_bets: int,
    wins: int,
    roi: float,
    profit: float,
    avg_odds: float,
    period: str = "Last 30 days",
):
    """Display backtest results summary"""
    section_title("Backtest Results", icon="🔬")
    
    roi_color = PGR_COLORS["accent"] if roi >= 0 else PGR_COLORS["danger"]
    hit_rate = wins / total_bets * 100 if total_bets > 0 else 0
    
    st.markdown(
        f"""
        <div class="pgr-backtest-result">
            <div style="font-size: 0.85rem; color: {PGR_COLORS["muted"]};">{period}</div>
            <div class="pgr-backtest-roi" style="color: {roi_color};">{roi:+.1f}%</div>
            <div style="font-size: 0.9rem; color: {PGR_COLORS["muted"]};">Return on Investment</div>
            
            <div style="display: flex; justify-content: center; gap: 2rem; margin-top: 1.5rem;">
                <div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: {PGR_COLORS["text"]};">{total_bets}</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Total Bets</div>
                </div>
                <div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: {PGR_COLORS["accent"]};">{wins}</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Wins</div>
                </div>
                <div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: {PGR_COLORS["text"]};">{hit_rate:.1f}%</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Hit Rate</div>
                </div>
                <div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: {PGR_COLORS["text"]};">{avg_odds:.2f}x</div>
                    <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Avg Odds</div>
                </div>
            </div>
            
            <div style="margin-top: 1.5rem;">
                <span style="font-size: 1.25rem; font-weight: 600; color: {roi_color};">{profit:+,.0f} SEK</span>
                <div style="font-size: 0.75rem; color: {PGR_COLORS["muted"]};">Net Profit</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def strategy_filters():
    """Show strategy filter controls for backtesting"""
    section_title("Strategy Filters", icon="⚙️")
    
    col1, col2 = st.columns(2)
    
    with col1:
        min_ev = st.slider("Min EV %", 0.0, 20.0, 3.0, 0.5)
        min_odds = st.slider("Min Odds", 1.0, 20.0, 5.0, 0.5)
        
    with col2:
        max_odds = st.slider("Max Odds", 5.0, 50.0, 15.0, 1.0)
        min_confidence = st.slider("Min Confidence %", 0, 100, 50, 5)
    
    products = st.multiselect(
        "Products",
        ["Exact Score", "SGP", "Women 1X2", "Value Singles"],
        default=["Exact Score", "SGP"],
    )
    
    return {
        "min_ev": min_ev,
        "min_odds": min_odds,
        "max_odds": max_odds,
        "min_confidence": min_confidence,
        "products": products,
    }


def insights_panel(insights: List[Dict]):
    """
    Display AI-generated insights
    
    insights format:
    [
        {"type": "good", "text": "High hit rate on La Liga matches"},
        {"type": "warning", "text": "Consider higher EV threshold"},
        {"type": "bad", "text": "Low performance on high odds bets"},
    ]
    """
    section_title("AI Insights", icon="🧠")
    
    if not insights:
        st.caption("Not enough data for insights")
        return
    
    badges_html = ""
    for insight in insights:
        badges_html += f'<span class="pgr-insight-badge {insight["type"]}">{insight["text"]}</span>'
    
    st.markdown(
        f"""
        <div class="pgr-analytics-card">
            {badges_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def cumulative_roi_chart(df: pd.DataFrame):
    """Display cumulative ROI over time"""
    section_title("Cumulative ROI", icon="📈")
    
    if df.empty:
        st.caption("No data available")
        return
    
    df = df.sort_values('date').copy()
    df['cumulative_profit'] = df['profit'].cumsum()
    df['cumulative_stake'] = df['stake'].cumsum()
    df['cumulative_roi'] = (df['cumulative_profit'] / df['cumulative_stake'] * 100).round(2)
    
    chart_df = df[['date', 'cumulative_roi']].set_index('date')
    st.line_chart(chart_df, height=300)


def monthly_performance(df: pd.DataFrame):
    """Show monthly performance breakdown"""
    section_title("Monthly Performance", icon="📅")
    
    if df.empty or 'date' not in df.columns:
        st.caption("No data available")
        return
    
    df = df.copy()
    df['month'] = pd.to_datetime(df['date']).dt.to_period('M').astype(str)
    
    monthly = df.groupby('month').agg({
        'won': ['sum', 'count'],
        'profit': 'sum',
        'stake': 'sum',
    }).reset_index()
    
    monthly.columns = ['month', 'wins', 'bets', 'profit', 'staked']
    monthly['roi'] = (monthly['profit'] / monthly['staked'] * 100).round(1)
    monthly['hit_rate'] = (monthly['wins'] / monthly['bets'] * 100).round(1)
    
    for _, row in monthly.iterrows():
        roi_color = PGR_COLORS["accent"] if row['roi'] >= 0 else PGR_COLORS["danger"]
        st.markdown(
            f"""
            <div class="pgr-stat-row">
                <span class="pgr-stat-label">{row['month']}</span>
                <span>
                    <span style="margin-right: 1rem;">{int(row['bets'])} bets</span>
                    <span style="margin-right: 1rem;">{row['hit_rate']:.1f}% hit</span>
                    <span style="font-weight: 700; color: {roi_color};">{row['roi']:+.1f}% ROI</span>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
