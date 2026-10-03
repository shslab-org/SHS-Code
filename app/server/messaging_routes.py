"""SHS Code messaging webhook routes (v4.2.0).

FastAPI router that completes the messaging-stub mission: webhook-based
platforms (WhatsApp Cloud API, Microsoft Teams Bot Framework, Google
Chat) finally have real inbound HTTP endpoints:

    GET  /messaging/webhooks/whatsapp   — Meta webhook verification
    POST /messaging/webhooks/whatsapp   — inbound WhatsApp events
    POST /messaging/webhooks/teams      — Bot Framework activities
    POST /messaging/webhooks/google-chat— Google Chat events
    GET  /messaging/channels            — adapter configuration status

Inbound messages are dispatched through the MessagingGateway default
handler (agent run + platform reply) as background tasks, so the HTTP
response returns immediately — platforms require a fast 200.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.logger import logger

router = APIRouter(prefix="/messaging", tags=["messaging"])

_gateway = None


def _gw():
    """Lazily build the MessagingGateway (config-aware adapter list)."""
    global _gateway
    if _gateway is None:
        from app.messaging.gateway import MessagingGateway
        _gateway = MessagingGateway(use_router=False)
    return _gateway


def _adapter(platform: str):
    for adapter in _gw()._adapters:
        if adapter.platform_name == platform:
            return adapter
    return None


def _dispatch(messages) -> int:
    """Fire the gateway handler for each parsed message (background)."""
    count = 0
    for msg in messages:
        try:
            task = asyncio.create_task(_gw()._default_handler(msg))
            # keep a strong reference so the task is not GC'd mid-run
            _BACKGROUND.add(task)
            task.add_done_callback(_BACKGROUND.discard)
            count += 1
        except Exception as e:
            logger.error(f"[MessagingWebhook] dispatch failed: {e}")
    return count


_BACKGROUND: set = set()


# ─── channel status (GUI / docs friendly) ──────────────────────────────────

@router.get("/channels")
async def messaging_channels() -> dict[str, Any]:
    """Which messaging adapters are configured (no secrets)."""
    out = {}
    for adapter in _gw()._adapters:
        out[adapter.platform_name] = {
            "configured": adapter.is_configured(),
        }
    return {"channels": out}


# ─── WhatsApp Cloud API ────────────────────────────────────────────────────

@router.get("/webhooks/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta webhook verification handshake (hub.mode/hub.verify_token)."""
    adapter = _adapter("whatsapp")
    if adapter is None:
        return JSONResponse({"error": "whatsapp adapter missing"}, 501)
    qp = request.query_params
    challenge = await adapter.verify_webhook(
        qp.get("hub.mode", ""), qp.get("hub.verify_token", ""),
        qp.get("hub.challenge", ""))
    if challenge is None:
        return JSONResponse({"error": "verification failed"}, 403)
    return JSONResponse(int(challenge) if challenge.isdigit() else challenge)


@router.post("/webhooks/whatsapp")
async def whatsapp_event(request: Request):
    """Inbound WhatsApp events (messages arrive as webhook payloads)."""
    adapter = _adapter("whatsapp")
    if adapter is None:
        return JSONResponse({"error": "whatsapp adapter missing"}, 501)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, 400)
    messages = await adapter.handle_webhook_event(payload)
    count = _dispatch(messages)
    # Meta requires a 200 regardless of processing outcome
    return JSONResponse({"received": True, "messages": count})


# ─── Microsoft Teams (Bot Framework) ───────────────────────────────────────

@router.post("/webhooks/teams")
async def teams_event(request: Request):
    """Bot Framework message webhook. Responds 200 fast; replies are
    sent asynchronously via the adapter."""
    adapter = _adapter("teams")
    if adapter is None:
        return JSONResponse({"error": "teams adapter missing"}, 501)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, 400)
    messages = await adapter.handle_webhook_event(payload)
    count = _dispatch(messages)
    return JSONResponse({"received": True, "messages": count})


# ─── Google Chat ───────────────────────────────────────────────────────────

@router.post("/webhooks/google-chat")
async def google_chat_event(request: Request):
    """Google Chat event webhook. Optionally verify ?token=… against
    GOOGLE_CHAT_VERIFY_TOKEN when configured."""
    adapter = _adapter("google_chat")
    if adapter is None:
        return JSONResponse({"error": "google_chat adapter missing"}, 501)
    verify = getattr(adapter, "_verify_token", "")
    if verify and request.query_params.get("token", "") != verify:
        return JSONResponse({"error": "invalid token"}, 401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, 400)
    messages = await adapter.handle_webhook_event(payload)
    count = _dispatch(messages)
    return JSONResponse({"received": True, "messages": count})
