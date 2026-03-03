"""
Inline keyboard builders for the Agent Telegram Bot.
"""

from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _build_grid(items: List[dict], cols: int = 2) -> List[List[InlineKeyboardButton]]:
    """Build a grid of inline buttons from items."""
    buttons = [
        InlineKeyboardButton(text=item["text"], callback_data=item["data"])
        for item in items
    ]
    return [buttons[i:i + cols] for i in range(0, len(buttons), cols)]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    buttons = [
        [
            InlineKeyboardButton("\U0001f4dd Feedback", callback_data="agent_menu_feedback"),
            InlineKeyboardButton("\U0001f3ab Cases", callback_data="agent_menu_cases"),
        ],
        [
            InlineKeyboardButton("\U0001f4da Training", callback_data="agent_menu_training"),
            InlineKeyboardButton("\U0001f916 Ask AI", callback_data="agent_menu_ask"),
        ],
        [
            InlineKeyboardButton("\U0001f464 Profile", callback_data="agent_menu_profile"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def bucket_keyboard() -> InlineKeyboardMarkup:
    """Department bucket selection keyboard."""
    items = [
        {"text": "\U0001f4cb Underwriting", "data": "abkt_underwriting"},
        {"text": "\U0001f4b0 Finance", "data": "abkt_finance"},
        {"text": "\U0001f3c6 Contest", "data": "abkt_contest"},
        {"text": "\u2699\ufe0f Operations", "data": "abkt_operations"},
        {"text": "\U0001f4e6 Product", "data": "abkt_product"},
    ]
    grid = _build_grid(items, cols=2)
    grid.append([InlineKeyboardButton("\u274c Cancel", callback_data="agent_cancel")])
    return InlineKeyboardMarkup(grid)


def reason_keyboard(reasons: list, selected: set) -> InlineKeyboardMarkup:
    """Reason code multi-select keyboard with checkmarks."""
    items = []
    for reason in reasons:
        code = reason.get("code", "")
        name = reason.get("reason_name", code)
        check = "\u2705 " if code in selected else ""
        items.append({
            "text": f"{check}{code}: {name[:30]}",
            "data": f"arsn_{code}",
        })
    grid = _build_grid(items, cols=1)
    grid.append([
        InlineKeyboardButton("\u2705 Done", callback_data="arsn_done"),
        InlineKeyboardButton("\u274c Cancel", callback_data="agent_cancel"),
    ])
    return InlineKeyboardMarkup(grid)


def confirm_cancel_keyboard(confirm_data: str = "agent_confirm", cancel_data: str = "agent_cancel") -> InlineKeyboardMarkup:
    """Simple confirm/cancel keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 Confirm", callback_data=confirm_data),
            InlineKeyboardButton("\u274c Cancel", callback_data=cancel_data),
        ]
    ])


def ticket_list_keyboard(tickets: list) -> InlineKeyboardMarkup:
    """Keyboard for selecting a ticket from a list."""
    items = []
    for t in tickets[:10]:  # Max 10
        status_icon = "\U0001f7e2" if t.get("status") == "responded" else "\U0001f7e1"
        items.append({
            "text": f"{status_icon} {t['ticket_id']}",
            "data": f"atkt_{t['ticket_id']}",
        })
    grid = _build_grid(items, cols=2)
    grid.append([InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="agent_menu_home")])
    return InlineKeyboardMarkup(grid)


def ticket_action_keyboard(ticket_id: str) -> InlineKeyboardMarkup:
    """Actions for a specific ticket."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f4dd Reply", callback_data=f"atreply_{ticket_id}"),
            InlineKeyboardButton("\U0001f504 Refresh", callback_data=f"atrefresh_{ticket_id}"),
        ],
        [InlineKeyboardButton("\u2b05\ufe0f Back to Cases", callback_data="agent_menu_cases")],
    ])


def training_category_keyboard(categories: list) -> InlineKeyboardMarkup:
    """Training category selection."""
    items = [{"text": cat.title(), "data": f"atrcat_{cat}"} for cat in categories]
    grid = _build_grid(items, cols=2)
    grid.append([InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="agent_menu_home")])
    return InlineKeyboardMarkup(grid)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Simple back to main menu button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f3e0 Main Menu", callback_data="agent_menu_home")],
    ])
