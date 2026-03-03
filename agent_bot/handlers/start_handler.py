"""
Start / Registration handler for the Agent Telegram Bot.
Handles /start command (phone-based registration), /help, and /menu.

Flow:
  /start -> check if already registered (agent_id in user_data)
         -> if not, ask for phone number
         -> call api_client.register_agent(phone, chat_id)
         -> if found, store agent_id and agent_name, show welcome
         -> if not found, tell them to contact their ADM
         -> confirm registration
"""

import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from agent_bot.config import config, AgentRegistrationStates
from agent_bot.utils.api_client import api_client
from agent_bot.utils.formatters import (
    format_welcome,
    format_main_menu,
    EMOJI_CHECK,
    EMOJI_CROSS,
    EMOJI_WAVE,
    EMOJI_PHONE,
    EMOJI_WARN,
    EMOJI_PERSON,
    EMOJI_BULB,
    EMOJI_HOME,
    EMOJI_MEMO,
    EMOJI_TICKET,
    EMOJI_BOOK,
    EMOJI_ROBOT,
)
from agent_bot.utils.keyboards import main_menu_keyboard, confirm_cancel_keyboard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_reg_data(context: ContextTypes.DEFAULT_TYPE):
    """Remove all registration-related keys from user_data."""
    for key in list(context.user_data.keys()):
        if key.startswith("reg_"):
            del context.user_data[key]


