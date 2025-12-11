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


def format_parlay_message(bet) -> str:
    """Format ML Parlay bet with clear leg-by-leg breakdown."""
    if isinstance(bet, dict):
        legs = bet.get('legs', [])
        kickoff = bet.get('match_date', bet.get('kickoff', ''))
        odds = bet.get('odds', 0)
        ev = bet.get('ev', None)
        trust_level = bet.get('trust_level', 'L2')
        num_legs = bet.get('num_legs', len(legs))
    else:
        legs = getattr(bet, 'legs', [])
        kickoff = getattr(bet, 'match_date', getattr(bet, 'kickoff', ''))
        odds = getattr(bet, 'odds', 0)
        ev = getattr(bet, 'ev', None)
        trust_level = getattr(bet, 'trust_level', 'L2')
        num_legs = getattr(bet, 'num_legs', len(legs))
    
    lines = [
        ":ticket: **ML PARLAY**",
        f"Kickoff: `{kickoff}`",
        ""
    ]
    
    if legs:
        lines.append("**PICKS:**")
        for i, leg in enumerate(legs, 1):
            home = leg.get('home_team', '')
            away = leg.get('away_team', '')
            selection = leg.get('selection', '')
            leg_odds = leg.get('odds', 0)
            lines.append(f"{i}. **{home}** vs {away}")
            lines.append(f"   :dart: {selection} @ {float(leg_odds):.2f}")
        lines.append("")
    
    lines.append(f":moneybag: **Combined Odds:** {float(odds):.2f}")
    
    if ev is not None:
        try:
            ev_val = float(ev)
            if ev_val > 100:
                ev_val = ev_val / 100
            if ev_val < 1:
                ev_val = ev_val * 100
            lines.append(f":chart_with_upwards_trend: **EV:** {ev_val:.1f}%")
        except:
            pass
    
    lines.append(f":pushpin: **Trust:** {trust_level}")
    lines.append(f":coin: **Stake:** 1 unit")
    lines.append("")
    lines.append("_PGR Sports Analytics – AI-powered betting_")
    
    return "\n".join(lines)


def format_value_single_message(bet) -> str:
    """Format Value Single bet with clear actionable info."""
    if isinstance(bet, dict):
        league = bet.get('league', 'Unknown League')
        home_team = bet.get('home_team', '')
        away_team = bet.get('away_team', '')
        kickoff = bet.get('match_date', bet.get('kickoff', ''))
        market = bet.get('market', '')
        selection = bet.get('selection', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', None)
        trust_level = bet.get('trust_level', 'L2')
        confidence = bet.get('confidence', None)
        product_type = bet.get('product', bet.get('product_type', '')).upper()
    else:
        league = getattr(bet, 'league', 'Unknown League')
        home_team = getattr(bet, 'home_team', '')
        away_team = getattr(bet, 'away_team', '')
        kickoff = getattr(bet, 'match_date', getattr(bet, 'kickoff', ''))
        market = getattr(bet, 'market', '')
        selection = getattr(bet, 'selection', '')
        odds = getattr(bet, 'odds', 0)
        ev = getattr(bet, 'ev', None)
        trust_level = getattr(bet, 'trust_level', 'L2')
        confidence = getattr(bet, 'confidence', None)
        product_type = getattr(bet, 'product', getattr(bet, 'product_type', '')).upper()
    
    is_basketball = 'BASKET' in product_type or 'NCAAB' in league.upper() or 'NCAA' in league.upper()
    sport_emoji = ":basketball:" if is_basketball else ":soccer:"
    
    lines = [
        f"{sport_emoji} **{league}**",
        f"**{home_team}** vs **{away_team}**",
        f"Kickoff: `{kickoff}`",
        "",
        f":dart: **PICK:** {selection}",
        f":moneybag: **Odds:** {float(odds):.2f}" if odds else "",
    ]
    
    if ev is not None:
        try:
            ev_val = float(ev)
            if ev_val > 100:
                ev_val = ev_val / 100
            if ev_val < 1:
                ev_val = ev_val * 100
            lines.append(f":chart_with_upwards_trend: **EV:** {ev_val:.1f}%")
        except:
            pass
    
    if confidence is not None:
        try:
            conf_val = float(confidence)
            if conf_val < 1:
                conf_val = conf_val * 100
            lines.append(f":bar_chart: **Confidence:** {conf_val:.0f}%")
        except:
            pass
    
    lines.append(f":pushpin: **Trust:** {trust_level}")
    lines.append(f":coin: **Stake:** 1 unit")
    lines.append("")
    lines.append("_PGR Sports Analytics – AI-powered betting_")
    
    return "\n".join([l for l in lines if l or l == ""])


def format_bet_message(bet) -> str:
    """Format bet details for Discord message based on product type."""
    if isinstance(bet, dict):
        product_type = bet.get('product', bet.get('product_type', '')).upper()
        legs = bet.get('legs', [])
    else:
        product_type = getattr(bet, 'product', getattr(bet, 'product_type', '')).upper()
        legs = getattr(bet, 'legs', [])
    
    if product_type == 'ML_PARLAY' or legs:
        return format_parlay_message(bet)
    elif product_type in ['VALUE_SINGLE', 'BASKET_SINGLE', 'BASKETBALL_SINGLE']:
        return format_value_single_message(bet)
    else:
        return format_value_single_message(bet)


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
    product_type = bet_info.get('product_type', bet_info.get('product', '')).upper()
    
    is_basketball = 'BASKET' in product_type or 'NCAAB' in league.upper() or 'NCAA' in league.upper()
    sport_emoji = ":basketball:" if is_basketball else ":soccer:"
    
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
    
    try:
        profit_units = (float(odds) - 1) if outcome == 'WIN' else -1.0
        if outcome in ['VOID', 'PUSH']:
            profit_units = 0.0
    except:
        profit_units = 0.0
    
    lines = [
        f"{emoji} **RESULT: {status}**",
        "",
        f"**{league}** – {home_team} vs {away_team}",
        f"{sport_emoji} Final Score: **{actual_score}**",
        f":dart: Our Pick: {selection}",
        f":moneybag: Odds: {float(odds):.2f}" if odds else "",
        "",
        f"{color_bar} **P/L: {profit_units:+.2f} units**",
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
    
    stats should contain: wins, losses, total, hit_rate, profit_units
    """
    webhook_url = PRODUCT_WEBHOOKS.get(product_type)
    if not webhook_url:
        return False
    
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    total = stats.get('total', wins + losses)
    hit_rate = stats.get('hit_rate', 0)
    profit_units = stats.get('profit_units', stats.get('profit', 0))
    
    profit_emoji = ":chart_with_upwards_trend:" if profit_units > 0 else ":chart_with_downwards_trend:"
    
    message = f"""
:bar_chart: **DAILY SUMMARY**

:white_check_mark: Wins: **{wins}**
:x: Losses: **{losses}**
:dart: Hit Rate: **{hit_rate:.1f}%**

{profit_emoji} **Day P/L: {profit_units:+.2f} units**

_PGR Sports Analytics – AI-powered betting_
"""
    
    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=5)
        return response.status_code == 204
    except Exception as e:
        print(f"[DISCORD] Failed to send daily summary: {e}")
        return False
