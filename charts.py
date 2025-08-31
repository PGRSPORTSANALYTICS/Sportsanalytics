import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any

class ChartGenerator:
    """Generates all charts and visualizations for the dashboard."""
    
    def __init__(self):
        self.colors = {
            'primary': '#1f77b4',
            'success': '#2ca02c',
            'danger': '#d62728',
            'warning': '#ff7f0e',
            'info': '#17a2b8',
            'secondary': '#6c757d'
        }
    
    def create_bankroll_chart(self, pnl_df: pd.DataFrame) -> go.Figure:
        """Create bankroll progression chart."""
        if pnl_df.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="No bankroll data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            fig.update_layout(title="Bankroll Progression", height=400)
            return fig
        
        fig = go.Figure()
        
        # Add bankroll line
        fig.add_trace(go.Scatter(
            x=pnl_df['timestamp'],
            y=pnl_df['bankroll'],
            mode='lines+markers',
            name='Bankroll',
            line=dict(color=self.colors['primary'], width=3),
            marker=dict(size=6),
            hovertemplate='<b>%{x}</b><br>Bankroll: $%{y:.2f}<extra></extra>'
        ))
        
        # Add trend line if we have enough data
        if len(pnl_df) > 2:
            # Simple linear regression for trend
            x_numeric = np.arange(len(pnl_df))
            z = np.polyfit(x_numeric, pnl_df['bankroll'], 1)
            p = np.poly1d(z)
            
            fig.add_trace(go.Scatter(
                x=pnl_df['timestamp'],
                y=p(x_numeric),
                mode='lines',
                name='Trend',
                line=dict(color=self.colors['secondary'], width=2, dash='dash'),
                hovertemplate='Trend: $%{y:.2f}<extra></extra>'
            ))
        
        fig.update_layout(
            title="💰 Bankroll Progression",
            xaxis_title="Time",
            yaxis_title="Bankroll ($)",
            height=400,
            hovermode='x unified',
            showlegend=True
        )
        
        return fig
    
    def create_pnl_distribution(self, settled_tickets: pd.DataFrame) -> go.Figure:
        """Create P&L distribution histogram."""
        if settled_tickets.empty or 'pnl' not in settled_tickets.columns:
            fig = go.Figure()
            fig.add_annotation(
                text="No settled bets available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            fig.update_layout(title="P&L Distribution", height=400)
            return fig
        
        # Create histogram
        fig = go.Figure()
        
        wins = settled_tickets[settled_tickets['pnl'] > 0]['pnl']
        losses = settled_tickets[settled_tickets['pnl'] <= 0]['pnl']
        
        if not wins.empty:
            fig.add_trace(go.Histogram(
                x=wins,
                name='Wins',
                marker_color=self.colors['success'],
                opacity=0.7,
                nbinsx=20
            ))
        
        if not losses.empty:
            fig.add_trace(go.Histogram(
                x=losses,
                name='Losses',
                marker_color=self.colors['danger'],
                opacity=0.7,
                nbinsx=20
            ))
        
        fig.update_layout(
            title="📊 P&L Distribution",
            xaxis_title="P&L ($)",
            yaxis_title="Frequency",
            height=400,
            barmode='overlay',
            showlegend=True
        )
        
        return fig
    
    def create_daily_performance_chart(self, pnl_df: pd.DataFrame) -> go.Figure:
        """Create daily performance chart."""
        if pnl_df.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="No performance data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            fig.update_layout(title="Daily Performance", height=400)
            return fig
        
        # Calculate daily changes
        pnl_df = pnl_df.copy()
        pnl_df['daily_change'] = pnl_df['bankroll'].diff()
        pnl_df = pnl_df.dropna()
        
        if pnl_df.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="Insufficient data for daily performance",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            fig.update_layout(title="Daily Performance", height=400)
            return fig
        
        # Color bars based on performance
        colors = [self.colors['success'] if x >= 0 else self.colors['danger'] for x in pnl_df['daily_change']]
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=pnl_df['timestamp'],
            y=pnl_df['daily_change'],
            marker_color=colors,
            name='Daily P&L',
            hovertemplate='<b>%{x}</b><br>Daily Change: $%{y:.2f}<extra></extra>'
        ))
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        
        fig.update_layout(
            title="📅 Daily Performance",
            xaxis_title="Date",
            yaxis_title="Daily Change ($)",
            height=400,
            showlegend=False
        )
        
        return fig
    
    def calculate_performance_metrics(self, settled_tickets: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        if settled_tickets.empty:
            return {
                'total_bets': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'total_staked': 0.0,
                'roi': 0.0,
                'avg_stake': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'max_win': 0.0,
                'max_loss': 0.0
            }
        
        total_bets = len(settled_tickets)
        wins = len(settled_tickets[settled_tickets['pnl'] > 0])
        losses = total_bets - wins
        win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
        
        total_pnl = settled_tickets['pnl'].sum()
        total_staked = settled_tickets['stake'].sum()
        roi = (total_pnl / total_staked * 100) if total_staked > 0 else 0
        
        avg_stake = settled_tickets['stake'].mean()
        
        winning_bets = settled_tickets[settled_tickets['pnl'] > 0]
        losing_bets = settled_tickets[settled_tickets['pnl'] <= 0]
        
        avg_win = winning_bets['pnl'].mean() if not winning_bets.empty else 0
        avg_loss = losing_bets['pnl'].mean() if not losing_bets.empty else 0
        
        gross_profit = winning_bets['pnl'].sum() if not winning_bets.empty else 0
        gross_loss = abs(losing_bets['pnl'].sum()) if not losing_bets.empty else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
        
        max_win = settled_tickets['pnl'].max()
        max_loss = settled_tickets['pnl'].min()
        
        return {
            'total_bets': total_bets,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_staked': total_staked,
            'roi': roi,
            'avg_stake': avg_stake,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_win': max_win,
            'max_loss': max_loss
        }
    
    def create_risk_exposure_chart(self, active_tickets: pd.DataFrame) -> go.Figure:
        """Create risk exposure visualization."""
        if active_tickets.empty:
            fig = go.Figure()
            fig.add_annotation(
                text="No active positions",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False, font=dict(size=16)
            )
            fig.update_layout(title="Risk Exposure", height=400)
            return fig
        
        # Group by market type
        market_risk = active_tickets.groupby('market_name')['stake'].sum().reset_index()
        
        fig = px.pie(
            market_risk,
            values='stake',
            names='market_name',
            title="🎯 Risk Exposure by Market",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='<b>%{label}</b><br>Risk: $%{value:.2f}<br>Percentage: %{percent}<extra></extra>'
        )
        
        fig.update_layout(height=400)
        
        return fig
