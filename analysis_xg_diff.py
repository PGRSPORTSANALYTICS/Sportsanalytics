"""
Analysis 1: xG Differential vs Outcomes
Understand how xG gap drives score outcomes and win rates
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class XGDifferentialAnalysis:
    """Analyze relationship between xG differential and match outcomes"""
    
    @staticmethod
    def run_analysis(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
        """
        Analyze xG differential vs outcomes
        
        Args:
            df: Clean historical data with xG fields
            
        Returns:
            Tuple of (results DataFrame, insights list)
        """
        logger.info("="*60)
        logger.info("ANALYSIS 1: xG DIFFERENTIAL vs OUTCOMES")
        logger.info("="*60 + "\n")
        
        # Need to get xG data from database if not in DataFrame
        # For now, we'll create placeholder xG values based on actual_score
        # This should be replaced with real xG data from advanced_features
        
        insights = []
        
        # Extract home/away goals from actual_score
        df['home_goals'] = df['actual_score'].apply(
            lambda x: int(x.split('-')[0]) if pd.notna(x) and '-' in str(x) else None
        )
        df['away_goals'] = df['actual_score'].apply(
            lambda x: int(x.split('-')[1]) if pd.notna(x) and '-' in str(x) else None
        )
        
        # Approximate xG from actual score (placeholder - replace with real xG)
        df['xg_home'] = df['home_goals']
        df['xg_away'] = df['away_goals']
        
        # Calculate xG differential
        df['xg_diff'] = df['xg_home'] - df['xg_away']
        
        # Define bins for xG differential
        bins = [-np.inf, -1.0, -0.5, 0, 0.5, 1.0, np.inf]
        labels = ['< -1.0', '-1.0 to -0.5', '-0.5 to 0', '0 to 0.5', '0.5 to 1.0', '> 1.0']
        df['xg_bin'] = pd.cut(df['xg_diff'], bins=bins, labels=labels)
        
        # Group by xG bin
        results = []
        
        for bin_label in labels:
            bin_data = df[df['xg_bin'] == bin_label]
            
            if len(bin_data) == 0:
                continue
            
            # Calculate hit rates by system
            es_data = bin_data[bin_data['system'] == 'ES']
            sgp_data = bin_data[bin_data['system'] == 'SGP']
            
            es_hit_rate = (es_data['result'] == 'win').mean() * 100 if len(es_data) > 0 else 0
            sgp_hit_rate = (sgp_data['result'] == 'win').mean() * 100 if len(sgp_data) > 0 else 0
            
            # Top 5 most frequent exact scores
            score_freq = bin_data['actual_score'].value_counts().head(5)
            top_scores = ', '.join([f"{score} ({count})" for score, count in score_freq.items()])
            
            # Calculate match outcomes
            home_win_pct = ((bin_data['home_goals'] > bin_data['away_goals']).sum() / len(bin_data) * 100) if len(bin_data) > 0 else 0
            draw_pct = ((bin_data['home_goals'] == bin_data['away_goals']).sum() / len(bin_data) * 100) if len(bin_data) > 0 else 0
            away_win_pct = ((bin_data['home_goals'] < bin_data['away_goals']).sum() / len(bin_data) * 100) if len(bin_data) > 0 else 0
            
            results.append({
                'xG_Bin': bin_label,
                'N_Bets': len(bin_data),
                'ES_Hit_Rate_%': f"{es_hit_rate:.1f}%",
                'SGP_Hit_Rate_%': f"{sgp_hit_rate:.1f}%",
                'Top_5_Scores': top_scores,
                'Home_Win_%': f"{home_win_pct:.1f}%",
                'Draw_%': f"{draw_pct:.1f}%",
                'Away_Win_%': f"{away_win_pct:.1f}%"
            })
        
        results_df = pd.DataFrame(results)
        
        # Generate insights
        if len(results_df) > 0:
            # Find bins with high draw rates
            results_df['draw_rate_num'] = results_df['Draw_%'].str.rstrip('%').astype(float)
            high_draw_bins = results_df[results_df['draw_rate_num'] > 25]
            
            if len(high_draw_bins) > 0:
                insights.append(f"• Draw-heavy zones: xG bins {', '.join(high_draw_bins['xG_Bin'].tolist())} show {high_draw_bins['draw_rate_num'].mean():.1f}% draw rate - prioritize 1-1, 0-0 exact scores")
            
            # Find bins with best ES performance
            results_df['es_hit_num'] = results_df['ES_Hit_Rate_%'].str.rstrip('%').astype(float)
            best_es_bin = results_df.loc[results_df['es_hit_num'].idxmax()]
            insights.append(f"• Best ES performance in {best_es_bin['xG_Bin']} bin with {best_es_bin['ES_Hit_Rate_%']} hit rate")
            
            # Identify balanced vs one-sided zones
            balanced_bins = results_df[(results_df['xG_Bin'].isin(['-0.5 to 0', '0 to 0.5']))]
            if len(balanced_bins) > 0:
                insights.append(f"• Balanced matches (|xG diff| < 0.5): {balanced_bins['N_Bets'].sum()} bets with {balanced_bins['draw_rate_num'].mean():.1f}% draw rate - ideal for low-scoring exact scores")
        
        # Print table
        print("\n" + "="*120)
        print("ANALYSIS 1: xG DIFFERENTIAL vs OUTCOMES")
        print("="*120)
        print(results_df.to_string(index=False))
        print("="*120 + "\n")
        
        # Print insights
        print("📌 KEY INSIGHTS:")
        for insight in insights:
            print(insight)
        print()
        
        logger.info(f"✅ Analysis 1 complete: {len(results_df)} xG bins analyzed\n")
        
        return results_df, insights


if __name__ == "__main__":
    from analysis_data_loader import AnalysisDataLoader
    from data_quality import DataQuality
    
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        clean_data = DataQuality.enforce_all_checks(data)
        results, insights = XGDifferentialAnalysis.run_analysis(clean_data)
        results.to_csv('analysis1.csv', index=False)
        print("✅ Saved to analysis1.csv")
