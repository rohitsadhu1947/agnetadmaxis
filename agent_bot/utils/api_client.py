"""
API Client for the Agent Telegram Bot.
Communicates with the backend's agent-portal endpoints.

Includes retry logic with exponential backoff to handle Vercel
serverless cold starts (which can take 5-15 seconds).
"""

import asyncio
import logging
from typing import Optional, List

import httpx

from agent_bot.config import config

logger = logging.getLogger(__name__)


class AgentAPIClient:
    """Singleton HTTP client for agent bot → backend API communication."""

    _instance: Optional["AgentAPIClient"] = None

    def __new__(cls) -> "AgentAPIClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = httpx.AsyncClient(
                base_url=config.API_BASE_URL,
                timeout=config.API_TIMEOUT,
            )
        return cls._instance

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _request(self, method: str, url: str, retries: int = 2, **kwargs) -> dict:
        """Make an HTTP request with automatic retry on transient errors.

        Retries on 5xx errors, timeouts, and connection errors with
        exponential backoff (1s, 2s). Does NOT retry 4xx client errors.
        """
        last_error = None

        for attempt in range(1, retries + 2):  # 3 total attempts
            try:
                resp = await self._client.request(method, url, **kwargs)
                if resp.status_code >= 500:
                    # Server error — retry
                    last_error = {"error": True, "status": resp.status_code, "detail": resp.text[:200]}
                    logger.warning(
                        "API %s %s → %d (attempt %d/%d)",
                        method, url, resp.status_code, attempt, retries + 1,
                    )
                    if attempt <= retries:
                        await asyncio.sleep(attempt)  # 1s, 2s backoff
                    continue
                if resp.status_code >= 400:
                    detail = resp.text
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        pass
                    return {"error": True, "status": resp.status_code, "detail": detail}
                return resp.json()
            except httpx.TimeoutException:
                last_error = {"error": True, "status": 408, "detail": "Request timed out"}
                logger.warning(
                    "Timeout: %s %s (attempt %d/%d)", method, url, attempt, retries + 1,
                )
                if attempt <= retries:
                    await asyncio.sleep(attempt)
            except Exception as e:
                last_error = {"error": True, "status": 500, "detail": str(e)}
                logger.warning(
                    "Request error: %s %s — %s (attempt %d/%d)",
                    method, url, e, attempt, retries + 1,
                )
                if attempt <= retries:
                    await asyncio.sleep(attempt)

        logger.error("API %s %s failed after %d attempts", method, url, retries + 1)
        return last_error or {"error": True, "status": 500, "detail": "Request failed after retries"}

    async def _get(self, url: str, **kwargs) -> dict:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> dict:
        return await self._request("POST", url, **kwargs)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_agent(self, phone: str, telegram_chat_id: str) -> dict:
        """Register agent by phone number and link Telegram chat ID."""
        return await self._post("/agent-portal/register", json={
            "phone": phone,
            "telegram_chat_id": telegram_chat_id,
        })

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    async def get_agent_profile(self, agent_id: int) -> dict:
        """Get agent profile with cohort info."""
        return await self._get(f"/agent-portal/profile/{agent_id}")

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def submit_feedback(
        self,
        agent_id: int,
        channel: str = "telegram",
        selected_reason_codes: Optional[List[str]] = None,
        raw_feedback_text: Optional[str] = None,
        voice_file_id: Optional[str] = None,
        attachment_type: Optional[str] = None,
    ) -> dict:
        """Submit agent feedback to a department."""
        payload = {"agent_id": agent_id, "channel": channel}
        if selected_reason_codes:
            payload["selected_reason_codes"] = selected_reason_codes
        if raw_feedback_text:
            payload["raw_feedback_text"] = raw_feedback_text
        if voice_file_id:
            payload["voice_file_id"] = voice_file_id
        if attachment_type:
            payload["attachment_type"] = attachment_type
        return await self._post("/agent-portal/feedback/submit", json=payload)

    async def get_agent_tickets(
        self, agent_id: int, status: Optional[str] = None, skip: int = 0, limit: int = 20
    ) -> dict:
        """Get list of agent's feedback tickets."""
        params = {"skip": skip, "limit": limit}
        if status:
            params["status"] = status
        return await self._get(f"/agent-portal/feedback/tickets/{agent_id}", params=params)

    async def get_ticket_detail(self, ticket_id: str) -> dict:
        """Get single ticket detail with messages."""
        return await self._get(f"/agent-portal/feedback/ticket/{ticket_id}")

    async def reply_to_ticket(
        self,
        ticket_id: str,
        sender_name: str,
        message_text: str,
        sender_type: str = "agent",
        message_type: str = "text",
        voice_file_id: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ) -> dict:
        """Reply to a ticket."""
        payload = {
            "sender_type": sender_type,
            "sender_name": sender_name,
            "message_text": message_text,
            "message_type": message_type,
        }
        if voice_file_id:
            payload["voice_file_id"] = voice_file_id
        if metadata_json:
            payload["metadata_json"] = metadata_json
        return await self._post(f"/agent-portal/feedback/ticket/{ticket_id}/reply", json=payload)

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    async def get_training_modules(self, category: Optional[str] = None) -> dict:
        """Get available training modules."""
        params = {}
        if category:
            params["category"] = category
        return await self._get("/agent-portal/training/modules", params=params)

    # ------------------------------------------------------------------
    # AI Q&A
    # ------------------------------------------------------------------

    async def ask_product_question(self, question: str, context: Optional[str] = None) -> dict:
        """Ask an AI-powered product question."""
        payload = {"question": question}
        if context:
            payload["context"] = context
        return await self._post("/agent-portal/ask", json=payload)

    # ------------------------------------------------------------------
    # Taxonomy
    # ------------------------------------------------------------------

    async def get_reason_taxonomy(self, bucket: Optional[str] = None) -> dict:
        """Get reason taxonomy for feedback selection."""
        params = {}
        if bucket:
            params["bucket"] = bucket
        return await self._get("/feedback-tickets/taxonomy", params=params)

    # ------------------------------------------------------------------
    # People Feedback (concerns about assigned ADM / mentor)
    # Privacy: visible only to Agency Development team. NOT to ADM.
    # ------------------------------------------------------------------

    async def get_people_feedback_categories(self) -> dict:
        """Fetch the category tree the bot renders."""
        return await self._get("/people-feedback/meta/categories")

    async def submit_people_feedback(
        self,
        agent_id: int,
        category: str,
        subcategory: Optional[str] = None,
        other_text: Optional[str] = None,
        initial_text: Optional[str] = None,
        voice_file_id: Optional[str] = None,
        attachment_file_id: Optional[str] = None,
        attachment_file_name: Optional[str] = None,
        attachment_mime_type: Optional[str] = None,
    ) -> dict:
        """Submit a new people-feedback ticket."""
        payload = {
            "agent_id": agent_id,
            "category": category,
            "channel": "telegram",
        }
        if subcategory: payload["subcategory"] = subcategory
        if other_text: payload["other_text"] = other_text
        if initial_text: payload["initial_text"] = initial_text
        if voice_file_id: payload["voice_file_id"] = voice_file_id
        if attachment_file_id:
            payload["attachment_file_id"] = attachment_file_id
            payload["attachment_file_name"] = attachment_file_name
            payload["attachment_mime_type"] = attachment_mime_type
        return await self._post("/people-feedback/submit", json=payload)

    async def list_my_people_feedback(self, agent_id: int) -> dict:
        return await self._get(f"/people-feedback/agent/{agent_id}/list")

    async def get_my_people_feedback_detail(self, agent_id: int, ticket_id: int) -> dict:
        return await self._get(f"/people-feedback/agent/{agent_id}/{ticket_id}")

    async def reply_to_my_people_feedback(
        self,
        agent_id: int,
        ticket_id: int,
        text: Optional[str] = None,
        voice_file_id: Optional[str] = None,
        attachment_file_id: Optional[str] = None,
        attachment_file_name: Optional[str] = None,
        attachment_mime_type: Optional[str] = None,
    ) -> dict:
        payload = {}
        if text: payload["text"] = text
        if voice_file_id: payload["voice_file_id"] = voice_file_id
        if attachment_file_id:
            payload["attachment_file_id"] = attachment_file_id
            payload["attachment_file_name"] = attachment_file_name
            payload["attachment_mime_type"] = attachment_mime_type
        return await self._post(
            f"/people-feedback/agent/{agent_id}/{ticket_id}/reply", json=payload,
        )


# Singleton
api_client = AgentAPIClient()
