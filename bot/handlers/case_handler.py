"""
Case History handler for the ADM Platform Telegram Bot.

Allows ADMs to:
1. /cases → Select agent → See open cases for that agent
2. Select a case → See conversation thread (ADM, department, AI messages)
3. Reply inline → Message goes back to department
4. Close ticket from conversation view
"""

import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import CaseStates
from utils.api_client import api_client
from utils.keyboards import agent_list_keyboard
from utils.voice import send_voice_response

logger = logging.getLogger(__name__)

# Emojis
E_FOLDER = "\U0001F4C1"
E_PERSON = "\U0001F464"
E_CHAT = "\U0001F4AC"
E_MEMO = "\U0001F4DD"
E_CHECK = "\u2705"
E_CROSS = "\u274C"
E_WARNING = "\u26A0\uFE0F"
E_CLOCK = "\U0001F552"
E_ARROW = "\u27A1\uFE0F"
E_STAR = "\u2B50"

STATUS_EMOJI = {
    "received": "\U0001F4E5",
    "classified": "\U0001F50D",
    "routed": "\U0001F4E4",
    "pending_dept": "\U0001F552",
    "pending_adm": "\U0001F4AC",
    "responded": "\U0001F4AC",
    "script_generated": "\U0001F4DD",
    "script_sent": E_CHECK,
    "closed": "\U0001F512",
}

STATUS_LABEL = {
    "received": "Received",
    "classified": "Classified",
    "routed": "Routed to Dept",
    "pending_dept": "Waiting on Department",
    "pending_adm": "Action Needed by You",
    "responded": "Department Responded",
    "script_generated": "Script Ready",
    "script_sent": "Script Sent",
    "closed": "Closed",
}


# ---------------------------------------------------------------------------
# Entry: /cases
# ---------------------------------------------------------------------------

