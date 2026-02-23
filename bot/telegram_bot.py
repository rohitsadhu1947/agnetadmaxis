"""
ADM Platform Telegram Bot - Main Entry Point.
Registers all handlers and starts polling.

Usage:
    python telegram_bot.py

Environment variables:
    TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
    API_BASE_URL        - Backend API URL (default: http://localhost:8000/api/v1)
"""

import logging
import sys
import os

# Ensure the bot package directory is on the path so that absolute imports work
# regardless of the working directory the script is launched from.
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BOT_DIR, ".env"))
    # Also try parent directory .env
    load_dotenv(os.path.join(BOT_DIR, "..", ".env"))
except ImportError:
    pass

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from config import config
from utils.api_client import api_client
from utils.formatters import (
    error_generic,
    E_WARNING, E_CROSS, E_SPARKLE, E_PEOPLE,
    E_CHART, E_PHONE, E_CALENDAR, E_BOOK,
    E_BRAIN, E_MEMO, E_FIRE, E_CHAT, E_GEAR,
    E_CHECK, E_SHIELD, E_SUNRISE,
    format_agent_list,
)
from utils.keyboards import main_menu_keyboard, agent_list_keyboard
from utils.voice import voice_command, send_voice_response, is_voice_enabled

# Handler imports
from handlers.start_handler import build_start_handler, help_command
from handlers.feedback_handler import build_feedback_handler
from handlers.diary_handler import build_diary_handler
from handlers.interaction_handler import build_interaction_handler
from handlers.training_handler import build_training_handler
from handlers.briefing_handler import briefing_command, briefing_callback
from handlers.ask_handler import build_ask_handler
from handlers.stats_handler import stats_command, stats_callback
from handlers.case_handler import build_cases_handler


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    format=config.LOG_FORMAT,
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# /agents command (simple, non-conversation)
# ---------------------------------------------------------------------------

async def agents_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /agents command - list assigned agents."""
    telegram_id = update.effective_user.id

    agents_resp = await api_client.get_assigned_agents(telegram_id)

    if agents_resp.get("error"):
        # API error — distinguish from "no agents"
        detail = agents_resp.get("detail", "Connection error")
        if len(str(detail)) > 100:
            detail = str(detail)[:100] + "..."
        text = (
            f"{E_CROSS} <b>Could not load agents</b>\n\n"
            f"Server se connect nahi ho pa raha.\n"
            f"Please try again in a moment.\n\n"
            f"<i>Error: {detail}</i>"
        )
        sent_msg = await update.message.reply_text(text, parse_mode="HTML")
        await send_voice_response(sent_msg, text)
        return

    agents = agents_resp.get("agents", agents_resp.get("data", []))
    total_pages = agents_resp.get("total_pages", 1)

    if not agents:
        text = (
            f"{E_WARNING} <b>No agents found</b>\n\n"
            "You don't have any agents assigned yet.\n"
            "Ask your admin to assign agents to you, or add them via the web dashboard."
        )
        sent_msg = await update.message.reply_text(text, parse_mode="HTML")
    else:
        text = format_agent_list(agents, page=1, total_pages=total_pages)
        sent_msg = await update.message.reply_text(text, parse_mode="HTML")
    await send_voice_response(sent_msg, text)


# ---------------------------------------------------------------------------
# /tickets command - view open feedback tickets
# ---------------------------------------------------------------------------

async def tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show ADM's open feedback tickets."""
    telegram_id = str(update.effective_user.id)
    profile = await api_client.get_adm_profile(telegram_id)
    if not profile or profile.get("error"):
        status = profile.get("status", 0) if profile else 0
        if status == 404:
            await update.message.reply_text("❌ Profile not found. Use /start to register.")
        else:
            await update.message.reply_text(
                f"{E_WARNING} Could not connect to server. Please try again in a moment."
            )
        return

    adm_id = profile.get("id", profile.get("adm_id"))
    result = await api_client.get_adm_tickets(adm_id)
    tickets = result.get("tickets", []) if isinstance(result, dict) else []

    if not tickets:
        await update.message.reply_text("📋 No open tickets found.")
        return

    for t in tickets[:10]:
        status_emoji = {"routed": "📤", "responded": "💬", "script_generated": "📝", "script_sent": "✅"}.get(t.get("status", ""), "📋")
        text = (
            f"{status_emoji} *{t['ticket_id']}*\n"
            f"Agent: {t.get('agent_name', '—')}\n"
            f"Dept: {t.get('bucket_display', t.get('bucket', '—'))}\n"
            f"Status: {t.get('status', '—')}\n"
            f"Reason: {t.get('reason_code', '—')}"
        )
        buttons = []
        if t.get("status") in ("script_sent", "script_generated", "responded"):
            buttons.append([InlineKeyboardButton("✅ Close Ticket", callback_data=f"close_ticket:{t['ticket_id']}")])

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )


