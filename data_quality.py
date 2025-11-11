"""
Data Quality Module for Offline Analysis
Handles cleaning, deduplication, and Brier score calculation
"""

import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataQuality:
    """Data quality enforcement for historical analysis"""
    
    @staticmethod
    def clean_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove missing data and enforce quality checks
        
        Args:
            df: Raw historical data
            
        Returns:
            Cleaned DataFrame
        """
        logger.info(f"🧹 Starting data quality checks on {len(df)} rows...")
        
        initial_count = len(df)
        
        # Drop rows with missing critical fields
        required_fields = ['odds_placed', 'model_p', 'result', 'league', 'match_id']
        df = df.dropna(subset=required_fields)
        logger.info(f"   ✓ Removed {initial_count - len(df)} rows with missing required fields")
        
        # Filter out invalid probabilities
        df = df[(df['model_p'] > 0) & (df['model_p'] <= 1)]
        logger.info(f"   ✓ Filtered to valid probabilities (0 < p ≤ 1)")
        
        # Filter out invalid odds
        df = df[df['odds_placed'] >= 1.01]
        logger.info(f"   ✓ Filtered to valid odds (≥ 1.01)")
        
        # Standardize result values
        df['result'] = df['result'].str.lower()
        df = df[df['result'].isin(['win', 'loss'])]
        logger.info(f"   ✓ Standardized result values")
        
        logger.info(f"✅ Data cleaning complete: {len(df)} rows remaining\n")
        
        return df
    
    @staticmethod
    def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove duplicate bets based on match_id, market, and odds
        
        Args:
            df: DataFrame with potential duplicates
            
        Returns:
            Deduplicated DataFrame
        """
        logger.info(f"🔍 Checking for duplicates in {len(df)} rows...")
        
        initial_count = len(df)
        
        # Deduplicate based on match_id, market, odds_placed, and timestamp
        # Keep the first occurrence (earliest timestamp)
        df = df.sort_values('ts')
        df = df.drop_duplicates(subset=['match_id', 'market', 'odds_placed'], keep='first')
        
        removed = initial_count - len(df)
        logger.info(f"✅ Removed {removed} duplicate rows\n")
        
        return df
    
    @staticmethod
    def calculate_brier_score(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Brier score for each prediction
        Brier Score = (p - y)^2 where y ∈ {0,1}
        
        Args:
            df: DataFrame with model_p and result_binary columns
            
        Returns:
            DataFrame with brier_score column added
        """
        logger.info(f"📊 Calculating Brier scores...")
        
        if 'result_binary' not in df.columns:
            df['result_binary'] = (df['result'] == 'win').astype(int)
        
        df['brier_score'] = (df['model_p'] - df['result_binary']) ** 2
        
        mean_brier = df['brier_score'].mean()
        logger.info(f"✅ Brier scores calculated. Mean: {mean_brier:.4f}\n")
        
        return df
    
    @staticmethod
    def calculate_ev(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Expected Value (EV) for each bet
        EV = model_p * (odds - 1) - (1 - model_p)
        
        Args:
            df: DataFrame with model_p and odds_placed columns
            
        Returns:
            DataFrame with ev and ev_pct columns added
        """
        logger.info(f"💰 Calculating Expected Value...")
        
        df['ev'] = df['model_p'] * (df['odds_placed'] - 1) - (1 - df['model_p'])
        df['ev_pct'] = df['ev'] * 100
        
        logger.info(f"✅ EV calculated. Mean EV: {df['ev_pct'].mean():.2f}%\n")
        
        return df
    
    @staticmethod
    def calculate_roi(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate ROI for each bet
        ROI = (payout - stake) / stake
        
        Args:
            df: DataFrame with stake, odds_placed, and result columns
            
        Returns:
            DataFrame with roi column added
        """
        logger.info(f"📈 Calculating ROI...")
        
        # Ensure stake column exists, default to 1 if missing
        if 'stake' not in df.columns or df['stake'].isna().all():
            df['stake'] = 1.0
        
        # Calculate payout: win = stake * odds, loss = 0
        df['payout'] = df.apply(
            lambda row: row['stake'] * row['odds_placed'] if row['result'] == 'win' else 0,
            axis=1
        )
        
        # Calculate ROI
        df['roi'] = ((df['payout'] - df['stake']) / df['stake']) * 100
        
        logger.info(f"✅ ROI calculated. Mean ROI: {df['roi'].mean():.2f}%\n")
        
        return df
    
    @staticmethod
    def enforce_all_checks(df: pd.DataFrame) -> pd.DataFrame:
        """
        Run all data quality checks in sequence
        
        Args:
            df: Raw historical data
            
        Returns:
            Fully cleaned and enriched DataFrame
        """
        logger.info("="*60)
        logger.info("🔧 RUNNING ALL DATA QUALITY CHECKS")
        logger.info("="*60 + "\n")
        
        df = DataQuality.clean_data(df)
        df = DataQuality.deduplicate(df)
        df = DataQuality.calculate_brier_score(df)
        df = DataQuality.calculate_ev(df)
        df = DataQuality.calculate_roi(df)
        
        logger.info("="*60)
        logger.info(f"✅ ALL CHECKS COMPLETE: {len(df)} high-quality rows ready")
        logger.info("="*60 + "\n")
        
        return df


if __name__ == "__main__":
    # Test with sample data
    from analysis_data_loader import AnalysisDataLoader
    
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        clean_data = DataQuality.enforce_all_checks(data)
        print(f"\n📊 Final Data Shape: {clean_data.shape}")
        print(f"\n📋 Final Columns: {list(clean_data.columns)}")
