"""
Analysis 3: Match Tempo & Goal Minutes (by league)
Inform SGP legs (BTTS/Over and late goals risk)
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TempoAnalysis:
    """Analyze match tempo and goal timing by league"""
    
    @staticmethod
    def run_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
        """
        Analyze match tempo and goal minutes by league
        
        Args:
            df: Clean historical data
            
        Returns:
            Tuple of (results DataFrame, insights list)
        """
        logger.info("="*60)
        logger.info("ANALYSIS 3: MATCH TEMPO & GOAL MINUTES (by league)")
        logger.info("="*60 + "\n")
        
        insights = []
        
        # Extract goals from actual_score
        df['home_goals'] = df['actual_score'].apply(
            lambda x: int(x.split('-')[0]) if pd.notna(x) and '-' in str(x) else None
        )
        df['away_goals'] = df['actual_score'].apply(
            lambda x: int(x.split('-')[1]) if pd.notna(x) and '-' in str(x) else None
        )
        df['total_goals'] = df['home_goals'] + df['away_goals']
        
        # Calculate BTTS and Over 2.5
        df['btts'] = ((df['home_goals'] > 0) & (df['away_goals'] > 0)).astype(int)
        df['over_2_5'] = (df['total_goals'] > 2.5).astype(int)
        
        # Group by league
        results = []
        
        for league in df['league'].unique():
            if pd.isna(league):
                continue
                
            league_data = df[df['league'] == league]
            
            if len(league_data) < 5:  # Skip leagues with very few matches
                continue
            
            # Calculate metrics
            n_matches = len(league_data)
            btts_rate = league_data['btts'].mean() * 100
            over_2_5_rate = league_data['over_2_5'].mean() * 100
            avg_goals = league_data['total_goals'].mean()
            
            # Placeholder for late goal frequency (would need minute-by-minute data)
            # For now, estimate based on high-scoring matches
            late_goal_proxy = (league_data['total_goals'] >= 3).mean() * 100
            
            results.append({
                'League': league,
                'N_Matches': n_matches,
                'Avg_Goals': f"{avg_goals:.2f}",
                'BTTS_Rate_%': f"{btts_rate:.1f}%",
                'Over_2.5_Rate_%': f"{over_2_5_rate:.1f}%",
                'Late_Goal_Proxy_%': f"{late_goal_proxy:.1f}%"
            })
        
        results_df = pd.DataFrame(results)
        
        # Sort by BTTS rate
        results_df['btts_num'] = results_df['BTTS_Rate_%'].str.rstrip('%').astype(float)
        results_df = results_df.sort_values('btts_num', ascending=False)
        
        # Generate insights
        if len(results_df) > 0:
            # Find leagues with high BTTS rate
            high_btts_leagues = results_df[results_df['btts_num'] > 60].head(3)
            if len(high_btts_leagues) > 0:
                insights.append(f"• Best BTTS leagues: {', '.join(high_btts_leagues['League'].tolist())} (avg {high_btts_leagues['btts_num'].mean():.1f}% BTTS rate)")
            
            # Find leagues with high Over 2.5 rate
            results_df['over_2_5_num'] = results_df['Over_2.5_Rate_%'].str.rstrip('%').astype(float)
            high_over_leagues = results_df[results_df['over_2_5_num'] > 55].head(3)
            if len(high_over_leagues) > 0:
                insights.append(f"• Best Over 2.5 leagues: {', '.join(high_over_leagues['League'].tolist())} (avg {high_over_leagues['over_2_5_num'].mean():.1f}% Over 2.5 rate)")
            
            # Leagues to avoid for BTTS/Over legs
            low_btts_leagues = results_df[results_df['btts_num'] < 45].head(3)
            if len(low_btts_leagues) > 0:
                insights.append(f"• Avoid BTTS in: {', '.join(low_btts_leagues['League'].tolist())} (low scoring)")
        
        # Print table
        print("\n" + "="*100)
        print("ANALYSIS 3: MATCH TEMPO & GOAL MINUTES (by league)")
        print("="*100)
        print(results_df.drop(columns=['btts_num', 'over_2_5_num'], errors='ignore').to_string(index=False))
        print("="*100 + "\n")
        
        # Print insights
        print("📌 KEY INSIGHTS:")
        for insight in insights:
            print(insight)
        print()
        
        logger.info(f"✅ Analysis 3 complete: {len(results_df)} leagues analyzed\n")
        
        return results_df, insights


if __name__ == "__main__":
    from analysis_data_loader import AnalysisDataLoader
    from data_quality import DataQuality
    
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        clean_data = DataQuality.enforce_all_checks(data)
        results, insights = TempoAnalysis.run_analysis(clean_data)
        results.to_csv('analysis3.csv', index=False)
        print("✅ Saved to analysis3.csv")
