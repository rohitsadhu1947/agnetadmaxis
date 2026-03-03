"""
API Client for the Agent Telegram Bot.
Communicates with the backend's agent-portal endpoints.
"""

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

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        """Make an HTTP request and return parsed JSON or error dict."""
        try:
            resp = await self._client.request(method, url, **kwargs)
            if resp.status_code >= 400:
                detail = resp.text
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    pass
                return {"error": True, "status": resp.status_code, "detail": detail}
            return resp.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout: {method} {url}")
            return {"error": True, "status": 408, "detail": "Request timed out"}
        except Exception as e:
            logger.error(f"Request failed: {method} {url} — {e}")
            return {"error": True, "status": 500, "detail": str(e)}

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
    ) -> dict:
        """Submit agent feedback to a department."""
        payload = {"agent_id": agent_id, "channel": channel}
        if selected_reason_codes:
            payload["selected_reason_codes"] = selected_reason_codes
        if raw_feedback_text:
            payload["raw_feedback_text"] = raw_feedback_text
        if voice_file_id:
            payload["voice_file_id"] = voice_file_id
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


# Singleton
api_client = AgentAPIClient()