# ---------------------------------------------------------------------------
# /start entry point
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start - check if user is registered, else start registration."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(">>> /start command received from user %s (%s)", user.id, user.first_name)

    # Clean up any stale reg data from a previous attempt
    _cleanup_reg_data(context)

    # If already registered in this session, welcome back
    if context.user_data.get("agent_id"):
        agent_name = context.user_data.get("agent_name", user.first_name or "Agent")
        await update.message.reply_text(
            f"{EMOJI_WAVE} <b>Welcome back, {agent_name}!</b>\n\n"
            f"Aap pehle se registered hain.\n"
            f"What would you like to do today?",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    # Not registered yet — ask for phone number
    await update.message.reply_text(
        f"{EMOJI_WAVE} <b>Welcome to Axis Max Life Agent Bot!</b>\n\n"
        f"Axis Max Life Agent Bot mein aapka swagat hai.\n\n"
        f"{EMOJI_PHONE} Please enter your <b>registered phone number</b> "
        f"to get started:\n"
        f"Apna registered mobile number dalein:",
        parse_mode="HTML",
    )
    return AgentRegistrationStates.ENTER_PHONE


# ---------------------------------------------------------------------------
# Step 1: Receive phone number and register
# ---------------------------------------------------------------------------

async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive phone number and attempt registration via API."""
    phone = update.message.text.strip()

    # Basic phone validation — digits only, 10-15 chars
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        await update.message.reply_text(
            f"{EMOJI_CROSS} Please enter a valid phone number (10+ digits).\n"
            f"Kripya sahi mobile number dalein.\n\n"
            f"{EMOJI_PHONE} Enter your phone number:",
            parse_mode="HTML",
        )
        return AgentRegistrationStates.ENTER_PHONE

    chat_id = str(update.effective_chat.id)

    # Call API to register / lookup agent by phone
    try:
        result = await api_client.register_agent(phone=digits, telegram_chat_id=chat_id)
    except Exception as e:
        logger.error("Registration API error: %s", e)
        await update.message.reply_text(
            f"{EMOJI_WARN} <b>Service temporarily unavailable</b>\n\n"
            f"Could not connect to the server. Please try /start again.\n"
            f"Server se connect nahi ho paya. Kuch der baad /start karein.",
            parse_mode="HTML",
        )
        _cleanup_reg_data(context)
        return ConversationHandler.END

    if result.get("error"):
        status = result.get("status", 500)
        if status == 404:
            # Agent not found in the system
            await update.message.reply_text(
                f"{EMOJI_CROSS} <b>Agent Not Found</b>\n\n"
                f"This phone number is not registered in our system.\n"
                f"Yeh number hamare system mein nahi hai.\n\n"
                f"{EMOJI_BULB} Please contact your ADM (Agency Development Manager) "
                f"to get registered.\n"
                f"Apne ADM se sampark karein registration ke liye.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"{EMOJI_WARN} <b>Registration failed</b>\n\n"
                f"Something went wrong. Please try /start again.\n"
                f"Kuch gadbad ho gayi. Dobara /start karein.\n\n"
                f"<i>Error: {result.get('detail', 'Unknown error')}</i>",
                parse_mode="HTML",
            )
        _cleanup_reg_data(context)
        return ConversationHandler.END

    # Agent found — store data for confirmation
    agent_id = result.get("agent_id") or result.get("id")
    agent_name = result.get("name") or result.get("agent_name") or "Agent"

    context.user_data["reg_agent_id"] = agent_id
    context.user_data["reg_agent_name"] = agent_name
    context.user_data["reg_phone"] = digits

    await update.message.reply_text(
        f"{EMOJI_CHECK} <b>Agent Found!</b>\n\n"
        f"{EMOJI_PERSON} <b>Name:</b> {agent_name}\n"
        f"{EMOJI_PHONE} <b>Phone:</b> {digits}\n\n"
        f"Is this correct? / Kya yeh sahi hai?",
        parse_mode="HTML",
        reply_markup=confirm_cancel_keyboard(
            confirm_data="agent_reg_confirm",
            cancel_data="agent_reg_cancel",
        ),
    )
    return AgentRegistrationStates.CONFIRM_REGISTRATION


# ---------------------------------------------------------------------------
# Step 2: Confirm registration
# ---------------------------------------------------------------------------

async def confirm_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle registration confirmation callback."""
    query = update.callback_query
    await query.answer()

    if query.data == "agent_reg_cancel":
        await query.edit_message_text(
            f"{EMOJI_CROSS} Registration cancelled.\n"
            f"Use /start to try again.",
            parse_mode="HTML",
        )
        _cleanup_reg_data(context)
        return ConversationHandler.END

    # Confirmed — persist to session
    agent_id = context.user_data.get("reg_agent_id")
    agent_name = context.user_data.get("reg_agent_name", "Agent")

    context.user_data["agent_id"] = agent_id
    context.user_data["agent_name"] = agent_name

    welcome_text = format_welcome(agent_name)
    await query.edit_message_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Clean up temporary registration data
    _cleanup_reg_data(context)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel registration flow."""
    _cleanup_reg_data(context)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            f"{EMOJI_CROSS} Cancelled. Use /start to try again.",
            parse_mode="HTML",
        )
    elif update.message:
        await update.message.reply_text(
            f"{EMOJI_CROSS} Cancelled. Use /start to try again.",
            parse_mode="HTML",
        )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /help command
# ---------------------------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command — show available commands."""
    agent_name = context.user_data.get("agent_name", update.effective_user.first_name or "Agent")
    help_text = (
        f"{EMOJI_BULB} <b>Help — {agent_name}</b>\n"
        f"{'━' * 28}\n\n"
        f"Available commands:\n\n"
        f"/start — Register or re-register\n"
        f"/menu — Main menu\n"
        f"/feedback — Submit feedback or report an issue\n"
        f"/cases — View and track your tickets\n"
        f"/training — Product training modules\n"
        f"/ask — Ask AI about products\n"
        f"/profile — View your profile\n"
        f"/help — Show this help message\n"
        f"/cancel — Cancel current action\n\n"
        f"Kisi bhi command ke liye help chahiye toh /help type karein."
    )
    await update.message.reply_text(
        help_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# /menu command
# ---------------------------------------------------------------------------

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command — show the main menu."""
    if not context.user_data.get("agent_id"):
        await update.message.reply_text(
            f"{EMOJI_WARN} You are not registered yet.\n"
            f"Pehle /start se register karein.",
            parse_mode="HTML",
        )
        return

    menu_text = format_main_menu()
    await update.message.reply_text(
        menu_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Menu callback handler (for inline keyboard taps on main menu)
# ---------------------------------------------------------------------------

async def menu_home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Main Menu' / 'Home' inline button taps."""
    query = update.callback_query
    await query.answer()
    menu_text = format_main_menu()
    await query.edit_message_text(
        menu_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Build ConversationHandler
# ---------------------------------------------------------------------------

handler = ConversationHandler(
    entry_points=[CommandHandler("start", start_command)],
    states={
        AgentRegistrationStates.ENTER_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone),
            CallbackQueryHandler(cancel, pattern=r"^agent_cancel$"),
        ],
        AgentRegistrationStates.CONFIRM_REGISTRATION: [
            CallbackQueryHandler(confirm_registration, pattern=r"^agent_reg_(confirm|cancel)$"),
        ],
        ConversationHandler.TIMEOUT: [
            MessageHandler(filters.ALL, cancel),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", start_command),
        CallbackQueryHandler(cancel, pattern=r"^agent_cancel$"),
    ],
    name="agent_registration",
    persistent=False,
    per_user=True,
    per_chat=True,
    allow_reentry=True,
    conversation_timeout=300,
)


def register(app):
    """Register standalone command handlers (not part of ConversationHandler)."""
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(menu_home_callback, pattern=r"^agent_menu_home$"))
