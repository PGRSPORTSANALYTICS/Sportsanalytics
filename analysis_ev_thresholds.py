"""
Analysis 2: EV Thresholds vs Realized Performance
Validate 8% vs 12% EV cutoffs and potential exploration range
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EVThresholdsAnalysis:
    """Analyze EV thresholds and their performance"""
    
    @staticmethod
    def run_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
        """
        Analyze EV thresholds vs realized performance
        
        Args:
            df: Clean historical data with EV calculated
            
        Returns:
            Tuple of (results DataFrame, insights list)
        """
        logger.info("="*60)
        logger.info("ANALYSIS 2: EV THRESHOLDS vs REALIZED PERFORMANCE")
        logger.info("="*60 + "\n")
        
        insights = []
        
        # Define EV buckets
        bins = [0, 5, 8, 10, 12, 15, 20, np.inf]
        labels = ['0-5%', '5-8%', '8-10%', '10-12%', '12-15%', '15-20%', '20%+']
        df['ev_bucket'] = pd.cut(df['ev_pct'], bins=bins, labels=labels)
        
        # Analyze separately for ES and SGP
        results = []
        
        for system in ['ES', 'SGP']:
            system_data = df[df['system'] == system]
            
            for bucket_label in labels:
                bucket_data = system_data[system_data['ev_bucket'] == bucket_label]
                
                if len(bucket_data) == 0:
                    continue
                
                # Calculate metrics
                n_bets = len(bucket_data)
                hit_rate = (bucket_data['result'] == 'win').mean() * 100
                roi = bucket_data['roi'].mean()
                avg_odds = bucket_data['odds_placed'].mean()
                avg_model_p = bucket_data['model_p'].mean() * 100
                brier_score = bucket_data['brier_score'].mean()
                
                results.append({
                    'System': system,
                    'EV_Bucket': bucket_label,
                    'N_Bets': n_bets,
                    'Hit_Rate_%': f"{hit_rate:.1f}%",
                    'ROI_%': f"{roi:.1f}%",
                    'Avg_Odds': f"{avg_odds:.2f}",
                    'Avg_Model_P_%': f"{avg_model_p:.1f}%",
                    'Brier_Score': f"{brier_score:.4f}"
                })
        
        results_df = pd.DataFrame(results)
        
        # Generate insights
        if len(results_df) > 0:
            # Extract numeric values for analysis
            results_df['roi_num'] = results_df['ROI_%'].str.rstrip('%').astype(float)
            results_df['n_bets_num'] = results_df['N_Bets']
            
            # Find best ROI bucket with sufficient volume (n >= 20)
            stable_buckets = results_df[results_df['n_bets_num'] >= 20]
            
            if len(stable_buckets) > 0:
                for system in ['ES', 'SGP']:
                    system_buckets = stable_buckets[stable_buckets['System'] == system]
                    if len(system_buckets) > 0:
                        best_bucket = system_buckets.loc[system_buckets['roi_num'].idxmax()]
                        insights.append(f"• {system} PRO cutoff: Recommend {best_bucket['EV_Bucket']} threshold (ROI: {best_bucket['ROI_%']}, n={best_bucket['N_Bets']})")
            
            # Analyze current 8% and 12% cutoffs
            for system in ['ES', 'SGP']:
                system_data = results_df[results_df['System'] == system]
                
                # Performance at 8-10% range
                range_8_10 = system_data[system_data['EV_Bucket'] == '8-10%']
                if len(range_8_10) > 0:
                    insights.append(f"• {system} at 8-10% EV: {range_8_10.iloc[0]['Hit_Rate_%']} hit rate, {range_8_10.iloc[0]['ROI_%']} ROI ({range_8_10.iloc[0]['N_Bets']} bets)")
                
                # Performance at 12%+ range
                range_12_plus = system_data[system_data['EV_Bucket'].isin(['12-15%', '15-20%', '20%+'])]
                if len(range_12_plus) > 0:
                    total_bets = range_12_plus['N_Bets'].sum()
                    avg_roi = range_12_plus['roi_num'].mean()
                    insights.append(f"• {system} at 12%+ EV: {avg_roi:.1f}% avg ROI ({total_bets} bets) - premium quality")
        
        # Print table
        print("\n" + "="*120)
        print("ANALYSIS 2: EV THRESHOLDS vs REALIZED PERFORMANCE")
        print("="*120)
        print(results_df.to_string(index=False))
        print("="*120 + "\n")
        
        # Print insights
        print("📌 KEY INSIGHTS:")
        for insight in insights:
            print(insight)
        print()
        
        logger.info(f"✅ Analysis 2 complete: {len(results_df)} EV buckets analyzed\n")
        
        return results_df, insights


if __name__ == "__main__":
    from analysis_data_loader import AnalysisDataLoader
    from data_quality import DataQuality
    
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        clean_data = DataQuality.enforce_all_checks(data)
        results, insights = EVThresholdsAnalysis.run_analysis(clean_data)
        results.to_csv('analysis2.csv', index=False)
        print("✅ Saved to analysis2.csv")
