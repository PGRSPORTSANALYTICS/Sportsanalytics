"""
Backtest Analyzer - Full Analysis of Historical Predictions
Analyzes EV thresholds, odds ranges, and league performance using settled bets
"""

import pandas as pd
import numpy as np
from db_helper import DatabaseHelper
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

USD_TO_SEK = 10.8

class BacktestAnalyzer:
    """Analyzes historical betting performance across multiple dimensions"""
    
    def __init__(self):
        self.sgp_data = None
        self.basketball_data = None
        self.training_data = None
        self._load_data()
    
    def _load_data(self):
        """Load all settled predictions from database"""
        try:
            sgp_rows = DatabaseHelper.execute("""
                SELECT 
                    league, bookmaker_odds as odds, ev_percentage as ev, 
                    status, stake, match_date_only as bet_date
                FROM sgp_predictions 
                WHERE status IN ('won', 'lost') AND bookmaker_odds IS NOT NULL
            """, fetch='all')
            
            if sgp_rows:
                self.sgp_data = pd.DataFrame(sgp_rows, columns=[
                    'league', 'odds', 'ev', 'status', 'stake', 'bet_date'
                ])
                self.sgp_data['profit_sek'] = self.sgp_data.apply(
                    lambda x: x['stake'] * x['odds'] - x['stake'] if x['status'] == 'won' else -x['stake'], 
                    axis=1
                )
                self.sgp_data['won'] = self.sgp_data['status'] == 'won'
            else:
                self.sgp_data = pd.DataFrame()
            
            bball_rows = DatabaseHelper.execute("""
                SELECT 
                    league, market, odds::float as odds, ev_percentage::float as ev, 
                    confidence::float as confidence, status, is_parlay,
                    created_at::date as bet_date
                FROM basketball_predictions 
                WHERE status IN ('won', 'lost') AND odds IS NOT NULL
            """, fetch='all')
            
            if bball_rows:
                self.basketball_data = pd.DataFrame(bball_rows, columns=[
                    'league', 'market', 'odds', 'ev', 'confidence', 'status', 'is_parlay', 'bet_date'
                ])
                base_stake = 130
                self.basketball_data['stake'] = self.basketball_data.apply(
                    lambda x: base_stake * 0.8 if x['is_parlay'] else base_stake,
                    axis=1
                )
                self.basketball_data['profit_sek'] = self.basketball_data.apply(
                    lambda x: x['stake'] * x['odds'] - x['stake'] if x['status'] == 'won' else -x['stake'], 
                    axis=1
                )
                self.basketball_data['won'] = self.basketball_data['status'] == 'won'
            else:
                self.basketball_data = pd.DataFrame()
            
            training_rows = DatabaseHelper.execute("""
                SELECT 
                    analysis_type, league, edge_percentage as ev,
                    model_probability, actual_score, prediction_correct,
                    created_at
                FROM training_data 
                WHERE actual_score IS NOT NULL
            """, fetch='all')
            
            if training_rows:
                self.training_data = pd.DataFrame(training_rows, columns=[
                    'analysis_type', 'league', 'ev', 'model_prob', 'actual_score', 
                    'prediction_correct', 'created_at'
                ])
            else:
                self.training_data = pd.DataFrame()
                
            logger.info(f"Loaded SGP: {len(self.sgp_data)}, Basketball: {len(self.basketball_data)}, Training: {len(self.training_data)}")
            
        except Exception as e:
            logger.error(f"Error loading backtest data: {e}")
            self.sgp_data = pd.DataFrame()
            self.basketball_data = pd.DataFrame()
            self.training_data = pd.DataFrame()
    
    def analyze_ev_thresholds(self, product='all'):
        """Analyze performance by EV threshold buckets"""
        results = []
        ev_thresholds = [
            (0, 5, "0-5%"),
            (5, 10, "5-10%"),
            (10, 20, "10-20%"),
            (20, 50, "20-50%"),
            (50, 200, "50%+")
        ]
        
        datasets = []
        if product in ['all', 'sgp'] and len(self.sgp_data) > 0:
            df = self.sgp_data.copy()
            df['product'] = 'SGP'
            datasets.append(df)
        if product in ['all', 'basketball'] and len(self.basketball_data) > 0:
            df = self.basketball_data.copy()
            df['product'] = 'Basketball'
            datasets.append(df)
        
        if not datasets:
            return pd.DataFrame()
        
        combined = pd.concat(datasets, ignore_index=True)
        
        for min_ev, max_ev, label in ev_thresholds:
            subset = combined[(combined['ev'] >= min_ev) & (combined['ev'] < max_ev)]
            if len(subset) > 0:
                total_bets = len(subset)
                wins = subset['won'].sum()
                total_stake = subset['stake'].sum()
                total_profit = subset['profit_sek'].sum()
                hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
                
                results.append({
                    'EV Range': label,
                    'Bets': total_bets,
                    'Wins': int(wins),
                    'Hit Rate': f"{hit_rate:.1f}%",
                    'Staked (SEK)': f"{total_stake:,.0f}",
                    'Profit (SEK)': f"{total_profit:+,.0f}",
                    'ROI': f"{roi:+.1f}%",
                    '_roi_sort': roi
                })
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values('_roi_sort', ascending=False).drop('_roi_sort', axis=1)
        return df
    
    def analyze_odds_ranges(self, product='all'):
        """Analyze performance by odds ranges"""
        results = []
        odds_ranges = [
            (1.0, 2.0, "1.00-2.00"),
            (2.0, 3.0, "2.00-3.00"),
            (3.0, 4.0, "3.00-4.00"),
            (4.0, 5.0, "4.00-5.00"),
            (5.0, 6.0, "5.00-6.00"),
            (6.0, 10.0, "6.00-10.00"),
            (10.0, 50.0, "10.00+")
        ]
        
        datasets = []
        if product in ['all', 'sgp'] and len(self.sgp_data) > 0:
            df = self.sgp_data.copy()
            df['product'] = 'SGP'
            datasets.append(df)
        if product in ['all', 'basketball'] and len(self.basketball_data) > 0:
            df = self.basketball_data.copy()
            df['product'] = 'Basketball'
            datasets.append(df)
        
        if not datasets:
            return pd.DataFrame()
        
        combined = pd.concat(datasets, ignore_index=True)
        
        for min_odds, max_odds, label in odds_ranges:
            subset = combined[(combined['odds'] >= min_odds) & (combined['odds'] < max_odds)]
            if len(subset) > 0:
                total_bets = len(subset)
                wins = subset['won'].sum()
                total_stake = subset['stake'].sum()
                total_profit = subset['profit_sek'].sum()
                hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
                breakeven = (1 / ((min_odds + max_odds) / 2)) * 100
                edge_vs_breakeven = hit_rate - breakeven
                
                results.append({
                    'Odds Range': label,
                    'Bets': total_bets,
                    'Wins': int(wins),
                    'Hit Rate': f"{hit_rate:.1f}%",
                    'Breakeven': f"{breakeven:.1f}%",
                    'Edge': f"{edge_vs_breakeven:+.1f}%",
                    'Profit (SEK)': f"{total_profit:+,.0f}",
                    'ROI': f"{roi:+.1f}%",
                    '_roi_sort': roi
                })
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values('_roi_sort', ascending=False).drop('_roi_sort', axis=1)
        return df
    
    def analyze_by_league(self, product='all'):
        """Analyze performance by league"""
        results = []
        
        datasets = []
        if product in ['all', 'sgp'] and len(self.sgp_data) > 0:
            df = self.sgp_data.copy()
            df['product'] = 'SGP'
            datasets.append(df)
        if product in ['all', 'basketball'] and len(self.basketball_data) > 0:
            df = self.basketball_data.copy()
            df['product'] = 'Basketball'
            datasets.append(df)
        
        if not datasets:
            return pd.DataFrame()
        
        combined = pd.concat(datasets, ignore_index=True)
        
        for league in combined['league'].unique():
            subset = combined[combined['league'] == league]
            if len(subset) >= 3:
                total_bets = len(subset)
                wins = subset['won'].sum()
                total_stake = subset['stake'].sum()
                total_profit = subset['profit_sek'].sum()
                hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
                avg_odds = subset['odds'].mean()
                
                results.append({
                    'League': league,
                    'Bets': total_bets,
                    'Wins': int(wins),
                    'Hit Rate': f"{hit_rate:.1f}%",
                    'Avg Odds': f"{avg_odds:.2f}",
                    'Profit (SEK)': f"{total_profit:+,.0f}",
                    'ROI': f"{roi:+.1f}%",
                    '_roi_sort': roi
                })
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values('_roi_sort', ascending=False).drop('_roi_sort', axis=1)
        return df
    
    def analyze_by_market(self, product='basketball'):
        """Analyze basketball performance by market type"""
        if len(self.basketball_data) == 0:
            return pd.DataFrame()
        
        results = []
        df = self.basketball_data.copy()
        
        for market in df['market'].unique():
            subset = df[df['market'] == market]
            if len(subset) >= 3:
                total_bets = len(subset)
                wins = subset['won'].sum()
                total_stake = subset['stake'].sum()
                total_profit = subset['profit_sek'].sum()
                hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
                avg_odds = subset['odds'].mean()
                avg_ev = subset['ev'].mean()
                
                results.append({
                    'Market': market,
                    'Bets': total_bets,
                    'Wins': int(wins),
                    'Hit Rate': f"{hit_rate:.1f}%",
                    'Avg Odds': f"{avg_odds:.2f}",
                    'Avg EV': f"{avg_ev:.1f}%",
                    'Profit (SEK)': f"{total_profit:+,.0f}",
                    'ROI': f"{roi:+.1f}%",
                    '_roi_sort': roi
                })
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values('_roi_sort', ascending=False).drop('_roi_sort', axis=1)
        return df
    
    def analyze_confidence_thresholds(self, product='basketball'):
        """Analyze basketball performance by confidence levels"""
        if len(self.basketball_data) == 0:
            return pd.DataFrame()
        
        results = []
        conf_ranges = [
            (50, 55, "50-55%"),
            (55, 60, "55-60%"),
            (60, 65, "60-65%"),
            (65, 70, "65-70%"),
            (70, 80, "70-80%"),
            (80, 100, "80%+")
        ]
        
        df = self.basketball_data.copy()
        
        for min_conf, max_conf, label in conf_ranges:
            subset = df[(df['confidence'] >= min_conf) & (df['confidence'] < max_conf)]
            if len(subset) > 0:
                total_bets = len(subset)
                wins = subset['won'].sum()
                total_stake = subset['stake'].sum()
                total_profit = subset['profit_sek'].sum()
                hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
                avg_odds = subset['odds'].mean()
                
                results.append({
                    'Confidence': label,
                    'Bets': total_bets,
                    'Wins': int(wins),
                    'Hit Rate': f"{hit_rate:.1f}%",
                    'Avg Odds': f"{avg_odds:.2f}",
                    'Profit (SEK)': f"{total_profit:+,.0f}",
                    'ROI': f"{roi:+.1f}%",
                    '_roi_sort': roi
                })
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values('_roi_sort', ascending=False).drop('_roi_sort', axis=1)
        return df
    
    def get_sgp_odds_analysis(self):
        """Detailed SGP odds range analysis"""
        if len(self.sgp_data) == 0:
            return pd.DataFrame()
        
        results = []
        odds_ranges = [
            (2.0, 3.0, "2.0-3.0"),
            (3.0, 4.0, "3.0-4.0"),
            (4.0, 5.0, "4.0-5.0"),
            (5.0, 6.0, "5.0-6.0"),
            (6.0, 7.0, "6.0-7.0"),
        ]
        
        df = self.sgp_data.copy()
        
        for min_odds, max_odds, label in odds_ranges:
            subset = df[(df['odds'] >= min_odds) & (df['odds'] < max_odds)]
            if len(subset) > 0:
                total_bets = len(subset)
                wins = subset['won'].sum()
                total_stake = subset['stake'].sum()
                total_profit = subset['profit_sek'].sum()
                hit_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
                required_hit = (1 / ((min_odds + max_odds) / 2)) * 100
                
                results.append({
                    'Odds Range': label,
                    'Bets': total_bets,
                    'Wins': int(wins),
                    'Hit Rate': f"{hit_rate:.1f}%",
                    'Required': f"{required_hit:.1f}%",
                    'Profit (SEK)': f"{total_profit:+,.0f}",
                    'ROI': f"{roi:+.1f}%",
                    '_roi_sort': roi
                })
        
        df = pd.DataFrame(results)
        if len(df) > 0:
            df = df.sort_values('_roi_sort', ascending=False).drop('_roi_sort', axis=1)
        return df
    
    def get_summary_stats(self):
        """Get overall summary statistics"""
        stats = {}
        
        if len(self.sgp_data) > 0:
            df = self.sgp_data
            stats['sgp'] = {
                'total_bets': len(df),
                'wins': int(df['won'].sum()),
                'hit_rate': df['won'].mean() * 100,
                'total_stake': df['stake'].sum(),
                'total_profit': df['profit_sek'].sum(),
                'roi': (df['profit_sek'].sum() / df['stake'].sum() * 100) if df['stake'].sum() > 0 else 0,
                'avg_odds': df['odds'].mean(),
                'avg_ev': df['ev'].mean()
            }
        
        if len(self.basketball_data) > 0:
            df = self.basketball_data
            singles = df[~df['is_parlay']]
            parlays = df[df['is_parlay']]
            
            stats['basketball_singles'] = {
                'total_bets': len(singles),
                'wins': int(singles['won'].sum()),
                'hit_rate': singles['won'].mean() * 100 if len(singles) > 0 else 0,
                'total_stake': singles['stake'].sum(),
                'total_profit': singles['profit_sek'].sum(),
                'roi': (singles['profit_sek'].sum() / singles['stake'].sum() * 100) if singles['stake'].sum() > 0 else 0,
                'avg_odds': singles['odds'].mean() if len(singles) > 0 else 0,
                'avg_ev': singles['ev'].mean() if len(singles) > 0 else 0
            }
            
            stats['basketball_parlays'] = {
                'total_bets': len(parlays),
                'wins': int(parlays['won'].sum()),
                'hit_rate': parlays['won'].mean() * 100 if len(parlays) > 0 else 0,
                'total_stake': parlays['stake'].sum(),
                'total_profit': parlays['profit_sek'].sum(),
                'roi': (parlays['profit_sek'].sum() / parlays['stake'].sum() * 100) if parlays['stake'].sum() > 0 else 0,
                'avg_odds': parlays['odds'].mean() if len(parlays) > 0 else 0,
                'avg_ev': parlays['ev'].mean() if len(parlays) > 0 else 0
            }
        
        return stats
    
    def get_daily_performance(self, days=14):
        """Get daily P&L for the last N days"""
        results = []
        
        datasets = []
        if len(self.sgp_data) > 0:
            df = self.sgp_data.copy()
            df['product'] = 'SGP'
            df['date'] = pd.to_datetime(df['bet_date'])
            datasets.append(df)
        if len(self.basketball_data) > 0:
            df = self.basketball_data.copy()
            df['product'] = 'Basketball'
            df['date'] = pd.to_datetime(df['bet_date'])
            datasets.append(df)
        
        if not datasets:
            return pd.DataFrame()
        
        combined = pd.concat(datasets, ignore_index=True)
        
        cutoff = datetime.now() - timedelta(days=days)
        combined = combined[combined['date'] >= cutoff]
        
        daily = combined.groupby(combined['date'].dt.date).agg({
            'profit_sek': 'sum',
            'stake': 'sum',
            'won': 'sum'
        }).reset_index()
        
        daily.columns = ['Date', 'Profit (SEK)', 'Staked', 'Wins']
        daily['Bets'] = combined.groupby(combined['date'].dt.date).size().values
        daily['ROI'] = (daily['Profit (SEK)'] / daily['Staked'] * 100).round(1)
        daily = daily.sort_values('Date', ascending=False)
        
        return daily


if __name__ == "__main__":
    analyzer = BacktestAnalyzer()
    
    print("\n=== SUMMARY STATS ===")
    stats = analyzer.get_summary_stats()
    for product, data in stats.items():
        print(f"\n{product.upper()}:")
        print(f"  Bets: {data['total_bets']}, Wins: {data['wins']}, Hit Rate: {data['hit_rate']:.1f}%")
        print(f"  Profit: {data['total_profit']:+,.0f} SEK, ROI: {data['roi']:+.1f}%")
    
    print("\n=== EV THRESHOLD ANALYSIS ===")
    print(analyzer.analyze_ev_thresholds().to_string(index=False))
    
    print("\n=== ODDS RANGE ANALYSIS ===")
    print(analyzer.analyze_odds_ranges().to_string(index=False))
    
    print("\n=== LEAGUE ANALYSIS ===")
    print(analyzer.analyze_by_league().to_string(index=False))
