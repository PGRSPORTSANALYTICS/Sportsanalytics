"""
Proactive Injury Poller
=======================
Polls API-Football /injuries endpoint 48h+ in advance for upcoming fixtures.
Stores data in `proactive_injuries` PostgreSQL table so the prediction engine
can factor in known absences BEFORE picks are created — not just on match day.

Schedule: every 6 hours via combined_sports_runner.py
Covered leagues: Big 5 + European cups + Championship (API-call budget conscious)
"""

import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Priority league IDs — Big 5 + European cups + major secondaries
# Kept intentionally narrow to stay within API call budget (~40-80 fixtures per run)
PRIORITY_LEAGUE_IDS = [
    39,   # Premier League
    40,   # Championship
    140,  # La Liga
    141,  # Spanish Segunda
    135,  # Serie A
    78,   # Bundesliga
    79,   # 2. Bundesliga
    61,   # Ligue 1
    179,  # Eredivisie
    94,   # Primeira Liga
    2,    # Champions League
    3,    # Europa League
    848,  # Conference League
]

# League names for logging clarity
LEAGUE_NAMES = {
    39: "Premier League", 40: "Championship", 140: "La Liga", 141: "Segunda",
    135: "Serie A", 78: "Bundesliga", 79: "2. Bundesliga", 61: "Ligue 1",
    179: "Eredivisie", 94: "Primeira Liga", 2: "Champions League",
    3: "Europa League", 848: "Conference League",
}


