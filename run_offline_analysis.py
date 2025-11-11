"""
Offline Analysis Orchestrator
Runs all 5 analyses and generates comprehensive summary report
"""

import logging
from datetime import datetime
from analysis_data_loader import AnalysisDataLoader
from data_quality import DataQuality
from analysis_xg_diff import XGDifferentialAnalysis
from analysis_ev_thresholds import EVThresholdsAnalysis
from analysis_tempo import TempoAnalysis
from analysis_home_away import HomeAwayBiasAnalysis
from analysis_league_roi import LeagueROIAnalysis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_header():
    """Print analysis header"""
    print("\n" + "="*120)
    print(" "*40 + "OFFLINE ANALYSIS REPORT")
    print(" "*30 + "Exact Score & SGP Model Improvement")
    print(" "*35 + f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*120 + "\n")


def print_summary(all_insights):
    """Print consolidated summary with actionable recommendations"""
    print("\n" + "="*120)
    print(" "*45 + "EXECUTIVE SUMMARY")
    print("="*120 + "\n")
    
    print("📋 ACTIONABLE TUNING SUGGESTIONS:\n")
    
    # Organize insights by category
    ev_insights = []
    league_insights = []
    bias_insights = []
    market_insights = []
    other_insights = []
    
    for analysis_name, insights in all_insights.items():
        for insight in insights:
            if 'EV' in insight or 'cutoff' in insight:
                ev_insights.append(f"{insight}")
            elif 'league' in insight.lower() or 'LEAGUE' in insight:
                league_insights.append(f"{insight}")
            elif 'bias' in insight.lower() or 'HOME' in insight or 'AWAY' in insight:
                bias_insights.append(f"{insight}")
            elif 'BTTS' in insight or 'Over' in insight:
                market_insights.append(f"{insight}")
            else:
                other_insights.append(f"{insight}")
    
    # Print by category
    if ev_insights:
        print("🎯 EV THRESHOLD ADJUSTMENTS:")
        for insight in ev_insights:
            print(f"  {insight}")
        print()
    
    if league_insights:
        print("🌍 LEAGUE PRIORITIZATION:")
        for insight in league_insights:
            print(f"  {insight}")
        print()
    
    if bias_insights:
        print("⚖️ MODEL CALIBRATION:")
        for insight in bias_insights:
            print(f"  {insight}")
        print()
    
    if market_insights:
        print("⚽ SGP MARKET SELECTION:")
        for insight in market_insights:
            print(f"  {insight}")
        print()
    
    if other_insights:
        print("💡 ADDITIONAL INSIGHTS:")
        for insight in other_insights:
            print(f"  {insight}")
        print()
    
    print("="*120 + "\n")


def main():
    """Main orchestrator function"""
    
    print_header()
    
    # Step 1: Load historical data
    logger.info("🔄 STEP 1: Loading historical data...")
    loader = AnalysisDataLoader()
    raw_data = loader.load_all_data()
    
    if raw_data.empty:
        logger.error("❌ No historical data available. Cannot proceed with analysis.")
        return
    
    logger.info(f"✅ Loaded {len(raw_data)} historical bets\n")
    
    # Step 2: Data quality checks
    logger.info("🔄 STEP 2: Enforcing data quality...")
    clean_data = DataQuality.enforce_all_checks(raw_data)
    
    if clean_data.empty:
        logger.error("❌ No data remaining after quality checks. Cannot proceed.")
        return
    
    logger.info(f"✅ {len(clean_data)} high-quality rows ready for analysis\n")
    
    # Step 3: Run all 5 analyses
    logger.info("🔄 STEP 3: Running all 5 analyses...\n")
    
    all_insights = {}
    
    # Analysis 1: xG Differential
    try:
        results1, insights1 = XGDifferentialAnalysis.run_analysis(clean_data)
        results1.to_csv('analysis1.csv', index=False)
        all_insights['Analysis 1 - xG Differential'] = insights1
        logger.info("✅ Analysis 1 saved to analysis1.csv\n")
    except Exception as e:
        logger.error(f"❌ Analysis 1 failed: {e}\n")
        all_insights['Analysis 1 - xG Differential'] = [f"Error: {e}"]
    
    # Analysis 2: EV Thresholds
    try:
        results2, insights2 = EVThresholdsAnalysis.run_analysis(clean_data)
        results2.to_csv('analysis2.csv', index=False)
        all_insights['Analysis 2 - EV Thresholds'] = insights2
        logger.info("✅ Analysis 2 saved to analysis2.csv\n")
    except Exception as e:
        logger.error(f"❌ Analysis 2 failed: {e}\n")
        all_insights['Analysis 2 - EV Thresholds'] = [f"Error: {e}"]
    
    # Analysis 3: Match Tempo
    try:
        results3, insights3 = TempoAnalysis.run_analysis(clean_data)
        results3.to_csv('analysis3.csv', index=False)
        all_insights['Analysis 3 - Match Tempo'] = insights3
        logger.info("✅ Analysis 3 saved to analysis3.csv\n")
    except Exception as e:
        logger.error(f"❌ Analysis 3 failed: {e}\n")
        all_insights['Analysis 3 - Match Tempo'] = [f"Error: {e}"]
    
    # Analysis 4: Home/Away Bias
    try:
        results4, insights4 = HomeAwayBiasAnalysis.run_analysis(clean_data)
        results4.to_csv('analysis4.csv', index=False)
        all_insights['Analysis 4 - Home/Away Bias'] = insights4
        logger.info("✅ Analysis 4 saved to analysis4.csv\n")
    except Exception as e:
        logger.error(f"❌ Analysis 4 failed: {e}\n")
        all_insights['Analysis 4 - Home/Away Bias'] = [f"Error: {e}"]
    
    # Analysis 5: League ROI
    try:
        results5, insights5 = LeagueROIAnalysis.run_analysis(clean_data)
        results5.to_csv('analysis5.csv', index=False)
        all_insights['Analysis 5 - League ROI'] = insights5
        logger.info("✅ Analysis 5 saved to analysis5.csv\n")
    except Exception as e:
        logger.error(f"❌ Analysis 5 failed: {e}\n")
        all_insights['Analysis 5 - League ROI'] = [f"Error: {e}"]
    
    # Step 4: Generate summary
    logger.info("🔄 STEP 4: Generating executive summary...\n")
    print_summary(all_insights)
    
    # Final status
    logger.info("="*120)
    logger.info("✅ OFFLINE ANALYSIS COMPLETE")
    logger.info("="*120)
    logger.info("📁 Output files:")
    logger.info("   - analysis1.csv (xG Differential vs Outcomes)")
    logger.info("   - analysis2.csv (EV Thresholds vs Performance)")
    logger.info("   - analysis3.csv (Match Tempo & Goal Minutes)")
    logger.info("   - analysis4.csv (Home vs Away Bias)")
    logger.info("   - analysis5.csv (League ROI & Stability)")
    logger.info("="*120 + "\n")


if __name__ == "__main__":
    main()
