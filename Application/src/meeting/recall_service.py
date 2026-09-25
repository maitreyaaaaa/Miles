"""
Recall.ai Cloud Meeting Bot Service.

Integrates with Recall.ai API v1 across global regions (defaulting to ap-northeast-1).
Supports ad-hoc meeting bot deployment, calendar-based scheduled bots,
bot lifecycle polling, and cryptographic webhook signature verification.
"""

from __future__ import annotations

import base64
import datetime
import hmac
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union
import httpx

from src.config import config

logger = logging.getLogger(__name__)


class RecallAPIError(Exception):
    """Raised when Recall.ai returns an error response."""
    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or message


class RecallService:
    """Production client for Recall.ai meeting bot management."""

    def __init__(self, api_key: Optional[str] = None, region: Optional[str] = None):
        self.api_key = config.recall_ai_api_key if api_key is None else api_key
        self.region = (config.recall_ai_region or "ap-northeast-1") if region is None else region
        self.base_url = f"https://{self.region}.recall.ai/api/v1"

    @property
    def headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RecallAPIError("RECALL_AI_API_KEY is not configured.", status_code=401)
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_bot(
        self,
        meeting_url: str,
        bot_name: str = "Miles AI Adversary",
        join_at: Optional[Union[str, datetime.datetime]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        transcription_provider: Optional[str] = "assemblyai",
    ) -> Dict[str, Any]:
        """Deploy an ad-hoc or scheduled meeting bot.
        
        Args:
            meeting_url: Google Meet, Zoom, or Microsoft Teams room link.
            bot_name: Display name of the bot participant in the meeting.
            join_at: Optional ISO8601 string or datetime. If >10 mins in future, schedules a bot.
            metadata: Custom key-value pairs (e.g. session_id, context_id).
            transcription_provider: Preferred transcription engine ('assemblyai' or default).
        """
        payload: Dict[str, Any] = {
            "meeting_url": meeting_url.strip(),
            "bot_name": bot_name.strip(),
            "automatic_leave": {
                "anyone_leaves": False,
                "bot_alone": True,
                "silence_detection": True,
            },
        }

        if join_at:
            if isinstance(join_at, datetime.datetime):
                # Ensure UTC ISO format
                if join_at.tzinfo is None:
                    join_at = join_at.replace(tzinfo=datetime.timezone.utc)
                payload["join_at"] = join_at.isoformat()
            else:
                payload["join_at"] = str(join_at).strip()

        if metadata:
            payload["metadata"] = metadata

        if transcription_provider:
            payload["transcription_options"] = {"provider": transcription_provider}

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.post(f"{self.base_url}/bot/", headers=self.headers, json=payload)
            except httpx.RequestError as exc:
                logger.error(f"[RecallService] Network error creating bot: {exc}")
                raise RecallAPIError(f"Network error communicating with Recall.ai: {exc}", status_code=503)

            if resp.status_code in (200, 201):
                data = resp.json()
                logger.info(f"[RecallService] Successfully spawned bot {data.get('id')} for {meeting_url}")
                return data

            err_text = resp.text
            logger.error(f"[RecallService] Failed to create bot ({resp.status_code}): {err_text}")
            raise RecallAPIError(
                f"Recall.ai error ({resp.status_code}): {err_text}",
                status_code=resp.status_code,
                detail=err_text,
            )

    async def get_bot(self, bot_id: str) -> Dict[str, Any]:
        """Fetch real-time status, lifecycle events, and recordings for a bot."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/bot/{bot_id}/", headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
            raise RecallAPIError(
                f"Failed to fetch bot {bot_id} ({resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )

    async def leave_call(self, bot_id: str) -> bool:
        """Command an in-call or joining bot to exit the meeting room."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self.base_url}/bot/{bot_id}/leave_call/", headers=self.headers)
            if resp.status_code in (200, 204):
                logger.info(f"[RecallService] Bot {bot_id} instructed to leave call.")
                return True
            logger.warning(f"[RecallService] Bot {bot_id} leave_call returned {resp.status_code}: {resp.text}")
            return False

    async def delete_scheduled_bot(self, bot_id: str) -> bool:
        """Delete/cancel a future scheduled bot before it begins joining."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(f"{self.base_url}/bot/{bot_id}/", headers=self.headers)
            if resp.status_code in (200, 204):
                logger.info(f"[RecallService] Scheduled bot {bot_id} deleted.")
                return True
            return False

    async def list_bots(
        self,
        limit: int = 20,
        join_at_after: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List active and scheduled bots."""
        params: Dict[str, Any] = {}
        if join_at_after:
            params["join_at_after"] = join_at_after

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/bot/", headers=self.headers, params=params)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                return results[:limit]
            return []

    @staticmethod
    def verify_webhook_signature(
        headers: Dict[str, str],
        payload: Union[str, bytes],
        secret: Optional[str] = None,
    ) -> bool:
        """Verify HMAC-SHA256 signature on incoming Recall.ai webhook requests.
        
        Follows Recall.ai cryptographic verification standard:
        toSign = "{webhook-id}.{webhook-timestamp}.{raw_payload}"
        """
        webhook_secret = secret or config.recall_ai_webhook_secret
        if not webhook_secret:
            # If no verification secret configured in .env, skip verification in dev
            logger.warning("[RecallWebhook] RECALL_AI_WEBHOOK_SECRET is not configured; skipping verification.")
            return True

        # Standardize headers (case-insensitive)
        lower_headers = {k.lower(): v for k, v in headers.items()}
        msg_id = lower_headers.get("webhook-id") or lower_headers.get("svix-id")
        msg_timestamp = lower_headers.get("webhook-timestamp") or lower_headers.get("svix-timestamp")
        msg_signature = lower_headers.get("webhook-signature") or lower_headers.get("svix-signature")

        if not msg_id or not msg_timestamp or not msg_signature:
            logger.warning("[RecallWebhook] Missing verification headers.")
            return False

        # Prepare raw payload string
        payload_str = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)

        # Handle 'whsec_' prefix
        raw_secret = webhook_secret[6:] if webhook_secret.startswith("whsec_") else webhook_secret
        try:
            key_bytes = base64.b64decode(raw_secret)
        except Exception:
            key_bytes = raw_secret.encode("utf-8")

        to_sign = f"{msg_id}.{msg_timestamp}.{payload_str}".encode("utf-8")
        expected_sig = base64.b64encode(hmac.new(key_bytes, to_sign, hashlib.sha256).digest()).decode("utf-8")

        # Recall delivers signatures formatted as: "v1,signature1 v1,signature2"
        for candidate in msg_signature.split():
            parts = candidate.split(",", 1)
            if len(parts) == 2 and parts[0] == "v1":
                if hmac.compare_digest(parts[1], expected_sig):
                    return True

        logger.warning("[RecallWebhook] HMAC signature mismatch.")
        return False
