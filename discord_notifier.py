import os
import json
import requests
from datetime import datetime


def format_kickoff(bet) -> str:
    """Extract and format kickoff time from bet data as 'Feb 6, 18:30 UTC'."""
    if isinstance(bet, dict):
        md = bet.get('match_date') or bet.get('commence_time') or bet.get('event_date', '')
    else:
        md = getattr(bet, 'match_date', '') or getattr(bet, 'commence_time', '') or getattr(bet, 'event_date', '')
    if not md:
        return ""
    try:
        if isinstance(md, datetime):
            dt = md
        else:
            s = str(md).strip()
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S%z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(s[:len(fmt)+5], fmt)
                    break
                except ValueError:
                    continue
            else:
                return ""
        if dt.hour == 0 and dt.minute == 0:
            return dt.strftime('%b %d')
        return dt.strftime('%b %d, %H:%M UTC')
    except:
        return ""


def build_analysis_reason(bet) -> str:
    """Build a human-readable analysis reason from bet data."""
    if isinstance(bet, dict):
        analysis_raw = bet.get('analysis', None)
        selection = bet.get('selection', '')
        odds = float(bet.get('odds', 0) or 0)
        edge = bet.get('edge_percentage', None)
        confidence = bet.get('confidence', None)
        model_prob = bet.get('model_prob', None)
    else:
        analysis_raw = getattr(bet, 'analysis', None)
        selection = getattr(bet, 'selection', '')
        odds = float(getattr(bet, 'odds', 0) or 0)
        edge = getattr(bet, 'edge_percentage', None)
        confidence = getattr(bet, 'confidence', None)
        model_prob = getattr(bet, 'model_prob', None)

    if not analysis_raw:
        return ""

    try:
        analysis = json.loads(analysis_raw) if isinstance(analysis_raw, str) else analysis_raw
    except:
        return ""

    if not isinstance(analysis, dict):
        return ""

    parts = []

    exp_home = analysis.get('expected_home_goals')
    exp_away = analysis.get('expected_away_goals')
    if exp_home is not None and exp_away is not None:
        total = float(exp_home) + float(exp_away)
        parts.append(f"xG {total:.1f}")

    avg_corners = analysis.get('avg_corners')
    if avg_corners is not None:
        parts.append(f"Avg {float(avg_corners):.1f} corners")

    avg_cards = analysis.get('avg_total_cards')
    if avg_cards is not None:
        parts.append(f"Avg {float(avg_cards):.1f} cards")

    p_model = analysis.get('p_model') or model_prob
    if p_model is not None:
        p = float(p_model)
        if p < 1:
            p = p * 100
        implied = (1 / odds * 100) if odds > 1 else 0
        parts.append(f"{p:.0f}% model vs {implied:.0f}% implied")

    if edge is not None:
        try:
            parts.append(f"+{float(edge):.1f}% edge")
        except:
            pass

    if not parts:
        return ""

    return "  _" + " | ".join(parts) + "_"

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
    """Format parlay bet matching standard Discord format."""
    if isinstance(bet, dict):
        legs = bet.get('legs', [])
        odds = bet.get('odds', 0)
    else:
        legs = getattr(bet, 'legs', [])
        odds = getattr(bet, 'odds', 0)
    
    content = "🎟️ **PARLAYS — Today's Picks**\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for leg in legs:
        home = leg.get('home_team', '')
        away = leg.get('away_team', '')
        selection = leg.get('selection', '')
        leg_odds = leg.get('odds', 0)
        leg_league = leg.get('league', '')
        ko = format_kickoff(leg)
        if leg_league:
            content += f"**{leg_league}**\n"
        ko_str = f" | {ko}" if ko else ""
        content += f"• {home} vs {away} — **{selection}** @ {float(leg_odds):.2f}{ko_str} (TBD) 🔘\n"
        leg_reason = build_analysis_reason(leg)
        if leg_reason:
            content += f"{leg_reason}\n"
        content += "\n"
    
    content += f"**Combined Odds:** {float(odds):.2f}\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"*{len(legs)} leg(s) | Flat 1u | PGR Analytics*"
    
    return content


