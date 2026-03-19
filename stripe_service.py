"""
Stripe service — checkout sessions, customer portal, Discord role management.
Ported from pgr-backend/app/routers/stripe_routes.py and adapted for this project.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx
import stripe

from db_helper import db_helper
from auth_premium import activate_premium, deactivate_premium, deactivate_by_stripe_customer, activate_by_stripe_customer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _stripe_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not set")
    return key

def _price_id() -> str:
    pid = os.getenv("STRIPE_PRICE_ID", "")
    if not pid:
        raise RuntimeError("STRIPE_PRICE_ID not set")
    return pid

def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "https://pgrsportsanalytics.com")

def _success_url() -> str:
    return os.getenv("FRONTEND_SUCCESS_URL", f"{_frontend_url()}/home?success=1")


# ---------------------------------------------------------------------------
# Discord role management (via Bot API)
# ---------------------------------------------------------------------------

async def grant_discord_role(discord_user_id: str) -> bool:
    """Assign the premium Discord role via Bot API. Returns True on success."""
    bot_token    = os.getenv("DISCORD_BOT_TOKEN")
    guild_id     = os.getenv("DISCORD_GUILD_ID")
    role_id      = os.getenv("DISCORD_PREMIUM_ROLE_ID")

    if not (bot_token and guild_id and role_id):
        logger.warning("Discord role grant skipped — DISCORD_BOT_TOKEN / GUILD_ID / PREMIUM_ROLE_ID not set")
        return False

    url     = f"https://discord.com/api/v10/guilds/{guild_id}/members/{discord_user_id}/roles/{role_id}"
    headers = {"Authorization": f"Bot {bot_token}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.put(url, headers=headers)
        if r.status_code in (200, 204):
            logger.info(f"Discord premium role granted to {discord_user_id}")
            return True
        logger.warning(f"Discord role grant failed: {r.status_code} {r.text}")
        return False
    except Exception as e:
        logger.error(f"Discord role grant error: {e}")
        return False


async def revoke_discord_role(discord_user_id: str) -> bool:
    """Remove the premium Discord role via Bot API. Returns True on success."""
    bot_token    = os.getenv("DISCORD_BOT_TOKEN")
    guild_id     = os.getenv("DISCORD_GUILD_ID")
    role_id      = os.getenv("DISCORD_PREMIUM_ROLE_ID")

    if not (bot_token and guild_id and role_id):
        logger.warning("Discord role revoke skipped — DISCORD_BOT_TOKEN / GUILD_ID / PREMIUM_ROLE_ID not set")
        return False

    url     = f"https://discord.com/api/v10/guilds/{guild_id}/members/{discord_user_id}/roles/{role_id}"
    headers = {"Authorization": f"Bot {bot_token}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(url, headers=headers)
        if r.status_code in (200, 204):
            logger.info(f"Discord premium role revoked from {discord_user_id}")
            return True
        logger.warning(f"Discord role revoke failed: {r.status_code} {r.text}")
        return False
    except Exception as e:
        logger.error(f"Discord role revoke error: {e}")
        return False


# ---------------------------------------------------------------------------
# Stripe metadata extraction helpers
# ---------------------------------------------------------------------------

def extract_discord_id(obj: Dict[str, Any]) -> Optional[str]:
    """
    Look for discord_id in all the places Stripe might store it:
      1. client_reference_id (checkout session)
      2. metadata.discord_id
      3. subscription_details.metadata.discord_id
    """
    if not obj:
        return None

    # Checkout session: client_reference_id
    if obj.get("client_reference_id"):
        return str(obj["client_reference_id"])

    # Top-level metadata
    meta = obj.get("metadata") or {}
    if meta.get("discord_id"):
        return str(meta["discord_id"])

    # Nested subscription_details metadata
    sub_details = obj.get("subscription_details") or {}
    meta2 = sub_details.get("metadata") or {}
    if meta2.get("discord_id"):
        return str(meta2["discord_id"])

    return None


# ---------------------------------------------------------------------------
# Idempotency (stripe_events table)
# ---------------------------------------------------------------------------

def ensure_stripe_events_table():
    """Create stripe_events table if it doesn't exist."""
    db_helper.execute("""
        CREATE TABLE IF NOT EXISTS stripe_events (
            id          TEXT PRIMARY KEY,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def is_duplicate_event(event_id: str) -> bool:
    """
    Insert event_id; return True if it was already processed (duplicate).
    """
    try:
        db_helper.execute(
            "INSERT INTO stripe_events (id) VALUES (%s) ON CONFLICT DO NOTHING",
            (event_id,),
        )
        # Check if the row was actually new
        row = db_helper.execute(
            "SELECT COUNT(*) FROM stripe_events WHERE id = %s AND received_at > NOW() - INTERVAL '5 seconds'",
            (event_id,), fetch='one'
        )
        # If count == 0, it existed before (was deduplicated)
        return (row[0] == 0) if row else False
    except Exception as e:
        logger.error(f"Idempotency check error: {e}")
        return False


# ---------------------------------------------------------------------------
# Checkout session creation
# ---------------------------------------------------------------------------

def create_checkout_session(discord_id: str, plan: str = "premium") -> str:
    """
    Create a Stripe Checkout Session for a Discord user.
    Returns the session URL to redirect the user to.
    """
    stripe.api_key = _stripe_key()

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": _price_id(), "quantity": 1}],
        client_reference_id=str(discord_id),
        success_url=_success_url(),
        cancel_url=f"{_frontend_url()}/upgrade",
        metadata={
            "discord_id": str(discord_id),
            "plan": str(plan),
        },
        subscription_data={
            "metadata": {
                "discord_id": str(discord_id),
                "plan": str(plan),
            }
        },
        allow_promotion_codes=True,
    )
    return session.url


# ---------------------------------------------------------------------------
# Customer portal
# ---------------------------------------------------------------------------

def create_customer_portal(stripe_customer_id: str) -> str:
    """
    Create a Stripe Billing Portal session for an existing customer.
    Returns the portal URL.
    """
    stripe.api_key = _stripe_key()

    session = stripe.billing_portal.Session.create(
        customer=str(stripe_customer_id),
        return_url=f"{_frontend_url()}/home",
    )
    return session.url


# ---------------------------------------------------------------------------
# Subscription lookup helper (used when invoice doesn't carry discord_id)
# ---------------------------------------------------------------------------

def resolve_discord_id_from_subscription(subscription_id: str) -> Optional[str]:
    """Fetch the subscription from Stripe and extract discord_id from its metadata."""
    try:
        stripe.api_key = _stripe_key()
        sub = stripe.Subscription.retrieve(subscription_id)
        return extract_discord_id(dict(sub))
    except Exception as e:
        logger.error(f"Could not retrieve subscription {subscription_id}: {e}")
        return None
