from __future__ import annotations
"""Slack adapter — full Socket Mode client + Web API send.

v4.2.0: the previous implementation only logged "Connecting via Socket
Mode..." — inbound Slack events never arrived. This adapter now speaks
the real Slack Socket Mode protocol:

    REST POST /apps.connections.open  (APP-level token xapp-…)
                                   → wss://… temporary RTM-style URL
    WS  {"type": "hello"}         → connection established
    WS  {"type": "events_api", "envelope_id": …, "payload": …}
                                  → MUST be acked {"envelope_id": …}
      payload.event.type == "message"  → IncomingMessage → on_message
    WS  slash_commands / interactive → acked the same way

The socket drops every ~24h; the loop reconnects with backoff and
requests a fresh wss URL each time.

Environment variables:
    SLACK_BOT_TOKEN   — xoxb-… user/bot token (Web API: chat.postMessage)
    SLACK_APP_TOKEN   — xapp-… app-level token with `connections:write`
                        (Socket Mode). Without it the adapter stays in
                        stub mode for inbound (send still works).
"""
import asyncio
import json
import os
from app.messaging.base import BaseMessagingAdapter, IncomingMessage
from app.logger import logger


class SlackAdapter(BaseMessagingAdapter):
    platform_name = "slack"
    _WS_BASE = "https://slack.com/api"

    def __init__(self) -> None:
        super().__init__(token=os.getenv("SLACK_BOT_TOKEN", ""))
        self._app_token = os.getenv("SLACK_APP_TOKEN", "")
        self._ws = None
        self._session = None

    def socket_mode_ready(self) -> bool:
        """Socket Mode needs BOTH the bot token and the app token."""
        return bool(self.token and self._app_token)

    async def connect(self) -> None:
        if not self.is_configured():
            logger.info("[Slack] Not configured (SLACK_BOT_TOKEN not set)")
            return
        if not self._app_token:
            logger.info("[Slack] SLACK_APP_TOKEN not set — send-only mode "
                        "(Socket Mode inbound disabled)")
            return
        url = await self._open_connection()
        if url:
            logger.info("[Slack] Socket Mode connection URL acquired")

    async def _open_connection(self) -> str:
        """Call apps.connections.open with the APP token → wss URL."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self._WS_BASE}/apps.connections.open",
                    headers={"Authorization": f"Bearer {self._app_token}"},
                ) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.warning(f"[Slack] apps.connections.open "
                                       f"failed: {data.get('error', '?')}")
                        return ""
                    return data.get("url", "")
        except Exception as e:
            logger.warning(f"[Slack] connection open error: {e}")
            return ""

    async def start(self, on_message) -> None:
        if not self.socket_mode_ready():
            logger.info("[Slack] Stub mode — not configured "
                        "(need SLACK_BOT_TOKEN + SLACK_APP_TOKEN)")
            return
        import aiohttp
        self._running = True
        logger.info("[Slack] Starting Socket Mode event loop")
        timeout = aiohttp.ClientTimeout(total=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            self._session = session
            backoff = 1.0
            while self._running:
                url = await self._open_connection()
                if not url:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 120)
                    continue
                try:
                    async with session.ws_connect(url) as ws:
                        self._ws = ws
                        backoff = 1.0
                        await self._socket_session(ws, on_message)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if not self._running:
                        break
                    logger.warning(f"[Slack] socket dropped: {e} — "
                                   f"reconnecting in {backoff:.0f}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 120)
                finally:
                    self._ws = None

    async def _socket_session(self, ws, on_message) -> None:
        import aiohttp
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:  # noqa: F821
                continue
            try:
                envelope = json.loads(msg.data)
            except ValueError:
                continue
            etype = envelope.get("type")

            if etype == "hello":
                logger.info("[Slack] Socket Mode connected")
                continue
            if etype in ("events_api", "slash_commands", "interactive"):
                # EVERY envelope must be acknowledged or Slack redelivers
                await self._ack(ws, envelope.get("envelope_id"))
            if etype == "events_api":
                await self._handle_event(envelope.get("payload") or {},
                                         on_message)
            if etype == "disconnect_cli":
                logger.warning("[Slack] server sent disconnect_cli — "
                               "reconnecting")
                await ws.close()
                return

    async def _ack(self, ws, envelope_id) -> None:
        if not envelope_id:
            return
        try:
            await ws.send_str(json.dumps({"envelope_id": envelope_id}))
        except Exception as e:
            logger.warning(f"[Slack] ack failed: {e}")

    async def _handle_event(self, payload: dict, on_message) -> None:
        event = payload.get("event") or {}
        if event.get("type") != "message":
            return
        # skip bot/subtyped messages (joins, edits, our own replies)
        if event.get("bot_id") or event.get("subtype"):
            return
        text = event.get("text") or ""
        if not text:
            return
        msg = IncomingMessage(
            platform="slack",
            user_id=str(event.get("user", "")),
            channel_id=str(event.get("channel", "")),
            text=text,
            message_id=str(event.get("client_msg_id",
                                     event.get("ts", ""))),
        )
        try:
            await on_message(msg)
        except Exception as e:
            logger.error(f"[Slack] handler error: {e}")

    async def send(self, channel_id: str, text: str) -> dict:
        if not self.is_configured():
            logger.info(f"[Slack:stub] Would send to #{channel_id}: {text[:80]}")
            return {"sent": False, "reason": "stub"}
        try:
            import aiohttp
            url = f"{self._WS_BASE}/chat.postMessage"
            headers = {"Authorization": f"Bearer {self.token}",
                       "Content-Type": "application/json"}
            ok = False
            async with aiohttp.ClientSession() as s:
                # chunk to Slack's ~4000 char limit per message
                chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [""]
                for chunk in chunks:
                    async with s.post(url, json={"channel": channel_id,
                                                 "text": chunk},
                                      headers=headers) as resp:
                        data = await resp.json()
                        if not data.get("ok"):
                            logger.warning(f"[Slack] Send error: "
                                           f"{data.get('error', '?')}")
                        else:
                            ok = True
            return {"sent": ok}
        except Exception as e:
            logger.warning(f"[Slack] Send failed: {e}")
            return {"sent": False}

    async def disconnect(self) -> None:
        self._running = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        logger.info("[Slack] Disconnected")