async def view_case_from_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'View Case' button press from Telegram notification."""
    query = update.callback_query
    await query.answer()

    ticket_id = query.data.split(":", 1)[1]

    # Fetch ticket details
    ticket = await api_client.get_ticket_by_id(ticket_id)
    if ticket.get("error"):
        await query.edit_message_text(f"{E_WARNING} Could not load case {ticket_id}. Use /cases to view your cases.")
        return

    msgs_resp = await api_client.get_ticket_messages(ticket_id)
    messages = msgs_resp.get("messages", []) if isinstance(msgs_resp, dict) else []

    agent_name = ticket.get("agent_name", "Agent")
    status = ticket.get("status", "")
    bucket = ticket.get("bucket_display") or ticket.get("bucket", "")
    reason = ticket.get("reason_display") or ticket.get("reason_code", "")

    text = (
        f"\U0001F4C1 <b>Case {ticket_id}</b>\n"
        f"{'=' * 28}\n"
        f"\U0001F464 <b>Agent:</b> {agent_name}\n"
        f"\U0001F3E2 <b>Dept:</b> {bucket}\n"
        f"\U0001F4CB <b>Reason:</b> {reason}\n"
        f"{'=' * 28}\n\n"
    )

    if messages:
        text += f"<b>Last {min(5, len(messages))} messages:</b>\n\n"
        for msg in messages[-5:]:
            sender = msg.get("sender_type", "")
            name = msg.get("sender_name", sender)
            msg_text = msg.get("message_text", "")
            if len(msg_text) > 200:
                msg_text = msg_text[:197] + "..."
            icon = {
                "adm": "\U0001F464",
                "department": "\U0001F3E2",
                "ai": "\U0001F916",
            }.get(sender, "\u2139\uFE0F")
            text += f"{icon} <b>{name}:</b>\n{msg_text}\n\n"

    text += f"<i>Use /cases to reply or manage this case.</i>"

    if len(text) > 4000:
        text = text[:3997] + "..."

    buttons = [[InlineKeyboardButton(
        "\u2705 Close Ticket", callback_data=f"close_ticket:{ticket_id}",
    )]]

    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def close_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle close ticket button press."""
    query = update.callback_query
    await query.answer()

    ticket_id = query.data.split(":", 1)[1]
    result = await api_client.close_ticket(ticket_id)

    if result.get("status") == "ok":
        await query.edit_message_text(f"✅ Ticket {ticket_id} closed successfully.")
    else:
        await query.edit_message_text(f"❌ Failed to close ticket: {result.get('detail', 'Unknown error')}")


