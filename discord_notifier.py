import os
import requests
from datetime import datetime

PRODUCT_WEBHOOKS = {
    "EXACT_SCORE": os.getenv("WEBHOOK_Final_score"),
    "ML_PARLAY": os.getenv("WEBHOOK_ML_PARLAYS"),
    "MULTI_MATCH_PARLAY": os.getenv("WEBHOOK_PARLAYS"),
    "PARLAY": os.getenv("WEBHOOK_PARLAYS"),
    "VALUE_SINGLE": os.getenv("WEBHOOK_Value_singles"),
    "BASKETBALL_SINGLE": os.getenv("WEB_HOOK_College_basket"),
    "BASKETBALL": os.getenv("WEB_HOOK_College_basket"),
    "BASKET_SINGLE": os.getenv("WEB_HOOK_College_basket"),
    "BASKET_PARLAY": os.getenv("WEB_HOOK_College_basket"),
    "CORNERS": os.getenv("DISCORD_PROPS_WEBHOOK_URL"),
    "CARDS": os.getenv("DISCORD_PROPS_WEBHOOK_URL"),
    "SHOTS": os.getenv("DISCORD_PROPS_WEBHOOK_URL"),
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


def create_bet_embed(bet, product_type=None) -> dict:
    """Create a clean Discord embed for any bet type."""
    if isinstance(bet, dict):
        home_team = bet.get('home_team', 'TBD')
        away_team = bet.get('away_team', 'TBD')
        selection = bet.get('selection', '')
        odds = bet.get('odds', 0)
        ev = bet.get('ev', bet.get('edge_percentage', 0))
        confidence = bet.get('confidence', 0)
        kickoff = bet.get('match_date', bet.get('kickoff', ''))
        league = bet.get('league', '')
        trust_level = bet.get('trust_level', 'L2')
        market = bet.get('market', product_type or '')
        legs = bet.get('legs', [])
    else:
        home_team = getattr(bet, 'home_team', 'TBD')
        away_team = getattr(bet, 'away_team', 'TBD')
        selection = getattr(bet, 'selection', '')
        odds = getattr(bet, 'odds', 0)
        ev = getattr(bet, 'ev', getattr(bet, 'edge_percentage', 0))
        confidence = getattr(bet, 'confidence', 0)
        kickoff = getattr(bet, 'match_date', getattr(bet, 'kickoff', ''))
        league = getattr(bet, 'league', '')
        trust_level = getattr(bet, 'trust_level', 'L2')
        market = getattr(bet, 'market', product_type or '')
        legs = getattr(bet, 'legs', [])
    
    market_upper = (market or product_type or '').upper()
    
    if 'CORNER' in market_upper:
        emoji = "🔷"
        color = 0x3498db
    elif 'CARD' in market_upper:
        emoji = "🟨"
        color = 0xf1c40f
    elif 'SHOT' in market_upper:
        emoji = "🎯"
        color = 0xe74c3c
    elif 'ML_PARLAY' in market_upper:
        emoji = "🎰"
        color = 0x9b59b6
        market_upper = "ML PARLAY"
    elif 'PARLAY' in market_upper or 'MULTI' in market_upper or legs:
        emoji = "🎟️"
        color = 0x9b59b6
        market_upper = "MULTI-MARKET PARLAY"
    elif 'BASKET' in market_upper:
        emoji = "🏀"
        color = 0xe67e22
    elif 'BTTS' in selection.upper():
        emoji = "⚽"
        color = 0x2ecc71
    elif 'OVER' in selection.upper() or 'UNDER' in selection.upper():
        emoji = "📊"
        color = 0x3498db
    else:
        emoji = "💰"
        color = 0x2ecc71
    
    try:
        ev_val = float(ev or 0)
        if ev_val > 100:
            ev_val = ev_val / 100
        if ev_val < 1 and ev_val > 0:
            ev_val = ev_val * 100
    except:
        ev_val = 0
    
    ev_bullets = "🔥🔥🔥" if ev_val >= 8 else "🔥🔥" if ev_val >= 5 else "🔥" if ev_val >= 3 else ""
    
    if legs and len(legs) > 0:
        if 'ML_PARLAY' in (market or product_type or '').upper():
            legs_lines = []
            for l in legs[:5]:
                ht = l.get('home_team', '')
                at = l.get('away_team', '')
                sel = l.get('selection', '')
                leg_odds = l.get('odds', 0)
                if ht and at:
                    legs_lines.append(f"• **{ht}** vs {at}: {sel} @ {leg_odds:.2f}")
                else:
                    legs_lines.append(f"• {sel} @ {leg_odds:.2f}")
            description = "\n".join(legs_lines)
        else:
            description = f"**{home_team}** vs **{away_team}**"
    else:
        description = f"**{home_team}** vs **{away_team}**"
    
    try:
        conf_val = float(confidence or 0)
        if conf_val < 1 and conf_val > 0:
            conf_val = conf_val * 100
    except:
        conf_val = 0
    
    fields = [
        {"name": "📊 Odds", "value": f"`{float(odds or 0):.2f}`", "inline": True},
        {"name": "💎 EV", "value": f"`+{ev_val:.1f}%` {ev_bullets}", "inline": True},
    ]
    
    if conf_val > 0:
        fields.append({"name": "🎯 Confidence", "value": f"`{conf_val:.0f}%`", "inline": True})
    
    if trust_level:
        trust_emoji = "🔥" if trust_level == 'L1' else "💎" if trust_level == 'L2' else "📊"
        fields.append({"name": "🏆 Trust", "value": f"`{trust_level}` {trust_emoji}", "inline": True})
    
    embed = {
        "title": f"{emoji} {market_upper} | {selection}",
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": f"{league} • {str(kickoff)[:16] if kickoff else 'TBD'}"},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def send_bet_to_discord(bet, product_type=None):
    """
    Send a bet to the appropriate Discord channel using clean embeds.
    Silently skips if no webhook is configured (won't crash the engine).
    """
    if product_type is None:
        if isinstance(bet, dict):
            product_type = bet.get('product', bet.get('product_type', bet.get('market', '')))
        else:
            product_type = getattr(bet, 'product', getattr(bet, 'product_type', getattr(bet, 'market', '')))
    
    webhook_url = PRODUCT_WEBHOOKS.get(product_type.upper() if product_type else '')
    if not webhook_url:
        return False

    embed = create_bet_embed(bet, product_type)
    payload = {
        "username": "PGR Picks Bot",
        "embeds": [embed]
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        return response.status_code in [200, 204]
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


def create_result_embed(bet_info: dict) -> dict:
    """Create a clean Discord embed for settled bet result."""
    outcome = bet_info.get('outcome', '').upper()
    home_team = bet_info.get('home_team', 'Unknown')
    away_team = bet_info.get('away_team', 'Unknown')
    selection = bet_info.get('selection', bet_info.get('parlay_description', ''))
    actual_score = bet_info.get('actual_score', bet_info.get('result', '?-?'))
    odds = bet_info.get('odds', bet_info.get('bookmaker_odds', 0))
    league = bet_info.get('league', '')
    product_type = bet_info.get('product_type', bet_info.get('product', '')).upper()
    
    if outcome in ['WIN', 'WON']:
        emoji = "✅"
        status = "WON"
        color = 0x2ecc71
    elif outcome in ['VOID', 'PUSH']:
        emoji = "↩️"
        status = "VOID"
        color = 0x95a5a6
    else:
        emoji = "❌"
        status = "LOST"
        color = 0xe74c3c
    
    try:
        profit_units = (float(odds) - 1) if outcome in ['WIN', 'WON'] else -1.0
        if outcome in ['VOID', 'PUSH']:
            profit_units = 0.0
    except:
        profit_units = 0.0
    
    embed = {
        "title": f"{emoji} {status} | {selection}",
        "description": f"**{home_team}** vs **{away_team}**",
        "color": color,
        "fields": [
            {"name": "⚽ Score", "value": f"`{actual_score}`", "inline": True},
            {"name": "📊 Odds", "value": f"`{float(odds or 0):.2f}`", "inline": True},
            {"name": "💰 P/L", "value": f"`{profit_units:+.2f}u`", "inline": True},
        ],
        "footer": {"text": f"{league} • {product_type}"},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def format_result_message(bet_info: dict) -> str:
    """Format a settled bet result for Discord (legacy text format)."""
    outcome = bet_info.get('outcome', '').upper()
    home_team = bet_info.get('home_team', 'Unknown')
    away_team = bet_info.get('away_team', 'Unknown')
    selection = bet_info.get('selection', bet_info.get('parlay_description', ''))
    actual_score = bet_info.get('actual_score', bet_info.get('result', '?-?'))
    odds = bet_info.get('odds', bet_info.get('bookmaker_odds', 0))
    league = bet_info.get('league', '')
    
    if outcome in ['WIN', 'WON']:
        emoji = "✅"
        status = "WON"
    elif outcome in ['VOID', 'PUSH']:
        emoji = "↩️"
        status = "VOID"
    else:
        emoji = "❌"
        status = "LOST"
    
    try:
        profit_units = (float(odds) - 1) if outcome in ['WIN', 'WON'] else -1.0
        if outcome in ['VOID', 'PUSH']:
            profit_units = 0.0
    except:
        profit_units = 0.0
    
    return f"{emoji} **{status}** | {home_team} vs {away_team} | {selection} @ {float(odds or 0):.2f} | P/L: `{profit_units:+.2f}u`"


def send_result_to_discord(bet_info: dict, product_type: str = None):
    """
    Send a settled bet result to the appropriate Discord channel using clean embeds.
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
        'corners': 'CORNERS',
        'CORNERS': 'CORNERS',
        'cards': 'CARDS',
        'CARDS': 'CARDS',
    }
    
    normalized_type = type_map.get(product_type, product_type.upper() if product_type else 'EXACT_SCORE')
    webhook_url = PRODUCT_WEBHOOKS.get(normalized_type)
    
    if not webhook_url:
        print(f"[DISCORD] No webhook for product type: {product_type} (normalized: {normalized_type})")
        return False
    
    embed = create_result_embed(bet_info)
    payload = {
        "username": "PGR Results Bot",
        "embeds": [embed]
    }
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        if response.status_code in [200, 204]:
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
