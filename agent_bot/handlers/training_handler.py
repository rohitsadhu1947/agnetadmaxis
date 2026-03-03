"""
Training handler for the Agent Telegram Bot.

Flow:
  /training or "agent_menu_training" callback
  -> Check registered
  -> Fetch training modules -> show category selection
  -> Select category -> show products/modules
  -> Select product -> show product details/summary
  -> Back navigation at each level
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from agent_bot.config import config, AgentTrainingStates
from agent_bot.utils.api_client import api_client
from agent_bot.utils.formatters import (
    EMOJI_CHECK,
    EMOJI_CROSS,
    EMOJI_WARN,
    EMOJI_BOOK,
    EMOJI_STAR,
    EMOJI_BULB,
    EMOJI_PIN,
    EMOJI_CHART,
    EMOJI_HOME,
    EMOJI_ARROW,
    EMOJI_BACK,
)
from agent_bot.utils.keyboards import (
    training_category_keyboard,
    main_menu_keyboard,
    back_to_menu_keyboard,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product_list_keyboard(products: list, category: str) -> InlineKeyboardMarkup:
    """Build product selection keyboard from a list of products."""
    buttons = []
    for prod in products[:10]:  # Max 10 products
        prod_id = prod.get("id", "")
        name = prod.get("name", "Unknown")
        display = name if len(name) <= 35 else name[:32] + "..."
        buttons.append([
            InlineKeyboardButton(
                f"{EMOJI_BOOK} {display}",
                callback_data=f"atrprod_{prod_id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(f"{EMOJI_BACK} Back to Categories", callback_data="atrcat_back"),
    ])
    buttons.append([
        InlineKeyboardButton(f"{EMOJI_HOME} Main Menu", callback_data="agent_menu_home"),
    ])
    return InlineKeyboardMarkup(buttons)


def _summary_keyboard(category: str) -> InlineKeyboardMarkup:
    """Keyboard for the product summary view."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{EMOJI_BACK} Back to Products", callback_data="atrsum_back_products")],
        [InlineKeyboardButton(f"{EMOJI_BOOK} Back to Categories", callback_data="atrcat_back")],
        [InlineKeyboardButton(f"{EMOJI_HOME} Main Menu", callback_data="agent_menu_home")],
    ])


# ---------------------------------------------------------------------------
# Entry: /training or agent_menu_training callback
# ---------------------------------------------------------------------------

async def training_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the training flow — fetch modules and show categories."""
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

    # Fetch training modules / categories
    modules_resp = await api_client.get_training_modules()
    modules = modules_resp.get("modules", modules_resp.get("data", []))

    if modules_resp.get("error") or not modules:
        # If API fails, show hardcoded categories so flow still works
        categories = ["term", "savings", "ulip", "pension", "child", "group"]
    else:
        # Extract unique categories from modules
        categories = list({m.get("category", "general") for m in modules if m.get("category")})
        if not categories:
            categories = ["term", "savings", "ulip", "pension", "child", "group"]

    context.user_data["atrain"] = {
        "modules_cache": modules,
        "categories": categories,
    }

    text = (
        f"{EMOJI_BOOK} <b>Product Training</b>\n\n"
        f"{EMOJI_STAR} Select a product category to learn:\n"
        f"Ek category chunein seekhne ke liye:"
    )

    kb = training_category_keyboard(categories)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=kb,
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=kb,
        )
    return AgentTrainingStates.SELECT_CATEGORY


# ---------------------------------------------------------------------------
# Step 1: Select category -> show products
# ---------------------------------------------------------------------------

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection — fetch and show products."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Back to categories
    if data == "atrcat_back":
        atrain = context.user_data.get("atrain", {})
        categories = atrain.get("categories", [])
        if not categories:
            categories = ["term", "savings", "ulip", "pension", "child", "group"]

        await query.edit_message_text(
            f"{EMOJI_BOOK} <b>Product Training</b>\n\n"
            f"{EMOJI_STAR} Select a category:",
            parse_mode="HTML",
            reply_markup=training_category_keyboard(categories),
        )
        return AgentTrainingStates.SELECT_CATEGORY

    category = data.replace("atrcat_", "")
    atrain = context.user_data.get("atrain", {})
    atrain["current_category"] = category

    # Fetch products for this category from API
    modules_resp = await api_client.get_training_modules(category=category)
    products = modules_resp.get("modules", modules_resp.get("data", []))

    if not products:
        await query.edit_message_text(
            f"{EMOJI_WARN} No training modules found for <b>{category.title()}</b>.\n"
            f"Is category mein abhi koi module nahi hai.\n\n"
            f"Try another category.",
            parse_mode="HTML",
            reply_markup=training_category_keyboard(
                atrain.get("categories", ["term", "savings", "ulip", "pension", "child", "group"])
            ),
        )
        return AgentTrainingStates.SELECT_CATEGORY

    atrain["products_cache"] = products

    await query.edit_message_text(
        f"{EMOJI_BOOK} <b>{category.title()} Training</b>\n\n"
        f"{EMOJI_STAR} Select a product to learn about:\n"
        f"Product chunein details ke liye:\n\n"
        f"<i>{len(products)} module(s) available</i>",
        parse_mode="HTML",
        reply_markup=_product_list_keyboard(products, category),
    )
    return AgentTrainingStates.SELECT_PRODUCT


# ---------------------------------------------------------------------------
# Step 2: Select product -> show summary
# ---------------------------------------------------------------------------

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle product selection — show product details/summary."""
    query = update.callback_query
    await query.answer()
    data = query.data

    atrain = context.user_data.get("atrain", {})

    # Back to categories
    if data == "atrcat_back":
        categories = atrain.get("categories", [])
        await query.edit_message_text(
            f"{EMOJI_BOOK} <b>Product Training</b>\n\n"
            f"{EMOJI_STAR} Select a category:",
            parse_mode="HTML",
            reply_markup=training_category_keyboard(categories),
        )
        return AgentTrainingStates.SELECT_CATEGORY

    product_id = data.replace("atrprod_", "")
    products = atrain.get("products_cache", [])

    # Find product info
    product_name = "Unknown Product"
    product_data = {}
    for prod in products:
        if str(prod.get("id", "")) == product_id:
            product_name = prod.get("name", "Unknown Product")
            product_data = prod
            break

    atrain["current_product_id"] = product_id
    atrain["current_product_name"] = product_name

    # Show loading
    await query.edit_message_text(
        f"\U0001f4a1 <b>Loading training content...</b>\n\n"
        f"<i>{product_name} ki jaankari load ho rahi hai...</i>",
        parse_mode="HTML",
    )

    # Build summary from available data
    summary = product_data.get("summary") or product_data.get("description") or ""
    key_features = product_data.get("key_features") or product_data.get("features", [])
    selling_tips = product_data.get("selling_tips", [])

    text_parts = [
        f"{EMOJI_BOOK} <b>{product_name}</b>",
        f"{'━' * 28}",
    ]

    if summary:
        text_parts.append(f"\n{EMOJI_PIN} <b>Overview:</b>\n{summary}")

    if key_features:
        features_text = "\n".join(
            f"  {EMOJI_CHECK} {f}" for f in (key_features if isinstance(key_features, list) else [key_features])
        )
        text_parts.append(f"\n{EMOJI_STAR} <b>Key Features:</b>\n{features_text}")

    if selling_tips:
        tips_text = "\n".join(
            f"  {EMOJI_BULB} {t}" for t in (selling_tips if isinstance(selling_tips, list) else [selling_tips])
        )
        text_parts.append(f"\n{EMOJI_BULB} <b>Selling Tips:</b>\n{tips_text}")

    if not summary and not key_features:
        text_parts.append(
            f"\n{EMOJI_PIN} <b>Category:</b> {atrain.get('current_category', '').title()}\n"
            f"Detailed content coming soon."
        )

    text_parts.append(f"\n{'━' * 28}")

    detail_text = "\n".join(text_parts)

    # Truncate if too long
    if len(detail_text) > 4000:
        detail_text = detail_text[:3997] + "..."

    category = atrain.get("current_category", "")
    await query.edit_message_text(
        detail_text,
        parse_mode="HTML",
        reply_markup=_summary_keyboard(category),
    )
    return AgentTrainingStates.VIEW_SUMMARY