class ProactiveInjuryPoller:
    """
    Fetches and stores injury data 48h+ before kickoff so the prediction
    engine and CLV service can factor in known absences early.
    """

    def __init__(self, api_football_client, db_helper_instance):
        self.af = api_football_client
        self.db = db_helper_instance
        self._ensure_table()

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------

    def _ensure_table(self):
        """Create proactive_injuries table if it doesn't exist."""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS proactive_injuries (
                    id            SERIAL PRIMARY KEY,
                    fixture_id    INTEGER NOT NULL,
                    league_id     INTEGER,
                    league_name   TEXT,
                    home_team     TEXT,
                    away_team     TEXT,
                    kickoff_epoch INTEGER,
                    team_id       INTEGER,
                    team_name     TEXT,
                    player_name   TEXT NOT NULL,
                    injury_type   TEXT,
                    reason        TEXT,
                    polled_at     INTEGER NOT NULL,
                    UNIQUE (fixture_id, player_name)
                )
            """)
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_pi_fixture
                    ON proactive_injuries (fixture_id)
            """)
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_pi_kickoff
                    ON proactive_injuries (kickoff_epoch)
            """)
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_pi_team
                    ON proactive_injuries (team_name)
            """)
            logger.info("✅ proactive_injuries table ready")
        except Exception as e:
            logger.error(f"❌ Failed to create proactive_injuries table: {e}")

    # ------------------------------------------------------------------
    # Core poll
    # ------------------------------------------------------------------

    def poll(self, days_ahead: int = 3) -> Dict:
        """
        Main entry point. Fetches upcoming fixtures for priority leagues
        and stores injury data for each fixture.

        Args:
            days_ahead: How far ahead to look (default 2 = next 48h)

        Returns:
            Summary dict with counts for logging/monitoring
        """
        run_start = time.time()
        now_epoch = int(run_start)

        logger.info(f"🏥 Proactive Injury Poll starting — {days_ahead}d window, "
                    f"{len(PRIORITY_LEAGUE_IDS)} leagues")

        # Step 1: Get upcoming fixtures
        fixtures = self._get_upcoming_fixtures(days_ahead)
        if not fixtures:
            logger.warning("⚠️ No upcoming fixtures found — skipping injury poll")
            return {"fixtures_checked": 0, "fixtures_with_injuries": 0, "injuries_stored": 0, "errors": 0}

        logger.info(f"📅 {len(fixtures)} fixtures in next {days_ahead}d")

        # Step 2: For each fixture, fetch injuries and upsert
        total_injuries = 0
        errors = 0
        fixtures_with_injuries = 0

        for fix in fixtures:
            fixture_id = fix.get("fixture_id")
            if not fixture_id:
                continue

            try:
                injury_data = self._fetch_injuries(fixture_id)
                players = injury_data.get("injuries", [])

                if players:
                    stored = self._upsert_injuries(fix, players, now_epoch)
                    total_injuries += stored
                    fixtures_with_injuries += 1
                    logger.info(
                        f"  🏥 {fix['home_team']} vs {fix['away_team']} "
                        f"({LEAGUE_NAMES.get(fix.get('league_id', 0), '?')}) "
                        f"— {len(players)} injured players stored"
                    )
                else:
                    logger.debug(
                        f"  ✅ {fix['home_team']} vs {fix['away_team']} — no injuries reported"
                    )

            except Exception as e:
                errors += 1
                logger.error(f"  ❌ Error for fixture {fixture_id}: {e}")

        elapsed = round(time.time() - run_start, 1)
        summary = {
            "fixtures_checked": len(fixtures),
            "fixtures_with_injuries": fixtures_with_injuries,
            "injuries_stored": total_injuries,
            "errors": errors,
            "elapsed_seconds": elapsed,
        }
        logger.info(
            f"✅ Proactive Injury Poll done in {elapsed}s — "
            f"{len(fixtures)} fixtures, {fixtures_with_injuries} with injuries, "
            f"{total_injuries} player records, {errors} errors"
        )
        return summary

    # ------------------------------------------------------------------
    # Fixture fetching
    # ------------------------------------------------------------------

    def _get_upcoming_fixtures(self, days_ahead: int) -> List[Dict]:
        """Get upcoming fixtures for priority leagues using the cached AF client."""
        try:
            raw = self.af.get_upcoming_fixtures_cached(
                league_ids=PRIORITY_LEAGUE_IDS,
                days_ahead=days_ahead,
            )
            # get_upcoming_fixtures_cached returns formatted dicts — enrich with league_id
            # The formatted dict has sport_key like "league_39" — extract the ID
            enriched = []
            for fix in raw:
                sport_key = fix.get("sport_key", "")
                league_id = None
                if sport_key.startswith("league_"):
                    try:
                        league_id = int(sport_key.split("_")[1])
                    except (ValueError, IndexError):
                        pass

                kickoff_epoch = None
                commence = fix.get("commence_time")
                if commence:
                    try:
                        dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                        kickoff_epoch = int(dt.timestamp())
                    except Exception:
                        pass

                enriched.append({
                    "fixture_id": fix.get("id"),
                    "league_id": league_id,
                    "league_name": fix.get("league_name", fix.get("sport_title", "")),
                    "home_team": fix.get("home_team", ""),
                    "away_team": fix.get("away_team", ""),
                    "kickoff_epoch": kickoff_epoch,
                })

            # Filter to only fixtures with a valid fixture_id and kickoff in the future
            now = int(time.time())
            valid = [
                f for f in enriched
                if f["fixture_id"]
                and f["kickoff_epoch"]
                and f["kickoff_epoch"] > now
            ]
            return valid

        except Exception as e:
            logger.error(f"❌ Error fetching upcoming fixtures: {e}")
            return []

    # ------------------------------------------------------------------
    # Injury fetching (uses existing AF client with 2h cache)
    # ------------------------------------------------------------------

    def _fetch_injuries(self, fixture_id: int) -> Dict:
        """
        Fetches injuries for a fixture via the existing AF client.
        The client handles caching (2h TTL) and rate limiting internally.
        We override the cache with a longer TTL only for proactive fetches
        that happen far from kickoff — handled by passing through the standard path.
        """
        return self.af.get_injuries(fixture_id)

    # ------------------------------------------------------------------
    # DB upsert
    # ------------------------------------------------------------------

    # Reasons that mean "not in squad for tactical/admin reasons" — not a real absence signal
    _SKIP_REASONS = {"inactive", "not in squad", "suspended (admin)"}

    def _upsert_injuries(self, fixture: Dict, players: List[Dict], polled_at: int) -> int:
        """
        Upsert player injury records into proactive_injuries.
        Skips 'Inactive' entries — those are squad-list omissions, not injuries or suspensions.
        ON CONFLICT (fixture_id, player_name) → update injury_type, reason, polled_at.

        Returns number of rows inserted/updated.
        """
        count = 0
        for player in players:
            if not player.get("player_name"):
                continue
            reason_raw = player.get("reason", "")
            # Fix 1: Skip "Inactive" — tactical omission, not an absence signal
            if reason_raw.strip().lower() in self._SKIP_REASONS:
                continue
            try:
                self.db.execute("""
                    INSERT INTO proactive_injuries
                        (fixture_id, league_id, league_name, home_team, away_team,
                         kickoff_epoch, team_id, team_name, player_name,
                         injury_type, reason, polled_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (fixture_id, player_name)
                    DO UPDATE SET
                        injury_type  = EXCLUDED.injury_type,
                        reason       = EXCLUDED.reason,
                        polled_at    = EXCLUDED.polled_at
                """, (
                    fixture["fixture_id"],
                    fixture.get("league_id"),
                    fixture.get("league_name", ""),
                    fixture.get("home_team", ""),
                    fixture.get("away_team", ""),
                    fixture.get("kickoff_epoch"),
                    player.get("team_id"),
                    player.get("team_name", ""),
                    player.get("player_name", "Unknown"),
                    player.get("type", player.get("injury_type", "")),
                    reason_raw,
                    polled_at,
                ))
                count += 1
            except Exception as e:
                logger.error(f"  ❌ Upsert error for {player.get('player_name')}: {e}")

        return count

    # ------------------------------------------------------------------
    # Query helpers (used by predictor / dashboard)
    # ------------------------------------------------------------------

    def get_injuries_for_match(
        self, home_team: str, away_team: str, max_age_hours: int = 48
    ) -> Dict:
        """
        Returns injury report for a specific match.

        Fix 1: Excludes 'Inactive' (tactical omissions, not real absences).
        Fix 2: Separates confirmed_out (Missing Fixture) from doubts (Questionable).
        Fix 3: Exposes last_polled_utc and data_age_minutes for freshness check.
        """
        cutoff = int(time.time()) - (max_age_hours * 3600)
        try:
            rows = self.db.execute("""
                SELECT team_name, player_name, injury_type, reason, polled_at
                FROM proactive_injuries
                WHERE (
                    home_team ILIKE %s OR away_team ILIKE %s
                    OR home_team ILIKE %s OR away_team ILIKE %s
                )
                AND polled_at >= %s
                AND LOWER(reason) NOT IN ('inactive', 'not in squad')
                ORDER BY injury_type ASC, polled_at DESC
            """, (
                f"%{home_team}%", f"%{home_team}%",
                f"%{away_team}%", f"%{away_team}%",
                cutoff,
            ), fetch="all") or []

            home_confirmed, home_doubts = [], []
            away_confirmed, away_doubts = [], []
            latest_polled = 0

            for row in rows:
                team, player, inj_type, reason, polled = row
                if polled and polled > latest_polled:
                    latest_polled = polled

                # Fix 2: classify by injury_type
                confidence = "confirmed" if (inj_type or "").lower() == "missing fixture" else "doubt"
                entry = {
                    "player_name": player,
                    "reason": reason or "",
                    "confidence": confidence,
                }

                if _name_match(team, home_team):
                    (home_confirmed if confidence == "confirmed" else home_doubts).append(entry)
                elif _name_match(team, away_team):
                    (away_confirmed if confidence == "confirmed" else away_doubts).append(entry)

            # Fix 3: freshness metadata
            now = int(time.time())
            data_age_min = round((now - latest_polled) / 60) if latest_polled else None
            last_polled_utc = (
                datetime.fromtimestamp(latest_polled, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                if latest_polled else None
            )

            home_all = home_confirmed + home_doubts
            away_all = away_confirmed + away_doubts

            return {
                "home_team": home_team,
                "away_team": away_team,
                # Detailed split
                "home_confirmed_out": home_confirmed,
                "home_doubts": home_doubts,
                "away_confirmed_out": away_confirmed,
                "away_doubts": away_doubts,
                # Flat lists kept for backwards compat
                "home_injuries": home_all,
                "away_injuries": away_all,
                # Counts
                "home_confirmed_count": len(home_confirmed),
                "home_doubt_count": len(home_doubts),
                "away_confirmed_count": len(away_confirmed),
                "away_doubt_count": len(away_doubts),
                "home_injury_count": len(home_all),
                "away_injury_count": len(away_all),
                "total_injuries": len(home_all) + len(away_all),
                # Flag only if confirmed absences (not just doubts)
                "has_key_injuries": (len(home_confirmed) + len(away_confirmed)) >= 2,
                # Fix 3: freshness
                "last_polled_utc": last_polled_utc,
                "data_age_minutes": data_age_min,
            }
        except Exception as e:
            logger.error(f"❌ get_injuries_for_match error: {e}")
            return _empty_report(home_team, away_team)

    def get_upcoming_injury_summary(self, hours_ahead: int = 48) -> List[Dict]:
        """
        Returns a summary of all upcoming matches with injuries, sorted by kickoff.
        Used by the dashboard's injury panel.
        """
        cutoff_ko = int(time.time())
        max_ko = cutoff_ko + hours_ahead * 3600
        try:
            rows = self.db.execute("""
                SELECT
                    fixture_id, home_team, away_team, league_name,
                    kickoff_epoch,
                    -- Fix 2: split confirmed vs doubt
                    COUNT(*) FILTER (WHERE injury_type = 'Missing Fixture') AS confirmed_out,
                    COUNT(*) FILTER (WHERE injury_type = 'Questionable')    AS doubts,
                    COUNT(*) AS total_absences,
                    COUNT(DISTINCT team_name)                                AS teams_affected,
                    MAX(polled_at)                                           AS last_polled
                FROM proactive_injuries
                WHERE kickoff_epoch BETWEEN %s AND %s
                -- Fix 1: exclude Inactive entries
                AND LOWER(reason) NOT IN ('inactive', 'not in squad')
                GROUP BY fixture_id, home_team, away_team, league_name, kickoff_epoch
                ORDER BY kickoff_epoch ASC
            """, (cutoff_ko, max_ko), fetch="all") or []

            now = int(time.time())
            results = []
            for row in rows:
                fixture_id, home, away, league, ko_epoch, confirmed, doubts, total, teams, last_polled = row
                ko_utc = (
                    datetime.fromtimestamp(ko_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                    if ko_epoch else "?"
                )
                # Fix 3: format last_polled as UTC string + age in minutes
                last_polled_utc = (
                    datetime.fromtimestamp(last_polled, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                    if last_polled else None
                )
                data_age_min = round((now - last_polled) / 60) if last_polled else None

                results.append({
                    "fixture_id": fixture_id,
                    "home_team": home,
                    "away_team": away,
                    "league_name": league,
                    "kickoff_epoch": ko_epoch,
                    "kickoff_utc": ko_utc,
                    # Fix 2: confirmed vs doubt breakdown
                    "confirmed_out": confirmed or 0,
                    "doubts": doubts or 0,
                    "total_absences": total or 0,
                    "teams_affected": teams or 0,
                    # Fix 3: freshness
                    "last_polled_utc": last_polled_utc,
                    "data_age_minutes": data_age_min,
                })
            return results
        except Exception as e:
            logger.error(f"❌ get_upcoming_injury_summary error: {e}")
            return []

    def get_stats(self) -> Dict:
        """Quick stats for logging and API endpoint."""
        try:
            total = self.db.execute(
                "SELECT COUNT(*) FROM proactive_injuries", fetch="one"
            )
            recent = self.db.execute(
                "SELECT COUNT(*) FROM proactive_injuries WHERE polled_at >= %s",
                (int(time.time()) - 86400,), fetch="one"
            )
            fixtures = self.db.execute(
                "SELECT COUNT(DISTINCT fixture_id) FROM proactive_injuries", fetch="one"
            )
            return {
                "total_injury_records": total[0] if total else 0,
                "records_last_24h": recent[0] if recent else 0,
                "unique_fixtures": fixtures[0] if fixtures else 0,
            }
        except Exception as e:
            logger.error(f"❌ get_stats error: {e}")
            return {}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _name_match(db_name: str, query_name: str) -> bool:
    """Fuzzy team name comparison — checks if either string contains the other."""
    if not db_name or not query_name:
        return False
    d = db_name.lower().strip()
    q = query_name.lower().strip()
    return d in q or q in d or d[:8] == q[:8]


def _empty_report(home_team: str, away_team: str) -> Dict:
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_injuries": [],
        "home_injury_count": 0,
        "away_injuries": [],
        "away_injury_count": 0,
        "total_injuries": 0,
        "has_key_injuries": False,
    }
