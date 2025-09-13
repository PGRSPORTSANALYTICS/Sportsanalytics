#!/usr/bin/env python3
"""
Test script to validate verification system works correctly
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from verify_results import RealResultVerifier
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    print("🧪 Testing verification system with past-date test data...")
    
    verifier = RealResultVerifier('data/real_football.db')
    
    print("📋 Checking for pending tips...")
    pending_tips = verifier._get_pending_tips()
    print(f"📊 Found {len(pending_tips)} tips for verification")
    
    if pending_tips:
        for tip in pending_tips:
            print(f"🎯 Tip: {tip['home_team']} vs {tip['away_team']} - {tip['selection']} (${tip['stake']})")
    
    print("\n🚀 Running verification...")
    results = verifier.verify_pending_tips()
    
    print(f"\n✅ Results: {results['verified']} verified, {results['failed']} failed, {results['api_failures']} API failures")