"""
People Feedback handler for the Agent Telegram Bot.

This is the bot-side flow for the "Report a concern about my ADM" feature.
The feedback never reaches the ADM; it is routed exclusively to the
Agency Development team via the /people-feedback backend API.

Two top-level entry points:
  /concern  or  "agent_menu_concern"        → submit a new concern
  /my_concerns  or  "agent_menu_my_concerns" → list + drill into past concerns

Submit flow:
  PICK_CATEGORY → PICK_SUBCATEGORY → (ENTER_OTHER_TEXT) → ADD_DETAILS → CONFIRM_SUBMIT

Detail / Reply flow:
  VIEW_MY_LIST → VIEW_TICKET_DETAIL → REPLY_TO_TICKET → back to detail
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from agent_bot.config import AgentPeopleFeedbackStates
from agent_bot.utils.api_client import api_client
from agent_bot.utils.keyboards import (
    people_feedback_category_keyboard,
    people_feedback_subcategory_keyboard,
    people_feedback_add_details_keyboard,
    people_feedback_confirm_keyboard,
    my_concerns_list_keyboard,
    my_concern_detail_keyboard,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_agent_id(update: Update, context: Optional[ContextTypes.DEFAULT_TYPE] = None) -> Optional[int]:
    """Resolve the Telegram user to a platform agent_id.

    Priority:
      1) context.user_data["agent_id"] — set by /start registration (canonical)
      2) Backend lookup by chat_id — fallback for bot restarts
    """
    # Priority 1: in-memory (matches what feedback_handler etc. use)
    if context is not None:
        cached = context.user_data.get("agent_id")
        if cached:
            return int(cached)

    # Priority 2: backend lookup so user doesn't have to /start again
    chat_id = str(update.effective_chat.id)
    try:
        profile = await api_client._get(f"/agent-portal/by-chat-id/{chat_id}")
        if isinstance(profile, dict) and profile.get("agent_id"):
            agent_id = int(profile["agent_id"])
            # Cache so subsequent calls in this session are instant
            if context is not None:
                context.user_data["agent_id"] = agent_id
            return agent_id
    except Exception as e:
        logger.debug("by-chat-id lookup failed: %s", e)

    return None


def _category_label(state: dict, key: str) -> str:
    for c in state.get("_categories", []):
        if c["key"] == key:
            return c["label"]
    return key


def _subcategory_label(state: dict, cat_key: str, sub_key: str) -> str:
    for c in state.get("_categories", []):
        if c["key"] == cat_key:
            for s in c["subcategories"]:
                if s["key"] == sub_key:
                    return s["label"]
    return sub_key


def _format_summary(state: dict) -> str:
    """Pretty summary shown before submit."""
    cat = state.get("category")
    sub = state.get("subcategory")
    other = state.get("other_text", "")
    initial = state.get("initial_text", "")
    has_voice = bool(state.get("voice_file_id"))
    has_attach = bool(state.get("attachment_file_id"))

    lines = ["<b>📋 Review your concern</b>", ""]
    lines.append(f"<b>Category:</b> {_category_label(state, cat) if cat else '—'}")
    if sub:
        lines.append(f"<b>Subcategory:</b> {_subcategory_label(state, cat, sub)}")
    if other:
        lines.append(f"<b>Details:</b> {other}")
    if initial:
        lines.append(f"<b>Your message:</b>\n{initial}")
    if has_voice:
        lines.append("🎙 <i>Voice note attached</i>")
    if has_attach:
        lines.append(f"📎 <i>Document attached: {state.get('attachment_file_name', 'file')}</i>")
    lines.append("")
    lines.append(
        "🔒 <i>Goes only to the Agency Development team. Your ADM cannot see this.</i>"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SUBMIT FLOW
# ---------------------------------------------------------------------------

async def submit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: /concern command or 'agent_menu_concern' callback."""
    if update.callback_query:
        await update.callback_query.answer()
        send = update.callback_query.edit_message_text
    else:
        send = update.message.reply_text

    agent_id = await _resolve_agent_id(update, context)
    if not agent_id:
        await send(
            "⚠️ <b>Please register first.</b>\n\n"
            "Use /start to link your phone number, then try again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # Fetch category tree (cached on context.user_data)
    try:
        cats = await api_client.get_people_feedback_categories()
    except Exception as e:
        logger.error("Could not fetch categories: %s", e)
        await send(
            "⚠️ Couldn't reach server. Please try again in a moment.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    if isinstance(cats, dict) and cats.get("error"):
        await send("⚠️ Service unavailable. Please try again shortly.", parse_mode="HTML")
        return ConversationHandler.END

    categories_list = cats.get("categories", [])
    context.user_data["pf"] = {
        "agent_id": agent_id,
        "_categories": categories_list,
        "category": None,
        "subcategory": None,
        "other_text": None,
        "initial_text": None,
        "voice_file_id": None,
        "attachment_file_id": None,
        "attachment_file_name": None,
        "attachment_mime_type": None,
    }

    await send(
        "<b>🛡 Report a concern about your ADM</b>\n\n"
        "🔒 Your feedback goes only to the <b>Agency Development team</b>. "
        "Your ADM does <b>not</b> see this.\n\n"
        "Pick a category below:",
        parse_mode="HTML",
        reply_markup=people_feedback_category_keyboard(categories_list),
    )
    return AgentPeopleFeedbackStates.PICK_CATEGORY


async def on_pick_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped a category button."""
    query = update.callback_query
    await query.answer()

    cat_key = query.data.replace("pfcat_", "", 1)
    state = context.user_data.get("pf", {})
    state["category"] = cat_key
    state["subcategory"] = None

    # "other" category has no sub-cats → go straight to free text
    if cat_key == "other":
        await query.edit_message_text(
            "<b>📝 Describe your concern</b>\n\n"
            "Please type a short description of the issue.",
            parse_mode="HTML",
        )
        return AgentPeopleFeedbackStates.ENTER_OTHER_TEXT

    # Find sub-cats and render keyboard
    subs = []
    for c in state.get("_categories", []):
        if c["key"] == cat_key:
            subs = c["subcategories"]
            break

    await query.edit_message_text(
        f"<b>{_category_label(state, cat_key)}</b>\n\nWhat specifically happened?",
        parse_mode="HTML",
        reply_markup=people_feedback_subcategory_keyboard(cat_key, subs),
    )
    return AgentPeopleFeedbackStates.PICK_SUBCATEGORY


async def on_back_to_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sub-screen 'Back' → return to category list."""
    query = update.callback_query
    await query.answer()
    state = context.user_data.get("pf", {})
    await query.edit_message_text(
        "<b>🛡 Report a concern about your ADM</b>\n\nPick a category below:",
        parse_mode="HTML",
        reply_markup=people_feedback_category_keyboard(state.get("_categories", [])),
    )
    return AgentPeopleFeedbackStates.PICK_CATEGORY


async def on_pick_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped a sub-category button."""
    query = update.callback_query
    await query.answer()

    sub_key = query.data.replace("pfsub_", "", 1)
    state = context.user_data.get("pf", {})
    state["subcategory"] = sub_key

    if sub_key == "other":
        await query.edit_message_text(
            "<b>📝 Please specify</b>\n\nType a short description of what happened.",
            parse_mode="HTML",
        )
        return AgentPeopleFeedbackStates.ENTER_OTHER_TEXT

    # Move on to optional details
    return await _prompt_add_details(query.edit_message_text, state)


async def on_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Free-text input for 'Other' branches."""
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Please type at least a few words.")
        return AgentPeopleFeedbackStates.ENTER_OTHER_TEXT

    state = context.user_data.get("pf", {})
    state["other_text"] = text[:2000]
    return await _prompt_add_details(update.message.reply_text, state)


async def _prompt_add_details(send_fn, state: dict) -> int:
    """Prompt for optional text / voice / document, with a Submit Now button."""
    await send_fn(
        f"{_format_summary(state)}\n\n"
        "👉 You can optionally <b>type a message</b>, <b>send a voice note</b>, "
        "or <b>attach a document</b>. When ready, tap <b>Submit Now</b>.",
        parse_mode="HTML",
        reply_markup=people_feedback_add_details_keyboard(),
    )
    return AgentPeopleFeedbackStates.ADD_DETAILS


async def on_details_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture the free-text body."""
    text = (update.message.text or "").strip()
    if not text:
        return AgentPeopleFeedbackStates.ADD_DETAILS
    state = context.user_data.get("pf", {})
    state["initial_text"] = text[:4000]
    await update.message.reply_text(
        "✅ Got it.\n\n" + _format_summary(state),
        parse_mode="HTML",
        reply_markup=people_feedback_add_details_keyboard(),
    )
    return AgentPeopleFeedbackStates.ADD_DETAILS


async def on_details_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture a voice note (Telegram file_id)."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return AgentPeopleFeedbackStates.ADD_DETAILS
    state = context.user_data.get("pf", {})
    state["voice_file_id"] = voice.file_id
    await update.message.reply_text(
        "🎙 Voice note attached.\n\n" + _format_summary(state),
        parse_mode="HTML",
        reply_markup=people_feedback_add_details_keyboard(),
    )
    return AgentPeopleFeedbackStates.ADD_DETAILS


async def on_details_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture a document attachment."""
    doc = update.message.document
    if not doc:
        return AgentPeopleFeedbackStates.ADD_DETAILS
    state = context.user_data.get("pf", {})
    state["attachment_file_id"] = doc.file_id
    state["attachment_file_name"] = doc.file_name or "document"
    state["attachment_mime_type"] = doc.mime_type or "application/octet-stream"
    await update.message.reply_text(
        f"📎 Document attached: {state['attachment_file_name']}\n\n" + _format_summary(state),
        parse_mode="HTML",
        reply_markup=people_feedback_add_details_keyboard(),
    )
    return AgentPeopleFeedbackStates.ADD_DETAILS


async def on_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Final submission → POST to backend."""
    query = update.callback_query
    await query.answer()
    state = context.user_data.get("pf", {})

    # Sanity: have at least a category and (sub or other text or initial text)
    if not state.get("category"):
        await query.edit_message_text("Session expired. Please /concern to start again.")
        return ConversationHandler.END

    try:
        result = await api_client.submit_people_feedback(
            agent_id=state["agent_id"],
            category=state["category"],
            subcategory=state.get("subcategory"),
            other_text=state.get("other_text"),
            initial_text=state.get("initial_text"),
            voice_file_id=state.get("voice_file_id"),
            attachment_file_id=state.get("attachment_file_id"),
            attachment_file_name=state.get("attachment_file_name"),
            attachment_mime_type=state.get("attachment_mime_type"),
        )
    except Exception as e:
        logger.error("submit failed: %s", e)
        await query.edit_message_text(
            "⚠️ Something went wrong submitting. Please try again in a moment.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    if isinstance(result, dict) and result.get("ok"):
        ref = result.get("ticket_ref", "?")
        await query.edit_message_text(
            f"✅ <b>Submitted as {ref}</b>\n\n"
            f"The Agency Development team will respond within <b>3 days</b>.\n"
            f"Use /my_concerns to check status anytime.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 My Concerns", callback_data="agent_menu_my_concerns")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="agent_menu_home")],
            ]),
        )
    else:
        await query.edit_message_text(
            "⚠️ Submission failed. Please try again.",
            parse_mode="HTML",
        )

    context.user_data.pop("pf", None)
    return ConversationHandler.END


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User tapped Cancel anywhere in the submit flow."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "Cancelled. Use /concern anytime to report a concern.",
            reply_markup=main_menu_keyboard(),
        )
    context.user_data.pop("pf", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# MY CONCERNS — list + detail + reply
# ---------------------------------------------------------------------------

STATUS_BADGE = {
    "new": "🟡 New",
    "reviewed": "🔵 Reviewed",
    "in_progress": "🟣 In progress",
    "action_taken": "🟢 Action taken",
    "closed": "⚫ Closed",
    "escalated": "🔴 Escalated",
}


async def my_concerns_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List the agent's own concerns."""
    if update.callback_query:
        await update.callback_query.answer()
        send = update.callback_query.edit_message_text
    else:
        send = update.message.reply_text

    agent_id = await _resolve_agent_id(update, context)
    if not agent_id:
        await send(
            "⚠️ Please register first via /start.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        resp = await api_client.list_my_people_feedback(agent_id)
    except Exception as e:
        logger.error("list failed: %s", e)
        await send("⚠️ Couldn't load your concerns.", parse_mode="HTML")
        return ConversationHandler.END

    tickets = resp.get("tickets", []) if isinstance(resp, dict) else []
    if not tickets:
        await send(
            "📭 You haven't submitted any concerns yet.\n\n"
            "Use /concern if you'd like to report one.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    lines = ["<b>📋 Your concerns</b>", ""]
    for t in tickets[:10]:
        badge = STATUS_BADGE.get(t.get("status", "new"), t.get("status", ""))
        cat = t.get("category_label", "")
        sub = t.get("subcategory_label") or t.get("other_text", "") or ""
        lines.append(f"<b>{t['ticket_ref']}</b>  {badge}\n<i>{cat}{' · ' + sub if sub else ''}</i>")
        lines.append("")

    await send(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=my_concerns_list_keyboard(tickets),
    )
    # Stash for reply flow
    context.user_data["pf_agent_id"] = agent_id
    return AgentPeopleFeedbackStates.VIEW_MY_LIST


async def on_open_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Open one ticket's thread."""
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.replace("pfopen_", "", 1))
    agent_id = context.user_data.get("pf_agent_id") or await _resolve_agent_id(update, context)
    if not agent_id:
        await query.edit_message_text("Session expired. Use /my_concerns again.")
        return ConversationHandler.END
    context.user_data["pf_agent_id"] = agent_id
    context.user_data["pf_open_ticket_id"] = ticket_id

    try:
        detail = await api_client.get_my_people_feedback_detail(agent_id, ticket_id)
    except Exception as e:
        logger.error("detail failed: %s", e)
        await query.edit_message_text("⚠️ Couldn't load that concern.")
        return ConversationHandler.END

    lines = [
        f"<b>{detail.get('ticket_ref', '?')}</b>  {STATUS_BADGE.get(detail.get('status', 'new'), '')}",
        "",
        f"<b>{detail.get('category_label', '')}</b>"
        + (f" · {detail.get('subcategory_label')}" if detail.get('subcategory_label') else ''),
    ]
    if detail.get("other_text"):
        lines.append(f"<i>{detail['other_text']}</i>")
    if detail.get("initial_text"):
        lines.append("")
        lines.append(detail["initial_text"])
    if detail.get("has_voice"):
        lines.append("🎙 <i>Voice note attached</i>")
    if detail.get("has_attachment"):
        lines.append(f"📎 <i>{detail.get('attachment_file_name', 'document')}</i>")

    messages = detail.get("messages", []) or []
    if messages:
        lines.append("")
        lines.append("<b>🧵 Thread</b>")
        for m in messages:
            who = "You" if m.get("sender_role") == "agent" else "Agency Dev"
            txt = m.get("text") or ""
            if m.get("is_status_change"):
                lines.append(f"  ⚙ <i>{txt}</i>")
            else:
                attaches = []
                if m.get("has_voice"):
                    attaches.append("🎙")
                if m.get("has_attachment"):
                    attaches.append("📎")
                tag = " ".join(attaches)
                lines.append(f"  <b>{who}:</b> {txt} {tag}".strip())

    if detail.get("status") == "closed":
        lines.append("")
        lines.append("⚫ <i>This concern is closed.</i>")

    allow_reply = detail.get("status") != "closed"
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=my_concern_detail_keyboard(ticket_id, allow_reply),
    )
    return AgentPeopleFeedbackStates.VIEW_TICKET_DETAIL


async def on_reply_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Agent tapped Reply on a ticket."""
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.replace("pfreply_", "", 1))
    context.user_data["pf_open_ticket_id"] = ticket_id
    await query.message.reply_text(
        "✏️ Type your reply, send a voice note, or attach a document.\n"
        "Send /cancel to abort.",
    )
    return AgentPeopleFeedbackStates.REPLY_TO_TICKET


async def on_reply_payload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture the actual reply (text / voice / doc) and POST."""
    agent_id = context.user_data.get("pf_agent_id")
    ticket_id = context.user_data.get("pf_open_ticket_id")
    if not (agent_id and ticket_id):
        await update.message.reply_text("Session expired. Use /my_concerns again.")
        return ConversationHandler.END

    text = update.message.text
    voice = update.message.voice or update.message.audio
    doc = update.message.document

    if not (text or voice or doc):
        await update.message.reply_text("Please send text, a voice note, or a document.")
        return AgentPeopleFeedbackStates.REPLY_TO_TICKET

    try:
        await api_client.reply_to_my_people_feedback(
            agent_id=agent_id,
            ticket_id=ticket_id,
            text=text if text and not text.startswith("/") else None,
            voice_file_id=voice.file_id if voice else None,
            attachment_file_id=doc.file_id if doc else None,
            attachment_file_name=(doc.file_name if doc else None),
            attachment_mime_type=(doc.mime_type if doc else None),
        )
    except Exception as e:
        logger.error("reply failed: %s", e)
        await update.message.reply_text("⚠️ Failed to send. Please try again.")
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Reply sent.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"pfopen_{ticket_id}")],
            [InlineKeyboardButton("📋 My Concerns", callback_data="agent_menu_my_concerns")],
        ]),
    )
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Cancelled.", reply_markup=main_menu_keyboard())
    context.user_data.pop("pf", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------

# Submit flow conversation
submit_handler = ConversationHandler(
    entry_points=[
        CommandHandler("concern", submit_entry),
        CallbackQueryHandler(submit_entry, pattern=r"^agent_menu_concern$"),
    ],
    states={
        AgentPeopleFeedbackStates.PICK_CATEGORY: [
            CallbackQueryHandler(on_pick_category, pattern=r"^pfcat_"),
            CallbackQueryHandler(on_cancel, pattern=r"^pf_cancel$"),
        ],
        AgentPeopleFeedbackStates.PICK_SUBCATEGORY: [
            CallbackQueryHandler(on_pick_subcategory, pattern=r"^pfsub_"),
            CallbackQueryHandler(on_back_to_category, pattern=r"^pf_back_cat$"),
            CallbackQueryHandler(on_cancel, pattern=r"^pf_cancel$"),
        ],
        AgentPeopleFeedbackStates.ENTER_OTHER_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, on_other_text),
        ],
        AgentPeopleFeedbackStates.ADD_DETAILS: [
            CallbackQueryHandler(on_submit, pattern=r"^pf_submit$"),
            CallbackQueryHandler(on_cancel, pattern=r"^pf_cancel$"),
            MessageHandler(filters.VOICE | filters.AUDIO, on_details_voice),
            MessageHandler(filters.Document.ALL, on_details_document),
            MessageHandler(filters.TEXT & ~filters.COMMAND, on_details_text),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_command)],
    name="people_feedback_submit",
    persistent=False,
    per_message=False,
)


# My-concerns flow conversation
my_concerns_handler = ConversationHandler(
    entry_points=[
        CommandHandler("my_concerns", my_concerns_entry),
        CallbackQueryHandler(my_concerns_entry, pattern=r"^agent_menu_my_concerns$"),
    ],
    states={
        AgentPeopleFeedbackStates.VIEW_MY_LIST: [
            CallbackQueryHandler(on_open_ticket, pattern=r"^pfopen_\d+$"),
        ],
        AgentPeopleFeedbackStates.VIEW_TICKET_DETAIL: [
            CallbackQueryHandler(on_reply_prompt, pattern=r"^pfreply_\d+$"),
            CallbackQueryHandler(on_open_ticket, pattern=r"^pfopen_\d+$"),
            CallbackQueryHandler(my_concerns_entry, pattern=r"^agent_menu_my_concerns$"),
        ],
        AgentPeopleFeedbackStates.REPLY_TO_TICKET: [
            MessageHandler(
                (filters.TEXT | filters.VOICE | filters.AUDIO | filters.Document.ALL)
                & ~filters.COMMAND,
                on_reply_payload,
            ),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_command)],
    name="people_feedback_my_concerns",
    persistent=False,
    per_message=False,
)
