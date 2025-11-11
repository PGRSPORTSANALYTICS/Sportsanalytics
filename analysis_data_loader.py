"""
Analysis Data Loader for Offline Historical Analysis
Extracts Exact Score and SGP predictions from PostgreSQL
"""

import pandas as pd
from db_helper import db_helper
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalysisDataLoader:
    """Load historical betting data from PostgreSQL for offline analysis"""
    
    def __init__(self):
        self.es_data = None
        self.sgp_data = None
    
    def load_exact_score_data(self):
        """
        Load Exact Score predictions from football_opportunities table
        
        Returns:
            DataFrame with standardized columns
        """
        logger.info("📊 Loading Exact Score historical data...")
        
        query = '''
            SELECT 
                timestamp,
                league,
                match_id,
                market,
                odds,
                outcome,
                home_team,
                away_team,
                match_date,
                actual_score,
                selection,
                stake,
                edge_percentage,
                confidence
            FROM football_opportunities
            WHERE market = 'exact_score'
            AND result IS NOT NULL
            AND outcome IN ('win', 'loss', 'won', 'lost')
            AND odds IS NOT NULL
        '''
        
        rows = db_helper.execute(query, fetch='all')
        
        if not rows:
            logger.warning("⚠️ No Exact Score data found")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=[
            'ts', 'league', 'match_id', 'market', 
            'odds_placed', 'result', 'home_team', 
            'away_team', 'kickoff', 'actual_score', 'recommended_score', 'stake',
            'edge_percentage', 'confidence'
        ])
        
        # Add system column
        df['system'] = 'ES'
        
        # Calculate model probability from odds (implied probability with edge)
        # model_p = 1 / odds + (edge / 100)
        df['model_p'] = (1.0 / df['odds_placed']) + (df['edge_percentage'].fillna(0) / 100.0)
        df['model_p'] = df['model_p'].clip(upper=1.0)  # Cap at 100%
        
        # Standardize result to win/loss
        df['result'] = df['result'].map({'win': 'win', 'won': 'win', 'loss': 'loss', 'lost': 'loss'})
        
        # Convert timestamp to datetime (handle ISO8601 format)
        df['kickoff'] = pd.to_datetime(df['kickoff'], format='ISO8601', errors='coerce')
        
        # Convert to binary for Brier score
        df['result_binary'] = (df['result'] == 'win').astype(int)
        
        logger.info(f"✅ Loaded {len(df)} Exact Score bets")
        self.es_data = df
        return df
    
    def load_sgp_data(self):
        """
        Load SGP predictions from sgp_predictions table (excluding MonsterSGP)
        
        Returns:
            DataFrame with standardized columns
        """
        logger.info("📊 Loading SGP historical data...")
        
        query = '''
            SELECT 
                timestamp,
                league,
                match_id,
                parlay_description,
                bookmaker_odds,
                parlay_probability,
                outcome,
                home_team,
                away_team,
                match_date,
                result,
                legs,
                stake
            FROM sgp_predictions
            WHERE result IS NOT NULL
            AND outcome IN ('win', 'loss')
            AND bookmaker_odds IS NOT NULL
            AND parlay_probability IS NOT NULL
        '''
        
        rows = db_helper.execute(query, fetch='all')
        
        if not rows:
            logger.warning("⚠️ No SGP data found")
            return pd.DataFrame()
        
        # Convert to DataFrame - MATCH query column order exactly
        df = pd.DataFrame(rows, columns=[
            'ts', 'league', 'match_id', 'parlay_description',
            'odds_placed', 'model_p', 'result', 'home_team',
            'away_team', 'kickoff', 'actual_score', 'legs', 'stake'
        ])
        
        # Add system column
        df['system'] = 'SGP'
        
        # Create market column from parlay_description
        df['market'] = df['parlay_description']
        
        # Filter out MonsterSGP (do this in pandas, not SQL, to avoid db_helper translation issues)
        monster_mask = df['parlay_description'].fillna('').str.contains('Monster|BEAST', case=False, na=False)
        initial_count = len(df)
        df = df[~monster_mask]
        filtered_count = initial_count - len(df)
        if filtered_count > 0:
            logger.info(f"   - Filtered out {filtered_count} MonsterSGP predictions")
        
        # Convert timestamp to datetime (handle ISO8601 format)
        df['kickoff'] = pd.to_datetime(df['kickoff'], format='ISO8601', errors='coerce')
        
        # Convert to binary for Brier score
        df['result_binary'] = (df['result'] == 'win').astype(int)
        
        logger.info(f"✅ Loaded {len(df)} SGP bets (MonsterSGP excluded)")
        self.sgp_data = df
        return df
    
    def load_all_data(self):
        """
        Load both ES and SGP data
        
        Returns:
            Combined DataFrame with all historical bets
        """
        es_df = self.load_exact_score_data()
        sgp_df = self.load_sgp_data()
        
        if es_df.empty and sgp_df.empty:
            logger.error("❌ No historical data available for analysis")
            return pd.DataFrame()
        
        # Combine datasets (align columns)
        # Fill missing columns with None
        all_columns = set(es_df.columns) | set(sgp_df.columns)
        for col in all_columns:
            if col not in es_df.columns:
                es_df[col] = None
            if col not in sgp_df.columns:
                sgp_df[col] = None
        
        combined = pd.concat([es_df, sgp_df], ignore_index=True)
        
        logger.info(f"\n✅ Total historical bets loaded: {len(combined)}")
        logger.info(f"   - Exact Score: {len(es_df)}")
        logger.info(f"   - SGP: {len(sgp_df)}")
        
        return combined


if __name__ == "__main__":
    # Test the loader
    loader = AnalysisDataLoader()
    data = loader.load_all_data()
    
    if not data.empty:
        print(f"\n📊 Data Sample:")
        print(data.head())
        print(f"\n📈 Data Shape: {data.shape}")
        print(f"\n📋 Columns: {list(data.columns)}")
        print(f"\n📊 System Distribution:")
        print(data['system'].value_counts())
