"""
Broadcast Dispatcher Worker.

Polls the broadcasts table for scheduled broadcasts whose time has come,
materialises recipients, sends each one via Telegram, tracks delivery
state per recipient. Designed to run alongside the agent + ADM bots on
the same Mac (or moved to Fly.io / Railway later — pure Python, no
external deps beyond what the backend already needs).

Run:
    cd /Users/rohit/AgentADMSolution/ADMAgent
    AGENT_TELEGRAM_BOT_TOKEN=... python3 broadcast_worker/runner.py

The worker:
  - Polls every POLL_INTERVAL_SEC (default 10s)
  - For each scheduled broadcast whose scheduled_at <= now():
      * Status → "dispatching"
      * Resolve filter → list of agents
      * For each agent: create a BroadcastRecipient row (status=queued)
      * For each queued recipient: rate-limited send via Telegram API
      * Updates per-recipient status + denormalised counts on the broadcast
      * When queue is drained: status → "completed"
  - Rate limit: 25 msg/sec (under Telegram's 30 msg/sec global limit)
  - On HTTP 429: respect retry_after from Telegram
  - On per-recipient failure: mark failed with reason, keep going

Note on attachments:
  - First recipient gets the file bytes uploaded
  - Telegram returns a file_id; we cache it on the broadcast
  - Subsequent recipients reference cached_telegram_file_id (cheap)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Make backend/ importable
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(BACKEND_DIR), ".env"))
    load_dotenv(os.path.join(BACKEND_DIR, ".env"))
except ImportError:
    pass

import httpx  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import Agent, Broadcast, BroadcastRecipient  # noqa: E402
from services.agent_filter import resolve_filter  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("broadcast_worker")

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
POLL_INTERVAL_SEC = int(os.environ.get("BROADCAST_POLL_INTERVAL_SEC", "10"))
SEND_RATE_PER_SEC = int(os.environ.get("BROADCAST_SEND_RATE_PER_SEC", "25"))
MAX_ATTEMPTS = int(os.environ.get("BROADCAST_MAX_ATTEMPTS", "2"))
HTTP_TIMEOUT = 30.0

# Bot token used to deliver broadcasts. We use the agent bot (since agents
# already trust it for the People Feedback flow) — they'll receive broadcasts
# from the same bot. Override via env to use the ADM bot instead if needed.
BOT_TOKEN = (
    os.environ.get("BROADCAST_BOT_TOKEN")
    or os.environ.get("AGENT_TELEGRAM_BOT_TOKEN")
    or ""
)
if not BOT_TOKEN:
    logger.error(
        "No bot token configured. Set BROADCAST_BOT_TOKEN or AGENT_TELEGRAM_BOT_TOKEN.",
    )
    sys.exit(1)


TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ---------------------------------------------------------------------------
# Telegram send helpers
# ---------------------------------------------------------------------------
def _build_caption(broadcast: Broadcast) -> str:
    """Format the message text. Telegram MarkdownV2 is finicky; use HTML."""
    parts = [f"<b>{_html_escape(broadcast.title)}</b>", ""]
    parts.append(_html_escape(broadcast.body))
    if broadcast.link_url:
        label = broadcast.link_label or "Open link"
        parts.append("")
        parts.append(f'<a href="{broadcast.link_url}">{_html_escape(label)}</a>')
    return "\n".join(parts)


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def _send_one(
    client: httpx.AsyncClient,
    broadcast: Broadcast,
    chat_id: str,
) -> tuple[str, Optional[str], Optional[str]]:
    """Send a single broadcast message. Returns (telegram_message_id, file_id, error).
    On success, file_id is the captured Telegram file_id for the attachment
    (only set on the FIRST send when we uploaded bytes — empty otherwise).
    On failure, (None, None, error_message).
    """
    caption = _build_caption(broadcast)
    has_attach = bool(broadcast.attachment_bytes)
    cached_file_id = broadcast.cached_telegram_file_id

    if not has_attach:
        # Plain text message
        resp = await client.post(f"{TG_BASE}/sendMessage", json={
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        })
        return _interpret_tg_response(resp, capture_file_id=False)

    # With attachment — branch by kind
    kind = broadcast.attachment_kind or "document"
    method = {
        "image": "sendPhoto",
        "voice": "sendVoice",
        "document": "sendDocument",
    }.get(kind, "sendDocument")
    file_field = {"image": "photo", "voice": "voice", "document": "document"}[
        kind if kind in ("image", "voice", "document") else "document"
    ]

    if cached_file_id:
        # Cheap path: reference the cached Telegram file_id (no bytes re-uploaded)
        resp = await client.post(f"{TG_BASE}/{method}", json={
            "chat_id": chat_id,
            file_field: cached_file_id,
            "caption": caption,
            "parse_mode": "HTML",
        })
        return _interpret_tg_response(resp, capture_file_id=False)

    # First send — upload bytes via multipart, capture file_id from response
    raw = base64.b64decode(broadcast.attachment_bytes)
    fname = broadcast.attachment_file_name or "attachment"
    mime = broadcast.attachment_mime_type or "application/octet-stream"

    files = {file_field: (fname, raw, mime)}
    data = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
    }
    resp = await client.post(f"{TG_BASE}/{method}", data=data, files=files)
    return _interpret_tg_response(resp, capture_file_id=True, kind=kind)


def _interpret_tg_response(
    resp: httpx.Response,
    capture_file_id: bool,
    kind: str = "",
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse Telegram's response. Returns (message_id, file_id_to_cache, error)."""
    try:
        body = resp.json()
    except Exception:
        return None, None, f"non-JSON response: {resp.text[:200]}"

    if not body.get("ok"):
        desc = body.get("description") or f"HTTP {resp.status_code}"
        retry_after = body.get("parameters", {}).get("retry_after")
        if retry_after:
            return None, None, f"RATE_LIMIT:{retry_after}"
        return None, None, desc

    result = body.get("result", {})
    msg_id = str(result.get("message_id", ""))

    file_id_to_cache = None
    if capture_file_id:
        # Different shape per method
        if kind == "image":
            # sendPhoto returns photo array of size variants
            photos = result.get("photo", [])
            if photos:
                file_id_to_cache = photos[-1].get("file_id")
        elif kind == "voice":
            file_id_to_cache = (result.get("voice") or {}).get("file_id")
        elif kind == "document":
            file_id_to_cache = (result.get("document") or {}).get("file_id")

    return msg_id, file_id_to_cache, None


