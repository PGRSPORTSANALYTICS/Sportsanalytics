#!/usr/bin/env python3
"""
PGR Premium Auth
================
Handles:
- pgr_users table (discord_user_id + premium_status)
- Session cookie creation / validation
- Premium check helper
- activate / deactivate premium (called by Stripe webhook)
"""

import os
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

from db_helper import db_helper

logger = logging.getLogger(__name__)

JWT_SECRET    = os.getenv("JWT_SECRET", "CHANGEME_pgr_secret")
JWT_ALGORITHM = "HS256"
COOKIE_NAME        = "pgr_session"
ADMIN_COOKIE_NAME  = "pgr_admin_session"
COOKIE_MAX_AGE     = 60 * 60 * 24 * 30   # 30 days
ADMIN_COOKIE_MAX_AGE = 60 * 60 * 8       # 8 hours

def is_production() -> bool:
    """True when running on Railway or any explicit production environment."""
    return (
        os.getenv("ENV") == "production"
        or os.getenv("RAILWAY_ENVIRONMENT") is not None
        or os.getenv("RAILWAY_PROJECT_ID") is not None
    )

# Routes that require an active premium session (HTML pages)
PROTECTED_HTML = {"/home", "/app", "/preview", "/value", "/opportunities"}
# API routes that require premium (return 401 JSON instead of redirect)
PROTECTED_API  = {"/api/bets", "/bets"}


# ─── DB bootstrap ────────────────────────────────────────────────────────────

def ensure_users_table():
    """Create pgr_users table if it does not exist."""
    try:
        db_helper.execute("""
            CREATE TABLE IF NOT EXISTS pgr_users (
                discord_user_id      TEXT PRIMARY KEY,
                username             TEXT,
                email                TEXT,
                premium_status       BOOLEAN DEFAULT FALSE,
                premium_until        TIMESTAMP,
                stripe_customer_id   TEXT,
                stripe_subscription_id TEXT,
                created_at           TIMESTAMP DEFAULT NOW(),
                updated_at           TIMESTAMP DEFAULT NOW()
            )
        """)
        logger.info("pgr_users table ready")
    except Exception as e:
        logger.error(f"ensure_users_table error: {e}")


def ensure_dashboard_tokens_table():
    """Create pgr_dashboard_tokens table if it does not exist."""
    try:
        db_helper.execute("""
            CREATE TABLE IF NOT EXISTS pgr_dashboard_tokens (
                token       TEXT PRIMARY KEY,
                discord_id  TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT NOW(),
                expires_at  TIMESTAMP NOT NULL,
                used        BOOLEAN DEFAULT FALSE
            )
        """)
        logger.info("pgr_dashboard_tokens table ready")
    except Exception as e:
        logger.error(f"ensure_dashboard_tokens_table error: {e}")


# ─── Dashboard token helpers ──────────────────────────────────────────────────

DASHBOARD_TOKEN_TTL_SECONDS = 300  # 5 minutes