def format_value_single_message(bet) -> str:
    """Format Value Single bet matching standard Discord format."""
    if isinstance(bet, dict):
        league = bet.get('league', 'Unknown League')
        home_team = bet.get('home_team', '')
        away_team = bet.get('away_team', '')
        selection = bet.get('selection', '')
        odds = bet.get('odds', 0)
        market = bet.get('market', '')
        product_type = bet.get('product', bet.get('product_type', '')).upper()
    else:
        league = getattr(bet, 'league', 'Unknown League')
        home_team = getattr(bet, 'home_team', '')
        away_team = getattr(bet, 'away_team', '')
        selection = getattr(bet, 'selection', '')
        odds = getattr(bet, 'odds', 0)
        market = getattr(bet, 'market', '')
        product_type = getattr(bet, 'product', getattr(bet, 'product_type', '')).upper()
    
    market_upper = (market or product_type or '').upper()
    if 'CORNER' in market_upper:
        product_emoji = "🔷"
        product_label = "CORNERS"
    elif 'CARD' in market_upper:
        product_emoji = "🟨"
        product_label = "CARDS"
    elif 'BASKET' in market_upper or 'NCAAB' in league.upper() or 'NCAA' in league.upper():
        product_emoji = "🏀"
        product_label = "BASKETBALL"
    else:
        product_emoji = "🎯"
        product_label = "VALUE SINGLES"
    
    reason = build_analysis_reason(bet)
    ko = format_kickoff(bet)
    ko_str = f" | {ko}" if ko else ""
    
    content = f"{product_emoji} **{product_label} — Today's Picks**\n\n"
    content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += f"**{league}**\n"
    content += f"• {home_team} vs {away_team} — **{selection}** @ {float(odds or 0):.2f}{ko_str} (TBD) 🔘\n"
    if reason:
        content += f"{reason}\n"
    content += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    content += "*1 pick(s) | Flat 1u | PGR Analytics*"
    
    return content


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
    """Create a clean Discord embed matching the standard format."""
    if isinstance(bet, dict):
        home_team = bet.get('home_team', 'TBD')
        away_team = bet.get('away_team', 'TBD')
        selection = bet.get('selection', '')
        odds = bet.get('odds', 0)
        league = bet.get('league', 'Unknown')
        market = bet.get('market', product_type or '')
        legs = bet.get('legs', [])
        units = bet.get('units', bet.get('stake', 1.0))
    else:
        home_team = getattr(bet, 'home_team', 'TBD')
        away_team = getattr(bet, 'away_team', 'TBD')
        selection = getattr(bet, 'selection', '')
        odds = getattr(bet, 'odds', 0)
        league = getattr(bet, 'league', 'Unknown')
        market = getattr(bet, 'market', product_type or '')
        legs = getattr(bet, 'legs', [])
        units = getattr(bet, 'units', getattr(bet, 'stake', 1.0))
    
    market_upper = (market or product_type or '').upper()
    
    if 'CORNER' in market_upper:
        product_emoji = "🔷"
        product_label = "CORNERS"
    elif 'CARD' in market_upper:
        product_emoji = "🟨"
        product_label = "CARDS"
    elif 'SHOT' in market_upper:
        product_emoji = "🎯"
        product_label = "SHOTS"
    elif 'PARLAY' in market_upper or 'MULTI' in market_upper or legs:
        product_emoji = "🎟️"
        product_label = "PARLAYS"
    elif 'BASKET' in market_upper:
        product_emoji = "🏀"
        product_label = "BASKETBALL"
    else:
        product_emoji = "🎯"
        product_label = "VALUE SINGLES"
    
    try:
        units_val = float(units or 1)
    except:
        units_val = 1
    
    if legs and len(legs) > 0:
        content = f"{product_emoji} **{product_label} — Today's Picks**\n\n"
        content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, leg in enumerate(legs, 1):
            ht = leg.get('home_team', '')
            at = leg.get('away_team', '')
            sel = leg.get('selection', '')
            leg_odds = leg.get('odds', 0)
            leg_league = leg.get('league', '')
            ko = format_kickoff(leg)
            if leg_league:
                content += f"**{leg_league}**\n"
            ko_str = f" | {ko}" if ko else ""
            content += f"• {ht} vs {at} — **{sel}** @ {float(leg_odds):.2f}{ko_str} (TBD) 🔘\n"
            leg_reason = build_analysis_reason(leg)
            if leg_reason:
                content += f"{leg_reason}\n"
            content += "\n"
        content += f"**Combined Odds:** {float(odds or 0):.2f}\n\n"
        content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        content += f"*{len(legs)} leg(s) | Flat {units_val:.0f}u | PGR Analytics*"
    else:
        reason = build_analysis_reason(bet)
        ko = format_kickoff(bet)
        ko_str = f" | {ko}" if ko else ""
        content = f"{product_emoji} **{product_label} — Today's Picks**\n\n"
        content += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        content += f"**{league}**\n"
        content += f"• {home_team} vs {away_team} — **{selection}** @ {float(odds or 0):.2f}{ko_str} (TBD) 🔘\n"
        if reason:
            content += f"{reason}\n"
        content += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        content += f"*1 pick(s) | Flat {units_val:.0f}u | PGR Analytics*"
    
    embed = {
        "description": content[:4000],
        "color": 3066993,
        "footer": {"text": f"PGR Sports Analytics — {product_label}"}
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
    
    is_basketball = 'BASKET' in product_type or 'NCAAB' in league.upper() or 'NCAA' in league.upper()
    score_emoji = "🏀" if is_basketball else "⚽"
    
    embed = {
        "title": f"{emoji} {status} | {selection}",
        "description": f"**{home_team}** vs **{away_team}**",
        "color": color,
        "fields": [
            {"name": f"{score_emoji} Score", "value": f"`{actual_score}`", "inline": True},
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
