from __future__ import annotations
"""Discord adapter — full Gateway (websocket) client + REST send.

v4.2.0: the previous implementation only logged "Connecting via Gateway..."
and never opened a socket — inbound Discord messages never arrived. This
adapter now speaks the real Discord Gateway protocol:

    REST GET /gateway/bot        → websocket URL + shard info
    WS  HELLO          (op 10)   → heartbeat_interval; start heartbeats
    WS  IDENTIFY       (op 2)    → bot token + intents
    WS  READY          (dispatch)→ session_id (for RESUME)
    WS  MESSAGE_CREATE (dispatch)→ IncomingMessage → on_message callback
    WS  HEARTBEAT_ACK  (op 11)   → keep-alive confirmation
    WS  RECONNECT      (op 7)    → reconnect + RESUME with last seq
    WS  INVALID_SESSION(op 9)    → re-IDENTIFY (fresh session)

Requires aiohttp (core dependency of SHS-Code).

Environment variables:
    DISCORD_BOT_TOKEN       — bot token from the Developer Portal
    DISCORD_INTENTS         — optional intent bitmask override (default:
                              Guilds | GuildMessages | MessageContent |
                              DirectMessages = 33281+... computed below).
                              NOTE: Message Content is a *privileged*
                              intent — enable it in the Dev Portal.
"""
import asyncio
import json
import os
from app.messaging.base import BaseMessagingAdapter, IncomingMessage
from app.logger import logger

_API = "https://discord.com/api/v10"

# Guilds(1<<0) | GuildMessages(1<<9) | MessageContent(1<<15) | DMs(1<<12)
_DEFAULT_INTENTS = (1 << 0) | (1 << 9) | (1 << 15) | (1 << 12)


