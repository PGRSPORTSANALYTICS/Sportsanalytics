"""
run_backtest.py
---------------------------------
Central backtest-runner för PGR Sports Analytics.

Idé:
- Kör backtest för flera produkter (VALUE_SINGLE, EXACT_SCORE, SGP, WBB etc)
- Använder ett "mode"-fält för att skilja BACKTEST/PROD/DEMO
- Låter resten av systemet (ROI, dashboards, modell-träning) återanvända samma tabeller.

Hur du använder den:
1. Scrolla längst ned i den här filen.
2. Fyll i TODO-delarna i:
      - load_fixtures_for_range(...)
      - generate_backtest_bets_for_fixture(...)
      - insert_backtest_bets(...)
   med den kod du redan har för att hämta matcher, bygga spel och skriva till DB.
3. Kör i Replit shell:
      python run_backtest.py
4. Titta i dashboarden med filtret "Mode = BACKTEST" för att se resultat.

Den här filen försöker INTE gissa dina interna modulnamn – du kopplar själv in dem
på ett ställe (= hookarna) så slipper du ändra på 20 olika ställen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Literal, Tuple

# ---------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------

# Mode-flaggor – du använder redan "PROD" i dina tabeller
Mode = Literal["PROD", "BACKTEST", "DEMO"]
BACKTEST_MODE: Mode = "BACKTEST"

# Vilka produkter du vill backtesta och vilken tabell de skriver till
# Justera tabellnamn så det matchar din PostgreSQL:
BACKTEST_PRODUCTS: List[Tuple[str, str]] = [
    ("VALUE_SINGLE", "football_opportunitties"),   # dina value singles
    ("EXACT_SCORE", "football_opportunitties"),    # exakta resultat (samma tabell, annan product)
    ("SGP", "sgp_predictions"),                    # same game parlays
    ("COLLEGE_BASKETBALL", "basketball_predictions"),
    ("WOMEN_1X2", "women_match_winner_predictions"),
]

# Standarddatum för en "stor" backtestperiod – ändra som du vill
DEFAULT_START = date(2024, 9, 1)
DEFAULT_END = date(2024, 11, 25)

# ---------------------------------------------------------
# Logging-setup
# ---------------------------------------------------------

logger = logging.getLogger("pgr_backtest")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = "[BACKTEST] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------
# Datamodeller
# ---------------------------------------------------------

@dataclass
class Fixture:
    """Minsta gemensamma info vi behöver från en match för backtest."""
    fixture_id: int
    league_id: int | None
    match_date: datetime
    home_team: str
    away_team: str
    raw: Dict[str, Any]  # hela API-svaret / DB-raden om du vill


@dataclass
class BacktestBet:
    """
    Normaliserad representation av ett bet som ska in i DB.

    Fält som i dina tabeller:
      - product: t.ex. 'VALUE_SINGLE', 'EXACT_SCORE', 'SGP'
      - stake:   insats i SEK
      - odds:    decimalodds
      - mode:    'BACKTEST'
      - result:  'PENDING', 'WON', 'LOST' etc (sätt PENDING vid insättning)
      - payout:  kan vara None vid insättning
      - home_team, away_team, match_date: för att dashboards ska funka
      - extra:   valfritt dict som kan dumpas till JSON-kolumn (t.ex. legs för SGP)
    """
    product: str
    stake: float
    odds: float
    mode: Mode
    home_team: str
    away_team: str
    match_date: datetime
    result: str = "PENDING"
    payout: float | None = None
    created_at: datetime = datetime.utcnow()
    extra: Dict[str, Any] | None = None  # t.ex. {"legs": "..."} eller {"edge": 0.12}

    def to_db_row(self) -> Dict[str, Any]:
        row = asdict(self)
        extra = row.pop("extra", None)
        if extra:
            # platta ut så det passar dina kolumner (anpassa efter schema)
            for k, v in extra.items():
                row[k] = v
        return row


# ---------------------------------------------------------
# Backtest-orchestrator
# ---------------------------------------------------------

def run_backtest_for_product(
    product: str,
    target_table: str,
    start_date: date,
    end_date: date,
) -> None:
    """Kör backtest för EN produkt över en period och skriver in BACKTEST-bets i DB."""
    logger.info("=" * 56)
    logger.info(f"Running BACKTEST for product={product}")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Target table: {target_table}")

    fixtures: List[Fixture] = load_fixtures_for_range(start_date, end_date, product)
    logger.info(f"Loaded {len(fixtures)} fixtures for product={product}")

    all_bets: List[BacktestBet] = []

    for fx in fixtures:
        bets_for_fixture = generate_backtest_bets_for_fixture(product, fx)
        if not bets_for_fixture:
            continue
        all_bets.extend(bets_for_fixture)

    if not all_bets:
        logger.info("No bets generated – nothing to insert.")
        return

    inserted = insert_backtest_bets(
        table_name=target_table,
        bets=all_bets,
        mode=BACKTEST_MODE,
    )
    logger.info(f"Done. Inserted {inserted} BACKTEST bets into {target_table}.")


def main() -> None:
    logger.info("=" * 56)
    logger.info("PGR BACKTEST RUNNER")
    logger.info("=" * 56)
    logger.info(f"Default date range: {DEFAULT_START} → {DEFAULT_END}")
    logger.info("Mode: BACKTEST (safe – påverkar inte PROD-bets)\n")

    for product, table in BACKTEST_PRODUCTS:
        run_backtest_for_product(
            product=product,
            target_table=table,
            start_date=DEFAULT_START,
            end_date=DEFAULT_END,
        )

    logger.info("=" * 56)
    logger.info("BACKTEST COMPLETED")
    logger.info("=" * 56)


# ---------------------------------------------------------
# HOOK 1 – Hämta fixtures att backtesta på
# ---------------------------------------------------------

def load_fixtures_for_range(
    start: date,
    end: date,
    product: str,
) -> List[Fixture]:
    """
    TODO: Koppla till din riktiga fixture-källa (API-Football eller egen DB).

    Startpunkt just nu: tom lista (→ inga bets).
    Fyll i med logik som:

        - Läs vilka ligor du vill backtesta på (t.ex. LEAGUE_REGISTRY)
        - För varje liga: hämta fixtures mellan start/end
        - Skapa Fixture-objekt

    Exempel-skelett (byt ut pseudo-kod mot dina riktiga moduler):

        from config.leagues import LEAGUE_REGISTRY
        from clients.api_football import api_client

        league_ids = [
            lg.api_football_id
            for lg in LEAGUE_REGISTRY
            if lg.backtest_enabled_for(product)
        ]

        fixtures = []
        for league_id in league_ids:
            raw_fixtures = api_client.get_fixtures(league_id, start, end)
            for rf in raw_fixtures:
                fixtures.append(
                    Fixture(
                        fixture_id=rf["fixture"]["id"],
                        league_id=league_id,
                        match_date=parse_datetime(rf["fixture"]["date"]),
                        home_team=rf["teams"]["home"]["name"],
                        away_team=rf["teams"]["away"]["name"],
                        raw=rf,
                    )
                )
        return fixtures
    """
    # JUST NU – placeholder så skriptet kör utan att krascha
    return []


# ---------------------------------------------------------
# HOOK 2 – Generera bets för en fixture med din befintliga motor
# ---------------------------------------------------------

def generate_backtest_bets_for_fixture(
    product: str,
    fixture: Fixture,
) -> List[BacktestBet]:
    """
    TODO: Anropa din befintliga motor för att skapa bets, men:
          - skicka INTE till Telegram
          - skriv inte direkt till PROD-tabeller
          - returnera BacktestBet-objekt istället.

    Du har redan logik någonstans som t.ex. gör:
        - värderar marknader
        - räknar EV
        - väljer ut hög-EDGE spel
        - bestämmer stake

    Koppla in den här, ungefär så här:

        if product == "VALUE_SINGLE":
            opportunities = value_engine.generate_for_fixture(fixture.raw)
            return [
                BacktestBet(
                    product="VALUE_SINGLE",
                    stake=opp.stake,
                    odds=opp.odds,
                    mode=BACKTEST_MODE,
                    home_team=fixture.home_team,
                    away_team=fixture.away_team,
                    match_date=fixture.match_date,
                    extra={"market": opp.market, "edge": opp.edge},
                )
                for opp in opportunities
            ]

        elif product == "EXACT_SCORE":
            ...

        elif product == "SGP":
            ...

        elif product == "COLLEGE_BASKETBALL":
            ...

    Tills du kopplat in motorn returnerar vi bara en tom lista.
    """
    return []


# ---------------------------------------------------------
# HOOK 3 – Skriv BACKTEST-bets till PostgreSQL
# ---------------------------------------------------------

def insert_backtest_bets(
    table_name: str,
    bets: Iterable[BacktestBet],
    mode: Mode,
) -> int:
    """
    TODO: Skriv in backtest-bets i dina befintliga tabeller.

    Viktigt:
      - Sätt kolumnen "mode" = BACKTEST (så dashboards kan filtrera bort dem vid PROD-läge)
      - Overwrite:a INTE befintliga PROD-bets.
      - Anpassa kolumnnamn efter ditt schema.

    Två vanliga sätt:

    1) Använd din befintliga DB-helper:
         from db_connection import execute_many

         rows = [bet.to_db_row() for bet in bets]
         for r in rows:
             r["mode"] = mode

         execute_many(
             f\"\"\"INSERT INTO {table_name} (...) VALUES (...)\"
             \"\"\",
             rows,
         )

    2) Använd psycopg2 direkt med DATABASE_URL (Replit-agenten kan hjälpa dig).

    Just nu returnerar funktionen bara 0 så skriptet kör utan att krascha.
    """
    _ = table_name, bets, mode  # tysta lintern
    return 0


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    main()