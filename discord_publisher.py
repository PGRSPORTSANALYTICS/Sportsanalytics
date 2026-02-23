"""
Discord Publisher for PGR Sports Analytics v2
Routes AI analysis picks to league-specific Discord channels via webhooks.
Runs as a worker loop (every 60s), fetches pending picks, dedupes, and posts embeds.

IMPORTANT: This posts ANALYSIS/INFO only — no staking, no units, no "bet" language.
"""

import os
import json
import time
import hashlib
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DISCORD-PUB] %(message)s")
logger = logging.getLogger("discord_publisher")

# ---------------------------------------------------------------------------
# DATABASE CONNECTION (reuse project's db_connection module)
# ---------------------------------------------------------------------------
try:
    from db_connection import DatabaseConnection
except ImportError:
    logger.error("Could not import db_connection — publisher cannot run without DB")
    raise

# ---------------------------------------------------------------------------
# LEAGUE -> WEBHOOK MAPPING
# Paste your Discord webhook URLs here per league.
# If a league is not mapped, it falls back to DEFAULT_WEBHOOK.
# ---------------------------------------------------------------------------
# >>>>>>>>>> PASTE YOUR WEBHOOK URLs BELOW <<<<<<<<<<
LEAGUE_WEBHOOKS: Dict[str, str] = {
    # "Premier League":           os.getenv("DISCORD_WH_PREMIER_LEAGUE", ""),
    # "La Liga":                  os.getenv("DISCORD_WH_LA_LIGA", ""),
    # "Bundesliga":               os.getenv("DISCORD_WH_BUNDESLIGA", ""),
    # "Serie A":                  os.getenv("DISCORD_WH_SERIE_A", ""),
    # "Ligue 1":                  os.getenv("DISCORD_WH_LIGUE_1", ""),
    # "Eredivisie":               os.getenv("DISCORD_WH_EREDIVISIE", ""),
    # "Champions League":         os.getenv("DISCORD_WH_CHAMPIONS_LEAGUE", ""),
    # "Europa League":            os.getenv("DISCORD_WH_EUROPA_LEAGUE", ""),
    # "English Championship":     os.getenv("DISCORD_WH_CHAMPIONSHIP", ""),
    # "English League One":       os.getenv("DISCORD_WH_LEAGUE_ONE", ""),
    # "English League Two":       os.getenv("DISCORD_WH_LEAGUE_TWO", ""),
    # "Portuguese Primeira Liga": os.getenv("DISCORD_WH_PRIMEIRA_LIGA", ""),
    # "Belgian First Division":   os.getenv("DISCORD_WH_BELGIAN", ""),
}
# >>>>>>>>>> END WEBHOOK URLs <<<<<<<<<<

DEFAULT_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

RATE_LIMIT_SECONDS = 2.0
DEDUPE_TTL_HOURS = 48
DEDUPE_FILE = "discord_publisher_dedupe.json"
POLL_INTERVAL = 60
BOT_USERNAME = "PGR Analytics"

# ---------------------------------------------------------------------------
# DEDUPE CACHE
# ---------------------------------------------------------------------------

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
    raw = f"{pick.get('league','')}|{pick.get('home_team','')}|{pick.get('away_team','')}|{pick.get('market','')}|{pick.get('match_date','')}|{pick.get('odds','')}"
    return hashlib.md5(raw.encode()).hexdigest()

# ---------------------------------------------------------------------------
# LEAGUE DISCOVERY
# ---------------------------------------------------------------------------

def discover_leagues(picks: List[dict]) -> List[str]:
    leagues = sorted(set(p.get("league", "Unknown") for p in picks))
    logger.info("=" * 50)
    logger.info(f"LEAGUE DISCOVERY — {len(leagues)} unique leagues in feed:")
    for lg in leagues:
        mapped = "MAPPED" if lg in LEAGUE_WEBHOOKS and LEAGUE_WEBHOOKS[lg] else "DEFAULT"
        logger.info(f"  • {lg:35s} [{mapped}]")
    logger.info("=" * 50)
    return leagues

# ---------------------------------------------------------------------------
# WEBHOOK ROUTING
# ---------------------------------------------------------------------------

def route_webhook(league: str) -> str:
    url = LEAGUE_WEBHOOKS.get(league, "")
    if url:
        return url
    return DEFAULT_WEBHOOK

# ---------------------------------------------------------------------------
# MESSAGE FORMATTING (Discord Embed — analysis only)
# ---------------------------------------------------------------------------

def _format_kickoff(match_date) -> str:
    if not match_date:
        return "TBD"
    try:
        if isinstance(match_date, datetime):
            dt = match_date
        else:
            s = str(match_date).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
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


def _confidence_emoji(confidence) -> str:
    try:
        c = int(confidence)
    except (TypeError, ValueError):
        return ""
    if c >= 90:
        return "HIGH TRUST"
    elif c >= 75:
        return "MEDIUM TRUST"
    else:
        return "STANDARD"


