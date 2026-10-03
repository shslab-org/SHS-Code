from __future__ import annotations
r"""Email adapter — full SMTP send + IMAP polling receive.

v4.2.0: the previous implementation logged "IMAP IDLE polling not yet
implemented" — inbound email never arrived. This adapter now polls the
IMAP inbox for unread messages on a fixed interval:

    IMAP4_SSL connect → LOGIN → SELECT INBOX →
    SEARCH UNSEEN → FETCH RFC822 → parse (email module) →
    IncomingMessage → on_message → STORE +FLAGS \Seen → LOGOUT

Each poll uses a fresh connection (simple + robust against server-side
idle timeouts). The poll interval defaults to 60s (EMAIL_POLL_INTERVAL).

Environment variables:
    EMAIL_SMTP_HOST — SMTP server hostname
    EMAIL_SMTP_PORT — SMTP server port (default: 587)
    EMAIL_IMAP_HOST — IMAP server hostname
    EMAIL_IMAP_PORT — IMAP server port (default: 993)
    EMAIL_USER      — login username (email address)
    EMAIL_PASS      — login password / app-specific password
    EMAIL_POLL_INTERVAL — seconds between inbox polls (default: 60)
"""
import os
import asyncio
from app.messaging.base import BaseMessagingAdapter, IncomingMessage
from app.logger import logger


class EmailAdapter(BaseMessagingAdapter):
    platform_name = "email"

    def __init__(self) -> None:
        self._smtp_host = os.getenv("EMAIL_SMTP_HOST", "")
        self._smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self._imap_host = os.getenv("EMAIL_IMAP_HOST", "")
        self._imap_port = int(os.getenv("EMAIL_IMAP_PORT", "993"))
        self._poll_interval = int(os.getenv("EMAIL_POLL_INTERVAL", "60"))
        user = os.getenv("EMAIL_USER", "")
        password = os.getenv("EMAIL_PASS", "")
        super().__init__(token=user if (user and password) else "")
        self._password = password
        self._imap = None

    async def connect(self) -> None:
        if not self.is_configured():
            logger.info("[Email] Not configured (EMAIL_USER / EMAIL_PASS not set)")
            return
        ok = await asyncio.to_thread(self._imap_probe)
        if ok:
            logger.info(f"[Email] IMAP login verified on "
                        f"{self._imap_host}:{self._imap_port}")
        else:
            logger.warning("[Email] IMAP login failed — check "
                           "EMAIL_IMAP_HOST / EMAIL_USER / EMAIL_PASS")

    def _imap_probe(self) -> bool:
        try:
            import imaplib
            conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            try:
                conn.login(self.token, self._password)
                return True
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[Email] IMAP probe error: {e}")
            return False

    async def start(self, on_message) -> None:
        if not self.is_configured():
            logger.info("[Email] Stub mode — not configured")
            return
        self._running = True
        logger.info(f"[Email] Starting IMAP poll loop "
                    f"(every {self._poll_interval}s)")
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                count = await asyncio.to_thread(self._poll_inbox,
                                                on_message, loop)
                if count:
                    logger.info(f"[Email] {count} new message(s) processed")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[Email] Poll error: {e}")
            # interruptible sleep
            for _ in range(self._poll_interval):
                if not self._running:
                    return
                await asyncio.sleep(1)

    def _poll_inbox(self, on_message, loop) -> int:
        """One synchronous IMAP poll — runs in a worker thread."""
        import imaplib
        from email import message_from_bytes
        from email.utils import parseaddr

        conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        processed = 0
        try:
            conn.login(self.token, self._password)
            conn.select("INBOX")
            typ, data = conn.search(None, "UNSEEN")
            if typ != "OK":
                return 0
            ids = (data[0] or b"").split()
            for num in ids[:20]:  # cap per poll
                typ, msg_data = conn.fetch(num, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = message_from_bytes(raw)
                # extract the first text part
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        if ctype in ("text/plain", "text/html") and \
                           not part.get_filename():
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(
                                    part.get_content_charset() or "utf-8",
                                    errors="replace")
                                if ctype == "text/plain":
                                    break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(
                            msg.get_content_charset() or "utf-8",
                            errors="replace")
                if not body:
                    continue
                sender_addr = parseaddr(msg.get("From", ""))[1]
                # strip HTML tags for the agent when only html exists
                if "<" in body and ">" in body and "text/plain" not in \
                        str(msg.get_content_type()):
                    import re
                    body = re.sub(r"<[^>]+>", " ", body)
                    body = re.sub(r"\s+", " ", body).strip()
                incoming = IncomingMessage(
                    platform="email",
                    user_id=sender_addr,
                    channel_id=sender_addr,   # reply to the sender
                    text=body[:10000],
                    message_id=msg.get("Message-ID", ""),
                )
                # dispatch on the event loop (we're in a thread)
                asyncio.run_coroutine_threadsafe(on_message(incoming), loop)
                processed += 1
            # mark processed messages as seen
            if ids:
                conn.store(b",".join(ids[:20]), "+FLAGS", "(\\Seen)")
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return processed

    async def send(self, channel_id: str, text: str) -> dict:
        """Send an email. ``channel_id`` should be the recipient address."""
        if not self.is_configured():
            logger.info(f"[Email:stub] Would send to {channel_id}: {text[:80]}")
            return {"sent": False, "reason": "stub"}
        try:
            from email.mime.text import MIMEText

            msg = MIMEText(text[:10000])
            msg["Subject"] = "SHS Code Response"
            msg["From"] = self.token
            msg["To"] = channel_id

            await asyncio.to_thread(self._smtp_send, msg)
            logger.debug(f"[Email] Message sent to {channel_id}")
            return {"sent": True}
        except Exception as e:
            logger.warning(f"[Email] Send failed: {e}")
            return {"sent": False}

    def _smtp_send(self, msg) -> None:
        """Blocking SMTP send — runs in a thread via asyncio.to_thread."""
        import smtplib

        with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
            server.starttls()
            server.login(self.token, self._password)
            server.send_message(msg)

    async def disconnect(self) -> None:
        self._running = False
        logger.info("[Email] Disconnected")
