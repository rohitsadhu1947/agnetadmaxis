"""
Feedback capture conversation handler for the ADM Platform Telegram Bot.
NEW WORKFLOW: Agent → Bucket → Pick Reasons (multi-select) → Optional Free Text → Confirm → AI Routes

Uses the 5-bucket reason taxonomy (Underwriting, Finance, Contest & Engagement, Operations, Product)
with pick-and-choose multi-select + optional free text.
"""

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

from config import FeedbackStates
from utils.api_client import api_client
from utils.formatters import (
    error_generic,
    cancelled,
    header,
    E_CHAT, E_PERSON, E_CHECK, E_CROSS,
    E_MEMO, E_SPARKLE, E_PENCIL, E_WARNING,
)
from utils.keyboards import agent_list_keyboard, confirm_keyboard
from utils.voice import send_voice_response

logger = logging.getLogger(__name__)

# Bucket display config (emoji + name + hindi)
BUCKET_CONFIG = {
    "underwriting": {"emoji": "\U0001F4CB", "name": "Underwriting", "hindi": "Underwriting"},
    "finance":      {"emoji": "\U0001F4B0", "name": "Finance", "hindi": "Commission / Payout"},
    "contest":      {"emoji": "\U0001F3C6", "name": "Contest & Engagement", "hindi": "Contest / Motivation"},
    "operations":   {"emoji": "\u2699\uFE0F", "name": "Operations", "hindi": "System / App Issues"},
    "product":      {"emoji": "\U0001F4E6", "name": "Product", "hindi": "Product Issues"},
}

# Cache for reason taxonomy (loaded once from API)
_reason_cache = {}


async def _get_reasons() -> dict:
    """Fetch reason taxonomy from API (cached — only refetches if cache is empty)."""
    global _reason_cache
    if _reason_cache:
        return _reason_cache

    try:
        resp = await api_client.get_reason_taxonomy()
        if isinstance(resp, list):
            for bucket_data in resp:
                bucket = bucket_data.get("bucket")
                reasons = bucket_data.get("reasons", [])
                if reasons:
                    _reason_cache[bucket] = reasons
        elif isinstance(resp, dict) and not resp.get("error"):
            for bucket, data in resp.items():
                if isinstance(data, dict):
                    _reason_cache[bucket] = data.get("reasons", [])
    except Exception as e:
        logger.error(f"Failed to fetch reason taxonomy: {e}")

    if not _reason_cache:
        logger.warning("No feedback reasons loaded from API — ReasonTaxonomy table may be empty")

    return _reason_cache


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------

