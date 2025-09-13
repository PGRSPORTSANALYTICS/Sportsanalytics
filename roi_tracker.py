#!/usr/bin/env python3
"""
ROI Progress Tracking System
============================

Comprehensive ROI tracking system to monitor progress toward 70% ROI target 
for tips monetization. Features real-time calculations, milestone tracking,
and business readiness indicators.

Features:
- Real-time ROI calculations across multiple timeframes
- Progress tracking toward 70% ROI target
- Milestone alerts (50%, 60%, 70% thresholds)
- Performance consistency monitoring (7+ days sustained performance)
- Business readiness indicators
- Historical trend analysis
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ROITracker:
    """
    Advanced ROI tracking system with milestone monitoring and business readiness indicators.
    """
    
    def __init__(self, db_path: str = 'data/real_football.db'):
        self.db_path = db_path
        self.target_roi = 70.0  # Target ROI for monetization
        self.consistency_days = 7  # Days needed to maintain target for business readiness
        self._ensure_roi_tables()
    
    def _ensure_roi_tables(self):
        """Create ROI tracking tables if they don't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # ROI snapshot history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roi_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE,
                    daily_roi REAL,
                    weekly_roi REAL,
                    monthly_roi REAL,
                    total_roi REAL,
                    total_stakes REAL,
                    total_profit_loss REAL,
                    win_rate REAL,
                    total_bets INTEGER,
                    settled_bets INTEGER,
                    milestone_50_reached INTEGER DEFAULT 0,
                    milestone_60_reached INTEGER DEFAULT 0,
                    milestone_70_reached INTEGER DEFAULT 0,
                    consistency_days INTEGER DEFAULT 0,
                    business_ready INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # ROI milestones tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roi_milestones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    milestone_type TEXT,
                    milestone_value REAL,
                    achieved_date TEXT,
                    achieved_roi REAL,
                    total_bets INTEGER,
                    consistency_days INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            # Tables initialized - removed noisy logging
            
        except Exception as e:
            logger.error(f"Error creating ROI tables: {e}")
            raise
    
    def calculate_current_roi(self) -> Dict:
        """
        Calculate comprehensive ROI metrics for all timeframes
        Returns detailed ROI analysis with progress indicators
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get all settled bets - CRITICAL: Use settlement date for ROI calculations
            settled_query = '''
                SELECT stake, profit_loss, outcome, 
                       datetime(timestamp, 'unixepoch') as bet_time,
                       datetime(settled_timestamp, 'unixepoch') as settled_time,
                       DATE(datetime(settled_timestamp, 'unixepoch')) as settled_date
                FROM football_opportunities 
                WHERE outcome IS NOT NULL 
                AND outcome != ''
                AND settled_timestamp IS NOT NULL
                ORDER BY settled_timestamp DESC
            '''
            
            df = pd.read_sql_query(settled_query, conn)
            conn.close()
            
            if df.empty:
                return self._empty_roi_metrics()
            
            # Calculate overall metrics
            total_stakes = df['stake'].sum()
            total_profit_loss = df['profit_loss'].sum()
            total_roi = (total_profit_loss / total_stakes * 100) if total_stakes > 0 else 0
            win_rate = (len(df[df['outcome'] == 'win']) / len(df) * 100) if len(df) > 0 else 0
            
            # Calculate timeframe-specific ROIs
            today = date.today()
            
            # Daily ROI (today) - using settlement date for accurate timeframes
            daily_df = df[df['settled_date'] == str(today)]
            daily_roi = self._calculate_timeframe_roi(daily_df)
            
            # Weekly ROI (last 7 days)
            week_ago = today - timedelta(days=7)
            weekly_df = df[df['settled_date'] >= str(week_ago)]
            weekly_roi = self._calculate_timeframe_roi(weekly_df)
            
            # Monthly ROI (last 30 days)
            month_ago = today - timedelta(days=30)
            monthly_df = df[df['settled_date'] >= str(month_ago)]
            monthly_roi = self._calculate_timeframe_roi(monthly_df)
            
            # Progress toward target
            progress_percentage = min((total_roi / self.target_roi) * 100, 100) if total_roi > 0 else 0
            
            # Milestone checks
            milestones = self._check_milestones(total_roi, len(df))
            
            # Consistency tracking
            consistency_info = self._check_consistency(df)
            
            # Business readiness
            business_ready = self._assess_business_readiness(
                total_roi, consistency_info['consistent_days'], len(df), win_rate
            )
            
            roi_metrics = {
                'timestamp': datetime.now().isoformat(),
                'total_roi': round(total_roi, 2),
                'daily_roi': round(daily_roi, 2),
                'weekly_roi': round(weekly_roi, 2),
                'monthly_roi': round(monthly_roi, 2),
                'total_stakes': round(total_stakes, 2),
                'total_profit_loss': round(total_profit_loss, 2),
                'win_rate': round(win_rate, 2),
                'total_bets': len(df),
                'settled_bets': len(df),
                'progress_percentage': round(progress_percentage, 2),
                'target_roi': self.target_roi,
                'milestones': milestones,
                'consistency': consistency_info,
                'business_ready': business_ready,
                'roi_status': self._get_roi_status(total_roi),
                'next_milestone': self._get_next_milestone(total_roi)
            }
            
            # Save snapshot
            self._save_roi_snapshot(roi_metrics)
            
            return roi_metrics
            
        except Exception as e:
            logger.error(f"Error calculating ROI: {e}")
            return self._empty_roi_metrics()
    
    def _calculate_timeframe_roi(self, df: pd.DataFrame) -> float:
        """Calculate ROI for a specific timeframe DataFrame"""
        if df.empty:
            return 0.0
        
        total_stakes = df['stake'].sum()
        total_profit_loss = df['profit_loss'].sum()
        
        return (total_profit_loss / total_stakes * 100) if total_stakes > 0 else 0.0
    
    def _check_milestones(self, current_roi: float, total_bets: int) -> Dict:
        """Check which ROI milestones have been reached"""
        milestones = {
            '50_percent': {
                'reached': current_roi >= 50.0,
                'progress': min((current_roi / 50.0) * 100, 100),
                'remaining': max(50.0 - current_roi, 0)
            },
            '60_percent': {
                'reached': current_roi >= 60.0,
                'progress': min((current_roi / 60.0) * 100, 100),
                'remaining': max(60.0 - current_roi, 0)
            },
            '70_percent': {
                'reached': current_roi >= 70.0,
                'progress': min((current_roi / 70.0) * 100, 100),
                'remaining': max(70.0 - current_roi, 0)
            }
        }
        
        # Record milestone achievements
        for milestone, data in milestones.items():
            if data['reached'] and total_bets >= 10:  # Minimum bets for milestone validity
                self._record_milestone_achievement(milestone, current_roi, total_bets)
        
        return milestones
    
    def _check_consistency(self, df: pd.DataFrame) -> Dict:
        """Check ROI consistency over recent days - FIXED to use settlement dates"""
        if df.empty:
            return {'consistent_days': 0, 'daily_rois': [], 'is_consistent': False, 'consistency_percentage': 0}
        
        # Group by settlement date and calculate daily ROIs
        df['settled_date'] = pd.to_datetime(df['settled_date'])
        daily_groups = df.groupby('settled_date').agg({
            'stake': 'sum',
            'profit_loss': 'sum'
        }).reset_index()
        
        daily_groups['daily_roi'] = (daily_groups['profit_loss'] / daily_groups['stake'] * 100)
        
        # Check recent days for consistency (last N days with settlements)
        recent_days = daily_groups.tail(self.consistency_days)
        consistent_days = len(recent_days[recent_days['daily_roi'] >= self.target_roi])
        
        is_consistent = consistent_days >= self.consistency_days
        
        return {
            'consistent_days': consistent_days,
            'required_days': self.consistency_days,
            'daily_rois': recent_days['daily_roi'].tolist(),
            'is_consistent': is_consistent,
            'consistency_percentage': (consistent_days / self.consistency_days * 100) if self.consistency_days > 0 else 0,
            'days_with_settlements': len(daily_groups)
        }
    
    def _assess_business_readiness(self, roi: float, consistent_days: int, total_bets: int, win_rate: float) -> Dict:
        """Assess if the business is ready for monetization"""
        criteria = {
            'roi_target': roi >= self.target_roi,
            'consistency': consistent_days >= self.consistency_days,
            'minimum_bets': total_bets >= 50,  # Minimum bets for statistical significance
            'win_rate': win_rate >= 55.0,  # Minimum win rate
        }
        
        all_criteria_met = all(criteria.values())
        
        readiness_score = sum(criteria.values()) / len(criteria) * 100
        
        recommendations = []
        if not criteria['roi_target']:
            remaining_roi = self.target_roi - roi
            recommendations.append(f"Need {remaining_roi:.1f}% more ROI to reach {self.target_roi}% target")
        
        if not criteria['consistency']:
            remaining_days = self.consistency_days - consistent_days
            recommendations.append(f"Need {remaining_days} more days of consistent {self.target_roi}%+ ROI")
        
        if not criteria['minimum_bets']:
            remaining_bets = 50 - total_bets
            recommendations.append(f"Need {remaining_bets} more settled bets for statistical significance")
        
        if not criteria['win_rate']:
            remaining_wr = 55.0 - win_rate
            recommendations.append(f"Need {remaining_wr:.1f}% higher win rate")
        
        return {
            'is_ready': all_criteria_met,
            'readiness_score': round(readiness_score, 1),
            'criteria': criteria,
            'recommendations': recommendations,
            'estimated_days_to_ready': self._estimate_days_to_ready(criteria, roi, consistent_days)
        }
    
    def _estimate_days_to_ready(self, criteria: Dict, current_roi: float, consistent_days: int) -> Optional[int]:
        """Estimate days until business ready"""
        if criteria['roi_target'] and criteria['consistency']:
            return 0  # Ready now
        
        if not criteria['roi_target']:
            # Need to improve ROI first
            return None  # Cannot estimate without trend data
        
        if not criteria['consistency']:
            return self.consistency_days - consistent_days
        
        return None
    
    def _record_milestone_achievement(self, milestone: str, roi: float, total_bets: int):
        """Record milestone achievement in database"""
        try:
            milestone_value = float(milestone.split('_')[0])
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if milestone already recorded for this date
            cursor.execute('''
                SELECT COUNT(*) FROM roi_milestones 
                WHERE milestone_type = ? AND milestone_value = ? AND achieved_date = ?
            ''', (milestone, milestone_value, date.today().isoformat()))
            
            if cursor.fetchone()[0] == 0:  # Milestone not yet recorded for today
                cursor.execute('''
                    INSERT INTO roi_milestones 
                    (milestone_type, milestone_value, achieved_date, achieved_roi, total_bets, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    milestone, 
                    milestone_value, 
                    date.today().isoformat(), 
                    roi, 
                    total_bets,
                    f"Reached {milestone_value}% ROI milestone with {total_bets} total bets"
                ))
                
                conn.commit()
                # Milestone logged - removed noisy celebration logging
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error recording milestone: {e}")
    
    def _save_roi_snapshot(self, metrics: Dict):
        """Save daily ROI snapshot"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            today = date.today().isoformat()
            
            # Insert or update today's snapshot
            cursor.execute('''
                INSERT OR REPLACE INTO roi_snapshots 
                (date, daily_roi, weekly_roi, monthly_roi, total_roi, total_stakes, 
                 total_profit_loss, win_rate, total_bets, settled_bets, 
                 milestone_50_reached, milestone_60_reached, milestone_70_reached,
                 consistency_days, business_ready)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                today,
                metrics['daily_roi'],
                metrics['weekly_roi'], 
                metrics['monthly_roi'],
                metrics['total_roi'],
                metrics['total_stakes'],
                metrics['total_profit_loss'],
                metrics['win_rate'],
                metrics['total_bets'],
                metrics['settled_bets'],
                int(metrics['milestones']['50_percent']['reached']),
                int(metrics['milestones']['60_percent']['reached']),
                int(metrics['milestones']['70_percent']['reached']),
                metrics['consistency']['consistent_days'],
                int(metrics['business_ready']['is_ready'])
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving ROI snapshot: {e}")
    
    def _get_roi_status(self, roi: float) -> str:
        """Get current ROI status message"""
        if roi >= 70.0:
            return "🎯 TARGET ACHIEVED"
        elif roi >= 60.0:
            return "🔥 EXCELLENT PROGRESS"  
        elif roi >= 50.0:
            return "📈 STRONG PERFORMANCE"
        elif roi >= 25.0:
            return "⚡ BUILDING MOMENTUM"
        elif roi >= 0.0:
            return "✅ PROFITABLE"
        else:
            return "📊 IMPROVING"
    
    def _get_next_milestone(self, roi: float) -> Dict:
        """Get information about the next milestone"""
        if roi < 50.0:
            return {'target': 50.0, 'remaining': 50.0 - roi, 'name': 'First Major Milestone'}
        elif roi < 60.0:
            return {'target': 60.0, 'remaining': 60.0 - roi, 'name': 'Strong Performance'}
        elif roi < 70.0:
            return {'target': 70.0, 'remaining': 70.0 - roi, 'name': 'MONETIZATION READY'}
        else:
            return {'target': 80.0, 'remaining': max(80.0 - roi, 0), 'name': 'Elite Performance'}
    
    def _empty_roi_metrics(self) -> Dict:
        """Return empty metrics structure"""
        return {
            'timestamp': datetime.now().isoformat(),
            'total_roi': 0.0,
            'daily_roi': 0.0,
            'weekly_roi': 0.0,
            'monthly_roi': 0.0,
            'total_stakes': 0.0,
            'total_profit_loss': 0.0,
            'win_rate': 0.0,
            'total_bets': 0,
            'settled_bets': 0,
            'progress_percentage': 0.0,
            'target_roi': self.target_roi,
            'milestones': {
                '50_percent': {'reached': False, 'progress': 0, 'remaining': 50.0},
                '60_percent': {'reached': False, 'progress': 0, 'remaining': 60.0},
                '70_percent': {'reached': False, 'progress': 0, 'remaining': 70.0}
            },
            'consistency': {'consistent_days': 0, 'daily_rois': [], 'is_consistent': False, 'consistency_percentage': 0, 'required_days': self.consistency_days, 'days_with_settlements': 0},
            'business_ready': {
                'is_ready': False, 
                'readiness_score': 0.0, 
                'criteria': {'roi_target': False, 'consistency': False, 'minimum_bets': False, 'win_rate': False},
                'recommendations': ['Start tracking settled bets to calculate ROI'],
                'estimated_days_to_ready': None
            },
            'roi_status': '🔄 STARTING TRACKING',
            'next_milestone': {'target': 50.0, 'remaining': 50.0, 'name': 'First Major Milestone'}
        }
    
    def get_roi_history(self, days: int = 30) -> pd.DataFrame:
        """Get historical ROI data"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            cutoff_date = (date.today() - timedelta(days=days)).isoformat()
            
            query = '''
                SELECT * FROM roi_snapshots 
                WHERE date >= ?
                ORDER BY date ASC
            '''
            
            df = pd.read_sql_query(query, conn, params=[cutoff_date])
            conn.close()
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting ROI history: {e}")
            return pd.DataFrame()
    
    def get_milestone_achievements(self) -> pd.DataFrame:
        """Get all milestone achievements"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            df = pd.read_sql_query('''
                SELECT * FROM roi_milestones 
                ORDER BY achieved_date DESC, milestone_value ASC
            ''', conn)
            
            conn.close()
            return df
            
        except Exception as e:
            logger.error(f"Error getting milestones: {e}")
            return pd.DataFrame()

# Convenience function for easy access
def get_current_roi_metrics() -> Dict:
    """Get current ROI metrics - main entry point"""
    tracker = ROITracker()
    return tracker.calculate_current_roi()

if __name__ == "__main__":
    # Test the ROI tracker
    print("🎯 Testing ROI Tracker System...")
    tracker = ROITracker()
    metrics = tracker.calculate_current_roi()
    
    print(f"📊 Current ROI: {metrics['total_roi']}%")
    print(f"🎯 Progress to Target: {metrics['progress_percentage']}%")
    print(f"🔥 Status: {metrics['roi_status']}")
    print(f"✅ Business Ready: {metrics['business_ready']['is_ready']}")