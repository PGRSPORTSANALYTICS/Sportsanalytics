#!/usr/bin/env python3
"""
Quick command to view Similar Matches impact
Run: python3 view_sm_impact.py
"""
from similar_matches_tracker import SimilarMatchesTracker

if __name__ == "__main__":
    print("\n🔍 Analyzing Similar Matches Technology Impact...\n")
    
    tracker = SimilarMatchesTracker()
    tracker.print_report(min_predictions=20)
    
    print("💡 TIP: Run this after every 20-30 settled predictions to track progress")
    print("📊 Data tracked in: data/real_football.db (similar_matches_impact table)\n")