def _bucket_keyboard() -> InlineKeyboardMarkup:
    """Build bucket selection keyboard."""
    buttons = []
    for bucket_key, cfg in BUCKET_CONFIG.items():
        buttons.append([
            InlineKeyboardButton(
                f"{cfg['emoji']} {cfg['name']} / {cfg['hindi']}",
                callback_data=f"fbucket_{bucket_key}",
            )
        ])
    buttons.append([InlineKeyboardButton(f"{E_CROSS} Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def _reason_keyboard(bucket: str, selected_codes: list, reasons: list) -> InlineKeyboardMarkup:
    """Build reason multi-select keyboard with checkmarks for selected items."""
    buttons = []
    for r in reasons:
        code = r.get("code", "")
        name = r.get("reason_name", "Unknown")
        is_selected = code in selected_codes
        check = "\u2705 " if is_selected else ""
        # Truncate long names
        display = name if len(name) <= 35 else name[:32] + "..."
        buttons.append([
            InlineKeyboardButton(
                f"{check}{display}",
                callback_data=f"freason_{code}",
            )
        ])

    # Action buttons at bottom
    action_row = []
    if selected_codes:
        action_row.append(InlineKeyboardButton(
            f"{E_CHECK} Done ({len(selected_codes)} selected)",
            callback_data="freason_done",
        ))
    action_row.append(InlineKeyboardButton("\u25C0 Back", callback_data="freason_back"))
    buttons.append(action_row)

    # More buckets option
    buttons.append([InlineKeyboardButton(
        "\u2795 Add from another department",
        callback_data="freason_add_bucket",
    )])

    buttons.append([InlineKeyboardButton(f"{E_CROSS} Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def _notes_keyboard() -> InlineKeyboardMarkup:
    """Ask for optional free text notes or voice note."""
    buttons = [
        [InlineKeyboardButton(f"{E_PENCIL} Type Details / Likhein", callback_data="fnotes_type")],
        [InlineKeyboardButton(f"\U0001F3A4 Voice Note / Bolein", callback_data="fnotes_voice")],
        [InlineKeyboardButton(f"\u23E9 Skip / Chhod Dein", callback_data="fnotes_skip")],
        [InlineKeyboardButton(f"{E_CROSS} Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def _format_selected_reasons(selected_codes: list, reasons_cache: dict) -> str:
    """Format selected reasons for display."""
    lines = []
    for code in selected_codes:
        bucket = _bucket_from_code(code)
        name = code
        for r in reasons_cache.get(bucket, []):
            if r.get("code") == code:
                name = r.get("reason_name", code)
                break
        cfg = BUCKET_CONFIG.get(bucket, {})
        emoji = cfg.get("emoji", "\U0001F4CB")
        lines.append(f"  {emoji} <code>{code}</code> — {name}")
    return "\n".join(lines)


def _bucket_from_code(code: str) -> str:
    """Get bucket name from reason code prefix."""
    prefix = code.split("-")[0].upper()
    mapping = {"UW": "underwriting", "FIN": "finance", "CON": "contest",
               "OPS": "operations", "PRD": "product"}
    return mapping.get(prefix, "operations")


# ---------------------------------------------------------------------------
# Entry: /feedback
# ---------------------------------------------------------------------------

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the feedback capture flow."""
    telegram_id = update.effective_user.id

    # --- FIX: Fetch ADM profile at the START and store adm_id early ---
    profile = await api_client.get_adm_profile(telegram_id)
    if profile.get("error") or not profile.get("id", profile.get("adm_id")):
        await update.message.reply_text(
            f"{E_WARNING} <b>Profile Not Found</b>\n\n"
            "You need to register first before submitting feedback.\n"
            "Pehle register karein, phir feedback dein.\n\n"
            "Use /start to register.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    adm_id = profile.get("id", profile.get("adm_id"))

    context.user_data["fb"] = {
        "adm_telegram_id": telegram_id,
        "adm_id": adm_id,
        "selected_codes": [],
    }

    # Pre-fetch reason taxonomy (uses cache if already loaded — no unnecessary API call)
    await _get_reasons()

    # Fetch agents
    agents_resp = await api_client.get_assigned_agents(telegram_id)
    agents = agents_resp.get("agents", agents_resp.get("data", []))

    if not agents or agents_resp.get("error"):
        text = (
            f"{E_WARNING} <b>No agents found</b>\n\n"
            "You don't have any agents assigned yet.\n"
            "Aapke paas abhi koi agent assign nahi hai.\n\n"
            "Add agents via the web dashboard first."
        )
        await update.message.reply_text(text, parse_mode="HTML")
        context.user_data.pop("fb", None)
        return ConversationHandler.END

    context.user_data["fb"]["agents_cache"] = agents
    total_pages = agents_resp.get("total_pages", 1)

    await update.message.reply_text(
        f"{E_CHAT} <b>Feedback Intelligence</b>\n\n"
        f"Select the agent you spoke with:\n"
        f"Jis agent se baat hui, unhe chunein:",
        parse_mode="HTML",
        reply_markup=agent_list_keyboard(agents, callback_prefix="fbagent", total_pages=total_pages),
    )
    return FeedbackStates.SELECT_AGENT


# ---------------------------------------------------------------------------
# Step 1: Select agent
# ---------------------------------------------------------------------------

async def select_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle agent selection."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Search
    if data == "fbagent_search":
        await query.edit_message_text(
            "\U0001F50D <b>Search Agent</b>\n\n"
            "Type the agent's name or code:\n"
            "Agent ka naam ya code type karein:",
            parse_mode="HTML",
        )
        return FeedbackStates.SEARCH_AGENT

    # Pagination
    if data.startswith("fbagent_page_"):
        page = int(data.split("_")[-1])
        telegram_id = update.effective_user.id
        agents_resp = await api_client.get_assigned_agents(telegram_id, page=page)
        agents = agents_resp.get("agents", agents_resp.get("data", []))
        if not agents or agents_resp.get("error"):
            await query.edit_message_text(f"{E_WARNING} Could not load agents.", parse_mode="HTML")
            return ConversationHandler.END
        total_pages = agents_resp.get("total_pages", 1)
        context.user_data["fb"]["agents_cache"] = agents
        await query.edit_message_text(
            f"{E_CHAT} <b>Feedback Intelligence</b>\n\nSelect agent:",
            parse_mode="HTML",
            reply_markup=agent_list_keyboard(agents, callback_prefix="fbagent", page=page, total_pages=total_pages),
        )
        return FeedbackStates.SELECT_AGENT

    # Agent selected
    agent_id = data.replace("fbagent_", "")
    agents = context.user_data.get("fb", {}).get("agents_cache", [])
    agent_name = "Agent"
    for a in agents:
        if str(a.get("id", a.get("agent_code", ""))) == agent_id:
            agent_name = a.get("name", "Agent")
            break

    context.user_data["fb"]["agent_id"] = agent_id
    context.user_data["fb"]["agent_name"] = agent_name

    # Go to bucket selection
    await query.edit_message_text(
        f"{E_PERSON} Agent: <b>{agent_name}</b>\n\n"
        f"What category does their feedback fall under?\n"
        f"Unka feedback kis category mein aata hai?",
        parse_mode="HTML",
        reply_markup=_bucket_keyboard(),
    )
    return FeedbackStates.SELECT_CATEGORY


async def search_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle agent search."""
    search_text = update.message.text.strip()
    telegram_id = update.effective_user.id

    agents_resp = await api_client.get_assigned_agents(telegram_id, search=search_text)
    agents = agents_resp.get("agents", agents_resp.get("data", []))

    if not agents or agents_resp.get("error"):
        await update.message.reply_text(
            f"{E_CROSS} No agents found for \"{search_text}\".\n"
            f"Koi agent nahi mila. Try again or /cancel.",
            parse_mode="HTML",
        )
        return FeedbackStates.SEARCH_AGENT

    context.user_data["fb"]["agents_cache"] = agents
    await update.message.reply_text(
        f"\U0001F50D Results for \"{search_text}\":",
        parse_mode="HTML",
        reply_markup=agent_list_keyboard(agents, callback_prefix="fbagent", show_search=False),
    )
    return FeedbackStates.SELECT_AGENT


# ---------------------------------------------------------------------------
# Step 2: Select bucket (category)
# ---------------------------------------------------------------------------

async def select_bucket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bucket selection — show reasons for multi-select."""
    query = update.callback_query
    await query.answer()

    bucket = query.data.replace("fbucket_", "")
    context.user_data["fb"]["current_bucket"] = bucket
    reasons_cache = await _get_reasons()
    reasons = reasons_cache.get(bucket, [])

    if not reasons:
        await query.edit_message_text(
            f"{E_WARNING} No reasons found for this category. Try another or /cancel.",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return FeedbackStates.SELECT_CATEGORY

    selected = context.user_data["fb"].get("selected_codes", [])
    cfg = BUCKET_CONFIG.get(bucket, {})

    text = (
        f"{cfg.get('emoji', '')} <b>{cfg.get('name', bucket)}</b>\n\n"
        f"Tap reasons to select/deselect (multi-select):\n"
        f"Reason tap karein chunne ke liye:\n"
    )
    if selected:
        text += f"\n<b>Selected so far:</b> {len(selected)}\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=_reason_keyboard(bucket, selected, reasons),
    )
    return FeedbackStates.SELECT_SUBCATEGORY


# ---------------------------------------------------------------------------
# Step 3: Multi-select reasons
# ---------------------------------------------------------------------------

async def toggle_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a reason code selection."""
    query = update.callback_query
    await query.answer()
    data = query.data

    fb = context.user_data.get("fb", {})
    selected = fb.get("selected_codes", [])
    bucket = fb.get("current_bucket", "operations")
    reasons_cache = await _get_reasons()

    # Done — move to notes
    if data == "freason_done":
        if not selected:
            await query.answer("Select at least one reason / Kam se kam ek reason chunein", show_alert=True)
            return FeedbackStates.SELECT_SUBCATEGORY

        agent_name = fb.get("agent_name", "Agent")
        reasons_text = _format_selected_reasons(selected, reasons_cache)

        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{agent_name}</b>\n"
            f"{E_MEMO} <b>Selected Reasons ({len(selected)}):</b>\n"
            f"{reasons_text}\n\n"
            f"Would you like to add more details in free text?\n"
            f"Kya aap aur details dena chahenge?",
            parse_mode="HTML",
            reply_markup=_notes_keyboard(),
        )
        return FeedbackStates.ADD_NOTES

    # Back to bucket selection
    if data == "freason_back":
        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{fb.get('agent_name', 'Agent')}</b>\n\n"
            f"Select feedback category:\n"
            f"Feedback category chunein:",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return FeedbackStates.SELECT_CATEGORY

    # Add from another bucket
    if data == "freason_add_bucket":
        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{fb.get('agent_name', 'Agent')}</b>\n"
            f"<b>Already selected:</b> {len(selected)} reasons\n\n"
            f"Select another department category:\n"
            f"Ek aur department chunein:",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return FeedbackStates.SELECT_CATEGORY

    # Toggle reason code
    code = data.replace("freason_", "")
    if code in selected:
        selected.remove(code)
    else:
        selected.append(code)
    context.user_data["fb"]["selected_codes"] = selected

    # Refresh keyboard
    reasons = reasons_cache.get(bucket, [])
    cfg = BUCKET_CONFIG.get(bucket, {})
    text = (
        f"{cfg.get('emoji', '')} <b>{cfg.get('name', bucket)}</b>\n\n"
        f"Tap reasons to select/deselect:\n"
    )
    if selected:
        text += f"\n<b>Selected:</b> {len(selected)} reasons\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=_reason_keyboard(bucket, selected, reasons),
    )
    return FeedbackStates.SELECT_SUBCATEGORY


# ---------------------------------------------------------------------------
# Step 4: Optional free text notes
# ---------------------------------------------------------------------------

async def notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle notes option selection."""
    query = update.callback_query
    await query.answer()

    if query.data == "fnotes_skip":
        context.user_data["fb"]["free_text"] = None
        return await _show_confirmation(query, context)

    if query.data == "fnotes_voice":
        await query.edit_message_text(
            f"\U0001F3A4 <b>Send a voice note now</b>\n\n"
            f"Agent ne kya bataya, apni awaaz mein record karein:\n"
            f"Ya type bhi kar sakte hain.",
            parse_mode="HTML",
        )
        return FeedbackStates.ADD_NOTES

    # Ask for text
    await query.edit_message_text(
        f"{E_PENCIL} <b>Type your additional details:</b>\n\n"
        f"Agent ne aur kya bataya? Free-text mein likhein:\n\n"
        f"<i>(e.g., 'He says too many proposals are rejected in his district...')</i>",
        parse_mode="HTML",
    )
    return FeedbackStates.ADD_NOTES


async def receive_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive free text notes."""
    context.user_data["fb"]["free_text"] = update.message.text.strip()
    return await _show_confirmation_msg(update, context)


async def receive_notes_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive voice note as feedback details."""
    try:
        voice = update.message.voice
        if not voice or not voice.file_id:
            await update.message.reply_text(
                f"{E_WARNING} Voice note could not be read. Please try again or type text instead.",
                parse_mode="HTML",
            )
            return FeedbackStates.ADD_NOTES

        context.user_data["fb"]["free_text"] = f"[Voice note: {voice.duration}s]"
        context.user_data["fb"]["voice_file_id"] = voice.file_id

        await update.message.reply_text(
            f"\U0001F3A4 <b>Voice note received!</b> ({voice.duration}s)\n"
            f"Voice note mil gaya! Proceeding to confirmation...",
            parse_mode="HTML",
        )
        return await _show_confirmation_msg(update, context)
    except Exception as e:
        logger.error(f"Voice note error in /feedback: {e}")
        await update.message.reply_text(
            f"{E_WARNING} Voice note mein error aaya. Text mein likhein ya dubara try karein.",
            parse_mode="HTML",
        )
        return FeedbackStates.ADD_NOTES


async def receive_notes_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle document sent as feedback notes."""
    doc = update.message.document
    caption = update.message.caption or ""
    file_name = doc.file_name if doc else "document"
    context.user_data["fb"]["free_text"] = caption or f"[Document: {file_name}]"
    if doc and doc.file_id:
        context.user_data["fb"]["voice_file_id"] = doc.file_id

    await update.message.reply_text(
        f"\U0001F4CE <b>Document received:</b> {file_name}\n"
        f"Proceeding to confirmation...",
        parse_mode="HTML",
    )
    return await _show_confirmation_msg(update, context)


async def receive_notes_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo sent as feedback notes."""
    caption = update.message.caption or ""
    context.user_data["fb"]["free_text"] = caption or "[Photo attached]"
    if update.message.photo:
        context.user_data["fb"]["voice_file_id"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        f"\U0001F4F7 <b>Photo received!</b>\nProceeding to confirmation...",
        parse_mode="HTML",
    )
    return await _show_confirmation_msg(update, context)


# ---------------------------------------------------------------------------
# Step 5: Confirm and submit
# ---------------------------------------------------------------------------

async def _show_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation summary (from callback query)."""
    fb = context.user_data.get("fb", {})
    reasons_cache = await _get_reasons()
    summary = _build_summary(fb, reasons_cache)

    await query.edit_message_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )
    return FeedbackStates.CONFIRM


async def _show_confirmation_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation summary (from text message)."""
    fb = context.user_data.get("fb", {})
    reasons_cache = await _get_reasons()
    summary = _build_summary(fb, reasons_cache)

    await update.message.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )
    return FeedbackStates.CONFIRM


def _build_summary(fb: dict, reasons_cache: dict) -> str:
    """Build confirmation summary text."""
    agent_name = fb.get("agent_name", "Agent")
    selected = fb.get("selected_codes", [])
    free_text = fb.get("free_text")

    reasons_text = _format_selected_reasons(selected, reasons_cache)

    text = (
        f"{E_SPARKLE} <b>Feedback Summary / Feedback Ka Saar</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E_PERSON} <b>Agent:</b> {agent_name}\n\n"
        f"{E_MEMO} <b>Reasons ({len(selected)}):</b>\n"
        f"{reasons_text}\n"
    )
    if free_text:
        display_text = free_text if len(free_text) <= 200 else free_text[:197] + "..."
        text += f"\n{E_PENCIL} <b>Additional Details:</b>\n<i>{display_text}</i>\n"

    # Show which departments will receive
    buckets = list({_bucket_from_code(c) for c in selected})
    dept_names = [BUCKET_CONFIG.get(b, {}).get("name", b) for b in buckets]
    text += (
        f"\n\U0001F3E2 <b>Will be routed to:</b> {', '.join(dept_names)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\nConfirm to submit / Submit karne ke liye confirm karein:"
    )
    return text


async def confirm_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation — submit the feedback ticket."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text(cancelled(), parse_mode="HTML")
        context.user_data.pop("fb", None)
        return ConversationHandler.END

    fb = context.user_data.get("fb", {})

    # Submit to API — adm_id was fetched and stored at the start of the flow
    adm_id = fb.get("adm_id", 0)
    if not adm_id:
        await query.edit_message_text(
            f"{E_WARNING} <b>Session Error</b>\n\n"
            f"Your ADM profile could not be found. Please use /start to register first.\n"
            f"Aapka profile nahi mila. Pehle /start se register karein.",
            parse_mode="HTML",
        )
        context.user_data.pop("fb", None)
        return ConversationHandler.END

    payload = {
        "agent_id": int(fb.get("agent_id", 0)),
        "adm_id": adm_id,
        "channel": "telegram",
        "selected_reason_codes": fb.get("selected_codes", []),
        "raw_feedback_text": fb.get("free_text"),
        "voice_file_id": fb.get("voice_file_id"),
    }

    result = await api_client.submit_feedback_ticket(payload)

    if result.get("error"):
        logger.warning("Feedback ticket submission failed: %s", result)
        await query.edit_message_text(
            f"{E_WARNING} <b>Submission failed</b>\n\n"
            f"Could not submit feedback. Please try again.\n"
            f"Feedback submit nahi ho paya. Dobara try karein.\n\n"
            f"<i>Error: {result.get('detail', 'Unknown error')}</i>",
            parse_mode="HTML",
        )
        context.user_data.pop("fb", None)
        return ConversationHandler.END

    # Success
    tickets = result.get("tickets", [])
    message = result.get("message", "Feedback submitted")

    ticket_lines = []
    for t in tickets:
        tid = t.get("ticket_id", "?")
        bucket_display = t.get("bucket_display", t.get("bucket", ""))
        sla_hours = t.get("sla_hours", 48)
        ticket_lines.append(f"  \U0001F3F7 <code>{tid}</code> \u2192 {bucket_display} (SLA: {sla_hours}h)")

    tickets_text = "\n".join(ticket_lines) if ticket_lines else "Ticket created"

    success_text = (
        f"{E_CHECK} <b>Feedback Submitted!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{E_PERSON} Agent: <b>{fb.get('agent_name', 'Agent')}</b>\n\n"
        f"\U0001F4E8 <b>Tickets Created:</b>\n{tickets_text}\n\n"
        f"\U0001F4AC {message}\n\n"
        f"\u23F0 You'll be notified when the department responds with a\n"
        f"communication script to use with the agent.\n\n"
        f"<i>Jab department jawab dega, aapko ek script milega\n"
        f"jo aap agent se baat karte waqt use kar sakte hain.</i>"
    )

    sent_msg = await query.edit_message_text(success_text, parse_mode="HTML")
    await send_voice_response(sent_msg, success_text)

    context.user_data.pop("fb", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the feedback flow."""
    context.user_data.pop("fb", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(cancelled(), parse_mode="HTML")
    else:
        await update.message.reply_text(cancelled(), parse_mode="HTML")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Build ConversationHandler
# ---------------------------------------------------------------------------

def build_feedback_handler() -> ConversationHandler:
    """Build the /feedback conversation handler with new reason taxonomy flow.

    allow_reentry=True lets users restart with /feedback if the flow gets stuck
    (e.g., after a bot restart wiping in-memory state). Cancel callback is
    registered in every state so stale inline-keyboard buttons always work.
    """
    _cancel_cb = lambda: CallbackQueryHandler(cancel_feedback, pattern=r"^cancel$")

    return ConversationHandler(
        entry_points=[CommandHandler("feedback", feedback_command)],
        states={
            FeedbackStates.SELECT_AGENT: [
                CallbackQueryHandler(select_agent, pattern=r"^fbagent_"),
                _cancel_cb(),
            ],
            FeedbackStates.SEARCH_AGENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_agent),
                _cancel_cb(),
            ],
            FeedbackStates.SELECT_CATEGORY: [
                CallbackQueryHandler(select_bucket, pattern=r"^fbucket_"),
                _cancel_cb(),
            ],
            FeedbackStates.SELECT_SUBCATEGORY: [
                CallbackQueryHandler(toggle_reason, pattern=r"^freason_"),
                _cancel_cb(),
            ],
            FeedbackStates.ADD_NOTES: [
                CallbackQueryHandler(notes_callback, pattern=r"^fnotes_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_notes_text),
                MessageHandler(filters.VOICE, receive_notes_voice),
                MessageHandler(filters.Document.ALL, receive_notes_document),
                MessageHandler(filters.PHOTO, receive_notes_photo),
                _cancel_cb(),
            ],
            FeedbackStates.CONFIRM: [
                CallbackQueryHandler(confirm_feedback, pattern=r"^confirm_"),
                _cancel_cb(),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_feedback),
            CommandHandler("feedback", feedback_command),  # Allow re-entry
            _cancel_cb(),
        ],
        name="feedback",
        persistent=False,
        allow_reentry=True,
    )
