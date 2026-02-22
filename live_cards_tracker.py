"""
Live Cards Tracker v1.0
=======================
Real-time tracking of ongoing cards picks using API-Football live data.
Shows current card count vs target line for pending cards bets.
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


def get_pending_cards_bets() -> List[Dict]:
    db = DatabaseConnection()
    try:
        rows = db.execute_query("""
            SELECT id, home_team, away_team, league, selection, odds, 
                   match_date, kickoff_epoch, fixture_id, 
                   edge_percentage, trust_level, mode
            FROM football_opportunities
            WHERE market = 'Cards'
              AND status = 'pending'
              AND mode IN ('PROD', 'PRODUCTION')
            ORDER BY kickoff_epoch ASC
        """)
        return rows if rows else []
    except Exception as e:
        logger.error(f"Failed to get pending cards bets: {e}")
        return []


def parse_cards_selection(selection: str) -> Dict:
    sel = selection.strip()
    parts = sel.split()

    direction = "over"
    line = 0.0
    scope = "match"

    if len(parts) >= 2:
        direction = parts[0].lower()
        try:
            line = float(parts[1])
        except ValueError:
            line = 3.5

    if "home" in sel.lower():
        scope = "home"
    elif "away" in sel.lower():
        scope = "away"

    return {"direction": direction, "line": line, "scope": scope}


def get_live_cards_data(fixture_id: int, home_team: str = "", away_team: str = "") -> Optional[Dict]:
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
                if home_norm and home_norm in card_team or card_team in home_norm:
                    home_cards += 1
                elif away_norm and away_norm in card_team or card_team in away_norm:
                    away_cards += 1
                else:
                    home_cards += 1

        total_cards = home_cards + away_cards
        status_short = status_data.get("status_short", "NS")

        return {
            "fixture_id": fixture_id,
            "status": status_short,
            "status_long": status_data.get("status_long", "Not Started"),
            "elapsed": status_data.get("elapsed", 0),
            "home_goals": status_data.get("home_goals", 0),
            "away_goals": status_data.get("away_goals", 0),
            "total_cards": total_cards,
            "home_cards": home_cards,
            "away_cards": away_cards,
            "card_events": card_events,
            "is_live": status_short in LIVE_STATUSES,
            "is_finished": status_short in FINISHED_STATUSES,
            "is_not_started": status_short in NOT_STARTED_STATUSES,
        }

    except Exception as e:
        logger.error(f"Failed to get live data for fixture {fixture_id}: {e}")
        return None


def calculate_cards_progress(total_cards: int, elapsed: int, line: float, direction: str) -> Dict:
    target = int(line) + 1 if direction == "over" else int(line)
    cards_needed = max(0, target - total_cards) if direction == "over" else 0
    remaining_minutes = max(0, 90 - (elapsed or 0))

    if direction == "over":
        if total_cards > line:
            status = "WON"
            progress_pct = 100.0
        elif elapsed and elapsed >= 90 and total_cards <= line:
            status = "LOST"
            progress_pct = (total_cards / target * 100) if target > 0 else 0
        else:
            progress_pct = (total_cards / target * 100) if target > 0 else 0
            if remaining_minutes > 0:
                cards_per_min = total_cards / max(elapsed, 1) if elapsed else 0
                projected = total_cards + (cards_per_min * remaining_minutes)
                if projected > line:
                    status = "ON_TRACK"
                else:
                    status = "NEEDS_CARDS"
            else:
                status = "NEEDS_CARDS"
    else:
        if elapsed and elapsed >= 90 and total_cards < line:
            status = "WON"
            progress_pct = 100.0
        elif total_cards >= line:
            status = "LOST"
            progress_pct = 0
        else:
            progress_pct = ((line - total_cards) / line * 100) if line > 0 else 100
            status = "ON_TRACK"

    return {
        "status": status,
        "progress_pct": min(100, progress_pct),
        "cards_needed": cards_needed,
        "remaining_minutes": remaining_minutes,
        "target": target,
    }


def get_tracker_data() -> List[Dict]:
    bets = get_pending_cards_bets()
    if not bets:
        return []

    results = []
    now_epoch = int(time.time())

    for bet in bets:
        bet_data = {
            "bet_id": bet.get("id"),
            "home_team": bet.get("home_team", ""),
            "away_team": bet.get("away_team", ""),
            "league": bet.get("league", ""),
            "selection": bet.get("selection", ""),
            "odds": bet.get("odds", 0),
            "match_date": bet.get("match_date", ""),
            "kickoff_epoch": bet.get("kickoff_epoch", 0),
            "fixture_id": bet.get("fixture_id"),
            "ev": bet.get("edge_percentage", 0),
            "trust": bet.get("trust_level", ""),
        }

        parsed = parse_cards_selection(bet.get("selection", ""))
        bet_data["direction"] = parsed["direction"]
        bet_data["line"] = parsed["line"]
        bet_data["scope"] = parsed["scope"]

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

        live = get_live_cards_data(fixture_id, bet.get("home_team", ""), bet.get("away_team", ""))
        if live:
            bet_data["live_data"] = live
            scope = parsed["scope"]
            if scope == "home":
                relevant_cards = live.get("home_cards", 0)
            elif scope == "away":
                relevant_cards = live.get("away_cards", 0)
            else:
                relevant_cards = live.get("total_cards", 0)
            bet_data["relevant_cards"] = relevant_cards

            if live["is_live"]:
                bet_data["match_status"] = "LIVE"
                progress = calculate_cards_progress(
                    relevant_cards, live["elapsed"],
                    parsed["line"], parsed["direction"]
                )
                bet_data["progress"] = progress
            elif live["is_finished"]:
                bet_data["match_status"] = "FINISHED"
                progress = calculate_cards_progress(
                    relevant_cards, 90,
                    parsed["line"], parsed["direction"]
                )
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
