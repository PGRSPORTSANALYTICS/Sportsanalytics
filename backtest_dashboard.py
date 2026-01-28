"""
================================================================================
BACKTEST VISUALIZATION DASHBOARD
================================================================================
⚠️ BACKTEST ONLY - NOT LIVE RESULTS ⚠️

This dashboard displays isolated historical backtest results.
100% SEPARATED from live bets, learning data, and existing ROI tracking.
================================================================================
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
from datetime import datetime
import os

st.set_page_config(
    page_title="BACKTEST ONLY Dashboard",
    page_icon="⚠️",
    layout="wide"
)

BACKTEST_LABEL = "⚠️ BACKTEST ONLY - NOT LIVE RESULTS ⚠️"

st.markdown(f"""
<div style="background-color: #ff4444; color: white; padding: 20px; text-align: center; font-size: 24px; font-weight: bold; border-radius: 10px; margin-bottom: 20px;">
{BACKTEST_LABEL}
</div>
""", unsafe_allow_html=True)

st.title("Isolated Historical Backtest Dashboard")

st.markdown("""
**CRITICAL NOTICE:** This backtest is 100% SEPARATED from:
- Live bets and results
- Learning-phase data  
- Existing ROI dashboards
- All cumulative statistics

All data shown is for **risk analysis purposes only**.
""")

st.divider()

try:
    with open('backtest_equity_curves.json', 'r') as f:
        equity_data = json.load(f)
except FileNotFoundError:
    st.error("Backtest not run yet. Run `python3 backtest_engine.py` first.")
    st.stop()

try:
    with open('backtest_report.txt', 'r') as f:
        report_text = f.read()
except FileNotFoundError:
    report_text = None

st.header("Equity Curves (BACKTEST ONLY)")

fig = go.Figure()

colors = {
    'Cap20_SL-10u': '#00ff88',
    'Cap20_SL-15u': '#00cc66',
    'Cap20_SLNone': '#009944',
    'Cap30_SL-10u': '#0088ff',
    'Cap30_SL-15u': '#0066cc',
    'Cap30_SLNone': '#004499',
    'Cap50_SL-10u': '#ff8800',
    'Cap50_SL-15u': '#cc6600',
    'Cap50_SLNone': '#994400',
}

for scenario_name, curve in equity_data.items():
    if curve:
        df = pd.DataFrame(curve)
        color = colors.get(scenario_name, '#888888')
        fig.add_trace(go.Scatter(
            x=list(range(len(df))),
            y=df['cumulative_units'],
            mode='lines',
            name=scenario_name,
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{scenario_name}</b><br>Bet #%{{x}}<br>Units: %{{y:.1f}}<extra></extra>"
        ))

fig.update_layout(
    title="Cumulative Units by Scenario (BACKTEST ONLY)",
    xaxis_title="Bet Number",
    yaxis_title="Cumulative Units",
    height=500,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    template="plotly_dark",
    annotations=[
        dict(
            text="⚠️ BACKTEST DATA - NOT LIVE RESULTS",
            xref="paper", yref="paper",
            x=0.5, y=0.98,
            showarrow=False,
            font=dict(size=14, color="red"),
            bgcolor="rgba(255,255,255,0.8)"
        )
    ]
)

st.plotly_chart(fig, use_container_width=True)

st.header("Daily P/L Distribution")

cap30_curve = equity_data.get('Cap30_SL-10u', [])
if cap30_curve:
    df = pd.DataFrame(cap30_curve)
    df['date'] = pd.to_datetime(df['date'])
    
    daily = df.groupby('date')['cumulative_units'].last().reset_index()
    daily['daily_pnl'] = daily['cumulative_units'].diff().fillna(daily['cumulative_units'].iloc[0])
    
    fig2 = go.Figure()
    
    colors_bar = ['#00ff88' if x >= 0 else '#ff4444' for x in daily['daily_pnl']]
    
    fig2.add_trace(go.Bar(
        x=daily['date'],
        y=daily['daily_pnl'],
        marker_color=colors_bar,
        name='Daily P/L'
    ))
    
    fig2.update_layout(
        title="Daily P/L - Cap 30/day Scenario (BACKTEST ONLY)",
        xaxis_title="Date",
        yaxis_title="Daily Units",
        height=400,
        template="plotly_dark"
    )
    
    st.plotly_chart(fig2, use_container_width=True)

st.header("Scenario Comparison")

scenario_stats = []
for name, curve in equity_data.items():
    if curve:
        df = pd.DataFrame(curve)
        final_units = df['cumulative_units'].iloc[-1] if len(df) > 0 else 0
        
        peak = 0
        max_dd = 0
        for u in df['cumulative_units']:
            if u > peak:
                peak = u
            dd = peak - u
            if dd > max_dd:
                max_dd = dd
        
        scenario_stats.append({
            'Scenario': name,
            'Total Units': round(final_units, 1),
            'Max Drawdown': round(max_dd, 1),
            'Total Bets': len(df),
            'Risk Ratio': round(max_dd / final_units, 3) if final_units > 0 else 999
        })

stats_df = pd.DataFrame(scenario_stats)
stats_df = stats_df.sort_values('Risk Ratio')

st.dataframe(
    stats_df.style.background_gradient(subset=['Total Units'], cmap='Greens')
                  .background_gradient(subset=['Max Drawdown'], cmap='Reds'),
    use_container_width=True
)

st.header("Risk Metrics Visualization")

col1, col2 = st.columns(2)

with col1:
    fig3 = px.bar(
        stats_df.sort_values('Total Units', ascending=True),
        x='Total Units',
        y='Scenario',
        orientation='h',
        title='Total Units by Scenario (BACKTEST)',
        color='Total Units',
        color_continuous_scale='Greens'
    )
    fig3.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig3, use_container_width=True)

with col2:
    fig4 = px.bar(
        stats_df.sort_values('Max Drawdown', ascending=False),
        x='Max Drawdown',
        y='Scenario',
        orientation='h',
        title='Max Drawdown by Scenario (BACKTEST)',
        color='Max Drawdown',
        color_continuous_scale='Reds'
    )
    fig4.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig4, use_container_width=True)

st.header("Full Backtest Report")

if report_text:
    st.code(report_text, language="text")
else:
    st.warning("Report file not found.")

st.divider()

st.markdown(f"""
<div style="background-color: #ff4444; color: white; padding: 15px; text-align: center; font-size: 18px; font-weight: bold; border-radius: 10px; margin-top: 20px;">
{BACKTEST_LABEL}<br>
<span style="font-size: 14px; font-weight: normal;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Period: 2025-12-11 to 2026-01-27</span>
</div>
""", unsafe_allow_html=True)
