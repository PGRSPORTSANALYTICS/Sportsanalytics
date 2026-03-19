#!/usr/bin/env python3
"""
Admin Bypass Authentication
============================
Provides a separate password-based login for the site owner.
Does NOT touch Discord OAuth — normal users are unaffected.

Routes:
  POST /admin-login   → validate ADMIN_PASSWORD, set pgr_admin_session cookie
  GET  /admin-logout  → clear pgr_admin_session cookie, redirect to /login
  GET  /admin-status  → return JSON indicating whether admin session is active

Cookie: pgr_admin_session (HTTP-only, separate from Discord pgr_session)
JWT claim: { sub: "admin", is_admin: True, exp: now + 8h }

Environment variables required:
  ADMIN_PASSWORD  — the secret password for admin access
  JWT_SECRET      — shared with auth_premium for token signing
"""

import os
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse

from auth_premium import (
    make_admin_token,
    is_admin_session,
    ADMIN_COOKIE_NAME,
    ADMIN_COOKIE_MAX_AGE,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-auth"])

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


# ─── Login page (GET) ─────────────────────────────────────────────────────────

@router.get("/admin-login", response_class=HTMLResponse)
async def admin_login_page(request: Request, error: str = ""):
    """Serve the minimal admin login form."""
    if is_admin_session(request):
        return RedirectResponse("/home", status_code=302)

    error_html = (
        '<p style="color:#f87171;font-size:13px;margin-top:10px;">Incorrect password.</p>'
        if error == "1" else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PGR Admin Login</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0b0e14;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
  }}
  .card {{
    background: #0d1117;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 32px 28px;
    width: 340px;
  }}
  .logo {{
    width: 36px; height: 36px;
    background: #22c55e;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 900; color: #000;
    margin-bottom: 18px;
  }}
  h1 {{
    font-size: 18px;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 4px;
  }}
  p.sub {{
    font-size: 12px;
    color: #52525b;
    margin-bottom: 22px;
  }}
  label {{
    display: block;
    font-size: 11px;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom: 6px;
  }}
  input[type=password] {{
    width: 100%;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
    color: #f1f5f9;
    outline: none;
    transition: border-color .15s;
  }}
  input[type=password]:focus {{ border-color: rgba(34,197,94,0.5); }}
  button {{
    width: 100%;
    margin-top: 16px;
    padding: 11px;
    background: #22c55e;
    color: #000;
    font-size: 14px;
    font-weight: 700;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: background .12s;
  }}
  button:hover {{ background: #16a34a; }}
  .note {{
    margin-top: 16px;
    font-size: 10px;
    color: #3f3f46;
    text-align: center;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">P</div>
  <h1>Admin Access</h1>
  <p class="sub">Site owner login — not for regular users</p>
  <form method="POST" action="/admin-login">
    <label>Admin Password</label>
    <input type="password" name="password" autofocus autocomplete="current-password" placeholder="Enter admin password" />
    {error_html}
    <button type="submit">Sign in as Admin</button>
  </form>
  <p class="note">Session expires after 8 hours · HTTP-only cookie</p>
</div>
</body>
</html>"""
    return HTMLResponse(html)


# ─── Login handler (POST) ─────────────────────────────────────────────────────

@router.post("/admin-login")
async def admin_login(password: str = Form(...)):
    """
    Validate ADMIN_PASSWORD and set the pgr_admin_session cookie.
    Redirects to /home on success, back to /admin-login?error=1 on failure.
    """
    if not ADMIN_PASSWORD:
        logger.error("ADMIN_PASSWORD env var is not set — admin login is disabled")
        return JSONResponse({"error": "admin_not_configured"}, status_code=503)

    if password != ADMIN_PASSWORD:
        logger.warning("Admin login: incorrect password attempt")
        return RedirectResponse("/admin-login?error=1", status_code=302)

    token = make_admin_token()

    response = RedirectResponse("/home", status_code=302)
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        max_age=ADMIN_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("ENV", "dev") == "production",
    )
    logger.info("Admin session started")
    return response


# ─── Logout (GET) ─────────────────────────────────────────────────────────────

@router.get("/admin-logout")
async def admin_logout():
    """Clear the admin session cookie and redirect to login."""
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(ADMIN_COOKIE_NAME)
    logger.info("Admin session cleared")
    return response


# ─── Status check (GET, JSON) ─────────────────────────────────────────────────

@router.get("/admin-status")
async def admin_status(request: Request):
    """
    Return whether an admin session is currently active.
    Only useful for debugging — never exposes token contents.
    """
    active = is_admin_session(request)
    return JSONResponse({"admin_active": active})
