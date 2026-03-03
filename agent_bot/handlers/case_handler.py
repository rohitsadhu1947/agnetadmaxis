"""
Case (ticket) handler for the Agent Telegram Bot.

Allows agents to:
1. /cases or "agent_menu_cases" callback -> See open tickets
2. Select a ticket -> See detail with conversation thread
3. Reply inline -> Message goes to ticket thread
4. Refresh -> Re-fetch and redisplay
"""

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

from agent_bot.config import config, AgentCaseStates
from agent_bot.utils.api_client import api_client
from agent_bot.utils.formatters import (
    format_ticket_list,
    format_ticket_detail,
    EMOJI_CHECK,
    EMOJI_CROSS,
    EMOJI_WARN,
    EMOJI_MEMO,
    EMOJI_TICKET,
    EMOJI_PERSON,
    EMOJI_HOME,
    STATUS_DISPLAY,
    BUCKET_DISPLAY,
    BUCKET_EMOJIS,
)
from agent_bot.utils.keyboards import (
    ticket_list_keyboard,
    ticket_action_keyboard,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry: /cases or agent_menu_cases callback
# ---------------------------------------------------------------------------

async def cases_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the cases flow — fetch and show agent's tickets."""
    agent_id = context.user_data.get("agent_id")
    if not agent_id:
        text = (
            f"{EMOJI_WARN} <b>Not Registered</b>\n\n"
            f"You need to register first. Use /start.\n"
            f"Pehle /start se register karein."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        return ConversationHandler.END

    agent_name = context.user_data.get("agent_name", "Agent")

    # Initialize case session
    context.user_data["acase"] = {
        "agent_id": agent_id,
        "agent_name": agent_name,
    }

    # Fetch tickets
    tickets_resp = await api_client.get_agent_tickets(agent_id=int(agent_id))
    tickets = tickets_resp.get("tickets", []) if isinstance(tickets_resp, dict) else []

    if tickets_resp.get("error"):
        text = (
            f"{EMOJI_WARN} <b>Could not load tickets</b>\n\n"
            f"Please try again later.\n"
            f"<i>Error: {tickets_resp.get('detail', 'Unknown error')}</i>"
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        else:
            await update.message.reply_text(text, parse_mode="HTML")
        context.user_data.pop("acase", None)
        return ConversationHandler.END

    if not tickets:
        text = (
            f"{EMOJI_TICKET} <b>Your Tickets</b>\n\n"
            f"{EMOJI_CHECK} You have no open tickets.\n"
            f"Aapka koi open ticket nahi hai.\n\n"
            f"Use /feedback to submit a new issue."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=main_menu_keyboard(),
            )
        else:
            await update.message.reply_text(
                text, parse_mode="HTML", reply_markup=main_menu_keyboard(),
            )
        context.user_data.pop("acase", None)
        return ConversationHandler.END

    context.user_data["acase"]["tickets_cache"] = tickets

    # Show ticket list
    text = (
        f"{EMOJI_TICKET} <b>Your Tickets ({len(tickets)})</b>\n\n"
        f"Tap a ticket to view details:\n"
        f"Ticket tap karein details dekhne ke liye:"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=ticket_list_keyboard(tickets),
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=ticket_list_keyboard(tickets),
        )
    return AgentCaseStates.VIEW_CASES


# ---------------------------------------------------------------------------
# Step 1: Select ticket -> show detail
# ---------------------------------------------------------------------------

async def select_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ticket selection — fetch and show detail."""
    query = update.callback_query
    await query.answer()
    data = query.data

    ticket_id = data.replace("atkt_", "")
    acase = context.user_data.get("acase", {})
    acase["current_ticket_id"] = ticket_id

    return await _render_ticket_detail(query, context, ticket_id)


async def _render_ticket_detail(query_or_msg, context, ticket_id: str, is_message=False) -> int:
    """Render ticket detail with conversation thread."""
    # Fetch ticket detail from API
    ticket = await api_client.get_ticket_detail(ticket_id)

    if ticket.get("error"):
        text = f"{EMOJI_WARN} Could not load ticket {ticket_id}."
        if is_message:
            await query_or_msg.reply_text(text, parse_mode="HTML")
        else:
            await query_or_msg.edit_message_text(text, parse_mode="HTML")
        return ConversationHandler.END

    detail_text = format_ticket_detail(ticket)

    # Truncate if too long for Telegram
    if len(detail_text) > 4000:
        detail_text = detail_text[:3997] + "..."

    if is_message:
        await query_or_msg.reply_text(
            detail_text,
            parse_mode="HTML",
            reply_markup=ticket_action_keyboard(ticket_id),
        )
    else:
        await query_or_msg.edit_message_text(
            detail_text,
            parse_mode="HTML",
            reply_markup=ticket_action_keyboard(ticket_id),
        )

    # Send voice notes as playable audio messages
    messages = ticket.get("messages", [])
    voice_messages = [m for m in messages if m.get("voice_file_id")]
    if voice_messages:
        # Determine chat — for callback queries use the message's chat,
        # for message replies use the message's chat
        try:
            if is_message:
                chat = query_or_msg.chat
            else:
                chat = query_or_msg.message.chat if hasattr(query_or_msg, "message") else None

            if chat:
                for vm in voice_messages[-3:]:  # Last 3 voice notes max
                    sender = vm.get("sender_name", vm.get("sender_type", "Unknown"))
                    ts = vm.get("created_at", "")[:16]
                    caption = f"\U0001f3a4 Voice from <b>{sender}</b> ({ts})"
                    try:
                        await chat.send_voice(
                            voice=vm["voice_file_id"],
                            caption=caption,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning("Could not send voice note %s: %s", vm.get("id"), e)
        except Exception as e:
            logger.warning("Voice playback skipped: %s", e)

    return AgentCaseStates.VIEW_CASE_DETAIL


# ---------------------------------------------------------------------------
# Step 2: Ticket detail actions (reply, refresh, back)
# ---------------------------------------------------------------------------

async def ticket_detail_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle actions from ticket detail view."""
    query = update.callback_query
    await query.answer()
    data = query.data

    acase = context.user_data.get("acase", {})

    # Reply to ticket
    if data.startswith("atreply_"):
        ticket_id = data.replace("atreply_", "")
        acase["current_ticket_id"] = ticket_id
        await query.edit_message_text(
            f"{EMOJI_MEMO} <b>Reply to Ticket {ticket_id}</b>\n\n"
            f"Type your message or send a voice note:\n"
            f"Apna message likhein ya voice note bhejein:",
            parse_mode="HTML",
        )
        return AgentCaseStates.REPLY_TO_CASE

    # Refresh ticket
    if data.startswith("atrefresh_"):
        ticket_id = data.replace("atrefresh_", "")
        return await _render_ticket_detail(query, context, ticket_id)

    # Back to cases list
    if data == "agent_menu_cases":
        agent_id = acase.get("agent_id")
        if not agent_id:
            context.user_data.pop("acase", None)
            return ConversationHandler.END

        tickets_resp = await api_client.get_agent_tickets(agent_id=int(agent_id))
        tickets = tickets_resp.get("tickets", []) if isinstance(tickets_resp, dict) else []

        if not tickets:
            await query.edit_message_text(
                f"{EMOJI_CHECK} No open tickets.\n"
                f"Koi open ticket nahi hai.",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            context.user_data.pop("acase", None)
            return ConversationHandler.END

        acase["tickets_cache"] = tickets
        await query.edit_message_text(
            f"{EMOJI_TICKET} <b>Your Tickets ({len(tickets)})</b>\n\n"
            f"Tap a ticket to view:",
            parse_mode="HTML",
            reply_markup=ticket_list_keyboard(tickets),
        )
        return AgentCaseStates.VIEW_CASES

    return AgentCaseStates.VIEW_CASE_DETAIL


# ---------------------------------------------------------------------------
# Step 3: Receive reply
# ---------------------------------------------------------------------------

async def receive_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive agent's text reply and send to ticket thread."""
    acase = context.user_data.get("acase", {})
    ticket_id = acase.get("current_ticket_id")
    agent_name = acase.get("agent_name", "Agent")

    if not ticket_id:
        await update.message.reply_text(
            f"{EMOJI_WARN} Session expired. Use /cases to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    message_text = update.message.text.strip()
    if not message_text:
        await update.message.reply_text(
            "Please type a message.",
            parse_mode="HTML",
        )
        return AgentCaseStates.REPLY_TO_CASE

    result = await api_client.reply_to_ticket(
        ticket_id=ticket_id,
        sender_name=agent_name,
        message_text=message_text,
        sender_type="agent",
        message_type="text",
    )

    if result.get("error"):
        await update.message.reply_text(
            f"{EMOJI_WARN} Could not send message. Try again or /cancel.",
            parse_mode="HTML",
        )
        return AgentCaseStates.REPLY_TO_CASE

    await update.message.reply_text(
        f"{EMOJI_CHECK} <b>Message sent!</b>\n\n"
        f"Your reply has been added to ticket {ticket_id}.\n"
        f"Loading updated ticket...",
        parse_mode="HTML",
    )

    return await _render_ticket_detail(update.message, context, ticket_id, is_message=True)


async def receive_reply_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive agent's voice reply."""
    acase = context.user_data.get("acase", {})
    ticket_id = acase.get("current_ticket_id")
    agent_name = acase.get("agent_name", "Agent")

    if not ticket_id:
        await update.message.reply_text(
            f"{EMOJI_WARN} Session expired. Use /cases to start again.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    try:
        voice = update.message.voice
        if not voice or not voice.file_id:
            await update.message.reply_text(
                f"{EMOJI_WARN} Voice note could not be read. Please type your reply.",
                parse_mode="HTML",
            )
            return AgentCaseStates.REPLY_TO_CASE

        message_text = f"[Voice note: {voice.duration}s]"
        result = await api_client.reply_to_ticket(
            ticket_id=ticket_id,
            sender_name=agent_name,
            message_text=message_text,
            sender_type="agent",
            message_type="voice",
            voice_file_id=voice.file_id,
        )

        if result.get("error"):
            await update.message.reply_text(
                f"{EMOJI_WARN} Could not send voice note. Try again.",
                parse_mode="HTML",
            )
            return AgentCaseStates.REPLY_TO_CASE

        await update.message.reply_text(
            f"{EMOJI_CHECK} <b>Voice note sent!</b> ({voice.duration}s)\n"
            f"Loading updated ticket...",
            parse_mode="HTML",
        )
        return await _render_ticket_detail(update.message, context, ticket_id, is_message=True)

    except Exception as e:
        logger.error("Voice reply error: %s", e)
        await update.message.reply_text(
            f"{EMOJI_WARN} Error sending voice note. Please type your reply.",
            parse_mode="HTML",
        )
        return AgentCaseStates.REPLY_TO_CASE


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_cases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the cases flow."""
    context.user_data.pop("acase", None)
    text = f"{EMOJI_CROSS} Cases closed."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Build ConversationHandler
# ---------------------------------------------------------------------------

def _all_callbacks():
    """Create handler instances for all callback patterns in this flow."""
    return [
        CallbackQueryHandler(select_ticket, pattern=r"^atkt_"),
        CallbackQueryHandler(ticket_detail_action, pattern=r"^(atreply_|atrefresh_|agent_menu_cases)"),
        CallbackQueryHandler(cancel_cases, pattern=r"^agent_cancel$"),
    ]


handler = ConversationHandler(
    entry_points=[
        CommandHandler("cases", cases_command),
        CallbackQueryHandler(cases_command, pattern=r"^agent_menu_cases$"),
    ],
    states={
        AgentCaseStates.VIEW_CASES: _all_callbacks(),
        AgentCaseStates.VIEW_CASE_DETAIL: _all_callbacks(),
        AgentCaseStates.REPLY_TO_CASE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reply_text),
            MessageHandler(filters.VOICE, receive_reply_voice),
            *_all_callbacks(),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_cases),
        CommandHandler("cases", cases_command),
        CallbackQueryHandler(cancel_cases, pattern=r"^agent_cancel$"),
    ],
    name="agent_cases",
    persistent=False,
    per_user=True,
    per_chat=True,
    allow_reentry=True,
    conversation_timeout=600,
)
