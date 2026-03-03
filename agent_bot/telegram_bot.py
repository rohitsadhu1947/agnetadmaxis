"""
Agent Telegram Bot - Main Entry Point.
Separate bot for insurance agents (distinct from the ADM bot).

Usage:
    python agent_bot/telegram_bot.py

Environment variables:
    AGENT_TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
    API_BASE_URL              - Backend API URL (default: http://localhost:8000/api/v1)
"""

import logging
import sys
import os

# Ensure project root is on path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters as tg_filters,
)

from agent_bot.config import config
from agent_bot.utils.formatters import (
    EMOJI_WARN, EMOJI_HOME, format_main_menu,
)
from agent_bot.utils.keyboards import main_menu_keyboard

# Handler imports
from agent_bot.handlers.start_handler import handler as start_handler, register as register_start_extras
from agent_bot.handlers.feedback_handler import handler as feedback_handler
from agent_bot.handlers.case_handler import handler as case_handler
from agent_bot.handlers.training_handler import handler as training_handler
from agent_bot.handlers.ask_handler import handler as ask_handler
from agent_bot.handlers.profile_handler import register as register_profile


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format=config.LOG_FORMAT,
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main menu callback router
# ---------------------------------------------------------------------------

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route main menu button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    cmd_map = {
        "agent_menu_feedback": "/feedback — Submit feedback ya issue report karein",
        "agent_menu_cases": "/cases — Apne tickets track karein",
        "agent_menu_training": "/training — Product training modules",
        "agent_menu_ask": "/ask — AI se product ke baare mein poochein",
        "agent_menu_profile": "/profile — Apni profile dekhein",
    }

    if data == "agent_menu_home":
        await query.edit_message_text(
            format_main_menu(),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    if data in cmd_map:
        await query.edit_message_text(
            f"{cmd_map[data]}\n\n<i>Command type karein to start!</i>",
            parse_mode="HTML",
        )


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and send a friendly message."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"{EMOJI_WARN} <b>Oops! Kuch gadbad ho gayi.</b>\n\n"
                f"Please try again. Agar problem continue ho toh /help use karein.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Post-init: set bot commands
# ---------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    """Set bot commands and verify backend connectivity."""
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Agent bot: Webhook deleted, pending updates dropped.")
    except Exception as exc:
        logger.warning("Could not delete webhook: %s", exc)

    # Health check
    import httpx
    try:
        health_url = config.API_BASE_URL.replace("/api/v1", "").rstrip("/") + "/health"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(health_url)
            health = resp.json()
            logger.info("=== AGENT BOT HEALTH CHECK ===")
            logger.info("  Database: %s", health.get("database", "unknown"))
            logger.info("  AI enabled: %s", health.get("ai_enabled", "unknown"))
            logger.info("==============================")
    except Exception as e:
        logger.warning("Could not verify backend: %s", e)

    commands = [
        BotCommand("start", "Register / Restart"),
        BotCommand("feedback", "Submit feedback / Report issue"),
        BotCommand("cases", "Track your tickets"),
        BotCommand("training", "Product training"),
        BotCommand("ask", "Ask AI about products"),
        BotCommand("profile", "View your profile"),
        BotCommand("menu", "Main menu"),
        BotCommand("help", "Help / Commands"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Agent bot commands set.")
    except Exception as exc:
        logger.warning("Could not set bot commands: %s", exc)


# ---------------------------------------------------------------------------
# Catch-all handler
# ---------------------------------------------------------------------------

async def unhandled_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle stray text that no handler claimed."""
    if not update.message or not update.message.text:
        return
    logger.warning(
        "CATCH-ALL: Unhandled text from user %s: %s",
        update.effective_user.id if update.effective_user else "unknown",
        update.message.text[:100],
    )
    await update.message.reply_text(
        f"{EMOJI_WARN} <b>Please use a command:</b>\n\n"
        f"/feedback — Submit feedback\n"
        f"/cases — View tickets\n"
        f"/training — Product training\n"
        f"/ask — AI product Q&A\n"
        f"/profile — Your profile\n"
        f"/help — All commands",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Build and run the Agent Telegram bot."""
    token = config.AGENT_TELEGRAM_BOT_TOKEN

    if not token:
        logger.error(
            "AGENT_TELEGRAM_BOT_TOKEN is not set! "
            "Please set the AGENT_TELEGRAM_BOT_TOKEN environment variable."
        )
        sys.exit(1)

    logger.info("Starting Agent Telegram Bot")
    logger.info("API Base URL: %s", config.API_BASE_URL)

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # ------------------------------------------------------------------
    # Register conversation handlers (order: specific first, /start last)
    # ------------------------------------------------------------------

    application.add_handler(feedback_handler)
    application.add_handler(case_handler)
    application.add_handler(training_handler)
    application.add_handler(ask_handler)
    application.add_handler(start_handler)  # Last — so others get priority

    # ------------------------------------------------------------------
    # Simple command/callback handlers
    # ------------------------------------------------------------------

    register_start_extras(application)
    register_profile(application)

    # Main menu callbacks
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^agent_menu_"))

    # Catch-all for unhandled text (low priority group)
    application.add_handler(
        MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, unhandled_text),
        group=99,
    )

    # Error handler
    application.add_error_handler(error_handler)

    # ------------------------------------------------------------------
    # Start polling
    # ------------------------------------------------------------------
    logger.info("Agent bot starting polling...")
    print("Agent bot started", flush=True)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0,
        close_loop=False,
    )


if __name__ == "__main__":
    main()
