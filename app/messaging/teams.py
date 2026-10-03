from __future__ import annotations
"""Microsoft Teams adapter — full Bot Framework implementation.

v4.2.0: the previous implementation logged "OAuth flow not implemented"
and could never deliver a message (it sent the app ID — not an access
token — as the bearer). This adapter now implements the real flow:

    1. OAuth2 client-credentials against Azure AD:
       POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
            grant_type=client_credentials
            scope=https://api.botframework.com/.default
            client_id / client_secret
       → access_token (cached until expiry − 60s)

    2. Send an activity:
       POST {service_url}/v3/conversations/{conversation_id}/activities
            Authorization: Bearer <access_token>

    3. Inbound: the Bot Framework messages webhook (POST) posts an
       "activity" JSON — handle_webhook_event() parses it into
       IncomingMessage objects (see app/server/messaging_routes.py).

Environment variables:
    MICROSOFT_APP_ID       — Azure AD app registration ID
    MICROSOFT_APP_PASSWORD — client secret for the app registration
    MICROSOFT_TENANT_ID    — Azure AD tenant (default: common)
"""
import os
import time
from typing import Optional
from app.messaging.base import BaseMessagingAdapter, IncomingMessage
from app.logger import logger

_TOKEN_URL = ("https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token")
_DEFAULT_SERVICE_URL = "https://smba.trafficmanager.net/amer/"


class TeamsAdapter(BaseMessagingAdapter):
    platform_name = "teams"

    def __init__(self) -> None:
        app_id = os.getenv("MICROSOFT_APP_ID", "")
        app_password = os.getenv("MICROSOFT_APP_PASSWORD", "")
        # both must be present for full configuration
        super().__init__(token=app_id if (app_id and app_password) else "")
        self._app_password = app_password
        self._tenant = os.getenv("MICROSOFT_TENANT_ID", "common")
        self._access_token: str = ""
        self._token_expiry: float = 0.0

    async def connect(self) -> None:
        if not self.is_configured():
            logger.info("[Teams] Not configured (MICROSOFT_APP_ID / "
                        "MICROSOFT_APP_PASSWORD not set)")
            return
        token = await self._get_access_token()
        if token:
            logger.info("[Teams] Bot Framework token acquired "
                        f"(tenant={self._tenant})")
        else:
            logger.warning("[Teams] Token acquisition failed — check "
                           "MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD / "
                           "MICROSOFT_TENANT_ID")

    async def _get_access_token(self) -> Optional[str]:
        """Client-credentials OAuth2 against Azure AD (cached)."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        try:
            import aiohttp
            url = _TOKEN_URL.format(tenant=self._tenant)
            payload = {
                "grant_type": "client_credentials",
                "client_id": self.token,
                "client_secret": self._app_password,
                "scope": "https://api.botframework.com/.default",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, data=payload,
                    headers={"Content-Type":
                             "application/x-www-form-urlencoded"},
                ) as resp:
                    data = await resp.json()
                    if resp.status != 200 or "access_token" not in data:
                        err = data.get("error_description",
                                       data.get("error", str(resp.status)))
                        logger.warning(f"[Teams] OAuth failed: {str(err)[:200]}")
                        return None
                    self._access_token = data["access_token"]
                    self._token_expiry = (time.time()
                                          + int(data.get("expires_in", 3600))
                                          - 60)
                    return self._access_token
        except Exception as e:
            logger.warning(f"[Teams] OAuth error: {e}")
            return None

    async def start(self, on_message) -> None:
        if not self.is_configured():
            logger.info("[Teams] Stub mode — not configured")
            return
        # Teams inbound arrives via the Bot Framework webhook (HTTP POST),
        # not a persistent socket: the HTTP server routes
        # POST /messaging/webhooks/teams → handle_webhook_event → on_message.
        self._running = True
        self._on_message = on_message
        logger.info("[Teams] Webhook listener ready "
                    "(route: POST /messaging/webhooks/teams)")

    async def handle_webhook_event(self, payload: dict) -> list[IncomingMessage]:
        """Parse a Bot Framework activity POST into incoming messages."""
        messages: list[IncomingMessage] = []
        try:
            if payload.get("type") != "message":
                return messages
            text = payload.get("text") or ""
            if not text:
                return messages
            conv = payload.get("conversation") or {}
            sender = payload.get("from") or {}
            service_url = payload.get("serviceUrl", _DEFAULT_SERVICE_URL)
            # remember the serviceUrl so replies go to the right region
            self._service_url = service_url
            messages.append(IncomingMessage(
                platform="teams",
                user_id=str(sender.get("id", sender.get("name", ""))),
                channel_id=str(conv.get("id", "")),
                text=text,
                message_id=str(payload.get("id", "")),
            ))
        except Exception as e:
            logger.error(f"[Teams] Webhook parse error: {e}")
        return messages

    async def send(self, channel_id: str, text: str) -> dict:
        """Send a message activity to a conversation."""
        if not self.is_configured():
            logger.info(f"[Teams:stub] Would send to {channel_id}: {text[:80]}")
            return {"sent": False, "reason": "stub"}
        token = await self._get_access_token()
        if not token:
            return {"sent": False, "reason": "no_token"}
        try:
            import aiohttp
            service_url = getattr(self, "_service_url", _DEFAULT_SERVICE_URL)
            url = (f"{service_url.rstrip('/')}/v3/conversations/"
                   f"{channel_id}/activities")
            headers = {"Authorization": f"Bearer {token}",
                       "Content-Type": "application/json"}
            payload = {"type": "message", "text": text[:4000]}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        headers=headers) as resp:
                    if resp.status not in (200, 201, 202, 204):
                        body = await resp.text()
                        logger.warning(f"[Teams] Send error {resp.status}: "
                                       f"{body[:200]}")
                        return {"sent": False, "status": resp.status}
                    return {"sent": True}
        except Exception as e:
            logger.warning(f"[Teams] Send failed: {e}")
            return {"sent": False}

    async def disconnect(self) -> None:
        self._running = False
        self._access_token = ""
        logger.info("[Teams] Disconnected")
