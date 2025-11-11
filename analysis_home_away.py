"""
Analysis 4: Home vs Away Bias
Detect model bias toward home teams
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HomeAwayBiasAnalysis:
    """Analyze model bias toward home vs away teams"""
    
    @staticmethod
    def determine_home_favored(row):
        """
        Determine if prediction favored home or away team
        
        For ES: Check if recommended score favors home
        For SGP: Use a proxy based on odds (lower odds = favorite)
        """
        if row['system'] == 'ES' and pd.notna(row.get('recommended_score')):
            try:
                home_rec, away_rec = map(int, row['recommended_score'].split('-'))
                if home_rec > away_rec:
                    return 'Home'
                elif away_rec > home_rec:
                    return 'Away'
                else:
                    return 'Draw'
            except:
                pass
        
        # Default: assume lower odds = home favored (proxy)
        # This is a simplification; ideally we'd parse the market description
        return 'Unknown'
    
    @staticmethod
    def run_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
        """
        Analyze home vs away bias in predictions
        
        Args:
            df: Clean historical data
            
        Returns:
            Tuple of (results DataFrame, insights list)
        """
        logger.info("="*60)
        logger.info("ANALYSIS 4: HOME vs AWAY BIAS")
        logger.info("="*60 + "\n")
        
        insights = []
        
        # Determine if each prediction favored home or away
        df['favored_side'] = df.apply(HomeAwayBiasAnalysis.determine_home_favored, axis=1)
        
        # Extract actual match outcomes
        df['home_goals'] = df['actual_score'].apply(
            lambda x: int(x.split('-')[0]) if pd.notna(x) and '-' in str(x) else None
        )
        df['away_goals'] = df['actual_score'].apply(
            lambda x: int(x.split('-')[1]) if pd.notna(x) and '-' in str(x) else None
        )
        
        df['actual_outcome'] = df.apply(
            lambda row: 'Home' if row['home_goals'] > row['away_goals'] 
            else ('Away' if row['away_goals'] > row['home_goals'] else 'Draw'),
            axis=1
        )
        
        # Analyze separately for ES and SGP
        results = []
        
        for system in ['ES', 'SGP']:
            system_data = df[df['system'] == system]
            
            for side in ['Home', 'Away', 'Draw']:
                side_data = system_data[system_data['favored_side'] == side]
                
                if len(side_data) == 0:
                    continue
                
                # Calculate metrics
                n_bets = len(side_data)
                hit_rate = (side_data['result'] == 'win').mean() * 100
                roi = side_data['roi'].mean()
                avg_odds = side_data['odds_placed'].mean()
                avg_model_p = side_data['model_p'].mean() * 100
                
                results.append({
                    'System': system,
                    'Favored_Side': side,
                    'N_Bets': n_bets,
                    'Hit_Rate_%': f"{hit_rate:.1f}%",
                    'ROI_%': f"{roi:.1f}%",
                    'Avg_Odds': f"{avg_odds:.2f}",
                    'Avg_Model_P_%': f"{avg_model_p:.1f}%"
                })
        
        results_df = pd.DataFrame(results)
        
        # Generate insights
        if len(results_df) > 0:
            results_df['roi_num'] = results_df['ROI_%'].str.rstrip('%').astype(float)
            
            for system in ['ES', 'SGP']:
                system_results = results_df[results_df['System'] == system]
                
                if len(system_results) == 0:
                    continue
                
                # Calculate ROI delta
                home_roi = system_results[system_results['Favored_Side'] == 'Home']['roi_num']
                away_roi = system_results[system_results['Favored_Side'] == 'Away']['roi_num']
                
                if len(home_roi) > 0 and len(away_roi) > 0:
                    delta = home_roi.iloc[0] - away_roi.iloc[0]
                    
                    if abs(delta) > 10:
                        if delta > 0:
                            insights.append(f"• {system} shows HOME BIAS: +{delta:.1f}% ROI delta (home performs better)")
                        else:
                            insights.append(f"• {system} shows AWAY BIAS: {delta:.1f}% ROI delta (away performs better)")
                    else:
                        insights.append(f"• {system} is WELL-BALANCED: {delta:+.1f}% ROI delta (minimal bias)")
                
                # Check if we should adjust away probabilities
                if len(away_roi) > 0 and away_roi.iloc[0] < -5:
                    insights.append(f"• {system} recommendation: Consider reducing away-side probabilities by 5-10% to improve calibration")
        
        # Print table
        print("\n" + "="*100)
        print("ANALYSIS 4: HOME vs AWAY BIAS")
        print("="*100)
        print(results_df.to_string(index=False))
        print("="*100 + "\n")
        
        # Print insights
        print("📌 KEY INSIGHTS:")
        for insight in insights:
            print(insight)
        print()
        
        logger.info(f"✅ Analysis 4 complete: {len(results_df)} bias groups analyzed\n")
        
        return results_df, insights


if __name__ == "__main__":
    from analysis_data_loader import AnalysisDataLoader
    from data_quality import DataQuality
    
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        clean_data = DataQuality.enforce_all_checks(data)
        results, insights = HomeAwayBiasAnalysis.run_analysis(clean_data)
        results.to_csv('analysis4.csv', index=False)
        print("✅ Saved to analysis4.csv")
