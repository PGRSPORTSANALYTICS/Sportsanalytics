#!/usr/bin/env python3
"""
Discord OAuth Authentication Module
====================================
Handles Discord OAuth2 flow for user authentication.
Returns JWT tokens for authenticated users.
"""

import os
import time
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import jwt

router = APIRouter(prefix="/auth/discord", tags=["auth"])

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGEME")
JWT_ALGORITHM = "HS256"

DISCORD_OAUTH_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_OAUTH_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_USER_URL = "https://discord.com/api/users/@me"


@router.get("/login")
async def discord_login():
    """Redirect user to Discord OAuth login page"""
    if not DISCORD_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")
    
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify email",
        "prompt": "consent"
    }
    url = f"{DISCORD_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def discord_callback(code: str):
    """Handle Discord OAuth callback and return JWT"""
    if not all([DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI]):
        raise HTTPException(status_code=500, detail="Discord OAuth not fully configured")
    
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token_resp = requests.post(DISCORD_OAUTH_TOKEN_URL, data=data, headers=headers)
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="discord_token_exchange_failed")

    token_data = token_resp.json()
    access_token = token_data["access_token"]

    user_resp = requests.get(
        DISCORD_API_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="discord_userinfo_error")

    user_data = user_resp.json()

    discord_id = user_data["id"]
    username = user_data.get("username")
    email = user_data.get("email")

    payload = {
        "sub": discord_id,
        "username": username,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400  # 24 hours
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return JSONResponse({
        "success": True,
        "token": token,
        "user": {
            "id": discord_id,
            "username": username,
            "email": email
        }
    })
