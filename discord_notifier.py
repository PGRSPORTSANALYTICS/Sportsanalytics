import os
import requests

PRODUCT_WEBHOOKS = {
    "EXACT_SCORE": os.getenv("WEBHOOK_Final_score"),
    "SGP": os.getenv("WEBHOOK_SGP"),
    "ML_PARLAY": os.getenv("WEBHOOK_ML_PARLAYS"),
    "VALUE_SINGLE": os.getenv("WEBHOOK_Value_singles"),
    "BASKETBALL_SINGLE": os.getenv("WEB_HOOK_College_basket"),
    "BASKETBALL": os.getenv("WEB_HOOK_College_basket"),
    "BASKET_SINGLE": os.getenv("WEB_HOOK_College_basket"),
    "BASKET_PARLAY": os.getenv("WEB_HOOK_College_basket"),
}

def format_bet_message(bet) -> str:
    """Format bet details for Discord message."""
    if isinstance(bet, dict):
        league = bet.get('league', 'Unknown League')
        home_team = bet.get('home_team', '')
        away_team = bet.get('away_team', '')
        kickoff = bet.get('match_date', bet.get('kickoff', ''))
        product_type = bet.get('product', bet.get('product_type', ''))
        market = bet.get('selection', bet.get('market', ''))
        selection = bet.get('selection', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', None)
        stake = bet.get('stake', None)
    else:
        league = getattr(bet, 'league', 'Unknown League')
        home_team = getattr(bet, 'home_team', '')
        away_team = getattr(bet, 'away_team', '')
        kickoff = getattr(bet, 'match_date', getattr(bet, 'kickoff', ''))
        product_type = getattr(bet, 'product', getattr(bet, 'product_type', ''))
        market = getattr(bet, 'market', '')
        selection = getattr(bet, 'selection', '')
        odds = getattr(bet, 'odds', 0)
        ev = getattr(bet, 'ev', None)
        stake = getattr(bet, 'stake', None)

    lines = [
        f"**{league}** – {home_team} vs {away_team}",
        f"Kickoff: `{kickoff}`",
        "",
        f"**Product:** {product_type}",
        f"**Bet:** {market if market != selection else selection}",
        f"**Odds:** {float(odds):.2f}" if odds else "",
    ]

    if ev is not None:
        try:
            ev_val = float(ev)
            if ev_val < 1:
                ev_val = ev_val * 100
            lines.append(f"**EV:** {ev_val:.1f}%")
        except:
            pass

    if stake is not None:
        try:
            lines.append(f"**Stake:** ${float(stake)/10.8:.0f}")
        except:
            pass

    lines.append("")
    lines.append("_PGR Sports Analytics – AI-powered betting_")

    return "\n".join([l for l in lines if l or l == ""])


def send_bet_to_discord(bet, product_type=None):
    """
    Send a bet to the appropriate Discord channel based on product type.
    Silently skips if no webhook is configured (won't crash the engine).
    """
    if product_type is None:
        if isinstance(bet, dict):
            product_type = bet.get('product', bet.get('product_type', ''))
        else:
            product_type = getattr(bet, 'product', getattr(bet, 'product_type', ''))
    
    webhook_url = PRODUCT_WEBHOOKS.get(product_type)
    if not webhook_url:
        return False

    payload = {"content": format_bet_message(bet)}

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        return response.status_code == 204
    except Exception as e:
        bet_id = bet.get('id', '?') if isinstance(bet, dict) else getattr(bet, 'id', '?')
        print(f"[DISCORD] Failed to post bet {bet_id}: {e}")
        return False


def send_custom_message(product_type: str, message: str):
    """Send a custom message to a specific product channel."""
    webhook_url = PRODUCT_WEBHOOKS.get(product_type)
    if not webhook_url:
        return False

    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=5)
        return response.status_code == 204
    except Exception as e:
        print(f"[DISCORD] Failed to send message: {e}")
        return False


