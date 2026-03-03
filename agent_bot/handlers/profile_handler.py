"""
Profile handler for the Agent Telegram Bot.

Simple command handler (not a ConversationHandler):
  /profile or "agent_menu_profile" callback
  -> Check registered
  -> Fetch profile from API
  -> Format and display with back to menu button

Exports a register(app) function that adds the handlers.
"""

import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from agent_bot.config import config
from agent_bot.utils.api_client import api_client
from agent_bot.utils.formatters import (
    format_profile,
    EMOJI_WARN,
    EMOJI_PERSON,
)
from agent_bot.utils.keyboards import back_to_menu_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# /profile command
# ---------------------------------------------------------------------------

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile — fetch and display agent profile."""
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
        return

    # Fetch profile from API
    profile = await api_client.get_agent_profile(int(agent_id))

    if profile.get("error"):
        text = (
            f"{EMOJI_WARN} <b>Could not load profile</b>\n\n"
            f"Please try again later.\n"
            f"<i>Error: {profile.get('detail', 'Unknown error')}</i>"
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=back_to_menu_keyboard(),
            )
        else:
            await update.message.reply_text(
                text, parse_mode="HTML", reply_markup=back_to_menu_keyboard(),
            )
        return

    profile_text = format_profile(profile)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            profile_text,
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            profile_text,
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )


# ---------------------------------------------------------------------------
# Profile callback (from inline menu)
# ---------------------------------------------------------------------------

async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle agent_menu_profile callback query."""
    await profile_command(update, context)


# ---------------------------------------------------------------------------
# Register handlers
# ---------------------------------------------------------------------------

def register(app):
    """Register profile handlers with the application."""
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CallbackQueryHandler(profile_callback, pattern=r"^agent_menu_profile$"))
