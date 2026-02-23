"""
Start / Registration handler for the ADM Platform Telegram Bot.
Handles /start command and multi-step registration flow.
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

from config import RegistrationStates
from utils.api_client import api_client
from utils.formatters import (
    welcome_message,
    registration_success,
    help_message,
    error_generic,
    greeting,
    E_CHECK, E_CROSS, E_PENCIL, E_PERSON, E_STAR,
    E_GEAR, E_SPARKLE,
)
from utils.keyboards import main_menu_keyboard, confirm_keyboard, yes_no_keyboard
from utils.voice import send_voice_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# /start entry point
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start - check if user is registered, else start registration."""
    user = update.effective_user
    telegram_id = user.id
    logger.info(">>> /start command received from user %s (%s)", telegram_id, user.first_name)

    # Check if already registered
    profile = await api_client.get_adm_profile(telegram_id)

    if profile and not profile.get("error"):
        name = profile.get("name", user.first_name or "ADM")
        welcome_text = (
            f"{greeting(name)}\n\n"
            f"{E_SPARKLE} Welcome back to <b>ADM Platform</b>!\n"
            f"Aap pehle se registered hain.\n\n"
            f"What would you like to do today?"
        )
        sent_msg = await update.message.reply_text(
            welcome_text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        await send_voice_response(sent_msg, welcome_text)
        return ConversationHandler.END

    # API error (e.g., backend restarting / connection error) — don't start
    # registration for what might be an existing user. Only proceed to
    # registration if the API explicitly returned 404 (user not found).
    if profile and profile.get("error"):
        status = profile.get("status", 0)
        if status != 404:
            # Server error or connection error — ask to retry
            await update.message.reply_text(
                f"\u26A0\uFE0F <b>Service temporarily unavailable</b>\n\n"
                f"Could not check your registration. Please try /start again in a few seconds.\n"
                f"Server se connect nahi ho paya. Kuch second baad /start karein.",
                parse_mode="HTML",
            )
            return ConversationHandler.END
        # status == 404 means genuinely not registered — fall through to registration

    # New user - start registration
    welcome_text = welcome_message()
    sent_msg = await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
    )
    await send_voice_response(sent_msg, welcome_text)
    return RegistrationStates.ENTER_NAME


# ---------------------------------------------------------------------------
# Registration steps
# ---------------------------------------------------------------------------

async def _abort_if_already_registered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is already registered. If so, abort registration and return True."""
    telegram_id = update.effective_user.id
    profile = await api_client.get_adm_profile(telegram_id)
    if profile and not profile.get("error"):
        name = profile.get("name", update.effective_user.first_name or "ADM")
        await update.message.reply_text(
            f"{E_CHECK} <b>Aap pehle se registered hain, {name}!</b>\n\n"
            f"You are already registered. No need to register again.\n"
            f"Use /help to see available commands.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        # Clean up any partial registration data
        for key in list(context.user_data.keys()):
            if key.startswith("reg_"):
                del context.user_data[key]
        return True
    return False


async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the ADM's full name."""
    # Guard: if user is already registered, don't capture their text
    if await _abort_if_already_registered(update, context):
        return ConversationHandler.END

    name = update.message.text.strip()

    if len(name) < 2 or len(name) > 100:
        await update.message.reply_text(
            f"{E_CROSS} Please enter a valid name (2-100 characters).\n"
            f"Kripya apna poora naam dalein.",
            parse_mode="HTML",
        )
        return RegistrationStates.ENTER_NAME

    context.user_data["reg_name"] = name
    await update.message.reply_text(
        f"{E_CHECK} Name: <b>{name}</b>\n\n"
        f"{E_PENCIL} Now please enter your <b>Employee ID</b>:\n"
        f"(e.g., ADM12345)",
        parse_mode="HTML",
    )
    return RegistrationStates.ENTER_EMPLOYEE_ID


