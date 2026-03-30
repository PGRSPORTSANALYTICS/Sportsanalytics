"""
Discord Publisher for PGR Sports Analytics v2
Routes AI analysis data to league-specific Discord channels via webhooks.

CRITICAL SEPARATION:
  - This publisher sends ANALYSIS/DATA ONLY — no staking, no units, no "bet" language.
  - All positive EV opportunities (PROD + LEARNING) are published as value analysis.
  - Internal pick system (discord_notifier.py) handles actual picks with units for AI tracking.

The AI engine can independently select from these same opportunities for real picks,
but what goes to Discord customers is purely informational data analysis.
"""

import os
import json
import time
import hashlib
import logging
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [DISCORD-PUB] %(message)s")
logger = logging.getLogger("discord_publisher")

try:
    from db_connection import DatabaseConnection
except ImportError:
    logger.error("Could not import db_connection — publisher cannot run without DB")
    raise

LEAGUE_WEBHOOKS: Dict[str, str] = {
    "Premier League":               os.getenv("DISCORD_WH_PREMIER_LEAGUE", ""),
    "La Liga":                      os.getenv("DISCORD_WH_LA_LIGA", ""),
    "Bundesliga":                   os.getenv("DISCORD_WH_BUNDESLIGA", ""),
    "Serie A":                      os.getenv("DISCORD_WH_SERIE_A", ""),
    "Ligue 1":                      os.getenv("DISCORD_WH_LIGUE_1", ""),
    "Eredivisie":                   os.getenv("DISCORD_WH_EREDIVISIE", ""),
    "Champions League":             os.getenv("DISCORD_WH_CHAMPIONS_LEAGUE", ""),
    "Europa League":                os.getenv("DISCORD_WH_EUROPA_LEAGUE", ""),
    "Conference League":            os.getenv("DISCORD_WH_CONFERENCE_LEAGUE", ""),
    "English Championship":         os.getenv("DISCORD_WH_CHAMPIONSHIP", ""),
    "English League One":           os.getenv("DISCORD_WH_LEAGUE_ONE", ""),
    "English League Two":           os.getenv("DISCORD_WH_LEAGUE_TWO", ""),
    "Portuguese Primeira Liga":     os.getenv("DISCORD_WH_PRIMEIRA_LIGA", ""),
    "Primeira Liga":                os.getenv("DISCORD_WH_PRIMEIRA_LIGA", ""),
    "Belgian First Division":       os.getenv("DISCORD_WH_BELGIAN", ""),
    "Turkish Super League":         os.getenv("DISCORD_WH_TURKISH", ""),
    "Greek Super League":           os.getenv("DISCORD_WH_GREEK", ""),
    "Scottish Premiership":         os.getenv("DISCORD_WH_SCOTTISH", ""),
    "Swedish Allsvenskan":          os.getenv("DISCORD_WH_ALLSVENSKAN", ""),
    "Norwegian Eliteserien":        os.getenv("DISCORD_WH_ELITESERIEN", ""),
    "Danish Superliga":             os.getenv("DISCORD_WH_DANISH", ""),
    "Austrian Bundesliga":          os.getenv("DISCORD_WH_AUSTRIAN", ""),
    "Swiss Super League":           os.getenv("DISCORD_WH_SWISS", ""),
    "Polish Ekstraklasa":           os.getenv("DISCORD_WH_POLISH", ""),
    "Czech First League":           os.getenv("DISCORD_WH_CZECH", ""),
    "Major League Soccer":          os.getenv("DISCORD_WH_MLS", ""),
    "Brazilian Serie A":            os.getenv("DISCORD_WH_BRASILEIRAO", ""),
    "Argentinian Primera Division": os.getenv("DISCORD_WH_ARGENTINA", ""),
    "Liga MX":                      os.getenv("DISCORD_WH_LIGA_MX", ""),
    "Japanese J1 League":           os.getenv("DISCORD_WH_J_LEAGUE", ""),
    "Korean K League 1":            os.getenv("DISCORD_WH_K_LEAGUE", ""),
    "Australian A-League":          os.getenv("DISCORD_WH_A_LEAGUE", ""),
    "German 2. Bundesliga":         os.getenv("DISCORD_WH_BUNDESLIGA2", ""),
    "Spanish Segunda Division":     os.getenv("DISCORD_WH_LA_LIGA2", ""),
    "Italian Serie B":              os.getenv("DISCORD_WH_SERIE_B", ""),
    "French Ligue 2":               os.getenv("DISCORD_WH_LIGUE_2", ""),
    "Dutch Eerste Divisie":         os.getenv("DISCORD_WH_EERSTE_DIVISIE", ""),
    "Portuguese Segunda Liga":      os.getenv("DISCORD_WH_SEGUNDA_LIGA", ""),
}

