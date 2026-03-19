#!/usr/bin/env python3
"""
Discord OAuth Authentication Module
====================================
Flow:
  1. GET /auth/discord/login       → redirect to Discord OAuth
  2. GET /auth/discord/callback    → exchange code, upsert user in DB,
                                     set HTTP-only session cookie,
                                     redirect to /home (premium) or /upgrade
  3. GET /auth/discord/logout      → clear cookie, redirect to /login
  4. GET /auth/discord/me          → return current user info (JSON)
"""

import os
import time
import logging
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from auth_premium import (
    make_session_token,
    decode_session_token,
    upsert_user,
    is_premium,
    COOKIE_NAME,
    COOKIE_MAX_AGE,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/discord", tags=["auth"])

DISCORD_CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI  = os.getenv("DISCORD_REDIRECT_URI")

DISCORD_OAUTH_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_OAUTH_TOKEN_URL     = "https://discord.com/api/oauth2/token"
DISCORD_API_USER_URL        = "https://discord.com/api/users/@me"


@router.get("/login")
async def discord_login():
    """Redirect user to Discord OAuth consent page."""
    if not DISCORD_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")

    params = {
        "client_id":    DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope":        "identify email",
        "prompt":       "consent",
    }
    return RedirectResponse(f"{DISCORD_OAUTH_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
async def discord_callback(code: str):
    """
    Handle Discord OAuth callback.
    - Exchanges code for Discord access token
    - Fetches user info (id, username, email)
    - Upserts user in pgr_users
    - Sets HTTP-only session cookie
    - Redirects to /home if premium, /upgrade otherwise
    """
    if not all([DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI]):
        raise HTTPException(status_code=500, detail="Discord OAuth not fully configured")

    # Exchange code for Discord access token
    token_resp = requests.post(
        DISCORD_OAUTH_TOKEN_URL,
        data={
            "client_id":     DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  DISCORD_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="discord_token_exchange_failed")

    access_token = token_resp.json().get("access_token")

    # Fetch Discord user info
    user_resp = requests.get(
        DISCORD_API_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="discord_userinfo_error")

    user_data  = user_resp.json()
    discord_id = user_data["id"]
    username   = user_data.get("username")
    email      = user_data.get("email")

    # Upsert user record (creates row if first login)
    upsert_user(discord_id, username, email)

    # Create session token
    session_token = make_session_token(discord_id, username, email)

    # Decide where to send the user
    destination = "/home" if is_premium(discord_id) else "/upgrade"

    response = RedirectResponse(destination, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("ENV", "dev") == "production",
    )
    return response


@router.get("/logout")
async def discord_logout():
    """Clear session cookie and redirect to login page."""
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/me")
async def discord_me(request: Request):
    """
    Return current authenticated user info.
    Used by frontend to check login state without a full page reload.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return JSONResponse({"authenticated": False}, status_code=401)

    payload = decode_session_token(token)
    if not payload:
        return JSONResponse({"authenticated": False}, status_code=401)

    discord_id = payload.get("sub")
    premium    = is_premium(discord_id)

    return JSONResponse({
        "authenticated": True,
        "discord_id":   discord_id,
        "username":     payload.get("username"),
        "email":        payload.get("email"),
        "premium":      premium,
    })
