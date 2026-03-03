"""
Feedback submission handler for the Agent Telegram Bot.

Flow:
  /feedback or "agent_menu_feedback" callback
  -> Check registered
  -> Select bucket (department)
  -> Fetch reason taxonomy for that bucket -> multi-select reasons
  -> Add notes (text, voice, photo, document)
  -> Confirm and submit
  -> Show success with ticket_id
"""

from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from agent_bot.config import config, AgentFeedbackStates
from agent_bot.utils.api_client import api_client
from agent_bot.utils.formatters import (
    format_feedback_confirm,
    EMOJI_CHECK,
    EMOJI_CROSS,
    EMOJI_MEMO,
    EMOJI_WARN,
    EMOJI_PIN,
    EMOJI_BULB,
    EMOJI_PERSON,
    EMOJI_TICKET,
    BUCKET_DISPLAY,
    BUCKET_EMOJIS,
)
from agent_bot.utils.keyboards import (
    bucket_keyboard,
    reason_keyboard,
    confirm_cancel_keyboard,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)

# Cache for reason taxonomy (loaded once from API, per bucket)
_reason_cache: dict = {}


async def _get_reasons(bucket: str | None = None) -> dict:
    """Fetch reason taxonomy from API (cached per bucket)."""
    global _reason_cache

    if bucket and bucket in _reason_cache:
        return _reason_cache

    try:
        resp = await api_client.get_reason_taxonomy(bucket=bucket)
        if isinstance(resp, list):
            for bucket_data in resp:
                b = bucket_data.get("bucket")
                reasons = bucket_data.get("reasons", [])
                if reasons:
                    _reason_cache[b] = reasons
        elif isinstance(resp, dict) and not resp.get("error"):
            for b, data in resp.items():
                if isinstance(data, dict):
                    _reason_cache[b] = data.get("reasons", [])
                elif isinstance(data, list):
                    _reason_cache[b] = data
    except Exception as e:
        logger.error("Failed to fetch reason taxonomy: %s", e)

    return _reason_cache


def _format_selected_reasons(selected_codes: list, reasons_by_bucket: dict) -> str:
    """Format selected reason codes for display."""
    lines = []
    for code in selected_codes:
        name = code
        for bucket_reasons in reasons_by_bucket.values():
            for r in bucket_reasons:
                if r.get("code") == code:
                    name = r.get("reason_name", code)
                    break
        lines.append(f"  {EMOJI_PIN} <code>{code}</code> - {name}")
    return "\n".join(lines) if lines else "  None selected"


# ---------------------------------------------------------------------------
# Registration guard
# ---------------------------------------------------------------------------

