"""
Live Props Tracker v2.0
=======================
Real-time tracking of ongoing Cards AND Corners picks using API-Football live data.
Shows current count vs target line for pending bets.
"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional
from db_connection import DatabaseConnection

logger = logging.getLogger(__name__)

LIVE_STATUSES = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "INT"}
FINISHED_STATUSES = {"FT", "AET", "PEN"}
NOT_STARTED_STATUSES = {"NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO"}


def get_pending_props_bets(market_filter: str = "all") -> List[Dict]:
    try:
        if market_filter == "cards":
            market_clause = "market = 'Cards'"
        elif market_filter == "corners":
            market_clause = "market = 'Corners'"
        else:
            market_clause = "market IN ('Cards', 'Corners')"

        with DatabaseConnection.get_cursor(dict_cursor=True) as cur:
            cur.execute("SET statement_timeout = '8000'")
            cur.execute(f"""
                SELECT id, home_team, away_team, league, market, selection, odds, 
                       match_date, kickoff_epoch, fixture_id, 
                       edge_percentage, trust_level, mode
                FROM football_opportunities
                WHERE {market_clause}
                  AND status = 'pending'
                  AND mode IN ('PROD', 'PRODUCTION')
                ORDER BY kickoff_epoch ASC
            """)
            rows = cur.fetchall()
        return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.error(f"Failed to get pending props bets: {e}")
        return []


def get_pending_cards_bets() -> List[Dict]:
    return get_pending_props_bets("cards")


def parse_selection(selection: str, market: str = "Cards", home_team: str = "", away_team: str = "") -> Dict:
    sel = selection.strip()
    direction = "over"
    line = 0.0
    scope = "match"
    team_name = ""

    lower = sel.lower()
    if "under" in lower:
        direction = "under"

    import re
    nums = re.findall(r'[\d]+\.?\d*', sel)
    if nums:
        try:
            line = float(nums[-1])
        except ValueError:
            line = 3.5

    if market == "Corners":
        if "Corner Handicap" in sel or "Handicap" in sel:
            scope = "handicap"
        elif "Match Corners" in sel or "Total Corners" in sel or sel.startswith("Corners "):
            scope = "match"
        else:
            ht = home_team.lower().strip()
            at = away_team.lower().strip()
            sel_lower = lower
            if ht and ht in sel_lower:
                scope = "team"
                team_name = home_team
            elif at and at in sel_lower:
                scope = "team"
                team_name = away_team
            else:
                parts = sel.split("Corners")
                if len(parts) > 1:
                    team_part = parts[0].strip()
                    skip_words = {"over", "under", "match", "total", ""}
                    if team_part.lower() not in skip_words:
                        scope = "team"
                        team_name = team_part
    else:
        if "home" in lower:
            scope = "home"
        elif "away" in lower:
            scope = "away"

    return {"direction": direction, "line": line, "scope": scope, "team_name": team_name}


def parse_cards_selection(selection: str) -> Dict:
    return parse_selection(selection, "Cards")


def get_live_match_data(fixture_id: int, home_team: str = "", away_team: str = "") -> Optional[Dict]:
    try:
        from api_football_client import APIFootballClient
        client = APIFootballClient()

        status_data = client.get_live_fixture_status(fixture_id)
        if not status_data:
            return None

        events_data = client.get_live_fixture_events(fixture_id)

        card_events = []
        home_cards = 0
        away_cards = 0

        if events_data and events_data.get("cards"):
            home_norm = home_team.lower().strip()
            away_norm = away_team.lower().strip()

            for card in events_data["cards"]:
                card_events.append(card)
                card_team = (card.get("team") or "").lower().strip()
                if home_norm and (home_norm in card_team or card_team in home_norm):
                    home_cards += 1
                elif away_norm and (away_norm in card_team or card_team in away_norm):
                    away_cards += 1
                else:
                    home_cards += 1

        home_corners = 0
        away_corners = 0
        try:
            stats = client.get_fixture_detailed_statistics(fixture_id)
            if stats:
                home_corners = stats.get("home", {}).get("corners", 0) or 0
                away_corners = stats.get("away", {}).get("corners", 0) or 0
        except Exception:
            pass

        status_short = status_data.get("status_short", "NS")

        return {
            "fixture_id": fixture_id,
            "status": status_short,
            "status_long": status_data.get("status_long", "Not Started"),
            "elapsed": status_data.get("elapsed", 0),
            "home_goals": status_data.get("home_goals", 0),
            "away_goals": status_data.get("away_goals", 0),
            "total_cards": home_cards + away_cards,
            "home_cards": home_cards,
            "away_cards": away_cards,
            "card_events": card_events,
            "total_corners": home_corners + away_corners,
            "home_corners": home_corners,
            "away_corners": away_corners,
            "is_live": status_short in LIVE_STATUSES,
            "is_finished": status_short in FINISHED_STATUSES,
            "is_not_started": status_short in NOT_STARTED_STATUSES,
        }

    except Exception as e:
        logger.error(f"Failed to get live data for fixture {fixture_id}: {e}")
        return None


def get_live_cards_data(fixture_id: int, home_team: str = "", away_team: str = "") -> Optional[Dict]:
    return get_live_match_data(fixture_id, home_team, away_team)


def calculate_progress(current_count: int, elapsed: int, line: float, direction: str) -> Dict:
    target = int(line) + 1 if direction == "over" else int(line)
    needed = max(0, target - current_count) if direction == "over" else 0
    remaining_minutes = max(0, 90 - (elapsed or 0))

    if direction == "over":
        if current_count > line:
            status = "WON"
            progress_pct = 100.0
        elif elapsed and elapsed >= 90 and current_count <= line:
            status = "LOST"
            progress_pct = (current_count / target * 100) if target > 0 else 0
        else:
            progress_pct = (current_count / target * 100) if target > 0 else 0
            if remaining_minutes > 0:
                rate = current_count / max(elapsed, 1) if elapsed else 0
                projected = current_count + (rate * remaining_minutes)
                status = "ON_TRACK" if projected > line else "NEEDS_MORE"
            else:
                status = "NEEDS_MORE"
    else:
        if elapsed and elapsed >= 90 and current_count < line:
            status = "WON"
            progress_pct = 100.0
        elif current_count >= line:
            status = "LOST"
            progress_pct = 0
        else:
            progress_pct = ((line - current_count) / line * 100) if line > 0 else 100
            status = "ON_TRACK"

    return {
        "status": status,
        "progress_pct": min(100, progress_pct),
        "needed": needed,
        "remaining_minutes": remaining_minutes,
        "target": target,
    }


def calculate_cards_progress(total_cards: int, elapsed: int, line: float, direction: str) -> Dict:
    result = calculate_progress(total_cards, elapsed, line, direction)
    result["cards_needed"] = result["needed"]
    return result


def _get_relevant_count(live: Dict, market: str, scope: str, team_name: str, home_team: str, away_team: str) -> int:
    if market == "Corners":
        if scope == "team":
            tn = team_name.lower().strip()
            hn = home_team.lower().strip()
            if tn and (tn in hn or hn in tn):
                return live.get("home_corners", 0)
            else:
                return live.get("away_corners", 0)
        elif scope == "handicap":
            return live.get("total_corners", 0)
        else:
            return live.get("total_corners", 0)
    else:
        if scope == "home":
            return live.get("home_cards", 0)
        elif scope == "away":
            return live.get("away_cards", 0)
        else:
            return live.get("total_cards", 0)


def get_tracker_data(market_filter: str = "all") -> List[Dict]:
    bets = get_pending_props_bets(market_filter)
    if not bets:
        return []

    results = []
    now_epoch = int(time.time())
    live_cache = {}

    for bet in bets:
        market = bet.get("market", "Cards")
        bet_data = {
            "bet_id": bet.get("id"),
            "home_team": bet.get("home_team", ""),
            "away_team": bet.get("away_team", ""),
            "league": bet.get("league", ""),
            "market": market,
            "selection": bet.get("selection", ""),
            "odds": bet.get("odds", 0),
            "match_date": bet.get("match_date", ""),
            "kickoff_epoch": bet.get("kickoff_epoch", 0),
            "fixture_id": bet.get("fixture_id"),
            "ev": bet.get("edge_percentage", 0),
            "trust": bet.get("trust_level", ""),
        }

        parsed = parse_selection(bet.get("selection", ""), market, bet.get("home_team", ""), bet.get("away_team", ""))
        bet_data["direction"] = parsed["direction"]
        bet_data["line"] = parsed["line"]
        bet_data["scope"] = parsed["scope"]
        bet_data["team_name"] = parsed.get("team_name", "")

        kickoff = bet.get("kickoff_epoch", 0) or 0
        if kickoff == 0:
            bet_data["match_status"] = "UPCOMING"
            bet_data["live_data"] = None
            results.append(bet_data)
            continue

        time_to_kick = kickoff - now_epoch
        if time_to_kick > 3600:
            bet_data["match_status"] = "UPCOMING"
            bet_data["live_data"] = None
            results.append(bet_data)
            continue

        fixture_id = bet.get("fixture_id")
        if not fixture_id:
            if time_to_kick < 0:
                bet_data["match_status"] = "IN_PROGRESS_NO_ID"
            else:
                bet_data["match_status"] = "UPCOMING"
            bet_data["live_data"] = None
            results.append(bet_data)
            continue

        if fixture_id in live_cache:
            live = live_cache[fixture_id]
        else:
            live = get_live_match_data(fixture_id, bet.get("home_team", ""), bet.get("away_team", ""))
            live_cache[fixture_id] = live

        if live:
            bet_data["live_data"] = live
            relevant = _get_relevant_count(live, market, parsed["scope"], parsed.get("team_name", ""),
                                           bet.get("home_team", ""), bet.get("away_team", ""))
            bet_data["relevant_count"] = relevant
            bet_data["relevant_cards"] = relevant

            if live["is_live"]:
                bet_data["match_status"] = "LIVE"
                progress = calculate_progress(relevant, live["elapsed"], parsed["line"], parsed["direction"])
                bet_data["progress"] = progress
            elif live["is_finished"]:
                bet_data["match_status"] = "FINISHED"
                progress = calculate_progress(relevant, 90, parsed["line"], parsed["direction"])
                bet_data["progress"] = progress
            else:
                bet_data["match_status"] = "UPCOMING"
        else:
            bet_data["match_status"] = "UPCOMING" if time_to_kick > 0 else "IN_PROGRESS_NO_DATA"
            bet_data["live_data"] = None

        results.append(bet_data)

    results.sort(key=lambda x: (
        0 if x["match_status"] == "LIVE" else
        1 if x["match_status"] == "FINISHED" else
        2 if x["match_status"] == "IN_PROGRESS_NO_DATA" else 3,
        x.get("kickoff_epoch", 0)
    ))

    return results


def get_tracker_data_json(market_filter: str = "all") -> List[Dict]:
    data = get_tracker_data(market_filter)
    clean = []
    for d in data:
        item = {k: v for k, v in d.items() if k != "live_data"}
        live = d.get("live_data")
        if live:
            item["elapsed"] = live.get("elapsed", 0)
            item["score"] = f"{live.get('home_goals', 0)}-{live.get('away_goals', 0)}"
            item["total_cards"] = live.get("total_cards", 0)
            item["home_cards"] = live.get("home_cards", 0)
            item["away_cards"] = live.get("away_cards", 0)
            item["total_corners"] = live.get("total_corners", 0)
            item["home_corners"] = live.get("home_corners", 0)
            item["away_corners"] = live.get("away_corners", 0)
            item["card_events"] = live.get("card_events", [])
            item["is_live"] = live.get("is_live", False)
            item["is_finished"] = live.get("is_finished", False)
        else:
            item["elapsed"] = 0
            item["score"] = "0-0"
            item["is_live"] = False
            item["is_finished"] = False
        clean.append(item)
    return clean
