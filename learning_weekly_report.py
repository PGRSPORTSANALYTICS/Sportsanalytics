"""
Weekly Learning System Report
Analyzes all learning-only markets and sends performance report to Discord.
Runs every Sunday alongside the weekly recap.
"""

import os
import logging
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
DATABASE_URL = os.getenv('DATABASE_URL')

LEARNING_MARKETS = {
    'HOME_WIN': {'pattern': '%home win%', 'label': 'Home Win (1X2)'},
    'AWAY_WIN': {'pattern': '%away win%', 'label': 'Away Win (1X2)'},
    'DRAW': {'pattern': '%draw%', 'exclude': '%no bet%', 'label': 'Draw (1X2)'},
    'FT_UNDER_2_5': {'pattern': '%under 2.5%', 'label': 'Under 2.5'},
    'FT_UNDER_3_5': {'pattern': '%under 3.5%', 'label': 'Under 3.5'},
    'ASIAN_HANDICAP': {'pattern': '%(ah)%', 'label': 'Asian Handicap'},
}

PRODUCTION_MARKETS = {
    'FT_OVER_2_5': {'pattern': '%over 2.5%', 'label': 'Over 2.5'},
    'FT_OVER_3_5': {'pattern': '%over 3.5%', 'label': 'Over 3.5'},
    'BTTS': {'pattern': '%btts%', 'label': 'BTTS'},
    'CARDS': {'market': 'Cards', 'label': 'Cards'},
    'CORNERS': {'market': 'Corners', 'label': 'Corners'},
}

BASKETBALL_MARKETS = {
    'BB_MONEYLINE': {'market_val': '1X2 Moneyline', 'label': 'Moneyline'},
    'BB_TOTALS': {'market_val': 'Totals', 'label': 'Totals (O/U)'},
    'BB_SPREAD': {'market_val': 'Spread', 'label': 'Spread'},
}


def _get_db():
    if not DATABASE_URL:
        return None
    return psycopg2.connect(DATABASE_URL)


def _query_market_stats(cursor, market_filter, table='football_opportunities', 
                         market_col_value=None, days=None):
    where_parts = []
    params = []
    
    if market_col_value:
        where_parts.append("market = %s")
        params.append(market_col_value)
    else:
        where_parts.append("market = 'Value Single'")
    
    pattern = market_filter.get('pattern')
    exclude = market_filter.get('exclude')
    
    if pattern:
        where_parts.append("selection ILIKE %s")
        params.append(pattern)
    if exclude:
        where_parts.append("selection NOT ILIKE %s")
        params.append(exclude)
    
    if days:
        where_parts.append("match_date >= %s")
        params.append((date.today() - timedelta(days=days)).isoformat())
    
    where_clause = " AND ".join(where_parts)
    
    query = f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'won' THEN 1 ELSE 0 END) as won,
            SUM(CASE WHEN outcome = 'lost' THEN 1 ELSE 0 END) as lost,
            SUM(CASE WHEN outcome IS NULL OR outcome = '' OR outcome = 'pending' THEN 1 ELSE 0 END) as pending,
            ROUND(AVG(odds)::numeric, 2) as avg_odds,
            ROUND(SUM(CASE WHEN outcome = 'won' THEN odds - 1 WHEN outcome = 'lost' THEN -1 ELSE 0 END)::numeric, 2) as profit_units
        FROM {table}
        WHERE {where_clause}
    """
    
    cursor.execute(query, params)
    return cursor.fetchone()


def _query_basketball_stats(cursor, market_filter, days=None):
    where_parts = ["is_parlay = false"]
    params = []
    
    market_val = market_filter.get('market_val')
    if market_val:
        where_parts.append("market = %s")
        params.append(market_val)
    
    pattern = market_filter.get('pattern')
    if pattern:
        where_parts.append("selection ILIKE %s")
        params.append(pattern)
    
    if days:
        where_parts.append("commence_time >= %s")
        params.append((datetime.utcnow() - timedelta(days=days)).isoformat())
    
    where_clause = " AND ".join(where_parts)
    
    query = f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as won,
            SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as lost,
            SUM(CASE WHEN status IS NULL OR status = '' OR status = 'pending' THEN 1 ELSE 0 END) as pending,
            ROUND(AVG(odds)::numeric, 2) as avg_odds,
            ROUND(SUM(CASE WHEN status = 'won' THEN odds - 1 WHEN status = 'lost' THEN -1 ELSE 0 END)::numeric, 2) as profit_units
        FROM basketball_predictions
        WHERE {where_clause}
    """
    
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    except Exception:
        return None


def _format_market_line(label, stats, threshold_note=""):
    if not stats or stats['total'] == 0:
        return None
    
    total = stats['total']
    won = stats['won'] or 0
    lost = stats['lost'] or 0
    pending = stats['pending'] or 0
    settled = won + lost
    avg_odds = stats['avg_odds'] or 0
    profit = stats['profit_units'] or 0
    
    if settled == 0:
        hit_rate = 0
        roi = 0
    else:
        hit_rate = won / settled * 100
        roi = profit / settled * 100
    
    profit_emoji = "+" if profit >= 0 else ""
    status = "🟢" if profit > 0 else ("🟡" if profit == 0 else "🔴")
    
    line = f"{status} **{label}**: {won}-{lost}"
    if pending > 0:
        line += f" ({pending} pending)"
    line += f" | {hit_rate:.0f}% | {profit_emoji}{profit:.1f}u"
    if avg_odds:
        line += f" | avg {avg_odds}"
    if threshold_note:
        line += f"\n   _{threshold_note}_"
    
    return line


