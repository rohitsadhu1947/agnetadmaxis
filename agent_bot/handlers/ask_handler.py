"""
AI Product Q&A handler for the Agent Telegram Bot.

Flow:
  /ask or "agent_menu_ask" callback
  -> Check registered
  -> Ask for question (WAITING_QUESTION)
  -> Receive text -> call api_client.ask_product_question(question)
  -> Show AI answer with formatting
  -> Ask if they have another question or back to menu
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

from agent_bot.config import config, AgentAskStates
from agent_bot.utils.api_client import api_client
from agent_bot.utils.formatters import (
    EMOJI_CHECK,
    EMOJI_CROSS,
    EMOJI_WARN,
    EMOJI_ROBOT,
    EMOJI_BULB,
    EMOJI_PIN,
    EMOJI_BOOK,
    EMOJI_STAR,
    EMOJI_MEMO,
    EMOJI_HOME,
)
from agent_bot.utils.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _ask_another_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with 'Ask Another' and 'Done' buttons."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{EMOJI_ROBOT} Ask Another / Aur Puchho", callback_data="aask_another")],
        [
            InlineKeyboardButton(f"{EMOJI_BOOK} Training", callback_data="aask_training"),
            InlineKeyboardButton(f"{EMOJI_CHECK} Done", callback_data="aask_done"),
        ],
    ])


def _prompt_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with quick topic suggestions."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Term Plans", callback_data="aask_topic_term"),
            InlineKeyboardButton("ULIPs", callback_data="aask_topic_ulip"),
        ],
        [
            InlineKeyboardButton("Savings", callback_data="aask_topic_savings"),
            InlineKeyboardButton("Child Plans", callback_data="aask_topic_child"),
        ],
        [
            InlineKeyboardButton("Commission", callback_data="aask_topic_commission"),
            InlineKeyboardButton("Claims", callback_data="aask_topic_claim"),
        ],
        [InlineKeyboardButton(f"{EMOJI_HOME} Main Menu", callback_data="agent_menu_home")],
    ])


# ---------------------------------------------------------------------------
# Entry: /ask or agent_menu_ask callback
# ---------------------------------------------------------------------------

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the AI Q&A flow."""
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

    # Check for inline question: /ask What is term insurance?
    if update.message and context.args:
        question = " ".join(context.args)
        return await _process_question(update, context, question)

    text = (
        f"{EMOJI_ROBOT} <b>AI Product Q&A</b>\n\n"
        f"{EMOJI_BULB} Ask me anything about Axis Max Life products!\n"
        f"Products ke baare mein kuch bhi poochein!\n\n"
        f"<b>Example questions:</b>\n"
        f"  {EMOJI_PIN} 'Term plan kya hai?'\n"
        f"  {EMOJI_PIN} 'ULIP vs savings plan?'\n"
        f"  {EMOJI_PIN} 'Commission kitna milta hai?'\n"
        f"  {EMOJI_PIN} 'Claim process kaise kaam karta hai?'\n\n"
        f"{EMOJI_MEMO} <b>Type your question below or tap a topic:</b>"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=_prompt_keyboard(),
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=_prompt_keyboard(),
        )
    return AgentAskStates.WAITING_QUESTION


# ---------------------------------------------------------------------------
# Process question
# ---------------------------------------------------------------------------

