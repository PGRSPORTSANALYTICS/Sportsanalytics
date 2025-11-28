import os
import datetime as dt
import psycopg2
from psycopg2.extras import DictCursor

# ==========================================
# DB-CONNECTION
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=DictCursor)


# ==========================================
# SYSTEM DEFINITIONS
# ==========================================
SYSTEMS = [
    ("VALUE_SINGLES",       "Value Singles"),
    ("EXACT_SCORE",         "Exact Score"),
    ("SGP",                 "Same Game Parlays"),
    ("COLLEGE_BASKETBALL",  "College Basketball"),
    # Lägg till fler här om du vill visa dem i listan
]

# ==========================================
# TABELL-KONFIG – JUSTERA HÄR
# ==========================================
# !!! VIKTIGT !!!
#  - Byt kolumnnamn så de matchar dina riktiga tabeller.
#  - extra_where kan vara tom sträng "" om du inte filtrerar på bet_type.
#
# Jag gissar på kolumnnamn, så räkna med att du behöver ändra dem.
# Kolla i Supabase vad kolumnerna heter exakt.

TABLE_CONFIG = {
    "EXACT_SCORE": {
        "table": "football_opportunities",
        "stake_col": "stake_sek",      # TODO: byt till rätt kolumn
        "profit_col": "profit_sek",    # TODO: byt till rätt kolumn (netto)
        "status_col": "status",        # t.ex. 'WON' / 'LOST' / 'PENDING'
        "date_col": "kickoff_time",    # eller 'event_date' / 'created_at'
        "extra_where": "AND bet_type = 'EXACT_SCORE'"  # TODO: justera eller ta bort
    },
    "VALUE_SINGLES": {
        "table": "football_opportunities",
        "stake_col": "stake_sek",      # TODO
        "profit_col": "profit_sek",    # TODO
        "status_col": "status",        # TODO
        "date_col": "kickoff_time",    # TODO
        "extra_where": "AND bet_type = 'VALUE_SINGLE'"  # TODO eller ""
    },
    "SGP": {
        "table": "sgp_predictions",
        "stake_col": "stake_sek",      # TODO
        "profit_col": "profit_sek",    # TODO
        "status_col": "status",        # t.ex. 'SETTLED'
        "date_col": "kickoff_time",    # TODO
        "extra_where": ""              # ev. "AND is_monster = FALSE"
    },
    "COLLEGE_BASKETBALL": {
        "table": "basketball_predictions",
        "stake_col": "stake_sek",      # TODO
        "profit_col": "profit_sek",    # TODO
        "status_col": "status",        # TODO
        "date_col": "game_time",       # TODO
        "extra_where": ""              # ev. "AND league = 'NCAAB'"
    },
    # Exempel om du vill koppla in fler senare:
    # "MONSTER_SGP": {
    #     "table": "sgp_predictions",
    #     "stake_col": "...",
    #     "profit_col": "...",
    #     "status_col": "...",
    #     "date_col": "...",
    #     "extra_where": "AND is_monster = TRUE"
    # },
}


# ==========================================
# BACKTEST-LOGIK FÖR ETT SYSTEM
# ==========================================
def run_backtest_for_system(system_id, date_from, date_to):
    cfg = TABLE_CONFIG.get(system_id)

    if cfg is None:
        print(f"[MULTI_BACKTEST] ⚠️  Skipping {system_id} – no table config yet")
        return {
            "bets": 0,
            "staked": 0.0,
            "profit": 0.0,
            "roi": 0.0,
        }

    table = cfg["table"]
    stake_col = cfg["stake_col"]
    profit_col = cfg["profit_col"]
    status_col = cfg["status_col"]
    date_col = cfg["date_col"]
    extra_where = cfg["extra_where"]

    # OBS: ändra 'SETTLED' om du använder annan status för färdiga spel
    query = f"""
        SELECT
            COUNT(*)                         AS bets,
            COALESCE(SUM({stake_col}), 0.0)  AS staked,
            COALESCE(SUM({profit_col}), 0.0) AS profit
        FROM {table}
        WHERE {date_col} >= %(date_from)s
          AND {date_col} <  %(date_to)s
          AND {status_col} = 'SETTLED'
          {extra_where}
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(query, {"date_from": date_from, "date_to": date_to})
        row = cur.fetchone()

    bets = row["bets"]
    staked = float(row["staked"])
    profit = float(row["profit"])
    roi = (profit / staked * 100.0) if staked > 0 else 0.0

    return {
        "bets": bets,
        "staked": staked,
        "profit": profit,
        "roi": roi,
    }


# ==========================================
# MAIN
# ==========================================
def main():
    # Standardperiod: från 1 sep 2024 till idag
    today = dt.date.today()
    default_from = dt.date(2024, 9, 1)
    default_to = today + dt.timedelta(days=1)

    date_from = default_from
    date_to = default_to

    print("[MULTI_BACKTEST] " + "=" * 60)
    print(f"[MULTI_BACKTEST] Period: {date_from} → {date_to}")
    print("[MULTI_BACKTEST] Mode: PROD (läser riktiga tabeller)")
    print("[MULTI_BACKTEST] " + "=" * 60)

    total_bets = 0
    total_staked = 0.0
    total_profit = 0.0

    for system_id, label in SYSTEMS:
        print(f"\n[MULTI_BACKTEST] → {label} ({system_id})")

        res = run_backtest_for_system(system_id, date_from, date_to)

        total_bets += res["bets"]
        total_staked += res["staked"]
        total_profit += res["profit"]

        print(f"  Bets:    {res['bets']}")
        print(f"  Staked:  {res['staked']:.2f} SEK")
        print(f"  Profit:  {res['profit']:.2f} SEK")
        print(f"  ROI:     {res['roi']:.2f}%")

    total_roi = (total_profit / total_staked * 100.0) if total_staked > 0 else 0.0

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Bets:   {total_bets}")
    print(f"Total Staked: {total_staked:.2f} SEK")
    print(f"Total Profit: {total_profit:.2f} SEK")
    print(f"Avg ROI:      {total_roi:.2f}%")

if __name__ == "__main__":
    main()