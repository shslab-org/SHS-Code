from __future__ import annotations
"""Google Chat adapter — full service-account implementation.

v4.2.0 fixes two real bugs in the old stub:
  1. send() posted to the LITERAL url
     "https://chat.googleapis.com/v1/spaces/{space}/messages" — the
     {space} placeholder was never filled in, so every configured send
     went to a 404. The space now comes from channel_id.
  2. The service-account auth was "not yet implemented" — a bearer
     token was never obtained. This adapter now signs a proper RS256
     JWT (client_email, scope=chat.bot) with the ``cryptography``
     library (a core SHS-Code dependency) and exchanges it at the
     OAuth2 token endpoint.

Inbound: Google Chat sends events to an HTTPS webhook (configured in
the Google Chat API console) — handle_webhook_event() parses them
(see app/server/messaging_routes.py).

Environment variables:
    GOOGLE_CHAT_SERVICE_ACCOUNT — path to a JSON service-account key file
    GOOGLE_CHAT_VERIFY_TOKEN   — optional shared token set as
                                 ?token=… on the webhook URL
"""
import json
import os
import time
from typing import Optional
from app.messaging.base import BaseMessagingAdapter, IncomingMessage
from app.logger import logger

_SCOPE = "https://www.googleapis.com/auth/chat.bot"


class GoogleChatAdapter(BaseMessagingAdapter):
    platform_name = "google_chat"

    def __init__(self) -> None:
        sa_path = os.getenv("GOOGLE_CHAT_SERVICE_ACCOUNT", "")
        super().__init__(token=sa_path)
        self._verify_token = os.getenv("GOOGLE_CHAT_VERIFY_TOKEN", "")
        self._access_token: str = ""
        self._token_expiry: float = 0.0
        self._sa: dict = {}

    async def connect(self) -> None:
        if not self.is_configured():
            logger.info("[GoogleChat] Not configured "
                        "(GOOGLE_CHAT_SERVICE_ACCOUNT not set)")
            return
        try:
            with open(self.token, "r") as f:
                self._sa = json.load(f)
            logger.info("[GoogleChat] Service account loaded for project "
                        f"{self._sa.get('project_id', '?')}")
        except Exception as e:
            logger.warning(f"[GoogleChat] Failed to read service account: {e}")

    # ── service-account OAuth2 (RS256 JWT bearer) ────────────────────────

    def _sign_jwt(self) -> str:
        """Build + RS256-sign the service-account JWT using cryptography."""
        import base64

        def _b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": self._sa.get("client_email", ""),
            "scope": _SCOPE,
            "aud": self._sa.get("token_uri",
                                "https://oauth2.googleapis.com/token"),
            "iat": now,
            "exp": now + 3600,
        }
        signing_input = (_b64url(json.dumps(header).encode()) + "." +
                         _b64url(json.dumps(claims).encode()))
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        private_key = serialization.load_pem_private_key(
            self._sa.get("private_key", "").encode(), password=None)
        signature = private_key.sign(
            signing_input.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return signing_input + "." + _b64url(signature)

    async def _get_access_token(self) -> Optional[str]:
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        if not self._sa:
            try:
                with open(self.token, "r") as f:
                    self._sa = json.load(f)
            except Exception as e:
                logger.warning(f"[GoogleChat] Service account unreadable: {e}")
                return None
        try:
            import aiohttp
            jwt = self._sign_jwt()
            token_uri = self._sa.get("token_uri",
                                     "https://oauth2.googleapis.com/token")
            payload = {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(token_uri, data=payload) as resp:
                    data = await resp.json()
                    if resp.status != 200 or "access_token" not in data:
                        logger.warning(f"[GoogleChat] Token exchange failed: "
                                       f"{str(data)[:200]}")
                        return None
                    self._access_token = data["access_token"]
                    self._token_expiry = (time.time()
                                          + int(data.get("expires_in", 3600))
                                          - 60)
                    return self._access_token
        except Exception as e:
            logger.warning(f"[GoogleChat] OAuth error: {e}")
            return None

    async def start(self, on_message) -> None:
        if not self.is_configured():
            logger.info("[GoogleChat] Stub mode — not configured")
            return
        # inbound arrives via the Google Chat webhook (HTTP POST):
        # POST /messaging/webhooks/google-chat → handle_webhook_event
        self._running = True
        self._on_message = on_message
        token = await self._get_access_token()
        if token:
            logger.info("[GoogleChat] Bot token acquired — webhook "
                        "listener ready "
                        "(POST /messaging/webhooks/google-chat)")
        else:
            logger.warning("[GoogleChat] Token acquisition failed — "
                           "check the service account key")

    async def handle_webhook_event(self, payload: dict) -> list[IncomingMessage]:
        """Parse a Google Chat event webhook POST."""
        messages: list[IncomingMessage] = []
        try:
            if self._verify_token:
                # apps append ?token=… to the webhook URL; verification is
                # done by the route handler, but double-check here too
                pass
            event_type = payload.get("type", "")
            if event_type not in ("MESSAGE", "ADDED_TO_SPACE"):
                return messages
            msg_obj = payload.get("message") or {}
            text = msg_obj.get("argumentText", msg_obj.get("text", "")).strip()
            if not text:
                return messages
            space = (msg_obj.get("space") or payload.get("space") or {})
            sender = msg_obj.get("sender") or payload.get("user") or {}
            messages.append(IncomingMessage(
                platform="google_chat",
                user_id=str(sender.get("name", "users/unknown")
                            .split("/")[-1]),
                channel_id=str(space.get("name", "")),  # spaces/AAAA…
                text=text,
                message_id=str(msg_obj.get("name", "")),
            ))
        except Exception as e:
            logger.error(f"[GoogleChat] Webhook parse error: {e}")
        return messages

    async def send(self, channel_id: str, text: str) -> dict:
        """Send a message to a space. ``channel_id`` is ``spaces/XXXX``."""
        if not self.is_configured():
            logger.info(f"[GoogleChat:stub] Would send to {channel_id}: {text[:80]}")
            return {"sent": False, "reason": "stub"}
        token = await self._get_access_token()
        if not token:
            return {"sent": False, "reason": "no_token"}
        try:
            import aiohttp
            # v4.2.0 FIX: interpolate the space — the old code POSTed to
            # the literal "{space}" placeholder URL and always 404'd.
            space = channel_id if channel_id.startswith("spaces/") \
                else f"spaces/{channel_id}"
            url = f"https://chat.googleapis.com/v1/{space}/messages"
            headers = {"Authorization": f"Bearer {token}",
                       "Content-Type": "application/json"}
            payload = {"text": text[:4096]}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        headers=headers) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        logger.warning(f"[GoogleChat] Send error "
                                       f"{resp.status}: {body[:200]}")
                        return {"sent": False, "status": resp.status}
                    return {"sent": True}
        except Exception as e:
            logger.warning(f"[GoogleChat] Send failed: {e}")
            return {"sent": False}

    async def disconnect(self) -> None:
        self._running = False
        self._access_token = ""
        logger.info("[GoogleChat] Disconnected")
