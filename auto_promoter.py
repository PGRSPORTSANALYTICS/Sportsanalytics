"""
Auto Promotion/Demotion System v1.0
====================================
Automatically moves market+league combinations between:
  - PRODUCTION: Live bets with real stakes
  - LEARNING_ONLY: Data collection, no real stakes
  - DISABLED: No data collection

Rules:
  LEARNING_ONLY -> PRODUCTION: bets >= 80, ROI > 3%, CLV positive
  PRODUCTION -> LEARNING_ONLY: ROI < 0% after 80 bets OR CLV negative after 80 bets
  LEARNING_ONLY -> DISABLED: ROI < -5% after 150 bets
  DISABLED -> LEARNING_ONLY: manual override only

All new league+market combos start as LEARNING_ONLY.
Manual overrides are respected and skip auto-evaluation.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from db_helper import db_helper

logger = logging.getLogger(__name__)

MIN_BETS_FOR_PROMOTION = 80
MIN_ROI_FOR_PROMOTION = 3.0
MIN_BETS_FOR_DEMOTION_CHECK = 80
MIN_BETS_FOR_DISABLE = 150
DISABLE_ROI_THRESHOLD = -5.0

VALID_STATUSES = {'PRODUCTION', 'LEARNING_ONLY', 'DISABLED'}


class AutoPromoter:

    def __init__(self):
        self._status_cache: Dict[str, str] = {}
        self._cache_loaded = False

    def _load_cache(self):
        if self._cache_loaded:
            return
        try:
            rows = db_helper.execute("""
                SELECT sport, league_id, market_type, status, manual_override
                FROM league_market_status
            """, fetch='all') or []
            for row in rows:
                key = f"{row[0]}|{row[1]}|{row[2]}"
                self._status_cache[key] = row[3]
            self._cache_loaded = True
        except Exception as e:
            logger.error(f"Error loading status cache: {e}")

    def get_market_status(self, sport: str, league: str, market: str) -> str:
        self._load_cache()
        key = f"{sport}|{league}|{market}"
        return self._status_cache.get(key, 'LEARNING_ONLY')

    def has_explicit_status(self, sport: str, league: str, market: str) -> bool:
        self._load_cache()
        key = f"{sport}|{league}|{market}"
        return key in self._status_cache

    def is_production(self, sport: str, league: str, market: str) -> bool:
        return self.get_market_status(sport, league, market) == 'PRODUCTION'

    def is_learning_only(self, sport: str, league: str, market: str) -> bool:
        return self.get_market_status(sport, league, market) == 'LEARNING_ONLY'

    def is_disabled(self, sport: str, league: str, market: str) -> bool:
        return self.get_market_status(sport, league, market) == 'DISABLED'

    def get_all_production_markets(self, sport: str = 'football') -> Set[str]:
        self._load_cache()
        result = set()
        prefix = f"{sport}|"
        for key, status in self._status_cache.items():
            if key.startswith(prefix) and status == 'PRODUCTION':
                parts = key.split('|', 2)
                if len(parts) == 3:
                    result.add(parts[2])
        return result

    def get_learning_only_markets(self, sport: str = 'football') -> Set[str]:
        self._load_cache()
        result = set()
        prefix = f"{sport}|"
        for key, status in self._status_cache.items():
            if key.startswith(prefix) and status == 'LEARNING_ONLY':
                parts = key.split('|', 2)
                if len(parts) == 3:
                    result.add(parts[2])
        return result

    def run_promotion_cycle(self) -> Dict[str, List[Dict]]:
        changes = {'promoted': [], 'demoted': [], 'disabled': [], 'new': [], 'unchanged': []}

        try:
            stats_rows = db_helper.execute("""
                SELECT sport, dimension_key, total_bets, wins, losses,
                       roi_pct, hit_rate, avg_clv, profit_units
                FROM learning_stats
                WHERE dimension = 'league_market' AND window_type = 'all_time'
                  AND total_bets >= 5
            """, fetch='all') or []
        except Exception as e:
            logger.error(f"Error fetching learning stats for promotion: {e}")
            return changes

        for row in stats_rows:
            sport = row[0]
            lm_key = row[1]
            total_bets = row[2]
            roi_pct = row[5]
            avg_clv = row[7]
            profit_units = row[8]

            if '|' not in lm_key:
                continue
            league, market = lm_key.split('|', 1)

            current_status = self._get_db_status(sport, league, market)
            is_manual = self._is_manual_override(sport, league, market)

            if is_manual:
                changes['unchanged'].append({
                    'sport': sport, 'league': league, 'market': market,
                    'status': current_status, 'reason': 'manual_override',
                })
                continue

            new_status = current_status
            reason = ''

            if current_status is None:
                new_status = 'LEARNING_ONLY'
                reason = f'New combo: {total_bets} bets'
                changes['new'].append({
                    'sport': sport, 'league': league, 'market': market,
                    'status': new_status, 'reason': reason,
                    'roi': roi_pct, 'clv': avg_clv, 'bets': total_bets,
                })
            elif current_status == 'LEARNING_ONLY':
                clv_ok = avg_clv > 0 or avg_clv == 0.0
                if (total_bets >= MIN_BETS_FOR_PROMOTION and
                        roi_pct > MIN_ROI_FOR_PROMOTION and
                        clv_ok):
                    new_status = 'PRODUCTION'
                    reason = f'Promoted: {total_bets} bets, ROI {roi_pct:.1f}%, CLV {avg_clv:.3f}'
                    changes['promoted'].append({
                        'sport': sport, 'league': league, 'market': market,
                        'status': new_status, 'reason': reason,
                        'roi': roi_pct, 'clv': avg_clv, 'bets': total_bets,
                    })
                elif total_bets >= MIN_BETS_FOR_DISABLE and roi_pct < DISABLE_ROI_THRESHOLD:
                    new_status = 'DISABLED'
                    reason = f'Disabled: {total_bets} bets, ROI {roi_pct:.1f}%'
                    changes['disabled'].append({
                        'sport': sport, 'league': league, 'market': market,
                        'status': new_status, 'reason': reason,
                        'roi': roi_pct, 'clv': avg_clv, 'bets': total_bets,
                    })
                else:
                    changes['unchanged'].append({
                        'sport': sport, 'league': league, 'market': market,
                        'status': current_status, 'reason': 'Still learning',
                    })
                    continue
            elif current_status == 'PRODUCTION':
                clv_negative = avg_clv < 0 and avg_clv != 0.0
                if total_bets >= MIN_BETS_FOR_DEMOTION_CHECK and (roi_pct < 0 or clv_negative):
                    new_status = 'LEARNING_ONLY'
                    reason = f'Demoted: {total_bets} bets, ROI {roi_pct:.1f}%, CLV {avg_clv:.3f}'
                    changes['demoted'].append({
                        'sport': sport, 'league': league, 'market': market,
                        'status': new_status, 'reason': reason,
                        'roi': roi_pct, 'clv': avg_clv, 'bets': total_bets,
                    })
                else:
                    changes['unchanged'].append({
                        'sport': sport, 'league': league, 'market': market,
                        'status': current_status, 'reason': 'Maintaining production',
                    })
                    continue
            elif current_status == 'DISABLED':
                changes['unchanged'].append({
                    'sport': sport, 'league': league, 'market': market,
                    'status': current_status, 'reason': 'Disabled - manual re-enable only',
                })
                continue

            if new_status != current_status or current_status is None:
                self._upsert_status(sport, league, market, new_status,
                                    total_bets, roi_pct, avg_clv, profit_units, reason)

        self._cache_loaded = False
        self._status_cache = {}

        promoted_count = len(changes['promoted'])
        demoted_count = len(changes['demoted'])
        disabled_count = len(changes['disabled'])
        new_count = len(changes['new'])
        logger.info(
            f"Promotion cycle complete: "
            f"{promoted_count} promoted, {demoted_count} demoted, "
            f"{disabled_count} disabled, {new_count} new"
        )

        return changes

    def _get_db_status(self, sport: str, league: str, market: str) -> Optional[str]:
        try:
            row = db_helper.execute("""
                SELECT status FROM league_market_status
                WHERE sport = %s AND league_id = %s AND market_type = %s
            """, (sport, league, market), fetch='one')
            return row[0] if row else None
        except Exception:
            return None

    def _is_manual_override(self, sport: str, league: str, market: str) -> bool:
        try:
            row = db_helper.execute("""
                SELECT manual_override FROM league_market_status
                WHERE sport = %s AND league_id = %s AND market_type = %s
            """, (sport, league, market), fetch='one')
            return bool(row[0]) if row else False
        except Exception:
            return False

    def _upsert_status(self, sport: str, league: str, market: str,
                       status: str, total_bets: int, roi_pct: float,
                       avg_clv: float, profit_units: float, reason: str):
        now = datetime.utcnow()
        try:
            db_helper.execute("""
                INSERT INTO league_market_status
                    (sport, league_id, market_type, status, total_bets, 
                     roi_pct, hit_rate, avg_clv, profit_units,
                     last_promotion_change, promotion_reason, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s)
                ON CONFLICT (sport, league_id, market_type)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    total_bets = EXCLUDED.total_bets,
                    roi_pct = EXCLUDED.roi_pct,
                    avg_clv = EXCLUDED.avg_clv,
                    profit_units = EXCLUDED.profit_units,
                    last_promotion_change = EXCLUDED.last_promotion_change,
                    promotion_reason = EXCLUDED.promotion_reason,
                    updated_at = EXCLUDED.updated_at
            """, (sport, league, market, status, total_bets,
                  roi_pct, avg_clv, profit_units, now, reason, now))
        except Exception as e:
            logger.error(f"Error upserting status {sport}/{league}/{market}: {e}")


_promoter_instance = None

def get_promoter() -> AutoPromoter:
    global _promoter_instance
    if _promoter_instance is None:
        _promoter_instance = AutoPromoter()
    return _promoter_instance


def run_promotion_cycle() -> Dict[str, List[Dict]]:
    return get_promoter().run_promotion_cycle()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    changes = run_promotion_cycle()
    for action, items in changes.items():
        if items and action != 'unchanged':
            print(f"\n{action.upper()} ({len(items)}):")
            for item in items:
                print(f"  {item['league']} / {item['market']}: {item.get('reason', '')}")
