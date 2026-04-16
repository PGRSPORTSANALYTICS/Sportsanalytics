"""
Stripe Subscription Sync
========================
Safety-net cron job that runs every 10 minutes.

Webhooks are the primary grant/revoke mechanism, but they can be missed
(network issues, Stripe outages).  This module verifies every premium
user's Stripe subscription status directly and deactivates anyone whose
subscription is no longer active.

Logic:
  1. Fetch all users with premium_status = TRUE from pgr_users
  2. For each user:
     a. If premium_until has passed → deactivate immediately (no API call)
     b. If stripe_subscription_id known → ask Stripe for real status
        • 'active' or 'trialing' → keep premium
        • anything else → deactivate + revoke Discord role
  3. Log a summary

Called from combined_sports_runner.py every 10 minutes (synchronous).
"""

import logging
import os
import time
from datetime import datetime
from typing import Optional

import requests

from auth_premium import deactivate_premium
from db_helper import db_helper

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"active", "trialing"}


def _stripe_key() -> Optional[str]:
    return os.getenv("STRIPE_SECRET_KEY") or None


def _revoke_discord_role_sync(discord_id: str):
    """Synchronous Discord role revoke via REST API."""
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    guild_id  = os.getenv("DISCORD_GUILD_ID")
    role_id   = os.getenv("DISCORD_PREMIUM_ROLE_ID")

    if not (bot_token and guild_id and role_id):
        return

    url     = f"https://discord.com/api/v10/guilds/{guild_id}/members/{discord_id}/roles/{role_id}"
    headers = {"Authorization": f"Bot {bot_token}"}
    try:
        r = requests.delete(url, headers=headers, timeout=8)
        if r.status_code in (200, 204):
            logger.info("subscription_sync: Discord role revoked for %s", discord_id)
        else:
            logger.warning("subscription_sync: Discord revoke HTTP %d for %s", r.status_code, discord_id)
    except Exception as exc:
        logger.debug("subscription_sync: Discord revoke error: %s", exc)


def sync_stripe_subscriptions() -> dict:
    """
    Verify all premium users against Stripe. Fully synchronous.
    Safe to call even if STRIPE_SECRET_KEY is not set (skips silently).
    """
    api_key = _stripe_key()
    if not api_key:
        logger.debug("subscription_sync: STRIPE_SECRET_KEY not set — skipping")
        return {"skipped": True}

    rows = db_helper.execute("""
        SELECT discord_user_id, stripe_subscription_id, premium_until
        FROM pgr_users
        WHERE premium_status = TRUE
    """, fetch="all") or []

    checked = 0
    expired_by_date = 0
    revoked_by_stripe = 0
    errors = 0
    kept = 0

    for row in rows:
        discord_id, sub_id, premium_until = row

        # ── Fast path: premium_until in past ─────────────────────────────
        if premium_until and premium_until < datetime.utcnow():
            deactivate_premium(discord_id)
            _revoke_discord_role_sync(discord_id)
            expired_by_date += 1
            logger.info(
                "subscription_sync: expired by date — discord=%s until=%s",
                discord_id, premium_until
            )
            continue

        # ── No sub_id → manually granted, skip API check ─────────────────
        if not sub_id:
            kept += 1
            continue

        # ── Ask Stripe for real subscription status ───────────────────────
        checked += 1
        try:
            resp = requests.get(
                f"https://api.stripe.com/v1/subscriptions/{sub_id}",
                auth=(api_key, ""),
                timeout=10,
            )
            if resp.status_code == 404:
                # Subscription not found → deactivate
                deactivate_premium(discord_id)
                _revoke_discord_role_sync(discord_id)
                revoked_by_stripe += 1
                logger.warning(
                    "subscription_sync: sub not found in Stripe — discord=%s sub=%s",
                    discord_id, sub_id
                )
                continue

            if resp.status_code != 200:
                errors += 1
                logger.error(
                    "subscription_sync: Stripe API HTTP %d for discord=%s",
                    resp.status_code, discord_id
                )
                continue

            status = resp.json().get("status", "")
            if status not in ACTIVE_STATUSES:
                deactivate_premium(discord_id)
                _revoke_discord_role_sync(discord_id)
                revoked_by_stripe += 1
                logger.warning(
                    "subscription_sync: REVOKED — discord=%s sub=%s stripe_status=%s",
                    discord_id, sub_id, status
                )
            else:
                kept += 1

        except Exception as exc:
            errors += 1
            logger.error(
                "subscription_sync: error for discord=%s: %s", discord_id, exc
            )

    summary = {
        "checked":          checked,
        "kept":             kept,
        "expired_by_date":  expired_by_date,
        "revoked_by_stripe": revoked_by_stripe,
        "errors":           errors,
    }

    if expired_by_date or revoked_by_stripe:
        logger.warning(
            "subscription_sync done — checked=%d kept=%d expired=%d revoked=%d errors=%d",
            checked, kept, expired_by_date, revoked_by_stripe, errors
        )
    else:
        logger.info(
            "subscription_sync OK — %d active verified, %d errors",
            kept + checked, errors
        )

    return summary
