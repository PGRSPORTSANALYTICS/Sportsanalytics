# settlement.py
"""
Central settlement-logik för PGR Sports Analytics.

- Läser matchresultat från match_results
- Settlar bets i:
    - football_opportunitties (VALUE_SINGLE + EXACT_SCORE)
    - sgp_predictions        (SGP_PARLAY)
    - basketball_predictions (BASKETBALL)
    - women_match_winner_predictions (WOMEN_1X2)
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional, Any, List
import json
import psycopg2
from psycopg2.extras import RealDictCursor


# -------------------------
# DB-connection helper
# -------------------------

from db_connection import get_db_conn as get_conn


# -------------------------
# Result column mapping per table
# -------------------------

RESULT_COLUMN_MAP = {
    "basketball_predictions": "status",   # basketball uses 'status'
    # other tables use 'result' as default
}

def get_result_column(table_name: str) -> str:
    """Return the correct result/status column for a given table."""
    return RESULT_COLUMN_MAP.get(table_name, "result")


# -------------------------
# Datamodell för matchresultat
# -------------------------

@dataclass
class MatchResult:
    fixture_id: int
    ft_home_goals: int
    ft_away_goals: int
    corners_home: Optional[int] = None
    corners_away: Optional[int] = None
    cards_home: Optional[int] = None
    cards_away: Optional[int] = None


# -------------------------
# Ladda resultat i minnet
# -------------------------

def load_results_dict(mode: str = "PROD") -> Dict[int, MatchResult]:
    """
    Hämtar alla resultat för ett visst mode (PROD/BACKTEST)
    och returnerar dict: {fixture_id: MatchResult}
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    fixture_id,
                    ft_home_goals,
                    ft_away_goals,
                    corners_home,
                    corners_away,
                    cards_home,
                    cards_away
                FROM match_results
                WHERE mode = %s
                """,
                (mode,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    results: Dict[int, MatchResult] = {}
    for r in rows:
        results[r["fixture_id"]] = MatchResult(
            fixture_id=r["fixture_id"],
            ft_home_goals=r["ft_home_goals"],
            ft_away_goals=r["ft_away_goals"],
            corners_home=r.get("corners_home"),
            corners_away=r.get("corners_away"),
            cards_home=r.get("cards_home"),
            cards_away=r.get("cards_away"),
        )
    return results


# -------------------------
# Hjälpfunktioner
# -------------------------

def _safe_json_load(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


# -------------------------
# SETTLEMENT FÖR VARJE PRODUKT
# Returnerar (status, payout)
# status: 'WON' / 'LOST' / 'VOID'
# payout: float
# -------------------------

def settle_value_single(row: Dict[str, Any], result: MatchResult) -> Tuple[str, float]:
    """
    Exempel: market: 'OVER_GOALS', line: 2.5
    Justera till dina riktiga kolumnnamn.
    """
    stake = float(row["stake"])
    odds = float(row["odds"])

    market = row.get("market")           # TODO: ändra till din kolumn
    line = row.get("line")               # t.ex. 2.5
    selection = row.get("selection")     # t.ex. 'HOME', 'AWAY', 'DRAW'

    total_goals = result.ft_home_goals + result.ft_away_goals

    if market == "OVER_GOALS":
        if total_goals > float(line):
            return "WON", stake * odds
        else:
            return "LOST", 0.0

    if market == "UNDER_GOALS":
        if total_goals < float(line):
            return "WON", stake * odds
        else:
            return "LOST", 0.0

    if market == "1X2":
        if result.ft_home_goals > result.ft_away_goals:
            winner = "HOME"
        elif result.ft_home_goals < result.ft_away_goals:
            winner = "AWAY"
        else:
            winner = "DRAW"

        if selection == winner:
            return "WON", stake * odds
        else:
            return "LOST", 0.0

    # fallback: okänt market → settla inte
    return "VOID", 0.0


def settle_exact_score(row: Dict[str, Any], result: MatchResult) -> Tuple[str, float]:
    """
    Exact score: lagrat som t.ex. home_goals, away_goals i raden.
    """
    stake = float(row["stake"])
    odds = float(row["odds"])

    predicted_home = int(row["home_goals"])  # TODO: ändra om du har andra namn
    predicted_away = int(row["away_goals"])

    if predicted_home == result.ft_home_goals and predicted_away == result.ft_away_goals:
        return "WON", stake * odds
    else:
        return "LOST", 0.0


def _leg_won(leg: Dict[str, Any], result: MatchResult) -> bool:
    """
    En enskild SGP-leg.
    Anpassa till hur dina legs ser ut.
    Exempelstruktur:
    {
        "type": "CORNERS_OVER",
        "line": 10.5
    }
    """
    leg_type = leg.get("type")
    line = float(leg.get("line", 0))

    total_goals = result.ft_home_goals + result.ft_away_goals
    total_corners = None
    if result.corners_home is not None and result.corners_away is not None:
        total_corners = result.corners_home + result.corners_away

    if leg_type == "GOALS_OVER":
        return total_goals is not None and total_goals > line

    if leg_type == "GOALS_UNDER":
        return total_goals is not None and total_goals < line

    if leg_type == "CORNERS_OVER":
        return total_corners is not None and total_corners > line

    if leg_type == "CORNERS_UNDER":
        return total_corners is not None and total_corners < line

    # okänd leg, räkna som fail (för att vara defensiv)
    return False


def settle_sgp_parlay(row: Dict[str, Any], result: MatchResult) -> Tuple[str, float]:
    """
    SGP: alla ben måste vinna.
    Antag legs-kolumn med JSON.
    """
    stake = float(row["stake"])
    odds = float(row["odds"])

    legs_raw = row.get("legs")  # TODO: rätt kolumnnamn
    legs: List[Dict[str, Any]] = _safe_json_load(legs_raw) or []

    if not legs:
        # Ingen legs-info → vågar inte settla
        return "VOID", 0.0

    for leg in legs:
        if not _leg_won(leg, result):
            return "LOST", 0.0

    # Alla legs vann
    return "WON", stake * odds


def settle_basketball(row: Dict[str, Any], result: MatchResult) -> Tuple[str, float]:
    """
    Basket: just nu kan du göra en enklare variant.
    Antag t.ex. match winner eller över/under total points
    beroende på hur du lagrar basket-bets.
    """
    # TODO: anpassa till ditt schema – samma princip som value_single.
    # Tills vidare: returnera VOID så att det inte sabbar något.
    return "VOID", 0.0


def settle_women_1x2(row: Dict[str, Any], result: MatchResult) -> Tuple[str, float]:
    """
    Kvinnor 1X2 (women_match_winner_predictions) – klassisk 1X2.
    """
    stake = float(row["stake"])
    odds = float(row["odds"])
    selection = row.get("selection")  # 'HOME' / 'AWAY' / 'DRAW'

    if result.ft_home_goals > result.ft_away_goals:
        winner = "HOME"
    elif result.ft_home_goals < result.ft_away_goals:
        winner = "AWAY"
    else:
        winner = "DRAW"

    if selection == winner:
        return "WON", stake * odds
    else:
        return "LOST", 0.0


# -------------------------
# Hämta alla PENDING bets per tabell
# -------------------------

def _fetch_pending(cur, table: str, mode: str) -> List[Dict[str, Any]]:
    result_col = get_result_column(table)

    query = f"""
        SELECT *
        FROM {table}
        WHERE {result_col} = 'PENDING'
          AND mode = %s
    """
    cur.execute(query, (mode,))
    return cur.fetchall()


def _update_result(cur, table_name: str, bet_id: int, result_value: str, payout: float, settled_at, mode: str):
    result_col = get_result_column(table_name)

    query = f"""
        UPDATE {table_name}
        SET {result_col} = %s,
            payout = %s,
            verified_at = %s
        WHERE id = %s
          AND mode = %s
    """
    cur.execute(query, (result_value, payout, settled_at, bet_id, mode))


# -------------------------
# Huvud-funktion: settle_all_bets
# -------------------------

def settle_all_bets(mode: str = "PROD") -> None:
    """
    Settlar ALLA PENDING bets för valt mode.
    Körs t.ex. som cron-jobb var 10:e minut.
    """
    results_by_fixture = load_results_dict(mode=mode)

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1) Hämta pending bets från alla produkt-tabeller
            singles = _fetch_pending(cur, "football_opportunities", mode)
            sgps = _fetch_pending(cur, "sgp_predictions", mode)
            baskets = _fetch_pending(cur, "basketball_predictions", mode)
            women = _fetch_pending(cur, "women_match_winner_predictions", mode)

            to_update: List[Tuple[str, int, str, float]] = []  # (table, id, result, payout)

            # --- VALUE_SINGLE + EXACT_SCORE (antar product-kolumn i football_opportunitties) ---
            for row in singles:
                fixture_id = row["fixture_id"]          # TODO: se till att kolumnen finns
                product = row.get("product", "VALUE_SINGLE")
                res_obj = results_by_fixture.get(fixture_id)
                if not res_obj:
                    continue  # inget resultat än

                if product == "VALUE_SINGLE":
                    status, payout = settle_value_single(row, res_obj)
                elif product == "EXACT_SCORE":
                    status, payout = settle_exact_score(row, res_obj)
                else:
                    # okänd produkt – hoppa
                    continue

                to_update.append(("football_opportunitties", row["id"], status, payout))

            # --- SGP_PARLAY ---
            for row in sgps:
                fixture_id = row["fixture_id"]
                res_obj = results_by_fixture.get(fixture_id)
                if not res_obj:
                    continue
                status, payout = settle_sgp_parlay(row, res_obj)
                to_update.append(("sgp_predictions", row["id"], status, payout))

            # --- BASKETBALL ---
            for row in baskets:
                fixture_id = row["fixture_id"]
                res_obj = results_by_fixture.get(fixture_id)
                if not res_obj:
                    continue
                status, payout = settle_basketball(row, res_obj)
                to_update.append(("basketball_predictions", row["id"], status, payout))

            # --- WOMEN_1X2 ---
            for row in women:
                fixture_id = row["fixture_id"]
                res_obj = results_by_fixture.get(fixture_id)
                if not res_obj:
                    continue
                status, payout = settle_women_1x2(row, res_obj)
                to_update.append(("women_match_winner_predictions", row["id"], status, payout))

            # Nu uppdaterar vi alla bets i databasen
            for table, bet_id, status, payout in to_update:
                cur.execute(
                    f"""
                    UPDATE {table}
                    SET
                        result = %s,
                        payout = %s,
                        settled_at = NOW()
                    WHERE id = %s
                    """,
                    (status, payout, bet_id),
                )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Exempel: kör från shell
    #   python settlement.py
    #
    print("[SETTLEMENT] Running for mode=PROD")
    settle_all_bets(mode="PROD")
    print("[SETTLEMENT] Done.")