# ---------------------------------------------------------------------------
# Dispatcher loop
# ---------------------------------------------------------------------------
async def materialise_recipients(broadcast: Broadcast, db) -> int:
    """Resolve the filter and create BroadcastRecipient rows. Returns recipient count."""
    spec = json.loads(broadcast.target_filter or "{}")
    matched = resolve_filter(db, {**spec, "only_telegram_registered": False})

    skipped = 0
    queued = 0
    for agent in matched:
        if not agent.telegram_chat_id:
            db.add(BroadcastRecipient(
                broadcast_id=broadcast.id,
                agent_id=agent.id,
                status="skipped",
                error_reason="agent not telegram-registered",
            ))
            skipped += 1
            continue
        db.add(BroadcastRecipient(
            broadcast_id=broadcast.id,
            agent_id=agent.id,
            telegram_chat_id=agent.telegram_chat_id,
            status="queued",
        ))
        queued += 1

    broadcast.recipient_count = queued + skipped
    broadcast.skipped_count = skipped
    db.commit()
    logger.info(
        "[%s] materialised: %d queued, %d skipped (total matched: %d)",
        broadcast.broadcast_ref, queued, skipped, len(matched),
    )
    return queued


async def dispatch_one(broadcast: Broadcast):
    """Drain the queued recipients for one broadcast, rate-limited."""
    delay_per_send = 1.0 / SEND_RATE_PER_SEC
    last_failed = None
    sent_so_far = 0
    failed_so_far = 0

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        while True:
            # Fetch the next batch of queued recipients
            db = SessionLocal()
            try:
                queued = db.query(BroadcastRecipient).filter(
                    BroadcastRecipient.broadcast_id == broadcast.id,
                    BroadcastRecipient.status == "queued",
                ).order_by(BroadcastRecipient.id).limit(50).all()
                if not queued:
                    break
                for r in queued:
                    chat_id = r.telegram_chat_id
                    if not chat_id:
                        r.status = "skipped"
                        r.error_reason = "no telegram_chat_id"
                        continue

                    r.attempts += 1
                    bc = db.query(Broadcast).get(broadcast.id)  # refresh for cached_file_id
                    msg_id, file_id_to_cache, error = await _send_one(client, bc, chat_id)

                    if error and error.startswith("RATE_LIMIT:"):
                        retry_after = int(error.split(":", 1)[1])
                        logger.warning(
                            "[%s] hit Telegram rate limit; sleeping %ds",
                            broadcast.broadcast_ref, retry_after,
                        )
                        await asyncio.sleep(retry_after + 1)
                        # Don't decrement attempt; recipient stays queued
                        r.attempts = max(r.attempts - 1, 0)
                        continue

                    if error:
                        if r.attempts >= MAX_ATTEMPTS:
                            r.status = "failed"
                            r.error_reason = error[:500]
                            failed_so_far += 1
                            last_failed = error
                        # else leave queued, will retry next loop
                        continue

                    # success
                    r.status = "sent"
                    r.telegram_message_id = msg_id
                    r.sent_at = datetime.utcnow()
                    sent_so_far += 1

                    # Cache file_id on the broadcast row on first successful send
                    if file_id_to_cache and not bc.cached_telegram_file_id:
                        bc.cached_telegram_file_id = file_id_to_cache
                        db.add(bc)

                    await asyncio.sleep(delay_per_send)
                db.commit()
            finally:
                db.close()

    # Final counter update
    db = SessionLocal()
    try:
        bc = db.query(Broadcast).get(broadcast.id)
        bc.sent_count = db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_id == bc.id,
            BroadcastRecipient.status == "sent",
        ).count()
        bc.failed_count = db.query(BroadcastRecipient).filter(
            BroadcastRecipient.broadcast_id == bc.id,
            BroadcastRecipient.status == "failed",
        ).count()
        bc.status = "completed"
        bc.completed_at = datetime.utcnow()
        db.commit()
        logger.info(
            "[%s] dispatch complete: sent=%d failed=%d skipped=%d",
            bc.broadcast_ref, bc.sent_count, bc.failed_count, bc.skipped_count,
        )
    finally:
        db.close()


