"""
Interaction logging conversation handler for the ADM Platform Telegram Bot.

UNIFIED FLOW:
  Agent -> Type Choice (Feedback vs Quick Log)
    - Quick Log path:  Topic -> Outcome -> Follow-up -> Notes -> Confirm  (saves Interaction)
    - Feedback path:   Bucket -> Reasons (multi-select) -> Notes -> Confirm  (saves FeedbackTicket)
"""

import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import InteractionStates
from utils.api_client import api_client
from utils.formatters import (
    format_interaction_summary,
    interaction_saved,
    error_generic,
    cancelled,
    voice_note_received,
    E_HANDSHAKE, E_PERSON, E_PENCIL, E_CHECK, E_CROSS,
    E_CALENDAR, E_MEMO, E_MIC, E_CHAT,
    E_WARNING, E_SPARKLE,
)
from utils.keyboards import (
    agent_list_keyboard,
    interaction_topic_keyboard,
    interaction_outcome_keyboard,
    followup_keyboard,
    notes_keyboard,
    confirm_keyboard,
)
from utils.voice import send_voice_response

# Import feedback taxonomy helpers from feedback_handler
from handlers.feedback_handler import (
    _bucket_keyboard,
    _reason_keyboard,
    _notes_keyboard,
    _format_selected_reasons,
    _build_summary,
    _bucket_from_code,
    _get_reasons,
    BUCKET_CONFIG,
)

logger = logging.getLogger(__name__)

TOPIC_MAP = {
    "topic_product": "Product Info",
    "topic_commission": "Commission Query",
    "topic_system": "System Help",
    "topic_reengage": "Re-engagement",
    "topic_training": "Training",
    "topic_other": "Other",
}

OUTCOME_MAP = {
    "ioutcome_positive": "Positive",
    "ioutcome_neutral": "Neutral",
    "ioutcome_negative": "Negative",
}

FOLLOWUP_DAYS = {
    "followup_tomorrow": 1,
    "followup_3days": 3,
    "followup_1week": 7,
    "followup_2weeks": 14,
    "followup_none": 0,
}


# ---------------------------------------------------------------------------
# Keyboard: interaction type choice (feedback vs quick log)
# ---------------------------------------------------------------------------