def format_message(pick: dict) -> dict:
    home = pick.get("home_team", "?")
    away = pick.get("away_team", "?")
    league = pick.get("league", "Unknown")
    market = pick.get("market", "")
    selection = pick.get("selection", market)
    odds = float(pick.get("odds", 0) or 0)
    edge = float(pick.get("edge_percentage", 0) or 0)
    confidence = pick.get("confidence", "")
    kickoff = _format_kickoff(pick.get("match_date"))

    conf_label = _confidence_emoji(confidence)
    conf_line = f"**Trust Level:** {conf_label}" if conf_label else ""

    description = (
        f"**Match:** {home} vs {away}\n"
        f"**League:** {league}\n"
        f"**Market:** {selection}\n"
        f"**Odds:** {odds:.2f}\n"
        f"**EV:** {edge:.1f}%\n"
        f"**Kickoff:** {kickoff}\n"
    )
    if conf_line:
        description += f"{conf_line}\n"

    description += "\n*AI Modeling / Info*"

    embed = {
        "title": f"{home} vs {away}",
        "description": description,
        "color": 3066993,
        "footer": {"text": f"PGR Sports Analytics — {league} | Analysis Only"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {
        "username": BOT_USERNAME,
        "embeds": [embed],
    }
    return payload

# ---------------------------------------------------------------------------
# FETCH PENDING PICKS FROM DATABASE
# ---------------------------------------------------------------------------

def fetch_pending_picks() -> List[dict]:
    query = """
        SELECT id, league, home_team, away_team, market, selection, odds,
               edge_percentage, match_date, confidence, mode, status
        FROM football_opportunities
        WHERE status = 'pending'
          AND mode IN ('PROD', 'PRODUCTION')
          AND match_date::date >= CURRENT_DATE
        ORDER BY match_date ASC
    """
    try:
        with DatabaseConnection.get_cursor(dict_cursor=True) as cur:
            cur.execute(query)
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"DB fetch error: {e}")
        return []

# ---------------------------------------------------------------------------
# POST TO DISCORD
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# MAIN PUBLISH CYCLE
# ---------------------------------------------------------------------------

def run_publish_cycle():
    logger.info("--- Publish cycle start ---")

    picks = fetch_pending_picks()
    if not picks:
        logger.info("No pending picks found")
        return

    logger.info(f"Fetched {len(picks)} pending pick(s)")

    discover_leagues(picks)

    dedupe_cache = _load_dedupe_cache()

    stats = {"posted": 0, "deduped": 0, "unknown_league": 0, "errors": 0}
    last_post_per_webhook: Dict[str, float] = {}

    for pick in picks:
        key = _dedupe_key(pick)
        if key in dedupe_cache:
            stats["deduped"] += 1
            continue

        league = pick.get("league", "Unknown")
        webhook_url = route_webhook(league)

        if webhook_url == DEFAULT_WEBHOOK and league not in ("Unknown", ""):
            if league not in LEAGUE_WEBHOOKS:
                stats["unknown_league"] += 1

        if not webhook_url:
            logger.warning(f"No webhook available for league '{league}' — skipping")
            stats["errors"] += 1
            continue

        now = time.time()
        last_time = last_post_per_webhook.get(webhook_url, 0)
        wait = RATE_LIMIT_SECONDS - (now - last_time)
        if wait > 0:
            time.sleep(wait)

        payload = format_message(pick)
        success = post_to_discord(webhook_url, payload)

        if success:
            stats["posted"] += 1
            dedupe_cache[key] = time.time()
            last_post_per_webhook[webhook_url] = time.time()
            pick_id = pick.get("id", "?")
            logger.info(f"Posted pick #{pick_id}: {pick.get('home_team')} vs {pick.get('away_team')} [{league}]")
        else:
            stats["errors"] += 1

    _save_dedupe_cache(dedupe_cache)

    logger.info(
        f"Cycle done — "
        f"fetched={len(picks)}, posted={stats['posted']}, "
        f"deduped={stats['deduped']}, unknown_league={stats['unknown_league']}, "
        f"errors={stats['errors']}"
    )

# ---------------------------------------------------------------------------
# WORKER LOOP
# ---------------------------------------------------------------------------

def main():
    logger.info("Discord Publisher starting (analysis-only mode)")
    logger.info(f"Poll interval: {POLL_INTERVAL}s | Dedupe TTL: {DEDUPE_TTL_HOURS}h | Rate limit: {RATE_LIMIT_SECONDS}s/webhook")

    mapped_count = sum(1 for v in LEAGUE_WEBHOOKS.values() if v)
    logger.info(f"League webhooks configured: {mapped_count} | Default webhook: {'SET' if DEFAULT_WEBHOOK else 'MISSING'}")

    while True:
        try:
            run_publish_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
