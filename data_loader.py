import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

class DataLoader:
    """Handles all data loading operations from the e-soccer bot's SQLite database."""
    
    def __init__(self, db_path: str = "data/esoccer.db"):
        self.db_path = Path(db_path)
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create database and tables if they don't exist."""
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # Create empty database with required tables
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS suggestions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts INTEGER, match_id TEXT, league TEXT, home TEXT, away TEXT,
                        market_t REAL, market_name TEXT, odds REAL, stake REAL, kelly REAL,
                        model_prob REAL, implied_prob REAL, edge_abs REAL, edge_rel REAL,
                        reason TEXT, score TEXT, elapsed INTEGER
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tickets (
                        id TEXT PRIMARY KEY, open_ts INTEGER, match_id TEXT, league TEXT,
                        home TEXT, away TEXT, market_t REAL, market_name TEXT, odds REAL, stake REAL,
                        is_settled INTEGER, win INTEGER, close_ts INTEGER, pnl REAL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pnl (
                        ts INTEGER PRIMARY KEY, bankroll REAL, open_risk REAL
                    )
                """)
                conn.commit()
    
    def _execute_query(self, query: str, params = None) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                return pd.read_sql_query(query, conn, params=params if params else [])
        except Exception as e:
            print(f"Database query error: {e}")
            return pd.DataFrame()
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get current bot statistics."""
        # Get latest bankroll
        pnl_df = self._execute_query("SELECT bankroll, open_risk FROM pnl ORDER BY ts DESC LIMIT 2")
        
        if len(pnl_df) == 0:
            current_bankroll = 1000.0  # Default
            bankroll_change = 0.0
            total_risk = 0.0
        else:
            current_bankroll = pnl_df.iloc[0]['bankroll']
            total_risk = pnl_df.iloc[0]['open_risk']
            if len(pnl_df) > 1:
                bankroll_change = current_bankroll - pnl_df.iloc[1]['bankroll']
            else:
                bankroll_change = 0.0
        
        # Get active bets count
        active_bets = self._execute_query("SELECT COUNT(*) as count FROM tickets WHERE is_settled = 0")
        active_bets_count = active_bets.iloc[0]['count'] if not active_bets.empty else 0
        
        # Get today's new bets
        today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        new_bets_today = self._execute_query(
            "SELECT COUNT(*) as count FROM tickets WHERE open_ts >= ?", 
            (today_start,)
        )
        new_bets_today_count = new_bets_today.iloc[0]['count'] if not new_bets_today.empty else 0
        
        # Get today's P&L
        settled_today = self._execute_query(
            "SELECT SUM(pnl) as total_pnl FROM tickets WHERE is_settled = 1 AND close_ts >= ?",
            (today_start,)
        )
        daily_pnl = settled_today.iloc[0]['total_pnl'] if not settled_today.empty and settled_today.iloc[0]['total_pnl'] is not None else 0.0
        
        # Get win rate
        settled_stats = self._execute_query(
            "SELECT COUNT(*) as total, SUM(win) as wins FROM tickets WHERE is_settled = 1"
        )
        if not settled_stats.empty and settled_stats.iloc[0]['total'] > 0:
            total_settled = settled_stats.iloc[0]['total']
            wins = settled_stats.iloc[0]['wins'] or 0
            win_rate = (wins / total_settled) * 100
        else:
            total_settled = 0
            win_rate = 0.0
        
        return {
            'bankroll': current_bankroll,
            'bankroll_change': bankroll_change,
            'total_risk': total_risk,
            'risk_percentage': (total_risk / current_bankroll * 100) if current_bankroll > 0 else 0,
            'active_bets': active_bets_count,
            'new_bets_today': new_bets_today_count,
            'daily_pnl': daily_pnl,
            'daily_pnl_percentage': (daily_pnl / current_bankroll * 100) if current_bankroll > 0 else 0,
            'win_rate': win_rate,
            'total_settled': total_settled
        }
    
    def get_active_tickets(self) -> pd.DataFrame:
        """Get all active (unsettled) tickets."""
        df = self._execute_query("""
            SELECT * FROM tickets 
            WHERE is_settled = 0 
            ORDER BY open_ts DESC
        """)
        
        if not df.empty:
            df['open_ts_formatted'] = pd.to_datetime(df['open_ts'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return df
    
    def get_tickets(self) -> pd.DataFrame:
        """Get all tickets."""
        df = self._execute_query("SELECT * FROM tickets ORDER BY open_ts DESC")
        
        if not df.empty:
            df['open_ts_formatted'] = pd.to_datetime(df['open_ts'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
            df['close_ts_formatted'] = pd.to_datetime(df['close_ts'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return df
    
    def get_suggestions(self, days: int = 7, market_filter: Optional[str] = None, min_edge: float = 0.0) -> pd.DataFrame:
        """Get suggestions with optional filtering."""
        cutoff_ts = int((datetime.now() - timedelta(days=days)).timestamp())
        
        query = "SELECT * FROM suggestions WHERE ts >= ?"
        params = [cutoff_ts]
        
        if market_filter:
            query += " AND market_name = ?"
            params.append(market_filter)
        
        if min_edge > 0:
            query += " AND edge_rel >= ?"
            params.append(min_edge)
        
        query += " ORDER BY ts DESC"
        
        df = self._execute_query(query, params)
        
        if not df.empty:
            df['ts_formatted'] = pd.to_datetime(df['ts'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
            df['match_title'] = df['home'] + ' vs ' + df['away']
        
        return df
    
    def get_recent_suggestions(self, limit: int = 10) -> pd.DataFrame:
        """Get most recent suggestions."""
        df = self._execute_query(f"SELECT * FROM suggestions ORDER BY ts DESC LIMIT {limit}")
        
        if not df.empty:
            df['ts_formatted'] = pd.to_datetime(df['ts'], unit='s').dt.strftime('%H:%M:%S')
            df['match_title'] = df['home'] + ' vs ' + df['away']
        
        return df
    
    def get_pnl_history(self) -> pd.DataFrame:
        """Get P&L history."""
        df = self._execute_query("SELECT * FROM pnl ORDER BY ts")
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['ts'], unit='s')
            df['date'] = df['timestamp'].dt.date
        
        return df
    
    def get_available_markets(self) -> List[str]:
        """Get list of all available markets from suggestions."""
        df = self._execute_query("SELECT DISTINCT market_name FROM suggestions ORDER BY market_name")
        return df['market_name'].tolist() if not df.empty else []
    
    def get_risk_metrics(self) -> Dict[str, float]:
        """Calculate current risk metrics."""
        # Get current bankroll and risk
        pnl_df = self._execute_query("SELECT bankroll, open_risk FROM pnl ORDER BY ts DESC LIMIT 1")
        
        if pnl_df.empty:
            return {
                'bankroll': 1000.0,
                'total_risk': 0.0,
                'risk_percentage': 0.0,
                'max_risk_per_match': 0.0
            }
        
        bankroll = pnl_df.iloc[0]['bankroll']
        total_risk = pnl_df.iloc[0]['open_risk']
        
        # Calculate risk per match
        active_tickets = self.get_active_tickets()
        if not active_tickets.empty:
            risk_per_match = active_tickets.groupby('match_id')['stake'].sum()
            max_risk_per_match = risk_per_match.max() if not risk_per_match.empty else 0.0
        else:
            max_risk_per_match = 0.0
        
        return {
            'bankroll': float(bankroll),
            'total_risk': float(total_risk),
            'risk_percentage': float((total_risk / bankroll * 100) if bankroll > 0 else 0),
            'max_risk_per_match': float(max_risk_per_match)
        }