async def cases_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start case history flow — show agent list."""
    telegram_id = update.effective_user.id

    profile = await api_client.get_adm_profile(telegram_id)
    if profile.get("error") or not profile.get("id", profile.get("adm_id")):
        await update.message.reply_text(
            f"{E_WARNING} <b>Profile Not Found</b>\n\n"
            "Register first with /start.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    adm_id = profile.get("id", profile.get("adm_id"))
    adm_name = profile.get("name", "ADM")

    context.user_data["cases"] = {
        "adm_id": adm_id,
        "adm_name": adm_name,
        "adm_telegram_id": telegram_id,
    }

    agents_resp = await api_client.get_assigned_agents(telegram_id)
    agents = agents_resp.get("agents", agents_resp.get("data", []))

    if not agents or agents_resp.get("error"):
        await update.message.reply_text(
            f"{E_CROSS} <b>No agents found</b>\n\n"
            "No agents assigned to you yet.",
            parse_mode="HTML",
        )
        context.user_data.pop("cases", None)
        return ConversationHandler.END

    context.user_data["cases"]["agents_cache"] = agents
    total_pages = agents_resp.get("total_pages", 1)

    await update.message.reply_text(
        f"{E_FOLDER} <b>Case History</b>\n\n"
        f"Select an agent to view their cases:\n"
        f"Agent chunein unke cases dekhne ke liye:",
        parse_mode="HTML",
        reply_markup=agent_list_keyboard(agents, callback_prefix="caseagent", total_pages=total_pages),
    )
    return CaseStates.SELECT_AGENT


# ---------------------------------------------------------------------------
# Step 1: Agent selection → show their open cases
# ---------------------------------------------------------------------------

async def select_agent_for_cases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle agent selection — fetch and show open cases for this agent."""
    query = update.callback_query
    await query.answer()
    data = query.data

    cases_data = context.user_data.get("cases", {})

    # Search
    if data == "caseagent_search":
        await query.edit_message_text(
            "\U0001F50D <b>Search Agent</b>\n\nType the agent's name:",
            parse_mode="HTML",
        )
        return CaseStates.SELECT_AGENT

    # Pagination
    if data.startswith("caseagent_page_"):
        page = int(data.split("_")[-1])
        telegram_id = cases_data.get("adm_telegram_id")
        agents_resp = await api_client.get_assigned_agents(telegram_id, page=page)
        agents = agents_resp.get("agents", agents_resp.get("data", []))
        if not agents:
            await query.edit_message_text(f"{E_WARNING} Could not load agents.", parse_mode="HTML")
            return ConversationHandler.END
        cases_data["agents_cache"] = agents
        total_pages = agents_resp.get("total_pages", 1)
        await query.edit_message_text(
            f"{E_FOLDER} <b>Case History</b>\n\nSelect agent:",
            parse_mode="HTML",
            reply_markup=agent_list_keyboard(agents, callback_prefix="caseagent", page=page, total_pages=total_pages),
        )
        return CaseStates.SELECT_AGENT

    # Agent selected
    agent_id = data.replace("caseagent_", "")
    agents = cases_data.get("agents_cache", [])
    agent_name = "Agent"
    for a in agents:
        if str(a.get("id", a.get("agent_code", ""))) == agent_id:
            agent_name = a.get("name", "Agent")
            break

    cases_data["selected_agent_id"] = int(agent_id)
    cases_data["selected_agent_name"] = agent_name

    # Fetch tickets for this agent
    adm_id = cases_data.get("adm_id")
    tickets_resp = await api_client.get_agent_tickets(adm_id, int(agent_id))
    tickets = tickets_resp.get("tickets", []) if isinstance(tickets_resp, dict) else []

    if not tickets:
        await query.edit_message_text(
            f"{E_PERSON} <b>{agent_name}</b>\n\n"
            f"{E_CHECK} No open cases for this agent.\n"
            f"Koi open case nahi hai.\n\n"
            f"Use /feedback to create a new case.",
            parse_mode="HTML",
        )
        context.user_data.pop("cases", None)
        return ConversationHandler.END

    # Show list of cases
    cases_data["tickets_cache"] = tickets
    buttons = []
    for t in tickets[:10]:
        emoji = STATUS_EMOJI.get(t.get("status", ""), "\U0001F4CB")
        label = STATUS_LABEL.get(t.get("status", ""), t.get("status", ""))
        reason = t.get("reason_display") or t.get("reason_code") or "General"
        btn_text = f"{emoji} {t['ticket_id']} | {reason} | {label}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"viewcase_{t['ticket_id']}")])

    buttons.append([InlineKeyboardButton(f"{E_CROSS} Cancel", callback_data="cancel")])

    await query.edit_message_text(
        f"{E_PERSON} <b>{agent_name}</b> \u2014 {len(tickets)} case(s)\n\n"
        f"Tap a case to view details and conversation:\n"
        f"Case tap karein details dekhne ke liye:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return CaseStates.VIEW_CASES


async def search_agent_for_cases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text search for agents in /cases."""
    search_text = update.message.text.strip().lower()
    agents = context.user_data.get("cases", {}).get("agents_cache", [])

    matches = [a for a in agents if search_text in a.get("name", "").lower()]

    if not matches:
        await update.message.reply_text(
            f"{E_WARNING} No agents found matching '{search_text}'. Try again or /cancel.",
            parse_mode="HTML",
        )
        return CaseStates.SELECT_AGENT

    await update.message.reply_text(
        f"\U0001F50D Found {len(matches)} agent(s):",
        parse_mode="HTML",
        reply_markup=agent_list_keyboard(matches, callback_prefix="caseagent"),
    )
    return CaseStates.SELECT_AGENT


# ---------------------------------------------------------------------------
# Step 2: View case detail → show conversation thread
# ---------------------------------------------------------------------------

async def view_case_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show detailed case with conversation thread."""
    query = update.callback_query
    await query.answer()
    data = query.data

    ticket_id = data.replace("viewcase_", "")
    cases_data = context.user_data.get("cases", {})
    cases_data["current_ticket_id"] = ticket_id

    return await _render_case_detail(query, context, ticket_id)


async def _render_case_detail(query_or_msg, context, ticket_id: str, is_message=False) -> int:
    """Render case detail with conversation thread."""
    cases_data = context.user_data.get("cases", {})
    agent_name = cases_data.get("selected_agent_name", "Agent")

    # Get ticket info
    ticket = await api_client.get_ticket_by_id(ticket_id)
    if ticket.get("error"):
        text = f"{E_WARNING} Could not load case {ticket_id}."
        if is_message:
            await query_or_msg.reply_text(text, parse_mode="HTML")
        else:
            await query_or_msg.edit_message_text(text, parse_mode="HTML")
        return ConversationHandler.END

    # Get messages
    msgs_resp = await api_client.get_ticket_messages(ticket_id)
    messages = msgs_resp.get("messages", []) if isinstance(msgs_resp, dict) else []

    status = ticket.get("status", "unknown")
    emoji = STATUS_EMOJI.get(status, "\U0001F4CB")
    label = STATUS_LABEL.get(status, status)
    reason = ticket.get("reason_display") or ticket.get("reason_code") or "General"
    bucket = ticket.get("bucket_display") or ticket.get("bucket") or "—"

    # Build header
    text = (
        f"{E_FOLDER} <b>Case {ticket_id}</b>\n"
        f"{'=' * 28}\n"
        f"{E_PERSON} <b>Agent:</b> {agent_name}\n"
        f"\U0001F3E2 <b>Dept:</b> {bucket}\n"
        f"\U0001F4CB <b>Reason:</b> {reason}\n"
        f"{emoji} <b>Status:</b> {label}\n"
        f"{'=' * 28}\n\n"
    )

    # Build conversation
    if messages:
        text += f"<b>Conversation ({len(messages)} messages):</b>\n\n"
        for msg in messages[-8:]:  # Show last 8 messages to fit in Telegram limit
            sender = msg.get("sender_type", "")
            name = msg.get("sender_name", sender)
            msg_text = msg.get("message_text", "")

            # Truncate long messages
            if len(msg_text) > 300:
                msg_text = msg_text[:297] + "..."

            if sender == "adm":
                icon = "\U0001F464"  # person
            elif sender == "department":
                icon = "\U0001F3E2"  # building
            elif sender == "ai":
                icon = "\U0001F916"  # robot
            else:
                icon = "\u2139\uFE0F"  # info

            # Attachment indicator
            msg_type = msg.get("message_type", "text")
            attach = ""
            if msg_type == "photo":
                attach = "\U0001F4F7 "
            elif msg_type == "document":
                attach = "\U0001F4CE "
            elif msg_type == "voice":
                attach = "\U0001F3A4 "

            text += f"{icon} <b>{name}:</b>\n{attach}{msg_text}\n\n"
    else:
        # Fallback to denormalized fields
        if ticket.get("raw_feedback_text"):
            text += f"\U0001F464 <b>Your Feedback:</b>\n{ticket['raw_feedback_text']}\n\n"
        if ticket.get("department_response_text"):
            text += f"\U0001F3E2 <b>Department Response:</b>\n{ticket['department_response_text']}\n\n"
        if ticket.get("generated_script"):
            script = ticket["generated_script"]
            if len(script) > 400:
                script = script[:397] + "..."
            text += f"\U0001F916 <b>Communication Script:</b>\n{script}\n\n"

    # Action buttons
    buttons = []
    if status != "closed":
        buttons.append([InlineKeyboardButton(
            f"{E_CHAT} Reply to Department",
            callback_data=f"casereply_{ticket_id}",
        )])
        buttons.append([InlineKeyboardButton(
            f"\U0001F512 Close Case",
            callback_data=f"caseclose_{ticket_id}",
        )])
    buttons.append([InlineKeyboardButton(
        f"\U0001F504 Refresh",
        callback_data=f"caserefresh_{ticket_id}",
    )])
    buttons.append([InlineKeyboardButton(
        f"\u25C0 Back to Cases",
        callback_data="caseback",
    )])

    # Telegram message limit is ~4096 chars
    if len(text) > 4000:
        text = text[:3997] + "..."

    if is_message:
        await query_or_msg.reply_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        await query_or_msg.edit_message_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    return CaseStates.VIEW_CASE_DETAIL


# ---------------------------------------------------------------------------
# Step 3: Actions on case detail (reply, close, refresh, back)
# ---------------------------------------------------------------------------

async def case_detail_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle actions from case detail view."""
    query = update.callback_query
    await query.answer()
    data = query.data

    cases_data = context.user_data.get("cases", {})

    # Reply to department
    if data.startswith("casereply_"):
        ticket_id = data.replace("casereply_", "")
        cases_data["current_ticket_id"] = ticket_id
        await query.edit_message_text(
            f"{E_CHAT} <b>Reply to Department \u2014 {ticket_id}</b>\n\n"
            f"Type your message below.\n"
            f"Department ko jawaab likhein:\n\n"
            f"<i>(Your message will be sent to the department handling this case)</i>",
            parse_mode="HTML",
        )
        return CaseStates.REPLY_TO_CASE

    # Close case
    if data.startswith("caseclose_"):
        ticket_id = data.replace("caseclose_", "")
        result = await api_client.close_ticket(ticket_id)
        if result.get("status") == "ok":
            await query.edit_message_text(
                f"{E_CHECK} <b>Case {ticket_id} closed.</b>\n\n"
                f"Use /cases to view other open cases.",
                parse_mode="HTML",
            )
        else:
            await query.edit_message_text(
                f"{E_CROSS} Failed to close: {result.get('detail', 'Unknown error')}",
                parse_mode="HTML",
            )
        context.user_data.pop("cases", None)
        return ConversationHandler.END

    # Refresh
    if data.startswith("caserefresh_"):
        ticket_id = data.replace("caserefresh_", "")
        return await _render_case_detail(query, context, ticket_id)

    # Back to agent's cases
    if data == "caseback":
        agent_id = cases_data.get("selected_agent_id")
        agent_name = cases_data.get("selected_agent_name", "Agent")
        adm_id = cases_data.get("adm_id")

        if not agent_id:
            context.user_data.pop("cases", None)
            return ConversationHandler.END

        tickets_resp = await api_client.get_agent_tickets(adm_id, agent_id)
        tickets = tickets_resp.get("tickets", []) if isinstance(tickets_resp, dict) else []

        if not tickets:
            await query.edit_message_text(
                f"{E_CHECK} No more open cases for {agent_name}.",
                parse_mode="HTML",
            )
            context.user_data.pop("cases", None)
            return ConversationHandler.END

        cases_data["tickets_cache"] = tickets
        buttons = []
        for t in tickets[:10]:
            emoji = STATUS_EMOJI.get(t.get("status", ""), "\U0001F4CB")
            label = STATUS_LABEL.get(t.get("status", ""), t.get("status", ""))
            reason = t.get("reason_display") or t.get("reason_code") or "General"
            btn_text = f"{emoji} {t['ticket_id']} | {reason} | {label}"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"viewcase_{t['ticket_id']}")])

        buttons.append([InlineKeyboardButton(f"{E_CROSS} Cancel", callback_data="cancel")])

        await query.edit_message_text(
            f"{E_PERSON} <b>{agent_name}</b> \u2014 {len(tickets)} case(s)\n\n"
            f"Tap a case to view:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return CaseStates.VIEW_CASES

    return CaseStates.VIEW_CASE_DETAIL


# ---------------------------------------------------------------------------
# Step 4: Receive reply text → send as ADM message
# ---------------------------------------------------------------------------

async def receive_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive ADM's reply text and send it to the ticket thread."""
    cases_data = context.user_data.get("cases", {})
    ticket_id = cases_data.get("current_ticket_id")
    adm_name = cases_data.get("adm_name", "ADM")

    if not ticket_id:
        await update.message.reply_text(
            f"{E_WARNING} Session expired. Use /cases to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    message_text = update.message.text.strip()
    if not message_text:
        await update.message.reply_text("Please type a message.", parse_mode="HTML")
        return CaseStates.REPLY_TO_CASE

    # Send message to API
    result = await api_client.add_ticket_message(
        ticket_id=ticket_id,
        sender_type="adm",
        sender_name=adm_name,
        message_text=message_text,
        message_type="text",
    )

    if result.get("error"):
        await update.message.reply_text(
            f"{E_WARNING} Could not send message. Try again or /cancel.",
            parse_mode="HTML",
        )
        return CaseStates.REPLY_TO_CASE

    await update.message.reply_text(
        f"{E_CHECK} <b>Message sent!</b>\n\n"
        f"Your reply has been added to case {ticket_id}.\n"
        f"Department ko aapka message mil gaya.\n\n"
        f"Loading updated case...",
        parse_mode="HTML",
    )

    # Show updated case detail as a NEW message (since we can't edit the reply)
    # We must render it so the user can continue interacting
    return await _render_case_detail(update.message, context, ticket_id, is_message=True)


async def receive_reply_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive ADM's voice reply and send it to the ticket thread."""
    cases_data = context.user_data.get("cases", {})
    ticket_id = cases_data.get("current_ticket_id")
    adm_name = cases_data.get("adm_name", "ADM")

    if not ticket_id:
        await update.message.reply_text(
            f"{E_WARNING} Session expired. Use /cases to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        voice = update.message.voice
        if not voice or not voice.file_id:
            await update.message.reply_text(
                f"{E_WARNING} Voice note could not be read. Please type your reply instead.",
                parse_mode="HTML",
            )
            return CaseStates.REPLY_TO_CASE

        message_text = f"[Voice note: {voice.duration}s]"
        result = await api_client.add_ticket_message(
            ticket_id=ticket_id,
            sender_type="adm",
            sender_name=adm_name,
            message_text=message_text,
            message_type="voice",
        )

        if result.get("error"):
            await update.message.reply_text(
                f"{E_WARNING} Could not send voice note. Try again.",
                parse_mode="HTML",
            )
            return CaseStates.REPLY_TO_CASE

        await update.message.reply_text(
            f"{E_CHECK} <b>Voice note sent!</b> ({voice.duration}s)\n"
            f"Loading updated case...",
            parse_mode="HTML",
        )
        return await _render_case_detail(update.message, context, ticket_id, is_message=True)

    except Exception as e:
        logger.error(f"Voice reply error: {e}")
        await update.message.reply_text(
            f"{E_WARNING} Error sending voice note. Please type your reply instead.",
            parse_mode="HTML",
        )
        return CaseStates.REPLY_TO_CASE


async def receive_reply_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive ADM's photo reply (screenshot, document photo, etc.)."""
    cases_data = context.user_data.get("cases", {})
    ticket_id = cases_data.get("current_ticket_id")
    adm_name = cases_data.get("adm_name", "ADM")

    if not ticket_id:
        await update.message.reply_text(
            f"{E_WARNING} Session expired. Use /cases to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        photo = update.message.photo[-1] if update.message.photo else None
        if not photo:
            await update.message.reply_text(
                f"{E_WARNING} Photo could not be read. Please try again.",
                parse_mode="HTML",
            )
            return CaseStates.REPLY_TO_CASE

        caption = update.message.caption or ""
        message_text = f"[Photo attached] {caption}".strip()
        metadata = json.dumps({
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "width": photo.width,
            "height": photo.height,
            "type": "photo",
        })

        result = await api_client.add_ticket_message(
            ticket_id=ticket_id,
            sender_type="adm",
            sender_name=adm_name,
            message_text=message_text,
            message_type="photo",
            voice_file_id=photo.file_id,
            metadata_json=metadata,
        )

        if result.get("error"):
            await update.message.reply_text(
                f"{E_WARNING} Could not send photo. Try again.",
                parse_mode="HTML",
            )
            return CaseStates.REPLY_TO_CASE

        await update.message.reply_text(
            f"{E_CHECK} <b>Photo sent!</b>\n"
            f"Loading updated case...",
            parse_mode="HTML",
        )
        return await _render_case_detail(update.message, context, ticket_id, is_message=True)

    except Exception as e:
        logger.error(f"Photo reply error: {e}")
        await update.message.reply_text(
            f"{E_WARNING} Error sending photo. Please type your reply instead.",
            parse_mode="HTML",
        )
        return CaseStates.REPLY_TO_CASE


async def receive_reply_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive ADM's document reply (PDF, Excel, etc.)."""
    cases_data = context.user_data.get("cases", {})
    ticket_id = cases_data.get("current_ticket_id")
    adm_name = cases_data.get("adm_name", "ADM")

    if not ticket_id:
        await update.message.reply_text(
            f"{E_WARNING} Session expired. Use /cases to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        doc = update.message.document
        if not doc:
            await update.message.reply_text(
                f"{E_WARNING} Document could not be read. Please try again.",
                parse_mode="HTML",
            )
            return CaseStates.REPLY_TO_CASE

        caption = update.message.caption or ""
        file_name = doc.file_name or "document"
        message_text = f"[Document: {file_name}] {caption}".strip()
        metadata = json.dumps({
            "file_id": doc.file_id,
            "file_unique_id": doc.file_unique_id,
            "file_name": file_name,
            "mime_type": doc.mime_type,
            "file_size": doc.file_size,
            "type": "document",
        })

        result = await api_client.add_ticket_message(
            ticket_id=ticket_id,
            sender_type="adm",
            sender_name=adm_name,
            message_text=message_text,
            message_type="document",
            voice_file_id=doc.file_id,
            metadata_json=metadata,
        )

        if result.get("error"):
            await update.message.reply_text(
                f"{E_WARNING} Could not send document. Try again.",
                parse_mode="HTML",
            )
            return CaseStates.REPLY_TO_CASE

        await update.message.reply_text(
            f"{E_CHECK} <b>Document sent!</b> ({file_name})\n"
            f"Loading updated case...",
            parse_mode="HTML",
        )
        return await _render_case_detail(update.message, context, ticket_id, is_message=True)

    except Exception as e:
        logger.error(f"Document reply error: {e}")
        await update.message.reply_text(
            f"{E_WARNING} Error sending document. Please type your reply instead.",
            parse_mode="HTML",
        )
        return CaseStates.REPLY_TO_CASE


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_cases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the case history flow."""
    context.user_data.pop("cases", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            f"{E_CROSS} Case history closed. / Case history band.",
            parse_mode="HTML",
        )
    elif update.message:
        await update.message.reply_text(
            f"{E_CROSS} Case history closed.",
            parse_mode="HTML",
        )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Build conversation handler
# ---------------------------------------------------------------------------

def build_cases_handler() -> ConversationHandler:
    """Build the /cases conversation handler.

    IMPORTANT: Every state must handle ALL callback patterns that can appear
    from any active inline keyboard in the chat.  After a user replies via
    text, _render_case_detail sends a NEW message (can't edit the user's
    message), so the old message's buttons remain active.  If the user taps
    an old button whose pattern isn't registered in the current state, the
    ConversationHandler silently drops it → the flow appears stuck.

    Fix: register every callback pattern in every state so the handler can
    route the user to the correct step regardless of which button they tap.
    """

    def _all_callbacks():
        """Create fresh handler instances for all callback patterns."""
        return [
            CallbackQueryHandler(select_agent_for_cases, pattern=r"^caseagent_"),
            CallbackQueryHandler(view_case_detail, pattern=r"^viewcase_"),
            CallbackQueryHandler(case_detail_action, pattern=r"^case(reply|close|refresh|back)"),
            CallbackQueryHandler(cancel_cases, pattern=r"^cancel$"),
        ]

    return ConversationHandler(
        entry_points=[CommandHandler("cases", cases_command)],
        states={
            CaseStates.SELECT_AGENT: [
                *_all_callbacks(),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_agent_for_cases),
            ],
            CaseStates.VIEW_CASES: _all_callbacks(),
            CaseStates.VIEW_CASE_DETAIL: _all_callbacks(),
            CaseStates.REPLY_TO_CASE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reply_text),
                MessageHandler(filters.VOICE, receive_reply_voice),
                MessageHandler(filters.PHOTO, receive_reply_photo),
                MessageHandler(filters.Document.ALL, receive_reply_document),
                *_all_callbacks(),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_cases),
            CommandHandler("cases", cases_command),  # Allow re-entry
            CallbackQueryHandler(cancel_cases, pattern=r"^cancel$"),
        ],
        name="case_history",
        persistent=False,
        allow_reentry=True,
        conversation_timeout=600,  # 10 min — auto-expire stale flows after bot restart
    )
