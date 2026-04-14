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

    def _upsert_injuries(self, fixture: Dict, players: List[Dict], polled_at: int) -> int:
        """
        Upsert player injury records into proactive_injuries.
        ON CONFLICT (fixture_id, player_name) → update injury_type, reason, polled_at.

        Returns number of rows inserted/updated.
        """
        count = 0
        for player in players:
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
                    player.get("reason", ""),
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
        Looks up by team name in proactive_injuries (recent records only).

        Returns dict with home_injuries, away_injuries lists and totals.
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
                ORDER BY polled_at DESC
            """, (
                f"%{home_team}%", f"%{home_team}%",
                f"%{away_team}%", f"%{away_team}%",
                cutoff,
            ), fetch="all") or []

            home_injuries, away_injuries = [], []
            for row in rows:
                team, player, inj_type, reason, polled = row
                entry = {
                    "player_name": player,
                    "injury_type": inj_type or "",
                    "reason": reason or "",
                    "polled_at": polled,
                }
                # Classify to home or away by fuzzy team name match
                if _name_match(team, home_team):
                    home_injuries.append(entry)
                elif _name_match(team, away_team):
                    away_injuries.append(entry)

            return {
                "home_team": home_team,
                "away_team": away_team,
                "home_injuries": home_injuries,
                "home_injury_count": len(home_injuries),
                "away_injuries": away_injuries,
                "away_injury_count": len(away_injuries),
                "total_injuries": len(home_injuries) + len(away_injuries),
                "has_key_injuries": (len(home_injuries) + len(away_injuries)) >= 2,
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
                    COUNT(*) as injury_count,
                    COUNT(DISTINCT team_name) as teams_affected,
                    MAX(polled_at) as last_polled
                FROM proactive_injuries
                WHERE kickoff_epoch BETWEEN %s AND %s
                GROUP BY fixture_id, home_team, away_team, league_name, kickoff_epoch
                ORDER BY kickoff_epoch ASC
            """, (cutoff_ko, max_ko), fetch="all") or []

            results = []
            for row in rows:
                results.append({
                    "fixture_id": row[0],
                    "home_team": row[1],
                    "away_team": row[2],
                    "league_name": row[3],
                    "kickoff_epoch": row[4],
                    "kickoff_utc": datetime.fromtimestamp(row[4], tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M"
                    ) if row[4] else "?",
                    "injury_count": row[5],
                    "teams_affected": row[6],
                    "last_polled": row[7],
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