# ---------------------------------------------------------------------------
# /version command - check which version is running
# ---------------------------------------------------------------------------

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot version — useful to verify Railway deployed the latest code."""
    import datetime
    text = (
        f"{E_GEAR} <b>ADM Bot Version</b>\n\n"
        f"Version: <code>2.5.0-2026-02-23</code>\n"
        f"Server time: <code>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"API: <code>{config.API_BASE_URL}</code>\n"
        f"API healthy: <code>{api_client.is_healthy}</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Main menu callback handler (for inline keyboard buttons on main menu)
# ---------------------------------------------------------------------------

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route main menu button presses to the correct handler."""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Map menu callbacks to instructions to use commands
    cmd_map = {
        "cmd_briefing": (f"{E_SUNRISE} Use /briefing for your morning briefing.\nBriefing ke liye /briefing type karein.", "/briefing"),
        "cmd_diary": (f"{E_CALENDAR} Use /diary to open your schedule.\nDiary ke liye /diary type karein.", "/diary"),
        "cmd_agents": (f"{E_PEOPLE} Use /agents to see your agent list.\nAgents ke liye /agents type karein.", "/agents"),
        "cmd_feedback": (f"{E_CHAT} Use /feedback to capture agent feedback.\nFeedback ke liye /feedback type karein.", "/feedback"),
        "cmd_log": (f"{E_MEMO} Use /log to log an interaction.\nInteraction log ke liye /log type karein.", "/log"),
        "cmd_train": (f"{E_BOOK} Use /train for product training.\nTraining ke liye /train type karein.", "/train"),
        "cmd_ask": (f"{E_BRAIN} Use /ask to ask AI about products.\nAI se puchne ke liye /ask type karein.", "/ask"),
        "cmd_stats": (f"{E_CHART} Use /stats for your performance.\nStats ke liye /stats type karein.", "/stats"),
    }

    if data in cmd_map:
        msg, cmd = cmd_map[data]
        await query.edit_message_text(
            f"{msg}\n\n<i>Tip: You can also type {cmd} directly!</i>",
            parse_mode="HTML",
        )
        return

    # Handle briefing-specific callbacks
    if data.startswith("brief_"):
        await briefing_callback(update, context)
        return

    # Handle stats callbacks
    if data.startswith("stats_"):
        await stats_callback(update, context)
        return


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and send a friendly message to the user."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Try to send a friendly message to the user
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"{E_WARNING} <b>Oops! Kuch gadbad ho gayi.</b>\n\n"
                f"Something went wrong. Please try again.\n"
                f"Agar problem continue ho toh /help use karein.\n\n"
                f"<i>Error has been logged for our team.</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass  # Can't send message - probably a network error