def _evaluate_promotion(label, stats_all, stats_7d):
    if not stats_all:
        return None
    
    settled = (stats_all['won'] or 0) + (stats_all['lost'] or 0)
    if settled < 20:
        return f"📊 {label}: Need {20 - settled} more settled bets for evaluation"
    
    won = stats_all['won'] or 0
    profit = stats_all['profit_units'] or 0
    hit_rate = won / settled * 100 if settled > 0 else 0
    avg_odds = float(stats_all['avg_odds'] or 1.5)
    
    break_even_rate = 100 / avg_odds if avg_odds > 0 else 50
    edge_over_breakeven = hit_rate - break_even_rate
    
    if profit > 5 and hit_rate > break_even_rate + 5 and settled >= 50:
        return f"✅ **{label}: READY FOR PRODUCTION** — {hit_rate:.0f}% hit ({break_even_rate:.0f}% needed), {profit:+.1f}u over {settled} bets"
    elif profit > 0 and hit_rate > break_even_rate:
        return f"🟡 {label}: Promising — {hit_rate:.0f}% hit ({break_even_rate:.0f}% needed), {profit:+.1f}u. Need more data."
    elif edge_over_breakeven > -5:
        return f"🟠 {label}: Marginal — {hit_rate:.0f}% hit ({break_even_rate:.0f}% needed), {profit:+.1f}u. Keep learning."
    else:
        return f"🔴 {label}: Not viable — {hit_rate:.0f}% hit ({break_even_rate:.0f}% needed), {profit:+.1f}u over {settled} bets"


def generate_weekly_learning_report():
    conn = _get_db()
    if not conn:
        logger.warning("No database connection for learning report")
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        report_sections = []
        
        report_sections.append("**🏆 PRODUCTION MARKETS (Last 7 Days)**")
        prod_lines = []
        for key, mf in PRODUCTION_MARKETS.items():
            market_col = mf.get('market')
            if market_col:
                stats = _query_market_stats(cursor, mf, market_col_value=market_col, days=7)
            else:
                stats = _query_market_stats(cursor, mf, days=7)
            line = _format_market_line(mf['label'], stats)
            if line:
                prod_lines.append(line)
        if prod_lines:
            report_sections.append("\n".join(prod_lines))
        else:
            report_sections.append("_No production data this week_")
        
        report_sections.append("\n**🧪 LEARNING MARKETS (All Time)**")
        learning_lines = []
        evaluations = []
        for key, mf in LEARNING_MARKETS.items():
            stats_all = _query_market_stats(cursor, mf)
            stats_7d = _query_market_stats(cursor, mf, days=7)
            line = _format_market_line(mf['label'], stats_all)
            if line:
                if stats_7d and (stats_7d['won'] or 0) + (stats_7d['lost'] or 0) > 0:
                    w7 = stats_7d['won'] or 0
                    l7 = stats_7d['lost'] or 0
                    p7 = stats_7d['profit_units'] or 0
                    line += f"\n   _This week: {w7}-{l7}, {p7:+.1f}u_"
                learning_lines.append(line)
            
            eval_line = _evaluate_promotion(mf['label'], stats_all, stats_7d)
            if eval_line:
                evaluations.append(eval_line)
        
        if learning_lines:
            report_sections.append("\n".join(learning_lines))
        else:
            report_sections.append("_No learning data yet_")
        
        report_sections.append("\n**🏀 BASKETBALL (All Time)**")
        bb_lines = []
        for key, mf in BASKETBALL_MARKETS.items():
            stats = _query_basketball_stats(cursor, mf)
            if stats:
                line = _format_market_line(mf['label'], stats)
                if line:
                    bb_lines.append(line)
        if bb_lines:
            report_sections.append("\n".join(bb_lines))
        else:
            report_sections.append("_No basketball data_")
        
        if evaluations:
            report_sections.append("\n**📋 PROMOTION EVALUATION**")
            report_sections.append("\n".join(evaluations))
        
        cursor.close()
        conn.close()
        
        return "\n\n".join(report_sections)
        
    except Exception as e:
        logger.error(f"Error generating learning report: {e}")
        if conn:
            conn.close()
        return None


def send_weekly_learning_report():
    logger.info("📊 Generating weekly learning system report...")
    
    report = generate_weekly_learning_report()
    if not report:
        logger.warning("No learning report generated")
        return False
    
    if not DISCORD_WEBHOOK_URL:
        logger.warning("No DISCORD_WEBHOOK_URL for learning report")
        print(report)
        return False
    
    today = date.today()
    week_num = today.isocalendar()[1]
    
    embed = {
        "title": f"🧪 Learning System Report — Week {week_num}",
        "description": report,
        "color": 0x7C3AED,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "PGR Learning System | Auto-generated weekly"}
    }
    
    try:
        payload = {"embeds": [embed]}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("✅ Weekly learning report sent to Discord")
        return True
    except Exception as e:
        logger.error(f"❌ Discord learning report error: {e}")
        return False


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--send':
        send_weekly_learning_report()
    else:
        report = generate_weekly_learning_report()
        if report:
            print(report)
        else:
            print("No report data available")