async def tick():
    """One poll cycle."""
    db = SessionLocal()
    try:
        # Scheduled broadcasts whose time has come
        now = datetime.utcnow()
        candidates = db.query(Broadcast).filter(
            Broadcast.status == "scheduled",
            Broadcast.scheduled_at <= now,
        ).order_by(Broadcast.scheduled_at).all()

        # Also pick up broadcasts that are already in dispatching state but have
        # queued recipients (resumes interrupted dispatch on worker restart)
        resuming = db.query(Broadcast).filter(
            Broadcast.status == "dispatching",
        ).all()
    finally:
        db.close()

    for bc in candidates:
        await _kick_off(bc.id)

    for bc in resuming:
        logger.info("[%s] resuming dispatch", bc.broadcast_ref)
        await _resume(bc.id)


async def _kick_off(broadcast_id: int):
    db = SessionLocal()
    try:
        bc = db.query(Broadcast).get(broadcast_id)
        if not bc or bc.status != "scheduled":
            return
        bc.status = "dispatching"
        bc.dispatched_at = datetime.utcnow()
        db.commit()
        await materialise_recipients(bc, db)
    finally:
        db.close()

    # Drain queue
    db = SessionLocal()
    try:
        bc = db.query(Broadcast).get(broadcast_id)
        await dispatch_one(bc)
    finally:
        db.close()


async def _resume(broadcast_id: int):
    db = SessionLocal()
    try:
        bc = db.query(Broadcast).get(broadcast_id)
        if not bc:
            return
    finally:
        db.close()
    db2 = SessionLocal()
    try:
        bc = db2.query(Broadcast).get(broadcast_id)
        await dispatch_one(bc)
    finally:
        db2.close()


async def main():
    logger.info("Broadcast worker starting (poll=%ds, rate=%d/s)", POLL_INTERVAL_SEC, SEND_RATE_PER_SEC)
    while True:
        try:
            await tick()
        except Exception:
            logger.exception("tick() crashed; sleeping then retrying")
        await asyncio.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