# ---------------------------------------------------------------------------
# Post-init: set bot commands in Telegram menu
# ---------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    """Set bot commands for the Telegram menu after initialization."""
    commands = [
        BotCommand("start", "Register / Restart"),
        BotCommand("briefing", "Morning briefing / Subah ki report"),
        BotCommand("diary", "Today's schedule / Aaj ka diary"),
        BotCommand("agents", "Your agents / Aapke agents"),
        BotCommand("feedback", "Capture agent feedback"),
        BotCommand("log", "Log an interaction"),
        BotCommand("train", "Product training modules"),
        BotCommand("ask", "AI product answers"),
        BotCommand("stats", "Your performance stats"),
        BotCommand("cases", "Case history per agent"),
        BotCommand("tickets", "View your open tickets"),
        BotCommand("voice", "Toggle voice notes on/off"),
        BotCommand("help", "Show all commands"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands set successfully.")
    except Exception as exc:
        logger.warning("Could not set bot commands: %s", exc)


# ---------------------------------------------------------------------------
# Shutdown: close API client
# ---------------------------------------------------------------------------

async def post_shutdown(application: Application) -> None:
    """Cleanup on shutdown."""
    await api_client.close()
    logger.info("API client closed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Build and run the Telegram bot."""
    token = config.TELEGRAM_BOT_TOKEN

    if not token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set! "
            "Please set the TELEGRAM_BOT_TOKEN environment variable."
        )
        sys.exit(1)

    BOT_VERSION = "2.5.0-2026-02-23"
    logger.info("Starting ADM Platform Telegram Bot v%s", BOT_VERSION)
    logger.info("API Base URL: %s", config.API_BASE_URL)

    # Build application
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ------------------------------------------------------------------
    # Register conversation handlers (order matters - first match wins)
    # ------------------------------------------------------------------

    # /start - registration flow (ConversationHandler)
    application.add_handler(build_start_handler())

    # /feedback - multi-step feedback capture (ConversationHandler)
    application.add_handler(build_feedback_handler())

    # /diary (/schedule) - diary management (ConversationHandler)
    application.add_handler(build_diary_handler())

    # /log - interaction logging (ConversationHandler)
    application.add_handler(build_interaction_handler())

    # /train - product training + quiz (ConversationHandler)
    application.add_handler(build_training_handler())

    # /ask - AI product Q&A (ConversationHandler)
    application.add_handler(build_ask_handler())

    # /cases - case history per agent (ConversationHandler)
    application.add_handler(build_cases_handler())

    # ------------------------------------------------------------------
    # Register simple command handlers
    # ------------------------------------------------------------------

    # /help
    application.add_handler(CommandHandler("help", help_command))

    # /briefing - morning briefing
    application.add_handler(CommandHandler("briefing", briefing_command))

    # /agents - view assigned agents
    application.add_handler(CommandHandler("agents", agents_command))

    # /stats - performance dashboard
    application.add_handler(CommandHandler("stats", stats_command))

    # /voice - toggle voice mode
    application.add_handler(CommandHandler("voice", voice_command))

    # /tickets - view open feedback tickets
    application.add_handler(CommandHandler("tickets", tickets_command))

    # /version - check running version
    application.add_handler(CommandHandler("version", version_command))

    # ------------------------------------------------------------------
    # Register callback query handlers for menus and actions
    # ------------------------------------------------------------------

    # Main menu button callbacks
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^cmd_"))

    # Briefing action callbacks
    application.add_handler(CallbackQueryHandler(briefing_callback, pattern=r"^brief_"))

    # Stats action callbacks
    application.add_handler(CallbackQueryHandler(stats_callback, pattern=r"^stats_"))

    # Close ticket callback
    application.add_handler(CallbackQueryHandler(close_ticket_callback, pattern=r"^close_ticket:"))

    # View case from Telegram notification (outside conversation handler)
    application.add_handler(CallbackQueryHandler(view_case_from_notification, pattern=r"^view_case:"))

    # ------------------------------------------------------------------
    # Catch-all handler — give user a helpful nudge instead of silence
    # This fires when no ConversationHandler or command matched the message,
    # which typically happens after a bot restart wipes in-memory state.
    # ------------------------------------------------------------------
    from telegram.ext import MessageHandler, filters as tg_filters

    async def unhandled_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle stray text that no ConversationHandler claimed.
        This typically happens after bot restart — the user was mid-flow
        but the bot lost all conversation state.
        """
        if not update.message or not update.message.text:
            return  # Ignore non-text (photos, stickers, etc.)
        logger.warning(
            "CATCH-ALL: Unhandled text from user %s: %s",
            update.effective_user.id if update.effective_user else "unknown",
            update.message.text[:100],
        )
        await update.message.reply_text(
            f"{E_WARNING} <b>Bot was restarted</b>\n\n"
            f"Your previous flow was interrupted.\n"
            f"Bot restart hua hai, pichla flow reset ho gaya.\n\n"
            f"Please use a command to start again:\n"
            f"/log — Log an interaction\n"
            f"/feedback — Capture feedback\n"
            f"/cases — View case history\n"
            f"/help — See all commands",
            parse_mode="HTML",
        )

    application.add_handler(
        MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, unhandled_text),
        group=99,  # low priority group — only fires if nothing else matched
    )

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------
    application.add_error_handler(error_handler)

    # ------------------------------------------------------------------
    # Start polling
    # ------------------------------------------------------------------
    logger.info("Bot is starting polling...")
    print("Bot started", flush=True)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