def _require_registered(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Return agent_id if registered, or None."""
    return context.user_data.get("agent_id")


# ---------------------------------------------------------------------------
# Entry: /feedback or agent_menu_feedback callback
# ---------------------------------------------------------------------------

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the feedback flow — show bucket selection."""
    agent_id = _require_registered(context)
    if not agent_id:
        text = (
            f"{EMOJI_WARN} <b>Not Registered</b>\n\n"
            f"You need to register first. Use /start to register.\n"
            f"Pehle /start se register karein."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return ConversationHandler.END

    # Initialize feedback session data
    context.user_data["afb"] = {
        "agent_id": agent_id,
        "selected_codes": [],
        "notes": None,
        "voice_file_id": None,
        "current_bucket": None,
    }

    # Pre-fetch taxonomy
    await _get_reasons()

    text = (
        f"{EMOJI_MEMO} <b>Submit Feedback</b>\n\n"
        f"Select the department your feedback is about:\n"
        f"Apna feedback kis department ke baare mein hai?"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=bucket_keyboard(),
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=bucket_keyboard(),
        )
    return AgentFeedbackStates.SELECT_BUCKET


# ---------------------------------------------------------------------------
# Step 1: Select bucket
# ---------------------------------------------------------------------------

async def select_bucket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bucket selection — show reasons for that bucket."""
    query = update.callback_query
    await query.answer()

    bucket = query.data.replace("abkt_", "")
    afb = context.user_data.get("afb", {})
    afb["current_bucket"] = bucket

    reasons_cache = await _get_reasons(bucket)
    reasons = reasons_cache.get(bucket, [])

    if not reasons:
        await query.edit_message_text(
            f"{EMOJI_WARN} No feedback reasons found for this department.\n"
            f"Is department ke liye abhi koi reason nahi hai.\n\n"
            f"Try another department or /cancel.",
            parse_mode="HTML",
            reply_markup=bucket_keyboard(),
        )
        return AgentFeedbackStates.SELECT_BUCKET

    selected = set(afb.get("selected_codes", []))
    bucket_display = BUCKET_DISPLAY.get(bucket, bucket.title())
    bucket_emoji = BUCKET_EMOJIS.get(bucket, EMOJI_MEMO)

    text = (
        f"{bucket_emoji} <b>{bucket_display}</b>\n\n"
        f"Tap reasons to select/deselect (multi-select):\n"
        f"Reasons tap karein chunne ke liye:\n"
    )
    if selected:
        text += f"\n<b>Selected so far:</b> {len(selected)}\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reason_keyboard(reasons, selected),
    )
    return AgentFeedbackStates.SELECT_REASONS


# ---------------------------------------------------------------------------
# Step 2: Multi-select reasons
# ---------------------------------------------------------------------------

async def toggle_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a reason code or handle done/cancel."""
    query = update.callback_query
    await query.answer()
    data = query.data

    afb = context.user_data.get("afb", {})
    selected = afb.get("selected_codes", [])
    bucket = afb.get("current_bucket", "operations")

    # Done — move to notes
    if data == "arsn_done":
        if not selected:
            await query.answer(
                "Select at least one reason / Kam se kam ek reason chunein",
                show_alert=True,
            )
            return AgentFeedbackStates.SELECT_REASONS

        reasons_cache = await _get_reasons()
        reasons_text = _format_selected_reasons(selected, reasons_cache)

        await query.edit_message_text(
            f"{EMOJI_MEMO} <b>Selected Reasons ({len(selected)}):</b>\n"
            f"{reasons_text}\n\n"
            f"Would you like to add notes?\n"
            f"Kya aap kuch aur detail dena chahenge?\n\n"
            f"Send a <b>text message</b>, <b>voice note</b>, "
            f"<b>photo</b>, or <b>document</b>.\n"
            f"Or type /skip to skip notes.",
            parse_mode="HTML",
        )
        return AgentFeedbackStates.ADD_NOTES

    # Toggle reason code
    code = data.replace("arsn_", "")
    if code in selected:
        selected.remove(code)
    else:
        selected.append(code)
    afb["selected_codes"] = selected

    # Refresh keyboard
    reasons_cache = await _get_reasons()
    reasons = reasons_cache.get(bucket, [])
    bucket_display = BUCKET_DISPLAY.get(bucket, bucket.title())
    bucket_emoji = BUCKET_EMOJIS.get(bucket, EMOJI_MEMO)

    text = (
        f"{bucket_emoji} <b>{bucket_display}</b>\n\n"
        f"Tap reasons to select/deselect:\n"
    )
    if selected:
        text += f"\n<b>Selected:</b> {len(selected)} reasons\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reason_keyboard(reasons, set(selected)),
    )
    return AgentFeedbackStates.SELECT_REASONS


# ---------------------------------------------------------------------------
# Step 3: Add notes (text, voice, photo, document)
# ---------------------------------------------------------------------------

async def receive_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive free text notes."""
    afb = context.user_data.get("afb")
    if not afb:
        await update.message.reply_text(
            f"{EMOJI_WARN} Session expired. Please start again with /feedback",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    text = update.message.text.strip()

    # Handle /skip
    if text.lower() == "/skip":
        afb["notes"] = None
        return await _show_confirmation_msg(update, context)

    afb["notes"] = text
    return await _show_confirmation_msg(update, context)


async def receive_notes_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive voice note as feedback details."""
    afb = context.user_data.get("afb")
    if not afb:
        await update.message.reply_text(
            f"{EMOJI_WARN} Session expired. Please start again with /feedback",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        voice = update.message.voice
        if not voice or not voice.file_id:
            await update.message.reply_text(
                f"{EMOJI_WARN} Voice note could not be read. Please try again or type text.",
                parse_mode="HTML",
            )
            return AgentFeedbackStates.ADD_NOTES

        afb["notes"] = f"[Voice note: {voice.duration}s]"
        afb["voice_file_id"] = voice.file_id

        await update.message.reply_text(
            f"\U0001f3a4 <b>Voice note received!</b> ({voice.duration}s)",
            parse_mode="HTML",
        )
        return await _show_confirmation_msg(update, context)
    except Exception as e:
        logger.error("Voice note error in /feedback: %s", e)
        await update.message.reply_text(
            f"{EMOJI_WARN} Voice note mein error aaya. Text mein likhein.",
            parse_mode="HTML",
        )
        return AgentFeedbackStates.ADD_NOTES


async def receive_notes_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo sent as feedback notes."""
    afb = context.user_data.get("afb")
    if not afb:
        await update.message.reply_text(
            f"{EMOJI_WARN} Session expired. Use /feedback to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    caption = update.message.caption or ""
    afb["notes"] = caption or "[Photo attached]"
    if update.message.photo:
        afb["voice_file_id"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        f"\U0001f4f7 <b>Photo received!</b>",
        parse_mode="HTML",
    )
    return await _show_confirmation_msg(update, context)


async def receive_notes_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle document sent as feedback notes."""
    afb = context.user_data.get("afb")
    if not afb:
        await update.message.reply_text(
            f"{EMOJI_WARN} Session expired. Use /feedback to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    doc = update.message.document
    caption = update.message.caption or ""
    file_name = doc.file_name if doc else "document"
    afb["notes"] = caption or f"[Document: {file_name}]"
    if doc and doc.file_id:
        afb["voice_file_id"] = doc.file_id

    await update.message.reply_text(
        f"\U0001f4ce <b>Document received:</b> {file_name}",
        parse_mode="HTML",
    )
    return await _show_confirmation_msg(update, context)


# ---------------------------------------------------------------------------
# Step 4: Confirmation
# ---------------------------------------------------------------------------

async def _show_confirmation_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation summary as a message reply."""
    afb = context.user_data.get("afb", {})
    bucket = afb.get("current_bucket", "")
    selected = afb.get("selected_codes", [])
    notes = afb.get("notes") or ""

    summary = format_feedback_confirm(bucket, selected, notes)

    await update.message.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_cancel_keyboard(
            confirm_data="afb_confirm",
            cancel_data="afb_cancel",
        ),
    )
    return AgentFeedbackStates.CONFIRM


async def confirm_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation — submit the feedback."""
    query = update.callback_query
    await query.answer()

    if query.data == "afb_cancel":
        await query.edit_message_text(
            f"{EMOJI_CROSS} Feedback cancelled.\n"
            f"Use /feedback to try again.",
            parse_mode="HTML",
        )
        context.user_data.pop("afb", None)
        return ConversationHandler.END

    afb = context.user_data.get("afb", {})
    agent_id = afb.get("agent_id")

    if not agent_id:
        await query.edit_message_text(
            f"{EMOJI_WARN} <b>Session Error</b>\n\n"
            f"Could not find your profile. Please /start first.",
            parse_mode="HTML",
        )
        context.user_data.pop("afb", None)
        return ConversationHandler.END

    # Submit to API
    result = await api_client.submit_feedback(
        agent_id=int(agent_id),
        channel="telegram",
        selected_reason_codes=afb.get("selected_codes", []),
        raw_feedback_text=afb.get("notes"),
        voice_file_id=afb.get("voice_file_id"),
    )

    if result.get("error"):
        logger.warning("Feedback submission failed: %s", result)
        await query.edit_message_text(
            f"{EMOJI_WARN} <b>Submission failed</b>\n\n"
            f"Could not submit feedback. Please try again.\n"
            f"Feedback submit nahi ho paya. Dobara try karein.\n\n"
            f"<i>Error: {result.get('detail', 'Unknown error')}</i>",
            parse_mode="HTML",
        )
        context.user_data.pop("afb", None)
        return ConversationHandler.END

    # Success
    ticket_id = result.get("ticket_id", result.get("id", "—"))
    tickets = result.get("tickets", [])

    if tickets:
        ticket_lines = []
        for t in tickets:
            tid = t.get("ticket_id", "?")
            bucket_display = t.get("bucket_display", t.get("bucket", ""))
            ticket_lines.append(f"  {EMOJI_TICKET} <code>{tid}</code> \u2192 {bucket_display}")
        tickets_text = "\n".join(ticket_lines)
    else:
        tickets_text = f"  {EMOJI_TICKET} <code>{ticket_id}</code>"

    success_text = (
        f"{EMOJI_CHECK} <b>Feedback Submitted!</b>\n"
        f"{'━' * 28}\n\n"
        f"\U0001f4e8 <b>Ticket(s) Created:</b>\n{tickets_text}\n\n"
        f"Aapko update milega jab department respond karega.\n"
        f"Track your tickets with /cases.\n"
        f"{'━' * 28}"
    )

    await query.edit_message_text(
        success_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    context.user_data.pop("afb", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the feedback flow."""
    context.user_data.pop("afb", None)
    text = f"{EMOJI_CROSS} Feedback cancelled."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Stale callback handler for old inline buttons
# ---------------------------------------------------------------------------

async def _stale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle stale inline button taps from this flow when user is not in it."""
    query = update.callback_query
    await query.answer("This button has expired. Use /feedback to start again.", show_alert=True)


# ---------------------------------------------------------------------------
# Build ConversationHandler
# ---------------------------------------------------------------------------

def _all_callbacks():
    """Create handler instances for all callback patterns in this flow."""
    return [
        CallbackQueryHandler(select_bucket, pattern=r"^abkt_"),
        CallbackQueryHandler(toggle_reason, pattern=r"^arsn_"),
        CallbackQueryHandler(confirm_feedback, pattern=r"^afb_(confirm|cancel)$"),
        CallbackQueryHandler(cancel_feedback, pattern=r"^agent_cancel$"),
    ]


handler = ConversationHandler(
    entry_points=[
        CommandHandler("feedback", feedback_command),
        CallbackQueryHandler(feedback_command, pattern=r"^agent_menu_feedback$"),
    ],
    states={
        AgentFeedbackStates.SELECT_BUCKET: [
            CallbackQueryHandler(select_bucket, pattern=r"^abkt_"),
            CallbackQueryHandler(cancel_feedback, pattern=r"^agent_cancel$"),
        ],
        AgentFeedbackStates.SELECT_REASONS: [
            CallbackQueryHandler(toggle_reason, pattern=r"^arsn_"),
            CallbackQueryHandler(cancel_feedback, pattern=r"^agent_cancel$"),
        ],
        AgentFeedbackStates.ADD_NOTES: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_notes_text),
            MessageHandler(filters.VOICE, receive_notes_voice),
            MessageHandler(filters.PHOTO, receive_notes_photo),
            MessageHandler(filters.Document.ALL, receive_notes_document),
            CommandHandler("skip", lambda u, c: receive_notes_text(u, c)),
            CallbackQueryHandler(cancel_feedback, pattern=r"^agent_cancel$"),
        ],
        AgentFeedbackStates.CONFIRM: [
            CallbackQueryHandler(confirm_feedback, pattern=r"^afb_(confirm|cancel)$"),
            CallbackQueryHandler(cancel_feedback, pattern=r"^agent_cancel$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_feedback),
        CommandHandler("feedback", feedback_command),
        CallbackQueryHandler(cancel_feedback, pattern=r"^agent_cancel$"),
    ],
    name="agent_feedback",
    persistent=False,
    per_user=True,
    per_chat=True,
    allow_reentry=True,
    conversation_timeout=600,
)