def interaction_type_keyboard():
    buttons = [
        [InlineKeyboardButton(
            "\U0001F4DD Log Agent Feedback / Feedback Dein",
            callback_data="itype_feedback",
        )],
        [InlineKeyboardButton(
            "\U0001F4DE Quick Call Log / Call Log Karein",
            callback_data="itype_quicklog",
        )],
        [InlineKeyboardButton(f"{E_CROSS} Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Entry: /log
# ---------------------------------------------------------------------------

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the interaction logging flow."""
    telegram_id = update.effective_user.id

    # Fetch ADM profile early so we have adm_id for the feedback path
    profile = await api_client.get_adm_profile(telegram_id)
    adm_id = None
    if not profile.get("error"):
        adm_id = profile.get("id", profile.get("adm_id"))

    context.user_data["ilog"] = {
        "adm_telegram_id": telegram_id,
        "adm_id": adm_id,
    }

    # Fetch agents from API
    agents_resp = await api_client.get_assigned_agents(telegram_id)
    agents = agents_resp.get("agents", agents_resp.get("data", []))

    if not agents or agents_resp.get("error"):
        error_detail = agents_resp.get("detail", "") if agents_resp.get("error") else ""
        await update.message.reply_text(
            f"{E_CROSS} <b>No agents found</b>\n\n"
            f"You don't have any agents assigned yet.\n"
            f"Aapke paas abhi koi agent assign nahi hai.\n\n"
            f"Add agents via the web dashboard first."
            + (f"\n\n<i>API: {error_detail}</i>" if error_detail else ""),
            parse_mode="HTML",
        )
        context.user_data.pop("ilog", None)
        return ConversationHandler.END

    context.user_data["ilog"]["agents_cache"] = agents
    total_pages = agents_resp.get("total_pages", 1)

    await update.message.reply_text(
        f"{E_HANDSHAKE} <b>Log Interaction</b>\n\n"
        f"Select the agent / Agent chunein:",
        parse_mode="HTML",
        reply_markup=agent_list_keyboard(agents, callback_prefix="iagent", total_pages=total_pages),
    )
    return InteractionStates.SELECT_AGENT


# ---------------------------------------------------------------------------
# Step 1: Agent selection
# ---------------------------------------------------------------------------

async def select_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "iagent_search":
        await query.edit_message_text(
            f"\U0001F50D <b>Search Agent</b>\n\nType the agent's name or code:",
            parse_mode="HTML",
        )
        # Reuse the same state; text will be caught by fallback search
        return InteractionStates.SELECT_AGENT

    if data.startswith("iagent_page_"):
        page = int(data.split("_")[-1])
        telegram_id = update.effective_user.id
        agents_resp = await api_client.get_assigned_agents(telegram_id, page=page)
        agents = agents_resp.get("agents", agents_resp.get("data", []))
        if not agents or agents_resp.get("error"):
            await query.edit_message_text(
                f"{E_CROSS} <b>Could not load agents</b>\n\n"
                f"Please try again with /log",
                parse_mode="HTML",
            )
            context.user_data.pop("ilog", None)
            return ConversationHandler.END
        context.user_data["ilog"]["agents_cache"] = agents
        total_pages = agents_resp.get("total_pages", 1)
        await query.edit_message_text(
            f"{E_HANDSHAKE} <b>Log Interaction</b>\n\nSelect the agent:",
            parse_mode="HTML",
            reply_markup=agent_list_keyboard(agents, callback_prefix="iagent", page=page, total_pages=total_pages),
        )
        return InteractionStates.SELECT_AGENT

    agent_id = data.replace("iagent_", "")
    agents = context.user_data.get("ilog", {}).get("agents_cache", [])
    agent_name = "Unknown Agent"
    for a in agents:
        if str(a.get("id", a.get("agent_code", ""))) == agent_id:
            agent_name = a.get("name", "Unknown Agent")
            break

    context.user_data["ilog"]["agent_id"] = agent_id
    context.user_data["ilog"]["agent_name"] = agent_name

    # NEW: Ask what type of interaction to log
    await query.edit_message_text(
        f"{E_PERSON} Agent: <b>{agent_name}</b>\n\n"
        f"What happened? / Kya hua?\n"
        f"Choose an option below:",
        parse_mode="HTML",
        reply_markup=interaction_type_keyboard(),
    )
    return InteractionStates.SELECT_TYPE


# ---------------------------------------------------------------------------
# Step 1b: Agent search (text input)
# ---------------------------------------------------------------------------

async def search_agent_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle free-text search for agents in the /log flow."""
    # Guard: if ilog data is missing (bot restarted), bail out
    if "ilog" not in context.user_data:
        await update.message.reply_text(
            f"{E_WARNING} Session expired. Please start again with /log",
            parse_mode="HTML",
        )
        return ConversationHandler.END

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
        return InteractionStates.SELECT_AGENT

    context.user_data["ilog"]["agents_cache"] = agents
    await update.message.reply_text(
        f"\U0001F50D Results for \"{search_text}\":",
        parse_mode="HTML",
        reply_markup=agent_list_keyboard(agents, callback_prefix="iagent", show_search=False),
    )
    return InteractionStates.SELECT_AGENT


# ---------------------------------------------------------------------------
# Step 2 (NEW): Type selection — feedback vs quick log
# ---------------------------------------------------------------------------

async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle interaction type selection."""
    query = update.callback_query
    await query.answer()
    data = query.data

    ilog = context.user_data.get("ilog", {})
    agent_name = ilog.get("agent_name", "Agent")

    if data == "itype_quicklog":
        # Quick log path — go to topic selection (original flow)
        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{agent_name}</b>\n\n"
            f"{E_CHAT} What was discussed?\n"
            f"Kya baat hui?",
            parse_mode="HTML",
            reply_markup=interaction_topic_keyboard(),
        )
        return InteractionStates.SELECT_TOPIC

    if data == "itype_feedback":
        # Feedback path — check if ADM profile exists
        adm_id = ilog.get("adm_id")
        if not adm_id:
            await query.edit_message_text(
                f"{E_WARNING} <b>Profile Not Found</b>\n\n"
                "You need to register first before submitting feedback.\n"
                "Pehle register karein, phir feedback dein.\n\n"
                "Use /start to register.",
                parse_mode="HTML",
            )
            context.user_data.pop("ilog", None)
            return ConversationHandler.END

        # Initialize feedback sub-flow data within ilog
        ilog["fb_selected_codes"] = []
        ilog["fb_free_text"] = None
        ilog["fb_voice_file_id"] = None

        # Pre-fetch reason taxonomy
        await _get_reasons()

        # Go to bucket selection
        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{agent_name}</b>\n\n"
            f"What category does their feedback fall under?\n"
            f"Unka feedback kis category mein aata hai?",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return InteractionStates.FB_SELECT_BUCKET

    # Unknown type — shouldn't happen
    return InteractionStates.SELECT_TYPE


# ═══════════════════════════════════════════════════════════════════
# QUICK LOG PATH (original flow, states 12-16)
# ═══════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Step 3: Topic
# ---------------------------------------------------------------------------

async def select_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    topic = TOPIC_MAP.get(query.data, "Other")
    context.user_data["ilog"]["topic"] = topic

    await query.edit_message_text(
        f"{E_CHAT} Topic: <b>{topic}</b>\n\n"
        f"How was the outcome?\n"
        f"Result kaisa raha?",
        parse_mode="HTML",
        reply_markup=interaction_outcome_keyboard(),
    )
    return InteractionStates.SELECT_OUTCOME


# ---------------------------------------------------------------------------
# Step 4: Outcome
# ---------------------------------------------------------------------------

async def select_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    outcome = OUTCOME_MAP.get(query.data, "Neutral")
    context.user_data["ilog"]["outcome"] = outcome

    await query.edit_message_text(
        f"{E_CHECK} Outcome: <b>{outcome}</b>\n\n"
        f"{E_CALENDAR} Schedule a follow-up?\n"
        f"Follow-up schedule karein?",
        parse_mode="HTML",
        reply_markup=followup_keyboard(),
    )
    return InteractionStates.SCHEDULE_FOLLOWUP


# ---------------------------------------------------------------------------
# Step 5: Follow-up
# ---------------------------------------------------------------------------

async def schedule_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    days = FOLLOWUP_DAYS.get(query.data, 0)
    if days > 0:
        followup_date = (datetime.now() + timedelta(days=days)).strftime("%d %b %Y")
        context.user_data["ilog"]["followup_date"] = followup_date
    else:
        context.user_data["ilog"]["followup_date"] = "Not set"

    await query.edit_message_text(
        f"{E_PENCIL} <b>Add Notes</b>\n\n"
        f"Any notes about this interaction?\n"
        f"Koi notes dalna chahenge?",
        parse_mode="HTML",
        reply_markup=notes_keyboard(),
    )
    return InteractionStates.ADD_NOTES


# ---------------------------------------------------------------------------
# Step 6: Notes
# ---------------------------------------------------------------------------

async def notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "notes_skip":
        context.user_data["ilog"]["notes"] = "No additional notes"
        summary = format_interaction_summary(context.user_data["ilog"])
        await query.edit_message_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
        return InteractionStates.CONFIRM

    if query.data == "notes_voice":
        await query.edit_message_text(
            f"{E_MIC} <b>Send a voice note now</b>\n\n"
            f"Or type your notes / Ya type karein:",
            parse_mode="HTML",
        )
        return InteractionStates.ADD_NOTES

    # notes_type
    await query.edit_message_text(
        f"{E_PENCIL} <b>Type your notes:</b>",
        parse_mode="HTML",
    )
    return InteractionStates.ADD_NOTES


async def receive_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "ilog" not in context.user_data:
        await update.message.reply_text(f"{E_WARNING} Session expired. Please start again with /log", parse_mode="HTML")
        return ConversationHandler.END
    context.user_data["ilog"]["notes"] = update.message.text.strip()
    summary = format_interaction_summary(context.user_data["ilog"])
    await update.message.reply_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
    return InteractionStates.CONFIRM


async def receive_notes_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        voice = update.message.voice
        if not voice or not voice.file_id:
            await update.message.reply_text(
                f"{E_WARNING} Voice note could not be read. Please try again or type text instead.",
                parse_mode="HTML",
            )
            return InteractionStates.ADD_NOTES

        context.user_data["ilog"]["notes"] = f"[Voice note: {voice.duration}s]"
        context.user_data["ilog"]["voice_file_id"] = voice.file_id

        await update.message.reply_text(voice_note_received(), parse_mode="HTML")
        summary = format_interaction_summary(context.user_data["ilog"])
        await update.message.reply_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
        return InteractionStates.CONFIRM
    except Exception as e:
        logger.error(f"Voice note error in /log quick path: {e}")
        await update.message.reply_text(
            f"{E_WARNING} Voice note mein error aaya. Text mein likhein ya dubara try karein.",
            parse_mode="HTML",
        )
        return InteractionStates.ADD_NOTES


async def receive_notes_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle document sent as notes in the quick log path."""
    doc = update.message.document
    caption = update.message.caption or ""
    file_name = doc.file_name if doc else "document"
    context.user_data["ilog"]["notes"] = caption or f"[Document: {file_name}]"
    if doc and doc.file_id:
        context.user_data["ilog"]["voice_file_id"] = doc.file_id

    await update.message.reply_text(
        f"\U0001F4CE <b>Document received:</b> {file_name}\n"
        f"Proceeding to confirmation...",
        parse_mode="HTML",
    )
    summary = format_interaction_summary(context.user_data["ilog"])
    await update.message.reply_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
    return InteractionStates.CONFIRM


async def receive_notes_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo sent as notes in the quick log path."""
    caption = update.message.caption or ""
    context.user_data["ilog"]["notes"] = caption or "[Photo attached]"
    if update.message.photo:
        context.user_data["ilog"]["voice_file_id"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        f"\U0001F4F7 <b>Photo received!</b>\nProceeding to confirmation...",
        parse_mode="HTML",
    )
    summary = format_interaction_summary(context.user_data["ilog"])
    await update.message.reply_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
    return InteractionStates.CONFIRM


# ---------------------------------------------------------------------------
# Step 7: Confirm (Quick Log)
# ---------------------------------------------------------------------------

async def confirm_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text(cancelled(), parse_mode="HTML")
        context.user_data.pop("ilog", None)
        return ConversationHandler.END

    ilog_data = context.user_data.get("ilog", {})
    payload = {
        "adm_telegram_id": ilog_data.get("adm_telegram_id"),
        "agent_id": ilog_data.get("agent_id"),
        "topic": ilog_data.get("topic"),
        "outcome": ilog_data.get("outcome"),
        "followup_date": ilog_data.get("followup_date"),
        "notes": ilog_data.get("notes", ""),
        "voice_file_id": ilog_data.get("voice_file_id"),
    }

    result = await api_client.log_interaction(payload)

    if result.get("error"):
        logger.error("Interaction log API failed: %s", result)
        error_detail = result.get("detail", "Could not save interaction")
        await query.edit_message_text(
            f"{E_CROSS} <b>Save Failed</b>\n\n"
            f"Interaction save nahi ho paya.\n"
            f"Please try again with /log.\n\n"
            f"<i>{error_detail}</i>",
            parse_mode="HTML",
        )
        context.user_data.pop("ilog", None)
        return ConversationHandler.END

    saved_text = interaction_saved()
    await query.edit_message_text(saved_text, parse_mode="HTML")
    await send_voice_response(query.message, saved_text)

    context.user_data.pop("ilog", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
# FEEDBACK PATH (inline taxonomy flow, states 17-20)
# ═══════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# FB Step 1: Select bucket (category)
# ---------------------------------------------------------------------------

async def fb_select_bucket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bucket selection in the feedback sub-flow — show reasons for multi-select."""
    query = update.callback_query
    await query.answer()

    bucket = query.data.replace("fbucket_", "")
    ilog = context.user_data.get("ilog", {})
    ilog["fb_current_bucket"] = bucket
    reasons_cache = await _get_reasons()
    reasons = reasons_cache.get(bucket, [])

    if not reasons:
        await query.edit_message_text(
            f"{E_WARNING} No reasons found for this category. Try another or /cancel.",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return InteractionStates.FB_SELECT_BUCKET

    selected = ilog.get("fb_selected_codes", [])
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
    return InteractionStates.FB_SELECT_REASONS


# ---------------------------------------------------------------------------
# FB Step 2: Multi-select reasons
# ---------------------------------------------------------------------------

async def fb_toggle_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a reason code selection in the feedback sub-flow."""
    query = update.callback_query
    await query.answer()
    data = query.data

    ilog = context.user_data.get("ilog", {})
    selected = ilog.get("fb_selected_codes", [])
    bucket = ilog.get("fb_current_bucket", "operations")
    reasons_cache = await _get_reasons()

    # Done — move to notes
    if data == "freason_done":
        if not selected:
            await query.answer("Select at least one reason / Kam se kam ek reason chunein", show_alert=True)
            return InteractionStates.FB_SELECT_REASONS

        agent_name = ilog.get("agent_name", "Agent")
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
        return InteractionStates.FB_ADD_NOTES

    # Back to bucket selection
    if data == "freason_back":
        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{ilog.get('agent_name', 'Agent')}</b>\n\n"
            f"Select feedback category:\n"
            f"Feedback category chunein:",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return InteractionStates.FB_SELECT_BUCKET

    # Add from another bucket
    if data == "freason_add_bucket":
        await query.edit_message_text(
            f"{E_PERSON} Agent: <b>{ilog.get('agent_name', 'Agent')}</b>\n"
            f"<b>Already selected:</b> {len(selected)} reasons\n\n"
            f"Select another department category:\n"
            f"Ek aur department chunein:",
            parse_mode="HTML",
            reply_markup=_bucket_keyboard(),
        )
        return InteractionStates.FB_SELECT_BUCKET

    # Toggle reason code
    code = data.replace("freason_", "")
    if code in selected:
        selected.remove(code)
    else:
        selected.append(code)
    ilog["fb_selected_codes"] = selected

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
    return InteractionStates.FB_SELECT_REASONS


# ---------------------------------------------------------------------------
# FB Step 3: Optional free text notes
# ---------------------------------------------------------------------------

async def fb_notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle notes option selection in the feedback sub-flow."""
    query = update.callback_query
    await query.answer()

    if query.data == "fnotes_skip":
        context.user_data["ilog"]["fb_free_text"] = None
        return await _fb_show_confirmation(query, context)

    if query.data == "fnotes_voice":
        await query.edit_message_text(
            f"\U0001F3A4 <b>Send a voice note now</b>\n\n"
            f"Agent ne kya bataya, apni awaaz mein record karein:\n"
            f"Ya type bhi kar sakte hain.",
            parse_mode="HTML",
        )
        return InteractionStates.FB_ADD_NOTES

    # Ask for text
    await query.edit_message_text(
        f"{E_PENCIL} <b>Type your additional details:</b>\n\n"
        f"Agent ne aur kya bataya? Free-text mein likhein:\n\n"
        f"<i>(e.g., 'He says too many proposals are rejected in his district...')</i>",
        parse_mode="HTML",
    )
    return InteractionStates.FB_ADD_NOTES


async def fb_receive_notes_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive free text notes for feedback sub-flow."""
    if "ilog" not in context.user_data:
        await update.message.reply_text(f"{E_WARNING} Session expired. Please start again with /log", parse_mode="HTML")
        return ConversationHandler.END
    context.user_data["ilog"]["fb_free_text"] = update.message.text.strip()
    return await _fb_show_confirmation_msg(update, context)


async def fb_receive_notes_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive voice note as feedback details in the feedback sub-flow."""
    try:
        voice = update.message.voice
        if not voice or not voice.file_id:
            await update.message.reply_text(
                f"{E_WARNING} Voice note could not be read. Please try again or type text instead.",
                parse_mode="HTML",
            )
            return InteractionStates.FB_ADD_NOTES

        context.user_data["ilog"]["fb_free_text"] = f"[Voice note: {voice.duration}s]"
        context.user_data["ilog"]["fb_voice_file_id"] = voice.file_id

        await update.message.reply_text(
            f"\U0001F3A4 <b>Voice note received!</b> ({voice.duration}s)\n"
            f"Voice note mil gaya! Proceeding to confirmation...",
            parse_mode="HTML",
        )
        return await _fb_show_confirmation_msg(update, context)
    except Exception as e:
        logger.error(f"Voice note error in /log feedback path: {e}")
        await update.message.reply_text(
            f"{E_WARNING} Voice note mein error aaya. Text mein likhein ya dubara try karein.",
            parse_mode="HTML",
        )
        return InteractionStates.FB_ADD_NOTES


async def fb_receive_notes_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle document sent as feedback notes in the feedback sub-flow."""
    doc = update.message.document
    caption = update.message.caption or ""
    file_name = doc.file_name if doc else "document"
    context.user_data["ilog"]["fb_free_text"] = caption or f"[Document: {file_name}]"
    if doc and doc.file_id:
        context.user_data["ilog"]["fb_voice_file_id"] = doc.file_id

    await update.message.reply_text(
        f"\U0001F4CE <b>Document received:</b> {file_name}\n"
        f"Proceeding to confirmation...",
        parse_mode="HTML",
    )
    return await _fb_show_confirmation_msg(update, context)


async def fb_receive_notes_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photo sent as feedback notes in the feedback sub-flow."""
    caption = update.message.caption or ""
    context.user_data["ilog"]["fb_free_text"] = caption or "[Photo attached]"
    if update.message.photo:
        context.user_data["ilog"]["fb_voice_file_id"] = update.message.photo[-1].file_id

    await update.message.reply_text(
        f"\U0001F4F7 <b>Photo received!</b>\nProceeding to confirmation...",
        parse_mode="HTML",
    )
    return await _fb_show_confirmation_msg(update, context)


# ---------------------------------------------------------------------------
# FB Step 4: Confirm and submit
# ---------------------------------------------------------------------------

def _fb_build_summary(ilog: dict, reasons_cache: dict) -> str:
    """Build confirmation summary for feedback sub-flow."""
    agent_name = ilog.get("agent_name", "Agent")
    selected = ilog.get("fb_selected_codes", [])
    free_text = ilog.get("fb_free_text")

    reasons_text = _format_selected_reasons(selected, reasons_cache)

    text = (
        f"{E_SPARKLE} <b>Feedback Summary / Feedback Ka Saar</b>\n"
        f"{'=' * 30}\n"
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
        f"{'=' * 30}\n"
        f"\nConfirm to submit / Submit karne ke liye confirm karein:"
    )
    return text


async def _fb_show_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation summary (from callback query)."""
    ilog = context.user_data.get("ilog", {})
    reasons_cache = await _get_reasons()
    summary = _fb_build_summary(ilog, reasons_cache)

    await query.edit_message_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )
    return InteractionStates.FB_CONFIRM


async def _fb_show_confirmation_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation summary (from text message)."""
    ilog = context.user_data.get("ilog", {})
    reasons_cache = await _get_reasons()
    summary = _fb_build_summary(ilog, reasons_cache)

    await update.message.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )
    return InteractionStates.FB_CONFIRM


async def fb_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation — submit the feedback ticket from /log flow."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text(cancelled(), parse_mode="HTML")
        context.user_data.pop("ilog", None)
        return ConversationHandler.END

    ilog = context.user_data.get("ilog", {})

    adm_id = ilog.get("adm_id", 0)
    if not adm_id:
        await query.edit_message_text(
            f"{E_WARNING} <b>Session Error</b>\n\n"
            f"Your ADM profile could not be found. Please use /start to register first.\n"
            f"Aapka profile nahi mila. Pehle /start se register karein.",
            parse_mode="HTML",
        )
        context.user_data.pop("ilog", None)
        return ConversationHandler.END

    payload = {
        "agent_id": int(ilog.get("agent_id", 0)),
        "adm_id": adm_id,
        "channel": "telegram",
        "selected_reason_codes": ilog.get("fb_selected_codes", []),
        "raw_feedback_text": ilog.get("fb_free_text"),
        "voice_file_id": ilog.get("fb_voice_file_id"),
    }

    result = await api_client.submit_feedback_ticket(payload)

    if result.get("error"):
        logger.warning("Feedback ticket submission from /log failed: %s", result)
        await query.edit_message_text(
            f"{E_WARNING} <b>Submission failed</b>\n\n"
            f"Could not submit feedback. Please try again.\n"
            f"Feedback submit nahi ho paya. Dobara try karein.\n\n"
            f"<i>Error: {result.get('detail', 'Unknown error')}</i>",
            parse_mode="HTML",
        )
        context.user_data.pop("ilog", None)
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
        f"{'=' * 30}\n\n"
        f"{E_PERSON} Agent: <b>{ilog.get('agent_name', 'Agent')}</b>\n\n"
        f"\U0001F4E8 <b>Tickets Created:</b>\n{tickets_text}\n\n"
        f"\U0001F4AC {message}\n\n"
        f"\u23F0 You'll be notified when the department responds with a\n"
        f"communication script to use with the agent.\n\n"
        f"<i>Jab department jawab dega, aapko ek script milega\n"
        f"jo aap agent se baat karte waqt use kar sakte hain.</i>"
    )

    sent_msg = await query.edit_message_text(success_text, parse_mode="HTML")
    await send_voice_response(sent_msg, success_text)

    context.user_data.pop("ilog", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("ilog", None)
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

def build_interaction_handler() -> ConversationHandler:
    """Build the /log interaction conversation handler with unified feedback + quick log.

    The cancel callback is registered in every state (not just fallbacks) so
    stale inline-keyboard cancel buttons always work regardless of current state.
    allow_reentry=True lets users restart with /log if the flow gets stuck
    (e.g., after a bot restart wiping in-memory state).
    """
    # Cancel handler must be in every state so stale buttons work
    _cancel_cb = lambda: CallbackQueryHandler(cancel_interaction, pattern=r"^cancel$")

    return ConversationHandler(
        entry_points=[CommandHandler("log", log_command)],
        states={
            InteractionStates.SELECT_AGENT: [
                CallbackQueryHandler(select_agent, pattern=r"^iagent_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_agent_text),
                _cancel_cb(),
            ],
            InteractionStates.SELECT_TYPE: [
                CallbackQueryHandler(select_type, pattern=r"^itype_"),
                _cancel_cb(),
            ],
            # --- Quick Log path ---
            InteractionStates.SELECT_TOPIC: [
                CallbackQueryHandler(select_topic, pattern=r"^topic_"),
                _cancel_cb(),
            ],
            InteractionStates.SELECT_OUTCOME: [
                CallbackQueryHandler(select_outcome, pattern=r"^ioutcome_"),
                _cancel_cb(),
            ],
            InteractionStates.SCHEDULE_FOLLOWUP: [
                CallbackQueryHandler(schedule_followup, pattern=r"^followup_"),
                _cancel_cb(),
            ],
            InteractionStates.ADD_NOTES: [
                CallbackQueryHandler(notes_callback, pattern=r"^notes_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_notes_text),
                MessageHandler(filters.VOICE, receive_notes_voice),
                MessageHandler(filters.Document.ALL, receive_notes_document),
                MessageHandler(filters.PHOTO, receive_notes_photo),
                _cancel_cb(),
            ],
            InteractionStates.CONFIRM: [
                CallbackQueryHandler(confirm_interaction, pattern=r"^confirm_"),
                _cancel_cb(),
            ],
            # --- Feedback sub-flow path ---
            InteractionStates.FB_SELECT_BUCKET: [
                CallbackQueryHandler(fb_select_bucket, pattern=r"^fbucket_"),
                _cancel_cb(),
            ],
            InteractionStates.FB_SELECT_REASONS: [
                CallbackQueryHandler(fb_toggle_reason, pattern=r"^freason_"),
                _cancel_cb(),
            ],
            InteractionStates.FB_ADD_NOTES: [
                CallbackQueryHandler(fb_notes_callback, pattern=r"^fnotes_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, fb_receive_notes_text),
                MessageHandler(filters.VOICE, fb_receive_notes_voice),
                MessageHandler(filters.Document.ALL, fb_receive_notes_document),
                MessageHandler(filters.PHOTO, fb_receive_notes_photo),
                _cancel_cb(),
            ],
            InteractionStates.FB_CONFIRM: [
                CallbackQueryHandler(fb_confirm, pattern=r"^confirm_"),
                _cancel_cb(),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_interaction),
            CommandHandler("log", log_command),  # Allow re-entry
            _cancel_cb(),
        ],
        name="interaction_log",
        persistent=False,
        allow_reentry=True,
        conversation_timeout=600,  # 10 min — auto-expire stale flows after bot restart
    )
