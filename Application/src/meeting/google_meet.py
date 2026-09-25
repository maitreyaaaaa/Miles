from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, Optional

from src.config import config
from src.meeting.scheduler import generate_meet_code

logger = logging.getLogger(__name__)


class GoogleMeetProvisioner:
    """Provisions real Google Meet links via the Google Calendar API v3."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or ""

    def _get_calendar_client(self):
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        if self.access_token:
            creds = Credentials(token=self.access_token)
            return build("calendar", "v3", credentials=creds, cache_discovery=False)
        elif config.google_refresh_token and config.google_client_id and config.google_client_secret:
            creds = Credentials(
                token=None,
                refresh_token=config.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=config.google_client_id,
                client_secret=config.google_client_secret,
            )
            return build("calendar", "v3", credentials=creds, cache_discovery=False)
        else:
            raise ValueError(
                "Google Calendar API credentials missing. "
                "Provide an access_token or configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
                "and GOOGLE_REFRESH_TOKEN in .env."
            )

    async def create_meeting_room(
        self,
        title: str = "Miles Adversarial Voice Sparring",
        duration_minutes: int = 30,
    ) -> Dict[str, Any]:
        """Create a real Google Calendar event with an attached Google Meet link."""
        import asyncio
        loop = asyncio.get_running_loop()

        if self.access_token or (config.google_refresh_token and config.google_client_id):
            try:
                return await loop.run_in_executor(None, self._sync_create_meeting, title, duration_minutes)
            except Exception as e:
                logger.error(f"[GoogleMeetProvisioner] Calendar API event creation failed: {e}")

        # Fallback to structured simulation link
        sim_url = generate_meet_code()
        return {
            "meet_url": sim_url,
            "event_id": f"sim_{uuid.uuid4().hex[:10]}",
            "is_real_meet": False,
            "provider_notice": (
                "Local simulation link generated. Configure GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET in .env to provision live Google Calendar Meet rooms."
            ),
        }

    def _sync_create_meeting(self, title: str, duration_minutes: int) -> Dict[str, Any]:
        cal = self._get_calendar_client()

        now = datetime.datetime.now(datetime.timezone.utc)
        start_time = now.isoformat()
        end_time = (now + datetime.timedelta(minutes=duration_minutes)).isoformat()
        request_id = f"miles_{uuid.uuid4().hex[:16]}"

        event_body = {
            "summary": title,
            "description": "Miles Full-Duplex AI Adversarial Sparring and Composure Session.",
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"},
            "conferenceData": {
                "createRequest": {
                    "requestId": request_id,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        created_event = cal.events().insert(
            calendarId="primary",
            body=event_body,
            conferenceDataVersion=1,
        ).execute()

        # Retrieve Google Meet URL
        meet_url = created_event.get("hangoutLink")
        if not meet_url and "conferenceData" in created_event:
            for ep in created_event["conferenceData"].get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    meet_url = ep.get("uri")
                    break

        if not meet_url:
            raise ValueError("Google Calendar event created, but no video conference link was attached.")

        logger.info(f"[GoogleMeetProvisioner] Provisioned real Google Meet: {meet_url}")
        return {
            "meet_url": meet_url,
            "event_id": created_event.get("id"),
            "is_real_meet": True,
            "html_link": created_event.get("htmlLink"),
            "provider_notice": "Live Google Meet room provisioned via Google Calendar.",
        }