def format_result_message(bet_info: dict) -> str:
    """Format a settled bet result for Discord."""
    outcome = bet_info.get('outcome', '').upper()
    home_team = bet_info.get('home_team', 'Unknown')
    away_team = bet_info.get('away_team', 'Unknown')
    selection = bet_info.get('selection', bet_info.get('parlay_description', ''))
    actual_score = bet_info.get('actual_score', bet_info.get('result', '?-?'))
    odds = bet_info.get('odds', bet_info.get('bookmaker_odds', 0))
    profit_loss = bet_info.get('profit_loss', 0)
    league = bet_info.get('league', '')
    product_type = bet_info.get('product_type', bet_info.get('product', ''))
    
    # Determine status emoji
    if outcome == 'WIN':
        emoji = ":white_check_mark:"
        status = "WON"
        color_bar = ":green_circle:"
    elif outcome in ['VOID', 'PUSH']:
        emoji = ":leftwards_arrow_with_hook:"
        status = "VOID"
        color_bar = ":white_circle:"
    else:
        emoji = ":x:"
        status = "LOST"
        color_bar = ":red_circle:"
    
    # Calculate USD
    profit_usd = profit_loss / 10.8 if profit_loss else 0
    
    lines = [
        f"{emoji} **RESULT: {status}**",
        "",
        f"**{league}** – {home_team} vs {away_team}",
        f":soccer: Final Score: **{actual_score}**",
        f":dart: Our Pick: {selection}",
        f":moneybag: Odds: {float(odds):.2f}" if odds else "",
        "",
        f"{color_bar} **P/L: ${profit_usd:+.0f} ({profit_loss:+.0f} SEK)**",
        "",
        "_PGR Sports Analytics_"
    ]
    
    return "\n".join([l for l in lines if l or l == ""])


def send_result_to_discord(bet_info: dict, product_type: str = None):
    """
    Send a settled bet result to the appropriate Discord channel.
    Maps product types to the correct webhooks.
    """
    if product_type is None:
        product_type = bet_info.get('product_type', bet_info.get('product', ''))
    
    # Normalize product type mapping
    type_map = {
        'exact_score': 'EXACT_SCORE',
        'EXACT_SCORE': 'EXACT_SCORE',
        'sgp': 'SGP',
        'SGP': 'SGP',
        'value_single': 'VALUE_SINGLE',
        'VALUE_SINGLE': 'VALUE_SINGLE',
        'ml_parlay': 'ML_PARLAY',
        'ML_PARLAY': 'ML_PARLAY',
        'basketball': 'BASKETBALL',
        'BASKETBALL': 'BASKETBALL',
        'basket_single': 'BASKET_SINGLE',
        'BASKET_SINGLE': 'BASKET_SINGLE',
        'basket_parlay': 'BASKET_PARLAY',
        'BASKET_PARLAY': 'BASKET_PARLAY',
    }
    
    normalized_type = type_map.get(product_type, product_type.upper() if product_type else 'EXACT_SCORE')
    webhook_url = PRODUCT_WEBHOOKS.get(normalized_type)
    
    if not webhook_url:
        print(f"[DISCORD] No webhook for product type: {product_type} (normalized: {normalized_type})")
        return False
    
    message = format_result_message(bet_info)
    
    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=5)
        if response.status_code == 204:
            print(f"[DISCORD] Sent result: {bet_info.get('home_team', '?')} vs {bet_info.get('away_team', '?')} = {bet_info.get('outcome', '?')}")
            return True
        else:
            print(f"[DISCORD] Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"[DISCORD] Failed to send result: {e}")
        return False


def send_daily_summary_to_discord(product_type: str, stats: dict):
    """
    Send end-of-day summary to a product channel.
    
    stats should contain: wins, losses, total, hit_rate, profit
    """
    webhook_url = PRODUCT_WEBHOOKS.get(product_type)
    if not webhook_url:
        return False
    
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    total = stats.get('total', wins + losses)
    hit_rate = stats.get('hit_rate', 0)
    profit = stats.get('profit', 0)
    profit_usd = profit / 10.8 if profit else 0
    
    profit_emoji = ":chart_with_upwards_trend:" if profit > 0 else ":chart_with_downwards_trend:"
    
    message = f"""
:bar_chart: **DAILY SUMMARY**

:white_check_mark: Wins: **{wins}**
:x: Losses: **{losses}**
:dart: Hit Rate: **{hit_rate:.1f}%**

{profit_emoji} **Day P/L: ${profit_usd:+.0f} ({profit:+.0f} SEK)**

_PGR Sports Analytics – AI-powered betting_
"""
    
    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=5)
        return response.status_code == 204
    except Exception as e:
        print(f"[DISCORD] Failed to send daily summary: {e}")
        return False