DEFAULT_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

RATE_LIMIT_SECONDS = 2.0
DEDUPE_TTL_HOURS = 48
DEDUPE_FILE = "discord_publisher_dedupe.json"
BOT_USERNAME = "PGR Analytics"

MARKET_DISPLAY = {
    "HOME_WIN": "Home Win (1)",
    "DRAW": "Draw (X)",
    "AWAY_WIN": "Away Win (2)",
    "OVER_2_5": "Over 2.5 Goals",
    "UNDER_2_5": "Under 2.5 Goals",
    "OVER_1_5": "Over 1.5 Goals",
    "UNDER_1_5": "Under 1.5 Goals",
    "OVER_3_5": "Over 3.5 Goals",
    "UNDER_3_5": "Under 3.5 Goals",
    "OVER_4_5": "Over 4.5 Goals",
    "OVER_0_5": "Over 0.5 Goals",
    "BTTS_YES": "Both Teams to Score — Yes",
    "BTTS_NO": "Both Teams to Score — No",
    "DC_HOME_DRAW": "Double Chance — Home or Draw (1X)",
    "DC_HOME_AWAY": "Double Chance — Home or Away (12)",
    "DC_DRAW_AWAY": "Double Chance — Draw or Away (X2)",
    "DNB_HOME": "Draw No Bet — Home",
    "DNB_AWAY": "Draw No Bet — Away",
    "HOME_OVER_0_5": "Home Team Over 0.5 Goals",
    "HOME_OVER_1_5": "Home Team Over 1.5 Goals",
    "AWAY_OVER_0_5": "Away Team Over 0.5 Goals",
    "AWAY_OVER_1_5": "Away Team Over 1.5 Goals",
    "1H_OVER_0_5": "1st Half Over 0.5 Goals",
    "CORNERS": "Corners",
    "CARDS": "Cards",
}

EMBED_COLORS = {
    "high": 0x2ECC71,
    "medium": 0x3498DB,
    "standard": 0x95A5A6,
}


def _load_dedupe_cache() -> Dict[str, float]:
    if not os.path.exists(DEDUPE_FILE):
        return {}
    try:
        with open(DEDUPE_FILE, "r") as f:
            data = json.load(f)
        cutoff = time.time() - (DEDUPE_TTL_HOURS * 3600)
        return {k: v for k, v in data.items() if v > cutoff}
    except Exception:
        return {}


