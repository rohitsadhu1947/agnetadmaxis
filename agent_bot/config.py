"""
Configuration for the Agent Telegram Bot.
Separate from the ADM bot — uses its own bot token.
"""

import os
from dataclasses import dataclass, field


@dataclass
class AgentBotConfig:
    """Agent bot configuration loaded from environment variables."""

    # Telegram
    AGENT_TELEGRAM_BOT_TOKEN: str = ""
    BOT_USERNAME: str = "AxisAgentBot"

    # Backend API
    API_BASE_URL: str = "http://localhost:8000/api/v1"
    API_TIMEOUT: int = 30

    # AI / Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Bot Behaviour
    DEFAULT_LANGUAGE: str = "en"
    MAX_ITEMS_PER_PAGE: int = 8

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def from_env(cls) -> "AgentBotConfig":
        return cls(
            AGENT_TELEGRAM_BOT_TOKEN=os.getenv("AGENT_TELEGRAM_BOT_TOKEN", ""),
            BOT_USERNAME=os.getenv("AGENT_BOT_USERNAME", "AxisAgentBot"),
            API_BASE_URL=os.getenv("API_BASE_URL", "http://localhost:8000/api/v1"),
            API_TIMEOUT=int(os.getenv("API_TIMEOUT", "30")),
            ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", ""),
            DEFAULT_LANGUAGE=os.getenv("DEFAULT_LANGUAGE", "en"),
            MAX_ITEMS_PER_PAGE=int(os.getenv("MAX_ITEMS_PER_PAGE", "8")),
            LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        )


config = AgentBotConfig.from_env()


# ---------------------------------------------------------------------------
# Conversation state constants (100+ range, non-overlapping with ADM bot)
# ---------------------------------------------------------------------------

class AgentRegistrationStates:
    ENTER_PHONE = 160
    CONFIRM_REGISTRATION = 161


class AgentFeedbackStates:
    SELECT_BUCKET = 100
    SELECT_REASONS = 101
    ADD_NOTES = 102
    CONFIRM = 103


class AgentCaseStates:
    VIEW_CASES = 120
    VIEW_CASE_DETAIL = 121
    REPLY_TO_CASE = 122


class AgentTrainingStates:
    SELECT_CATEGORY = 140
    SELECT_PRODUCT = 141
    VIEW_SUMMARY = 142
    START_QUIZ = 143
    ANSWER_QUIZ = 144
    QUIZ_RESULT = 145


class AgentAskStates:
    WAITING_QUESTION = 170


class AgentProfileStates:
    VIEW_PROFILE = 180