async def enter_employee_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the Employee ID."""
    # Guard: if user is already registered, don't capture their text
    if await _abort_if_already_registered(update, context):
        return ConversationHandler.END

    emp_id = update.message.text.strip().upper()

    if len(emp_id) < 3 or len(emp_id) > 20:
        await update.message.reply_text(
            f"{E_CROSS} Please enter a valid Employee ID.\n"
            f"Kripya sahi Employee ID dalein.",
            parse_mode="HTML",
        )
        return RegistrationStates.ENTER_EMPLOYEE_ID

    context.user_data["reg_employee_id"] = emp_id
    await update.message.reply_text(
        f"{E_CHECK} Employee ID: <b>{emp_id}</b>\n\n"
        f"{E_PENCIL} Now please enter your <b>Region / Zone</b>:\n"
        f"(e.g., North, South, East, West, Central)",
        parse_mode="HTML",
    )
    return RegistrationStates.ENTER_REGION


async def enter_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the region."""
    # Guard: if user is already registered, don't capture their text
    if await _abort_if_already_registered(update, context):
        return ConversationHandler.END

    region = update.message.text.strip().title()

    if len(region) < 2:
        await update.message.reply_text(
            f"{E_CROSS} Please enter a valid region.\n"
            f"Kripya apna region dalein.",
            parse_mode="HTML",
        )
        return RegistrationStates.ENTER_REGION

    context.user_data["reg_region"] = region

    name = context.user_data.get("reg_name", "")
    emp_id = context.user_data.get("reg_employee_id", "")

    await update.message.reply_text(
        f"{E_STAR} <b>Registration Summary</b>\n\n"
        f"{E_PERSON} Name: <b>{name}</b>\n"
        f"{E_GEAR} Employee ID: <b>{emp_id}</b>\n"
        f"\U0001F30D Region: <b>{region}</b>\n\n"
        f"<i>Is this correct? / Kya ye sahi hai?</i>",
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )
    return RegistrationStates.CONFIRM_REGISTRATION


async def confirm_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle registration confirmation callback."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text(
            f"{E_CROSS} Registration cancelled.\n"
            f"Use /start to try again.",
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    # confirm_yes - register with backend
    telegram_id = update.effective_user.id
    name = context.user_data.get("reg_name", "")
    emp_id = context.user_data.get("reg_employee_id", "")
    region = context.user_data.get("reg_region", "")

    result = await api_client.register_adm(
        telegram_id=telegram_id,
        name=name,
        employee_id=emp_id,
        region=region,
    )

    if result.get("error"):
        logger.warning("Registration API failed: %s", result)

    web_username = result.get("web_username", emp_id.lower() if emp_id else "")

    await query.edit_message_text(
        registration_success(name, web_username=web_username, employee_id=emp_id),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Clean up
    for key in list(context.user_data.keys()):
        if key.startswith("reg_"):
            del context.user_data[key]

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel registration flow."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            f"{E_CROSS} Registration cancelled. Use /start to try again.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"{E_CROSS} Registration cancelled. Use /start to try again.",
            parse_mode="HTML",
        )
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /help command
# ---------------------------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    user = update.effective_user
    profile = await api_client.get_adm_profile(user.id)
    name = (profile.get("name", user.first_name) if profile and not profile.get("error") else user.first_name) or "ADM"

    help_text = help_message(name)
    sent_msg = await update.message.reply_text(
        help_text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    await send_voice_response(sent_msg, help_text)


# ---------------------------------------------------------------------------
# Build ConversationHandler
# ---------------------------------------------------------------------------

def build_start_handler() -> ConversationHandler:
    """Build the /start registration conversation handler.

    allow_reentry=True so users can restart with /start if stuck.
    This is critical because if the API is down during /start, the user
    could get trapped in registration flow even though they're already
    registered.
    """
    _cancel_cb = lambda: CallbackQueryHandler(cancel, pattern=r"^cancel$")

    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            RegistrationStates.ENTER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name),
                _cancel_cb(),
            ],
            RegistrationStates.ENTER_EMPLOYEE_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_employee_id),
                _cancel_cb(),
            ],
            RegistrationStates.ENTER_REGION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_region),
                _cancel_cb(),
            ],
            RegistrationStates.CONFIRM_REGISTRATION: [
                CallbackQueryHandler(confirm_registration, pattern=r"^confirm_"),
                _cancel_cb(),
            ],
            # Timeout handler — auto-cancel after 5 minutes of inactivity
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, cancel),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start_command),  # Allow re-entry
            _cancel_cb(),
        ],
        name="registration",
        persistent=False,
        allow_reentry=True,
        conversation_timeout=300,  # 5 minutes — auto-expire stale registrations
    )
