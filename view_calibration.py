#!/usr/bin/env python3
"""
View Model Calibration Report
Check if your probability models are accurate
"""
from model_calibration_tracker import ModelCalibrationTracker

if __name__ == "__main__":
    print("\n🔬 Analyzing Model Calibration...\n")
    
    tracker = ModelCalibrationTracker()
    tracker.print_calibration_report(min_predictions=30)
    
    print("💡 What this means:")
    print("   - Well calibrated = Model probabilities match reality")
    print("   - Error < 5% = Excellent calibration")
    print("   - Error > 10% = Models need adjustment")
    print("\n📊 Data in: data/real_football.db (model_calibration table)\n")