async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and process a product question from text."""
    question = update.message.text.strip()

    if len(question) < 2:
        await update.message.reply_text(
            f"{EMOJI_WARN} Please ask a more detailed question.\n"
            f"Thoda aur detail mein poochein.\n\n"
            f"{EMOJI_MEMO} Type your question:",
            parse_mode="HTML",
        )
        return AgentAskStates.WAITING_QUESTION

    return await _process_question(update, context, question)


async def _process_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> int:
    """Process a question and return AI answer."""
    msg = update.message or (update.callback_query.message if update.callback_query else None)

    # Show thinking message
    thinking_msg = None
    if msg:
        try:
            thinking_msg = await msg.reply_text(
                f"{EMOJI_ROBOT} <b>Thinking...</b> {EMOJI_BULB}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Call AI API
    try:
        answer_resp = await api_client.ask_product_question(question=question)
    except Exception as e:
        logger.error("Ask API error: %s", e)
        answer_resp = None

    if answer_resp and not answer_resp.get("error") and answer_resp.get("answer"):
        answer_text = answer_resp["answer"]
    elif answer_resp and answer_resp.get("error"):
        answer_text = (
            f"{EMOJI_WARN} Could not get an answer right now.\n"
            f"Abhi jawab nahi mil paya. Please try again.\n\n"
            f"<i>Error: {answer_resp.get('detail', 'Service unavailable')}</i>"
        )
    else:
        answer_text = (
            f"{EMOJI_WARN} AI service is currently unavailable.\n"
            f"AI service abhi available nahi hai.\n"
            f"Please try again later."
        )

    # Build response
    response_text = (
        f"{EMOJI_MEMO} <b>Q:</b> <i>{question}</i>\n\n"
        f"{answer_text}"
    )

    # Truncate if too long
    if len(response_text) > 4000:
        response_text = response_text[:3997] + "..."

    # Delete thinking message
    if thinking_msg:
        try:
            await thinking_msg.delete()
        except Exception:
            pass

    # Send answer
    if msg:
        await msg.reply_text(
            response_text,
            parse_mode="HTML",
            reply_markup=_ask_another_keyboard(),
        )

    return AgentAskStates.WAITING_QUESTION


# ---------------------------------------------------------------------------
# Callback actions
# ---------------------------------------------------------------------------

async def ask_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ask flow callback buttons."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Quick topic buttons
    if data.startswith("aask_topic_"):
        topic = data.replace("aask_topic_", "")
        topic_questions = {
            "term": "Tell me about term insurance plans",
            "ulip": "Tell me about ULIP plans",
            "savings": "Tell me about savings plans",
            "child": "Tell me about child insurance plans",
            "commission": "What is the commission structure?",
            "claim": "How does the claim process work?",
        }
        question = topic_questions.get(topic, f"Tell me about {topic}")
        return await _process_question(update, context, question)

    # Ask another
    if data == "aask_another":
        await query.edit_message_text(
            f"{EMOJI_ROBOT} <b>Ask Another Question</b>\n\n"
            f"{EMOJI_MEMO} Type your question below or tap a topic:",
            parse_mode="HTML",
            reply_markup=_prompt_keyboard(),
        )
        return AgentAskStates.WAITING_QUESTION

    # Go to training
    if data == "aask_training":
        await query.edit_message_text(
            f"{EMOJI_BOOK} Use /training to start product training!\n"
            f"Training ke liye /training type karein.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # Done
    if data == "aask_done":
        await query.edit_message_text(
            f"{EMOJI_CHECK} <b>Q&A session complete!</b>\n\n"
            f"Bahut achha! {EMOJI_STAR}\n\n"
            f"{EMOJI_BULB} Kabhi bhi /ask use karke sawal pooch sakte hain.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    return AgentAskStates.WAITING_QUESTION


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel ask flow."""
    text = f"{EMOJI_CROSS} Q&A session ended."
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Build ConversationHandler
# ---------------------------------------------------------------------------

handler = ConversationHandler(
    entry_points=[
        CommandHandler("ask", ask_command),
        CallbackQueryHandler(ask_command, pattern=r"^agent_menu_ask$"),
    ],
    states={
        AgentAskStates.WAITING_QUESTION: [
            CallbackQueryHandler(ask_callback, pattern=r"^aask_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_ask),
        CommandHandler("ask", ask_command),
        CallbackQueryHandler(cancel_ask, pattern=r"^(agent_cancel|cancel)$"),
    ],
    name="agent_ask",
    persistent=False,
    per_user=True,
    per_chat=True,
    allow_reentry=True,
    conversation_timeout=600,
)