# ---------------------------------------------------------------------------
# Step 3: Summary view actions (back navigation)
# ---------------------------------------------------------------------------

async def summary_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle actions from the product summary view."""
    query = update.callback_query
    await query.answer()
    data = query.data

    atrain = context.user_data.get("atrain", {})

    # Back to product list
    if data == "atrsum_back_products":
        category = atrain.get("current_category", "")
        products = atrain.get("products_cache", [])

        if products:
            await query.edit_message_text(
                f"{EMOJI_BOOK} <b>{category.title()} Training</b>\n\n"
                f"{EMOJI_STAR} Select a product:",
                parse_mode="HTML",
                reply_markup=_product_list_keyboard(products, category),
            )
            return AgentTrainingStates.SELECT_PRODUCT

        # Fallback to categories
        categories = atrain.get("categories", [])
        await query.edit_message_text(
            f"{EMOJI_BOOK} <b>Product Training</b>\n\n"
            f"{EMOJI_STAR} Select a category:",
            parse_mode="HTML",
            reply_markup=training_category_keyboard(categories),
        )
        return AgentTrainingStates.SELECT_CATEGORY

    # Back to categories
    if data == "atrcat_back":
        categories = atrain.get("categories", [])
        await query.edit_message_text(
            f"{EMOJI_BOOK} <b>Product Training</b>\n\n"
            f"{EMOJI_STAR} Select a category:",
            parse_mode="HTML",
            reply_markup=training_category_keyboard(categories),
        )
        return AgentTrainingStates.SELECT_CATEGORY

    return AgentTrainingStates.VIEW_SUMMARY


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

async def cancel_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel training flow."""
    context.user_data.pop("atrain", None)
    text = f"{EMOJI_CROSS} Training session ended."
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
        CommandHandler("training", training_command),
        CallbackQueryHandler(training_command, pattern=r"^agent_menu_training$"),
    ],
    states={
        AgentTrainingStates.SELECT_CATEGORY: [
            CallbackQueryHandler(select_category, pattern=r"^atrcat_"),
            CallbackQueryHandler(cancel_training, pattern=r"^agent_cancel$"),
        ],
        AgentTrainingStates.SELECT_PRODUCT: [
            CallbackQueryHandler(select_product, pattern=r"^atrprod_"),
            CallbackQueryHandler(select_category, pattern=r"^atrcat_"),
            CallbackQueryHandler(cancel_training, pattern=r"^agent_cancel$"),
        ],
        AgentTrainingStates.VIEW_SUMMARY: [
            CallbackQueryHandler(summary_action, pattern=r"^(atrsum_|atrcat_)"),
            CallbackQueryHandler(cancel_training, pattern=r"^agent_cancel$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_training),
        CommandHandler("training", training_command),
        CallbackQueryHandler(cancel_training, pattern=r"^(agent_cancel|cancel)$"),
    ],
    name="agent_training",
    persistent=False,
    per_user=True,
    per_chat=True,
    allow_reentry=True,
    conversation_timeout=600,
)