def create_dashboard_token(discord_id: str) -> str:
    """Create a one-time dashboard access token for a premium user."""
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=DASHBOARD_TOKEN_TTL_SECONDS)
    db_helper.execute(
        """
        INSERT INTO pgr_dashboard_tokens (token, discord_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (token, discord_id, expires_at),
    )
    return token


def validate_and_consume_dashboard_token(token: str) -> bool:
    """
    Atomically validate and consume a dashboard token in a single UPDATE.

    The UPDATE only succeeds when:
    - The token exists
    - It has not been used
    - It has not expired

    Returns True if exactly one row was updated (i.e. token was valid).
    """
    try:
        row = db_helper.execute(
            """
            UPDATE pgr_dashboard_tokens
            SET used = TRUE
            WHERE token = %s
              AND used = FALSE
              AND expires_at > NOW()
            RETURNING token
            """,
            (token,),
            fetch="one",
        )
        return row is not None
    except Exception as e:
        logger.error(f"validate_and_consume_dashboard_token error: {e}")
        return False


# ─── User helpers ─────────────────────────────────────────────────────────────

def upsert_user(discord_id: str, username: str = None, email: str = None):
    """Insert or update basic user info (called on every Discord login)."""
    try:
        db_helper.execute("""
            INSERT INTO pgr_users (discord_user_id, username, email, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (discord_user_id)
            DO UPDATE SET
                username   = COALESCE(EXCLUDED.username, pgr_users.username),
                email      = COALESCE(EXCLUDED.email,    pgr_users.email),
                updated_at = NOW()
        """, (discord_id, username, email))
    except Exception as e:
        logger.error(f"upsert_user error: {e}")


def is_premium(discord_id: str) -> bool:
    """Return True if user has active premium subscription."""
    try:
        row = db_helper.execute("""
            SELECT premium_status, premium_until
            FROM pgr_users
            WHERE discord_user_id = %s
        """, (discord_id,), fetch='one')
        if not row:
            return False
        status, until = row
        if not status:
            return False
        if until and until < datetime.utcnow():
            # expired — deactivate silently
            deactivate_premium(discord_id)
            return False
        return True
    except Exception as e:
        logger.error(f"is_premium error: {e}")
        return False


def activate_premium(
    discord_id: str,
    stripe_customer_id: str = None,
    stripe_subscription_id: str = None,
    until: datetime = None,
):
    """Grant premium to a user. Called from Stripe webhook."""
    try:
        if until is None:
            until_expr = "NOW() + INTERVAL '30 days'"
            params = (stripe_customer_id, stripe_subscription_id, discord_id)
            db_helper.execute(f"""
                UPDATE pgr_users
                SET premium_status          = TRUE,
                    premium_until           = {until_expr},
                    stripe_customer_id      = COALESCE(%s, stripe_customer_id),
                    stripe_subscription_id  = COALESCE(%s, stripe_subscription_id),
                    updated_at              = NOW()
                WHERE discord_user_id = %s
            """, params)
        else:
            db_helper.execute("""
                UPDATE pgr_users
                SET premium_status          = TRUE,
                    premium_until           = %s,
                    stripe_customer_id      = COALESCE(%s, stripe_customer_id),
                    stripe_subscription_id  = COALESCE(%s, stripe_subscription_id),
                    updated_at              = NOW()
                WHERE discord_user_id = %s
            """, (until, stripe_customer_id, stripe_subscription_id, discord_id))
        logger.info(f"Premium activated for discord_id={discord_id}")
    except Exception as e:
        logger.error(f"activate_premium error: {e}")


def deactivate_premium(discord_id: str):
    """Revoke premium. Called on subscription cancellation / payment failure."""
    try:
        db_helper.execute("""
            UPDATE pgr_users
            SET premium_status = FALSE, updated_at = NOW()
            WHERE discord_user_id = %s
        """, (discord_id,))
        logger.info(f"Premium deactivated for discord_id={discord_id}")
    except Exception as e:
        logger.error(f"deactivate_premium error: {e}")


def deactivate_by_stripe_customer(stripe_customer_id: str):
    """Revoke premium by Stripe customer ID (used in webhook)."""
    try:
        db_helper.execute("""
            UPDATE pgr_users
            SET premium_status = FALSE, updated_at = NOW()
            WHERE stripe_customer_id = %s
        """, (stripe_customer_id,))
    except Exception as e:
        logger.error(f"deactivate_by_stripe_customer error: {e}")


def activate_by_stripe_customer(stripe_customer_id: str, stripe_subscription_id: str = None):
    """Activate premium by Stripe customer ID (used in webhook)."""
    try:
        db_helper.execute("""
            UPDATE pgr_users
            SET premium_status         = TRUE,
                premium_until          = NOW() + INTERVAL '35 days',
                stripe_subscription_id = COALESCE(%s, stripe_subscription_id),
                updated_at             = NOW()
            WHERE stripe_customer_id = %s
        """, (stripe_subscription_id, stripe_customer_id))
    except Exception as e:
        logger.error(f"activate_by_stripe_customer error: {e}")


# ─── Session cookie helpers ───────────────────────────────────────────────────

def make_session_token(discord_id: str, username: str = None, email: str = None) -> str:
    """Encode a JWT session token for a Discord-authenticated user."""
    payload = {
        "sub":      discord_id,
        "username": username,
        "email":    email,
        "iat":      int(time.time()),
        "exp":      int(time.time()) + COOKIE_MAX_AGE,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def make_admin_token() -> str:
    """Encode a short-lived JWT for the site owner admin session."""
    payload = {
        "sub":      "admin",
        "is_admin": True,
        "iat":      int(time.time()),
        "exp":      int(time.time()) + ADMIN_COOKIE_MAX_AGE,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> Optional[dict]:
    """Decode JWT; return None on any error."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def get_discord_id(request: Request) -> Optional[str]:
    """Extract discord_user_id from the regular session cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_session_token(token)
    return payload.get("sub") if payload else None


def is_admin_session(request: Request) -> bool:
    """
    Return True if the request carries a valid admin session cookie.
    Checks ADMIN_COOKIE_NAME (pgr_admin_session) for is_admin=True claim.
    """
    token = request.cookies.get(ADMIN_COOKIE_NAME)
    if not token:
        return False
    payload = decode_session_token(token)
    return bool(payload and payload.get("is_admin") is True)


# ─── FastAPI middleware ───────────────────────────────────────────────────────

async def premium_middleware(request: Request, call_next):
    """
    Protect HTML pages and API endpoints.

    Access is granted when ANY of the following is true:
      1. Request carries a valid admin session cookie (is_admin=True)
      2. Request carries a valid Discord session AND user has active premium in DB

    HTML protected paths  → redirect to /login (no cookie) or /upgrade (no premium)
    API protected paths   → return 401/403 JSON
    Everything else       → pass through
    """
    path = request.url.path

    is_html_protected = any(path == p or path.startswith(p + "/") for p in PROTECTED_HTML)
    is_api_protected  = any(path == p or path.startswith(p + "/") for p in PROTECTED_API)

    if not (is_html_protected or is_api_protected):
        return await call_next(request)

    # ── Gate 1: admin bypass ──────────────────────────────────────────────────
    if is_admin_session(request):
        return await call_next(request)

    # ── Gate 2: Discord + premium ─────────────────────────────────────────────
    discord_id = get_discord_id(request)

    if not discord_id:
        if is_api_protected:
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        return RedirectResponse("/login")

    if not is_premium(discord_id):
        if is_api_protected:
            return JSONResponse({"error": "premium_required"}, status_code=403)
        return RedirectResponse("/upgrade")

    return await call_next(request)
