#!/usr/bin/env python3
"""
Form Cacher
-----------
Runs after each engine cycle and fills in form + H2H data for any
upcoming picks that are missing a training_data row.

Flow:
  1. Query football_opportunities → unique upcoming matches
  2. Check which have no row in training_data
  3. For each missing match → fetch form + H2H from SofaScore
  4. Save via DataCollector.collect_match_analysis()

This means every match in the dashboard has form/H2H preloaded
and the detail panel opens instantly with no extra network calls.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import db_helper

logger = logging.getLogger(__name__)


def _agg_form(matches: list) -> Optional[dict]:
    """Aggregate raw SofaScore match list into DataCollector-compatible dict."""
    if not matches:
        return None
    wins = sum(1 for m in matches if m.get('result') == 'W')
    draws = sum(1 for m in matches if m.get('result') == 'D')
    losses = sum(1 for m in matches if m.get('result') == 'L')
    goals_for = goals_against = clean_sheets = 0
    for m in matches:
        try:
            score = m.get('score', '0-0')
            hg, ag = map(int, score.split('-'))
            gf, ga = (hg, ag) if m.get('home_away') == 'H' else (ag, hg)
            goals_for += gf
            goals_against += ga
            if ga == 0:
                clean_sheets += 1
        except Exception:
            pass
    n = len(matches)
    ppg = round((wins * 3 + draws) / n, 2) if n else 0
    return {
        'wins': wins,
        'draws': draws,
        'losses': losses,
        'ppg': ppg,
        'goals_scored': round(goals_for / n, 2) if n else None,
        'goals_conceded': round(goals_against / n, 2) if n else None,
        'clean_sheets': clean_sheets,
    }


def _agg_h2h(h2h_raw: list, home_team: str, away_team: str) -> Optional[dict]:
    """Aggregate raw H2H list into DataCollector-compatible dict."""
    if not h2h_raw:
        return None
    n = len(h2h_raw)
    hw = sum(1 for m in h2h_raw if m.get('home_team') == home_team and m.get('home_score', 0) > m.get('away_score', 0))
    aw = sum(1 for m in h2h_raw if m.get('away_team') == away_team and m.get('away_score', 0) > m.get('home_score', 0))
    dw = n - hw - aw
    total_g = sum(m.get('home_score', 0) + m.get('away_score', 0) for m in h2h_raw)
    btts = sum(1 for m in h2h_raw if m.get('home_score', 0) > 0 and m.get('away_score', 0) > 0)
    over25 = sum(1 for m in h2h_raw if m.get('home_score', 0) + m.get('away_score', 0) > 2.5)
    return {
        'matches_count': n,
        'home_wins': hw,
        'away_wins': aw,
        'draws': dw,
        'avg_goals': round(total_g / n, 2) if n else None,
        'btts_rate': round(btts / n, 3) if n else None,
        'over25_rate': round(over25 / n, 3) if n else None,
    }


def run_form_cacher():
    """
    Main entry point. Finds upcoming picks without training_data,
    fetches SofaScore data, and saves to DB.
    Called by combined_sports_runner.py after each engine cycle.
    """
    try:
        now_utc = datetime.utcnow()
        today_str = now_utc.strftime('%Y-%m-%d')
        horizon_str = (now_utc + timedelta(days=5)).strftime('%Y-%m-%d')

        # 1. Get unique upcoming matches from football_opportunities
        upcoming = db_helper.execute("""
            SELECT DISTINCT home_team, away_team, league, match_date
            FROM football_opportunities
            WHERE match_date BETWEEN %s AND %s
              AND mode != 'TEST'
        """, (today_str, horizon_str), fetch='all') or []

        if not upcoming:
            logger.info("🗂️ FormCacher: no upcoming matches found")
            return

        # 2. Find which already have training_data
        placeholders = ','.join(['(%s,%s,%s)'] * len(upcoming))
        flat = [v for row in upcoming for v in (row[0], row[1], str(row[3]))]
        existing = db_helper.execute(f"""
            SELECT DISTINCT home_team, away_team, match_date::text
            FROM training_data
            WHERE (home_team, away_team, match_date::text) IN ({placeholders})
        """, flat, fetch='all') or []
        existing_set = {(r[0], r[1], str(r[2])) for r in existing}

        # 3. Filter to only matches without data
        missing = [
            row for row in upcoming
            if (row[0], row[1], str(row[3])) not in existing_set
        ]

        if not missing:
            logger.info(f"✅ FormCacher: all {len(upcoming)} matches already have training data")
            return

        logger.info(f"📥 FormCacher: fetching form+H2H for {len(missing)} matches…")

        from sofascore_scraper import SofaScoreScraper
        from data_collector import DataCollector

        scraper = SofaScoreScraper()
        collector = DataCollector()
        saved = 0

        for row in missing:
            home_team, away_team, league, match_date = row[0], row[1], row[2], row[3]
            try:
                # Fetch form (last 5 matches each)
                home_raw = scraper.get_team_form(home_team, league or '', last_n=5)
                away_raw = scraper.get_team_form(away_team, league or '', last_n=5)

                # Fetch H2H
                h2h_raw = scraper.get_h2h_data(home_team, away_team, league or '')

                home_form = _agg_form(home_raw)
                away_form = _agg_form(away_raw)
                h2h = _agg_h2h(h2h_raw, home_team, away_team)

                if not home_form and not away_form and not h2h:
                    logger.warning(f"⚠️ FormCacher: no data from SofaScore for {home_team} vs {away_team}")
                    continue

                # Build h2h_data in DataCollector format
                h2h_data_dc = {}
                if h2h:
                    h2h_data_dc = {
                        'matches_count': h2h['matches_count'],
                        'home_wins': h2h['home_wins'],
                        'away_wins': h2h['away_wins'],
                        'draws': h2h['draws'],
                        'avg_goals': h2h['avg_goals'],
                        'btts_rate': h2h['btts_rate'],
                        'over25_rate': h2h['over25_rate'],
                    }

                ok = collector.collect_match_analysis(
                    home_team=home_team,
                    away_team=away_team,
                    league=league,
                    match_date=match_date if isinstance(match_date, datetime) else datetime.strptime(str(match_date), '%Y-%m-%d'),
                    home_form=home_form or {},
                    away_form=away_form or {},
                    h2h_data=h2h_data_dc,
                    data_source='form_cacher_sofascore',
                )
                if ok:
                    saved += 1
                    logger.info(f"✅ FormCacher: saved {home_team} vs {away_team}")

            except Exception as e:
                logger.warning(f"⚠️ FormCacher: failed {home_team} vs {away_team}: {e}")
                continue

        logger.info(f"📊 FormCacher: done — {saved}/{len(missing)} matches saved")

    except Exception as e:
        logger.error(f"❌ FormCacher error: {e}")
