#!/usr/bin/env python3
import logging
from db_helper import db_helper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sql_translation():
    """Test SQL translation from SQLite to PostgreSQL"""
    logger.info("=" * 60)
    logger.info("TESTING SQL TRANSLATION")
    logger.info("=" * 60)
    
    test_cases = [
        ("SELECT * FROM bets WHERE id = ?", "SELECT * FROM bets WHERE id = %s"),
        ("SELECT datetime('now')", "SELECT NOW()"),
        ("SELECT strftime('%s', 'now')", "SELECT EXTRACT(EPOCH FROM NOW())::BIGINT"),
        ("SELECT DATE('now')", "SELECT CURRENT_DATE"),
        ("INSERT INTO bets VALUES (?, ?, ?)", "INSERT INTO bets VALUES (%s, %s, %s)"),
    ]
    
    all_passed = True
    for original, expected in test_cases:
        result = db_helper.translate_sql(original)
        passed = result == expected
        all_passed = all_passed and passed
        status = "✅" if passed else "❌"
        logger.info(f"{status} '{original}' → '{result}'")
        if not passed:
            logger.error(f"   Expected: '{expected}'")
    
    return all_passed

def test_basic_query():
    """Test basic database query"""
    logger.info("=" * 60)
    logger.info("TESTING BASIC QUERY")
    logger.info("=" * 60)
    
    try:
        result = db_helper.execute(
            "SELECT COUNT(*) FROM football_opportunities WHERE market = ?",
            ('exact_score',),
            fetch='one'
        )
        logger.info(f"✅ Found {result[0]} exact score predictions")
        return True
    except Exception as e:
        logger.error(f"❌ Query failed: {e}")
        return False

def test_nov8_predictions():
    """Test querying Nov 8 predictions"""
    logger.info("=" * 60)
    logger.info("TESTING NOV 8 PREDICTIONS")
    logger.info("=" * 60)
    
    try:
        results = db_helper.execute(
            "SELECT home_team, away_team, selection, status FROM football_opportunities WHERE market = ? AND DATE(match_date) = ?",
            ('exact_score', '2025-11-08'),
            fetch='all'
        )
        logger.info(f"✅ Found {len(results)} predictions from Nov 8")
        for i, row in enumerate(results[:3], 1):
            logger.info(f"   {i}. {row[0]} vs {row[1]} = {row[2]} [{row[3]}]")
        return True
    except Exception as e:
        logger.error(f"❌ Query failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Testing PostgreSQL compatibility layer...")
    logger.info("")
    
    test1 = test_sql_translation()
    logger.info("")
    test2 = test_basic_query()
    logger.info("")
    test3 = test_nov8_predictions()
    logger.info("")
    
    if test1 and test2 and test3:
        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED - Compatibility layer working!")
        logger.info("=" * 60)
    else:
        logger.error("=" * 60)
        logger.error("❌ SOME TESTS FAILED")
        logger.error("=" * 60)
