"""
Analysis 5: League ROI & Stability
Find best/worst performing leagues (pockets)
"""

import pandas as pd
import numpy as np
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LeagueROIAnalysis:
    """Analyze league-level performance and stability"""
    
    @staticmethod
    def run_analysis(df: pd.DataFrame, min_bets: int = 30) -> Tuple[pd.DataFrame, list]:
        """
        Analyze ROI and stability by league
        
        Args:
            df: Clean historical data
            min_bets: Minimum number of bets for a league to be included
            
        Returns:
            Tuple of (results DataFrame, insights list)
        """
        logger.info("="*60)
        logger.info("ANALYSIS 5: LEAGUE ROI & STABILITY")
        logger.info("="*60 + "\n")
        
        insights = []
        
        # Group by league
        results = []
        
        for league in df['league'].unique():
            if pd.isna(league):
                continue
                
            league_data = df[df['league'] == league]
            
            # Skip leagues with insufficient data
            if len(league_data) < min_bets:
                continue
            
            # Overall metrics
            n_bets = len(league_data)
            hit_rate = (league_data['result'] == 'win').mean() * 100
            roi = league_data['roi'].mean()
            avg_odds = league_data['odds_placed'].mean()
            
            # Split by system
            es_data = league_data[league_data['system'] == 'ES']
            sgp_data = league_data[league_data['system'] == 'SGP']
            
            es_count = len(es_data)
            sgp_count = len(sgp_data)
            es_roi = es_data['roi'].mean() if len(es_data) > 0 else 0
            sgp_roi = sgp_data['roi'].mean() if len(sgp_data) > 0 else 0
            
            results.append({
                'League': league,
                'N_Bets': n_bets,
                'Hit_Rate_%': f"{hit_rate:.1f}%",
                'ROI_%': f"{roi:.1f}%",
                'Avg_Odds': f"{avg_odds:.2f}",
                'ES_Count': es_count,
                'ES_ROI_%': f"{es_roi:.1f}%",
                'SGP_Count': sgp_count,
                'SGP_ROI_%': f"{sgp_roi:.1f}%"
            })
        
        results_df = pd.DataFrame(results)
        
        # Sort by ROI
        results_df['roi_num'] = results_df['ROI_%'].str.rstrip('%').astype(float)
        results_df = results_df.sort_values('roi_num', ascending=False)
        
        # Generate insights
        if len(results_df) > 0:
            # Find top performing leagues
            top_leagues = results_df.head(3)
            insights.append(f"• TOP PERFORMING LEAGUES: {', '.join(top_leagues['League'].tolist())} (avg ROI: {top_leagues['roi_num'].mean():.1f}%)")
            
            # Find underperforming leagues
            bottom_leagues = results_df.tail(3)
            if bottom_leagues['roi_num'].mean() < -5:
                insights.append(f"• UNDERPERFORMING LEAGUES: {', '.join(bottom_leagues['League'].tolist())} (avg ROI: {bottom_leagues['roi_num'].mean():.1f}%) - consider downweighting or skipping")
            
            # Find leagues with consistent positive ROI
            consistent_leagues = results_df[(results_df['roi_num'] > 5) & (results_df['N_Bets'] >= 50)]
            if len(consistent_leagues) > 0:
                insights.append(f"• STABLE WINNERS ({min_bets}+ bets, ROI > 5%): {', '.join(consistent_leagues['League'].tolist())} - upweight these leagues")
            
            # Check for leagues with strong ES vs SGP differences
            results_df['es_roi_num'] = results_df['ES_ROI_%'].str.rstrip('%').astype(float)
            results_df['sgp_roi_num'] = results_df['SGP_ROI_%'].str.rstrip('%').astype(float)
            
            # Find leagues where ES performs significantly better
            es_strong = results_df[(results_df['es_roi_num'] - results_df['sgp_roi_num'] > 15) & (results_df['ES_Count'] >= 20)]
            if len(es_strong) > 0:
                insights.append(f"• ES-FAVORABLE LEAGUES: {', '.join(es_strong['League'].tolist())} (ES outperforms SGP by 15%+)")
            
            # Find leagues where SGP performs significantly better
            sgp_strong = results_df[(results_df['sgp_roi_num'] - results_df['es_roi_num'] > 15) & (results_df['SGP_Count'] >= 20)]
            if len(sgp_strong) > 0:
                insights.append(f"• SGP-FAVORABLE LEAGUES: {', '.join(sgp_strong['League'].tolist())} (SGP outperforms ES by 15%+)")
        
        # Print table
        print("\n" + "="*120)
        print("ANALYSIS 5: LEAGUE ROI & STABILITY")
        print("="*120)
        print(results_df.drop(columns=['roi_num', 'es_roi_num', 'sgp_roi_num'], errors='ignore').to_string(index=False))
        print("="*120 + "\n")
        
        # Print insights
        print("📌 KEY INSIGHTS:")
        for insight in insights:
            print(insight)
        print()
        
        logger.info(f"✅ Analysis 5 complete: {len(results_df)} leagues analyzed\n")
        
        return results_df, insights


if __name__ == "__main__":
    from analysis_data_loader import AnalysisDataLoader
    from data_quality import DataQuality
    
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        clean_data = DataQuality.enforce_all_checks(data)
        results, insights = LeagueROIAnalysis.run_analysis(clean_data)
        results.to_csv('analysis5.csv', index=False)
        print("✅ Saved to analysis5.csv")