class DiscordAdapter(BaseMessagingAdapter):
    platform_name = "discord"

    def __init__(self) -> None:
        super().__init__(token=os.getenv("DISCORD_BOT_TOKEN", ""))
        self._gateway_url: str = ""
        self._session_id: str = ""
        self._seq: int | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._ws = None
        self._session = None

    # ── lifecycle ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if not self.is_configured():
            logger.info("[Discord] Not configured (DISCORD_BOT_TOKEN not set)")
            return
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{_API}/gateway/bot",
                    headers={"Authorization": f"Bot {self.token}"},
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(f"[Discord] Gateway lookup failed "
                                       f"{resp.status}: {body[:200]}")
                        return
                    data = await resp.json()
                    self._gateway_url = data.get("url", "")
                    shards = data.get("shards", 1)
                    logger.info(f"[Discord] Gateway acquired "
                                f"(shards={shards}, url={self._gateway_url})")
        except Exception as e:
            logger.warning(f"[Discord] Connection error: {e}")

    async def start(self, on_message) -> None:
        """Run the gateway event loop until disconnect()."""
        if not self.is_configured():
            logger.info("[Discord] Stub mode — not configured")
            return
        if not self._gateway_url:
            await self.connect()
        if not self._gateway_url:
            logger.warning("[Discord] No gateway URL — cannot start")
            return

        import aiohttp
        self._running = True
        logger.info("[Discord] Starting gateway event loop")
        timeout = aiohttp.ClientTimeout(total=None, heartbeat=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            self._session = session
            backoff = 1.0
            while self._running:
                try:
                    async with session.ws_connect(
                        self._gateway_url,
                        max_msg_size=2 ** 22,
                        autoping=True,
                    ) as ws:
                        self._ws = ws
                        backoff = 1.0
                        await self._gateway_session(ws, on_message)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if not self._running:
                        break
                    logger.warning(f"[Discord] Gateway connection lost: {e} "
                                   f"— reconnecting in {backoff:.0f}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                finally:
                    self._ws = None
                    if self._heartbeat_task:
                        self._heartbeat_task.cancel()
                        self._heartbeat_task = None

    async def _gateway_session(self, ws, on_message) -> None:
        """One websocket session: HELLO → (RESUME|IDENTIFY) → dispatch loop."""
        import aiohttp
        resumed = False
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:  # noqa: F821
                continue
            try:
                payload = json.loads(msg.data)
            except ValueError:
                continue
            op = payload.get("op")
            t = payload.get("t")
            d = payload.get("d") or {}

            if payload.get("s") is not None:
                self._seq = payload["s"]

            if op == 10:  # HELLO
                interval = (d.get("heartbeat_interval") or 45000) / 1000.0
                self._heartbeat_task = asyncio.create_task(
                    self._heartbeat_loop(ws, interval))
                if self._session_id and self._seq is not None:
                    await self._send_op(ws, 6, {  # RESUME
                        "token": self.token,
                        "session_id": self._session_id,
                        "seq": self._seq,
                    })
                    resumed = True
                    logger.info("[Discord] Resuming session "
                                f"{self._session_id} @ seq {self._seq}")
                else:
                    await self._identify(ws)
            elif op == 11:  # HEARTBEAT_ACK
                logger.debug("[Discord] heartbeat acknowledged")
            elif op == 7:  # RECONNECT requested by server
                logger.info("[Discord] server requested reconnect")
                await ws.close()
                return
            elif op == 9:  # INVALID_SESSION
                self._session_id = ""
                self._seq = None
                wait = d if isinstance(d, (int, float)) else 5
                logger.warning(f"[Discord] invalid session — re-identifying "
                               f"in {wait}s")
                await asyncio.sleep(wait)
                await self._identify(ws)
            elif op == 0 and t == "READY":
                self._session_id = d.get("session_id", "")
                user = (d.get("user") or {}).get("username", "?")
                logger.info(f"[Discord] READY as {user} "
                            f"(session {self._session_id[:8]}…)")
                if resumed:
                    # drop any events replayed before resume finished
                    resumed = False
            elif op == 0 and t == "MESSAGE_CREATE":
                await self._handle_message(d, on_message)

    async def _identify(self, ws) -> None:
        intents = int(os.getenv("DISCORD_INTENTS", str(_DEFAULT_INTENTS)))
        await self._send_op(ws, 2, {
            "token": self.token,
            "intents": intents,
            "properties": {"os": "linux", "browser": "shscode",
                           "device": "shscode"},
        })
        logger.info("[Discord] IDENTIFY sent "
                    f"(intents={intents}, MessageContent requires the "
                    "privileged toggle in the Dev Portal)")

    async def _heartbeat_loop(self, ws, interval: float) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await self._send_op(ws, 1, self._seq)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[Discord] heartbeat loop ended: {e}")

    async def _send_op(self, ws, op: int, data) -> None:
        try:
            await ws.send_str(json.dumps({"op": op, "d": data}))
        except Exception as e:
            logger.warning(f"[Discord] send op {op} failed: {e}")

    async def _handle_message(self, d: dict, on_message) -> None:
        # ignore our own messages and non-text types
        author = d.get("author") or {}
        if author.get("bot"):
            return
        content = d.get("content") or ""
        if not content:
            return
        msg = IncomingMessage(
            platform="discord",
            user_id=str(author.get("id", "")),
            channel_id=str(d.get("channel_id", "")),
            text=content,
            message_id=str(d.get("id", "")),
        )
        try:
            await on_message(msg)
        except Exception as e:
            logger.error(f"[Discord] handler error: {e}")

    # ── outbound ─────────────────────────────────────────────────────────

    async def send(self, channel_id: str, text: str) -> dict:
        """Send via REST (chunked to Discord's 2000-char limit)."""
        if not self.is_configured():
            logger.info(f"[Discord:stub] Would send to channel {channel_id}: {text[:80]}")
            return {"sent": False, "reason": "stub"}
        results = []
        try:
            import aiohttp
            chunks = [text[i:i + 2000] for i in range(0, len(text), 2000)] or [""]
            async with aiohttp.ClientSession() as s:
                for chunk in chunks:
                    url = f"{_API}/channels/{channel_id}/messages"
                    headers = {"Authorization": f"Bot {self.token}",
                               "Content-Type": "application/json"}
                    async with s.post(url, json={"content": chunk},
                                      headers=headers) as resp:
                        if resp.status not in (200, 201):
                            body = await resp.text()
                            logger.warning(f"[Discord] Send error "
                                           f"{resp.status}: {body[:200]}")
                            results.append(False)
                        else:
                            results.append(True)
        except Exception as e:
            logger.warning(f"[Discord] Send failed: {e}")
            results.append(False)
        return {"sent": all(results), "chunks": len(results)}

    async def disconnect(self) -> None:
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
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
        logger.info("[Discord] Disconnected")
