"""
Configuration for the ADM Platform Telegram Bot.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BotConfig:
    """Bot configuration loaded from environment variables."""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    BOT_USERNAME: str = "ADMPlatformBot"

    # Backend API
    API_BASE_URL: str = "http://localhost:8000/api/v1"
    API_TIMEOUT: int = 30

    # AI / Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Bot Behaviour
    DEFAULT_LANGUAGE: str = "en"  # "en" or "hi"
    MAX_AGENTS_PER_PAGE: int = 8
    QUIZ_QUESTIONS_COUNT: int = 3
    MORNING_BRIEFING_HOUR: int = 8  # 8 AM IST
    FOLLOW_UP_REMINDER_HOURS: list = field(default_factory=lambda: [9, 14, 18])

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Create config from environment variables."""
        return cls(
            TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            BOT_USERNAME=os.getenv("BOT_USERNAME", "ADMPlatformBot"),
            API_BASE_URL=os.getenv("API_BASE_URL", "http://localhost:8000/api/v1"),
            API_TIMEOUT=int(os.getenv("API_TIMEOUT", "30")),
            ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", ""),
            DEFAULT_LANGUAGE=os.getenv("DEFAULT_LANGUAGE", "en"),
            MAX_AGENTS_PER_PAGE=int(os.getenv("MAX_AGENTS_PER_PAGE", "8")),
            QUIZ_QUESTIONS_COUNT=int(os.getenv("QUIZ_QUESTIONS_COUNT", "3")),
            MORNING_BRIEFING_HOUR=int(os.getenv("MORNING_BRIEFING_HOUR", "8")),
            LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        )


# Singleton config instance
config = BotConfig.from_env()


# ---------------------------------------------------------------------------
# Conversation state constants (used by ConversationHandler)
# ---------------------------------------------------------------------------

# Feedback flow states
class FeedbackStates:
    SELECT_AGENT = 0
    SEARCH_AGENT = 1
    SELECT_CONTACT_TYPE = 2
    SELECT_OUTCOME = 3
    SELECT_CATEGORY = 4
    SELECT_SUBCATEGORY = 5
    ADD_NOTES = 6
    SET_FOLLOWUP = 7
    CONFIRM = 8


# Interaction logging states
class InteractionStates:
    SELECT_AGENT = 10
    SELECT_TYPE = 11       # NEW: feedback vs quick log
    SELECT_TOPIC = 12      # quick log path
    SELECT_OUTCOME = 13    # quick log path
    SCHEDULE_FOLLOWUP = 14 # quick log path
    ADD_NOTES = 15         # quick log path
    CONFIRM = 16           # quick log path
    # Feedback sub-flow (within /log)
    FB_SELECT_BUCKET = 17
    FB_SELECT_REASONS = 18
    FB_ADD_NOTES = 19
    FB_CONFIRM = 20


# Case history flow states
class CaseStates:
    SELECT_AGENT = 40
    VIEW_CASES = 41
    VIEW_CASE_DETAIL = 42
    REPLY_TO_CASE = 43


# Training flow states
class TrainingStates:
    SELECT_CATEGORY = 20
    SELECT_PRODUCT = 21
    VIEW_SUMMARY = 22
    START_QUIZ = 23
    ANSWER_QUIZ = 24
    QUIZ_RESULT = 25


# Diary flow states
class DiaryStates:
    VIEW_DIARY = 30
    ADD_ENTRY = 31
    ENTRY_DETAILS = 32
    RESCHEDULE = 33


# Registration states
# NOTE: Must NOT overlap with CaseStates (40-43) — was 40-43, now 60-63
class RegistrationStates:
    ENTER_NAME = 60
    ENTER_EMPLOYEE_ID = 61
    ENTER_REGION = 62
    CONFIRM_REGISTRATION = 63


# Product Q&A states
class AskStates:
    WAITING_QUESTION = 50