def _save_dedupe_cache(cache: Dict[str, float]):
    try:
        with open(DEDUPE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logger.warning(f"Could not save dedupe cache: {e}")


def _dedupe_key(pick: dict) -> str:
    raw = (f"{pick.get('league','')}|{pick.get('home_team','')}|"
           f"{pick.get('away_team','')}|{pick.get('market','')}|"
           f"{pick.get('match_date','')}|{pick.get('odds','')}")
    return hashlib.md5(raw.encode()).hexdigest()


# Markets that are mutually exclusive on the same match — only ONE per group per match
_CONFLICT_GROUPS = {
    "HOME_WIN":    "1X2",
    "AWAY_WIN":    "1X2",
    "DRAW":        "1X2",
    "Home Win":    "1X2",
    "Away Win":    "1X2",
    "Draw":        "1X2",
    "FT_OVER_2_5":  "TOTALS_2_5",
    "FT_UNDER_2_5": "TOTALS_2_5",
    "Over 2.5 Goals":  "TOTALS_2_5",
    "Under 2.5 Goals": "TOTALS_2_5",
    "FT_OVER_3_5":  "TOTALS_3_5",
    "FT_UNDER_3_5": "TOTALS_3_5",
    "BTTS_YES": "BTTS",
    "BTTS_NO":  "BTTS",
    "BTTS Yes": "BTTS",
    "BTTS No":  "BTTS",
}


def _conflict_group_key(pick: dict) -> Optional[str]:
    """Returns a key representing 'match + market group', or None if no conflict group."""
    market = pick.get("selection") or pick.get("market", "")
    group = _CONFLICT_GROUPS.get(market)
    if not group:
        return None
    raw = (f"conflict|{pick.get('home_team','')}|{pick.get('away_team','')}|"
           f"{pick.get('match_date','')}|{group}")
    return hashlib.md5(raw.encode()).hexdigest()


def _db_contradicts_already_sent(pick: dict) -> bool:
    """DB-based contradiction check — survives engine restarts.
    Blocks Over/Under same line, BTTS Yes/No, and 1X2 opposites for the same match."""
    selection = (pick.get("selection") or "").strip()
    home = pick.get("home_team", "")
    away = pick.get("away_team", "")
    match_date = pick.get("match_date", "")
    pick_id = pick.get("id", -1)

    if not selection or not home or not away:
        return False

    try:
        with DatabaseConnection.get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM football_opportunities
                WHERE home_team = %s AND away_team = %s AND match_date = %s
                  AND discord_sent = true
                  AND id != %s
                  AND (
                    (
                      %s ILIKE '%%Over%%' AND selection ILIKE '%%Under%%'
                      AND REGEXP_REPLACE(%s, '[^0-9.]', '', 'g') != ''
                      AND REGEXP_REPLACE(%s, '[^0-9.]', '', 'g') =
                          REGEXP_REPLACE(selection, '[^0-9.]', '', 'g')
                    ) OR (
                      %s ILIKE '%%Under%%' AND selection ILIKE '%%Over%%'
                      AND REGEXP_REPLACE(%s, '[^0-9.]', '', 'g') != ''
                      AND REGEXP_REPLACE(%s, '[^0-9.]', '', 'g') =
                          REGEXP_REPLACE(selection, '[^0-9.]', '', 'g')
                    )
                    OR (%s = 'BTTS Yes' AND selection = 'BTTS No')
                    OR (%s = 'BTTS No'  AND selection = 'BTTS Yes')
                    OR (
                      %s IN ('Home Win','Away Win','Draw')
                      AND selection IN ('Home Win','Away Win','Draw')
                      AND selection != %s
                    )
                  )
            """, (
                home, away, match_date, pick_id,
                selection, selection, selection,
                selection, selection, selection,
                selection, selection,
                selection, selection,
            ))
            count = cur.fetchone()[0]
            return count > 0
    except Exception as e:
        logger.error(f"Contradiction DB check error: {e}")
        return False


def route_webhook(league: str) -> str:
    url = LEAGUE_WEBHOOKS.get(league, "")
    if url:
        return url
    return DEFAULT_WEBHOOK


def _format_kickoff(match_date) -> str:
    if not match_date:
        return "TBD"
    try:
        if isinstance(match_date, datetime):
            dt = match_date
        else:
            s = str(match_date).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z",
                        "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(s[:len(fmt) + 5], fmt)
                    break
                except ValueError:
                    continue
            else:
                return str(match_date)
        return dt.strftime("%b %d, %H:%M UTC") if dt.hour or dt.minute else dt.strftime("%b %d")
    except Exception:
        return str(match_date)


def _trust_label(confidence) -> str:
    try:
        c = int(confidence)
    except (TypeError, ValueError):
        return ""
    if c >= 90:
        return "HIGH"
    elif c >= 75:
        return "MEDIUM"
    return "STANDARD"


def _edge_color(edge: float) -> int:
    if edge >= 10:
        return EMBED_COLORS["high"]
    elif edge >= 5:
        return EMBED_COLORS["medium"]
    return EMBED_COLORS["standard"]


def _build_analysis_line(pick: dict) -> str:
    parts = []

    analysis_raw = pick.get("analysis")
    if analysis_raw:
        try:
            analysis = json.loads(analysis_raw) if isinstance(analysis_raw, str) else analysis_raw
            if isinstance(analysis, dict):
                xg_h = analysis.get("expected_home_goals")
                xg_a = analysis.get("expected_away_goals")
                if xg_h is not None and xg_a is not None:
                    parts.append(f"xG {float(xg_h) + float(xg_a):.1f}")
        except Exception:
            pass

    # Prefer calibrated_prob (adjusted) over raw model_prob for accuracy
    model_prob = pick.get("calibrated_prob") or pick.get("model_prob")
    odds = float(pick.get("odds", 0) or 0)
    if model_prob and odds > 1:
        mp = float(model_prob)
        if mp < 1:
            mp *= 100
        implied = (1 / odds) * 100
        parts.append(f"Model {mp:.0f}% vs Implied {implied:.0f}%")

    if not parts:
        return ""
    return "_" + " | ".join(parts) + "_"


def _format_odds_shopping(pick: dict) -> str:
    """Format top bookmaker odds as a compact shopping line for Discord."""
    odds_by_book = pick.get("odds_by_bookmaker")
    best_value = pick.get("best_odds_value")
    best_book = pick.get("best_odds_bookmaker")
    model_odds = float(pick.get("odds", 0) or 0)

    if not odds_by_book:
        return ""
    try:
        if isinstance(odds_by_book, str):
            odds_by_book = json.loads(odds_by_book)
    except Exception:
        return ""
    if not isinstance(odds_by_book, dict) or not odds_by_book:
        return ""

    sorted_books = sorted(
        [(b, float(o)) for b, o in odds_by_book.items() if o],
        key=lambda x: x[1], reverse=True
    )
    if not sorted_books:
        return ""

    top3 = sorted_books[:3]
    parts = [f"**{o:.2f}** {b}" for b, o in top3]
    line = "🔍 " + " · ".join(parts)

    if best_value and best_book:
        bv = float(best_value)
        if bv > model_odds * 1.02:
            line += f"\n🔝 Best: **{bv:.2f}** @ {best_book}"

    return line


def format_analysis_embed(pick: dict) -> dict:
    home = pick.get("home_team", "?")
    away = pick.get("away_team", "?")
    league = pick.get("league", "Unknown")
    market = pick.get("market", "")
    selection = pick.get("selection", market)
    odds = float(pick.get("odds", 0) or 0)
    edge = float(pick.get("edge_percentage", 0) or 0)
    confidence = pick.get("confidence", "")
    mode = pick.get("mode", "")
    kickoff = _format_kickoff(pick.get("match_date"))

    display_market = MARKET_DISPLAY.get(market, selection or market)

    trust = _trust_label(confidence)

    lines = []
    lines.append(f"**{home}** vs **{away}**")
    lines.append(f"Market: {display_market}")
    lines.append(f"Odds: {odds:.2f}")

    odds_line = _format_odds_shopping(pick)
    if odds_line:
        lines.append(odds_line)

    lines.append(f"Edge: +{edge:.1f}%")
    if trust:
        lines.append(f"Trust: {trust}")
    lines.append(f"Kickoff: {kickoff}")

    analysis_line = _build_analysis_line(pick)
    if analysis_line:
        lines.append("")
        lines.append(analysis_line)

    color = _edge_color(edge)

    analysis_data = {}
    try:
        import json as _json
        analysis_data = _json.loads(pick.get("analysis") or "{}") or {}
    except Exception:
        pass
    pgr_score = pick.get("pgr_score") or analysis_data.get("pgr_score")
    league_tier = pick.get("league_tier") or analysis_data.get("league_tier")
    pgr_str = f" · PGR {float(pgr_score):.1f}" if pgr_score is not None else ""
    tier_str = f" [T{league_tier}]" if league_tier else ""

    if mode == "DATA":
        title = f"Match Analysis — {league}"
        color = 0x808080
    elif mode == "PROD":
        title = f"\U0001f3af PRO PICK{pgr_str}{tier_str} — {league}"
        color = 0x00C853
    elif mode == "VALUE_OPP":
        title = f"\U0001f4ca VALUE OPPORTUNITY{pgr_str}{tier_str} — {league}"
        color = 0xFFAA00
    elif mode == "WATCHLIST":
        return None
    else:
        title = f"\U0001f4ca VALUE OPPORTUNITY — {league}"

    if pgr_score is not None:
        try:
            lines.append(f"PGR Score: {float(pgr_score):.1f}")
        except Exception:
            pass
    if league_tier:
        lines.append(f"League Tier: {league_tier}")

    # Show when odds were collected so users know data freshness
    raw_ts = pick.get("timestamp") or pick.get("open_ts")
    if raw_ts:
        try:
            from datetime import timezone as _tz
            odds_dt = datetime.fromtimestamp(float(raw_ts), tz=_tz.utc)
            odds_time_str = odds_dt.strftime("%H:%M UTC")
        except Exception:
            odds_time_str = None
    else:
        odds_time_str = None

    footer_text = "PGR Sports Analytics | Data Analysis Only — Not Financial Advice"
    if odds_time_str:
        footer_text += f" | Odds from {odds_time_str}"

    embed = {
        "title": title,
        "description": "\n".join(lines),
        "color": color,
        "footer": {
            "text": footer_text
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "username": BOT_USERNAME,
        "embeds": [embed],
    }


DISCORD_BLOCKED_SELECTION_PATTERNS = [
    "%-0.5 (AH)%",
    "%-1.0 (AH)%",
    "%-1.5 (AH)%",
    "%-2.0 (AH)%",
]


def fetch_analysis_picks() -> List[dict]:
    blocked_clauses = " AND ".join(
        [f"selection NOT ILIKE %s" for _ in DISCORD_BLOCKED_SELECTION_PATTERNS]
    )
    query = f"""
        SELECT id, league, home_team, away_team, market, selection, odds,
               edge_percentage, match_date, confidence, mode, status,
               model_prob, calibrated_prob, analysis, discord_sent,
               odds_by_bookmaker, best_odds_value, best_odds_bookmaker,
               kickoff_epoch, open_ts,
               pgr_score, league_tier, routing_reason
        FROM football_opportunities
        WHERE status = 'pending'
          AND mode IN ('PROD', 'VALUE_OPP')
          AND edge_percentage >= 10
          AND odds > 1.0
          AND match_date::date >= CURRENT_DATE
          AND (kickoff_epoch IS NULL OR kickoff_epoch > EXTRACT(EPOCH FROM NOW())::bigint)
          AND (discord_sent IS NULL OR discord_sent = false)
          AND selection NOT IN ('Home Win', 'Away Win', 'Draw', 'BTTS No')
          AND ({blocked_clauses})
        ORDER BY match_date ASC, edge_percentage DESC
    """
    try:
        with DatabaseConnection.get_cursor(dict_cursor=True) as cur:
            cur.execute(query, DISCORD_BLOCKED_SELECTION_PATTERNS)
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"DB fetch error: {e}")
        return []


def mark_discord_sent(pick_ids):
    if not pick_ids:
        return
    if isinstance(pick_ids, int):
        pick_ids = [pick_ids]
    try:
        with DatabaseConnection.get_cursor() as cur:
            cur.execute(
                "UPDATE football_opportunities SET discord_sent = true WHERE id = ANY(%s)",
                (pick_ids,)
            )
    except Exception as e:
        logger.error(f"Failed to mark discord_sent: {e}")


def post_to_discord(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        logger.warning("No webhook URL — skipping post")
        return False
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return True
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            logger.warning(f"Rate limited — waiting {retry_after}s")
            time.sleep(retry_after)
            resp2 = requests.post(webhook_url, json=payload, timeout=10)
            return resp2.status_code in (200, 204)
        else:
            logger.error(f"Discord HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Discord post failed: {e}")
        return False


def _best_pick_per_match(picks: List[dict]) -> List[dict]:
    """Keep only the highest-EV pick per match. PROD > VALUE_OPP; within same mode, higher EV wins."""
    MODE_PRIORITY = {"PROD": 2, "VALUE_OPP": 1}
    seen: Dict[str, dict] = {}
    for pick in picks:
        key = (
            (pick.get("home_team") or "").lower().strip(),
            (pick.get("away_team") or "").lower().strip(),
            pick.get("match_date", ""),
        )
        ev = float(pick.get("edge_percentage") or 0)
        mode = (pick.get("mode") or "").upper()
        mode_rank = MODE_PRIORITY.get(mode, 0)
        existing = seen.get(key)
        if not existing:
            seen[key] = pick
        else:
            existing_mode = (existing.get("mode") or "").upper()
            existing_rank = MODE_PRIORITY.get(existing_mode, 0)
            existing_ev = float(existing.get("edge_percentage") or 0)
            # Higher mode priority wins; within same priority, higher EV wins
            if mode_rank > existing_rank:
                seen[key] = pick
            elif mode_rank == existing_rank and ev > existing_ev:
                seen[key] = pick
    return list(seen.values())


def run_publish_cycle():
    logger.info("--- Analysis publish cycle start ---")

    picks = fetch_analysis_picks()
    if not picks:
        logger.info("No new analysis data to publish")
        return 0

    logger.info(f"Found {len(picks)} analysis opportunities before match-dedup")

    # One best pick per match (highest EV, PROD > LEARNING)
    all_picks = picks
    picks = _best_pick_per_match(all_picks)
    logger.info(f"After match-dedup: {len(picks)} picks to publish")

    # Mark non-winners as discord_sent so they don't repeat next cycle
    winner_ids = {p["id"] for p in picks}
    for skipped in all_picks:
        if skipped["id"] not in winner_ids:
            mark_discord_sent(skipped["id"])

    leagues_found = sorted(set(p.get("league", "?") for p in picks))
    modes = {}
    for p in picks:
        m = p.get("mode", "?")
        modes[m] = modes.get(m, 0) + 1
    logger.info(f"  Leagues: {', '.join(leagues_found)}")
    logger.info(f"  Modes: {modes}")

    dedupe_cache = _load_dedupe_cache()
    stats = {"posted": 0, "deduped": 0, "no_webhook": 0, "errors": 0}
    last_post_per_webhook: Dict[str, float] = {}

    for pick in picks:
        key = _dedupe_key(pick)
        if key in dedupe_cache:
            stats["deduped"] += 1
            mark_discord_sent(pick["id"])
            continue

        # Block opposing/conflicting markets on the same match (e.g. Home Win + Away Win)
        conflict_key = _conflict_group_key(pick)
        if conflict_key and conflict_key in dedupe_cache:
            stats["deduped"] += 1
            market = pick.get("selection") or pick.get("market", "")
            logger.info(
                f"  CONFLICT BLOCKED (cache): {pick.get('home_team')} vs {pick.get('away_team')} "
                f"— {market} conflicts with already-published pick for this match"
            )
            mark_discord_sent(pick["id"])
            continue

        # DB-based contradiction check — catches conflicts across engine restarts
        if _db_contradicts_already_sent(pick):
            stats["deduped"] += 1
            market = pick.get("selection") or pick.get("market", "")
            logger.info(
                f"  CONTRADICTION BLOCKED (DB): {pick.get('home_team')} vs {pick.get('away_team')} "
                f"— {market} contradicts an already-sent pick for this match"
            )
            mark_discord_sent(pick["id"])
            continue

        league = pick.get("league", "Unknown")
        webhook_url = route_webhook(league)

        if not webhook_url:
            stats["no_webhook"] += 1
            logger.debug(f"No webhook for '{league}' — skipping")
            continue

        now = time.time()
        last_time = last_post_per_webhook.get(webhook_url, 0)
        wait = RATE_LIMIT_SECONDS - (now - last_time)
        if wait > 0:
            time.sleep(wait)

        payload = format_analysis_embed(pick)
        if payload is None:
            stats["deduped"] = stats.get("deduped", 0) + 1
            mark_discord_sent(pick["id"])
            continue
        success = post_to_discord(webhook_url, payload)

        if success:
            stats["posted"] += 1
            dedupe_cache[key] = time.time()
            # Also store the conflict group key so no opposing market gets published later
            if conflict_key:
                dedupe_cache[conflict_key] = time.time()
            last_post_per_webhook[webhook_url] = time.time()
            mark_discord_sent(pick["id"])
            logger.info(
                f"  Published: {pick.get('home_team')} vs {pick.get('away_team')} "
                f"[{league}] {pick.get('market')} @ {pick.get('odds')} "
                f"(mode={pick.get('mode')})"
            )
        else:
            stats["errors"] += 1

    _save_dedupe_cache(dedupe_cache)

    logger.info(
        f"Cycle done — posted={stats['posted']}, deduped={stats['deduped']}, "
        f"no_webhook={stats['no_webhook']}, errors={stats['errors']}"
    )
    return stats["posted"]


def publish_after_cycle():
    try:
        count = run_publish_cycle()
        if count > 0:
            logger.info(f"Published {count} analysis entries to Discord")
        return count
    except Exception as e:
        logger.error(f"Analysis publish error: {e}", exc_info=True)
        return 0


def discover_webhook_status():
    configured = []
    missing = []
    for league, url in LEAGUE_WEBHOOKS.items():
        if url:
            configured.append(league)
        else:
            missing.append(league)
    return configured, missing


def main():
    logger.info("=" * 60)
    logger.info("Discord Analysis Publisher v2.0 — Starting")
    logger.info("MODE: Analysis/Data Only — NO units, NO staking")
    logger.info("=" * 60)

    configured, missing = discover_webhook_status()
    logger.info(f"Webhooks configured: {len(configured)}/{len(LEAGUE_WEBHOOKS)}")
    if missing:
        logger.info(f"Missing webhooks: {', '.join(missing[:10])}{'...' if len(missing) > 10 else ''}")
    if DEFAULT_WEBHOOK:
        logger.info("Default fallback webhook: SET")
    else:
        logger.warning("Default fallback webhook: MISSING — unmapped leagues won't publish")

    poll_interval = 60
    while True:
        try:
            run_publish_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
