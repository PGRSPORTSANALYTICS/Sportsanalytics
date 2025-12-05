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
