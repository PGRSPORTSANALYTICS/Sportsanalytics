"""
Web Push Notification Service
==============================
Handles push subscription storage and sending push notifications
via the Web Push Protocol (VAPID).

Tables:
  push_subscriptions — stores browser push endpoints

Usage:
  from push_service import PushService
  svc = PushService()
  svc.send_to_all("New Pick", "BTTS YES @ 2.10", "/")
"""

import os
import json
import logging
import base64
from typing import Optional

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CONTACT     = os.getenv("VAPID_CONTACT", "mailto:admin@pgranalytics.com")


class PushService:
    def __init__(self):
        from db_helper import db_helper
        self.db = db_helper
        self._ensure_table()

    def _ensure_table(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id          SERIAL PRIMARY KEY,
                endpoint    TEXT UNIQUE NOT NULL,
                p256dh      TEXT NOT NULL,
                auth        TEXT NOT NULL,
                user_agent  TEXT,
                created_at  BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
            )
        """, ())

    def save_subscription(self, endpoint: str, p256dh: str, auth: str,
                          user_agent: str = "") -> bool:
        self.db.execute("""
            INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_agent)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE
              SET p256dh = EXCLUDED.p256dh,
                  auth   = EXCLUDED.auth,
                  user_agent = EXCLUDED.user_agent
        """, (endpoint, p256dh, auth, user_agent))
        logger.info(f"push_subscription saved: {endpoint[:40]}...")
        return True

    def delete_subscription(self, endpoint: str):
        try:
            self.db.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = %s", (endpoint,)
            )
        except Exception as e:
            logger.error(f"delete_subscription failed: {e}")

    def get_subscriptions(self):
        rows = self.db.execute(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions", (),
            fetch='all'
        ) or []
        return [{"endpoint": r[0], "p256dh": r[1], "auth": r[2]} for r in rows]

    def count(self) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM push_subscriptions", (),
            fetch='one'
        )
        return row[0] if row else 0

    def send_to_all(self, title: str, body: str, url: str = "/",
                    icon: str = "/static/icon-192.png") -> dict:
        if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
            logger.warning("VAPID keys not configured — push skipped")
            return {"sent": 0, "failed": 0}

        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            logger.error("pywebpush not installed")
            return {"sent": 0, "failed": 0}

        payload = json.dumps({
            "title": title,
            "body":  body,
            "url":   url,
            "icon":  icon,
        })

        priv_key = VAPID_PRIVATE_KEY
        if priv_key and not priv_key.startswith("-----"):
            try:
                padding = "=" * ((4 - len(priv_key) % 4) % 4)
                decoded = base64.urlsafe_b64decode(priv_key + padding)
                priv_key = decoded.decode("utf-8")
            except Exception:
                pass  # Use as-is if decode fails

        subs = self.get_subscriptions()
        sent = failed = 0
        dead_endpoints = []

        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {
                            "p256dh": sub["p256dh"],
                            "auth":   sub["auth"],
                        },
                    },
                    data=payload,
                    vapid_private_key=priv_key,
                    vapid_claims={
                        "sub": VAPID_CONTACT,
                    },
                    ttl=86400,
                )
                sent += 1
            except WebPushException as e:
                status = getattr(e.response, "status_code", 0)
                if status in (404, 410):
                    dead_endpoints.append(sub["endpoint"])
                else:
                    logger.warning(f"Push failed ({status}): {e}")
                failed += 1
            except Exception as e:
                logger.warning(f"Push error: {e}")
                failed += 1

        for ep in dead_endpoints:
            self.delete_subscription(ep)

        logger.info(f"Push: {sent} sent, {failed} failed, {len(dead_endpoints)} cleaned")
        return {"sent": sent, "failed": failed, "cleaned": len(dead_endpoints)}
