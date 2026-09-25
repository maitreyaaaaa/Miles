from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, Optional, Tuple
import urllib.parse

import httpx

from src.config import config

logger = logging.getLogger(__name__)

# Scopes needed for Google Drive and Google Calendar/Meet
GOOGLE_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
]

# Patterns for Google Drive, Docs, Sheets, Slides URLs
DOCS_URL_PATTERNS = [
    re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)"),
    re.compile(r"drive\.google\.com/uc\?id=([a-zA-Z0-9_-]+)"),
]


def extract_google_drive_file_id(url_or_id: str) -> Optional[str]:
    """Extract file ID from a Google Drive/Docs URL or return raw ID if already valid."""
    cleaned = (url_or_id or "").strip()
    if not cleaned:
        return None

    for pattern in DOCS_URL_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return match.group(1)

    # If it's a bare alphanumeric string with dashes/underscores (typically 25-45 chars)
    if re.match(r"^[a-zA-Z0-9_-]{20,60}$", cleaned):
        return cleaned

    return None


def get_google_auth_url(redirect_uri: Optional[str] = None, state: Optional[str] = None) -> str:
    """Generate the Google OAuth 2.0 authorization URL for Drive and Calendar."""
    client_id = config.google_client_id
    if not client_id:
        raise ValueError("GOOGLE_CLIENT_ID is not configured in .env.")

    redirect = redirect_uri or config.google_redirect_uri
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(GOOGLE_OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state

    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


async def exchange_google_code_for_tokens(
    code: str,
    redirect_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange OAuth authorization code for Google access and refresh tokens."""
    client_id = config.google_client_id
    client_secret = config.google_client_secret
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured.")

    redirect = redirect_uri or config.google_redirect_uri
    token_url = "https://oauth2.googleapis.com/token"

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=payload)
        if resp.status_code != 200:
            logger.error(f"[GoogleOAuth] Token exchange failed: {resp.text}")
            raise ValueError(f"Google token exchange failed ({resp.status_code}): {resp.text}")
        return resp.json()


async def refresh_google_access_token(refresh_token: str) -> Dict[str, Any]:
    """Obtain a new access token using a refresh token."""
    client_id = config.google_client_id
    client_secret = config.google_client_secret
    if not client_id or not client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured.")

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=payload)
        if resp.status_code != 200:
            logger.error(f"[GoogleOAuth] Refresh token exchange failed: {resp.text}")
            raise ValueError(f"Failed to refresh Google token ({resp.status_code}): {resp.text}")
        return resp.json()


async def download_public_google_doc_export(file_id: str) -> Optional[Tuple[str, str, bytes]]:
    """Attempt direct export download for publicly shared Google Docs, Sheets, or Slides.
    
    Returns (filename, mime_type, file_bytes) or None.
    """
    export_targets = [
        # Google Docs as text
        (f"https://docs.google.com/document/d/{file_id}/export?format=txt", "text/plain", f"GoogleDoc_{file_id[:8]}.txt"),
        # Google Sheets as CSV
        (f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv", "text/csv", f"GoogleSheet_{file_id[:8]}.csv"),
        # Google Slides as PDF
        (f"https://docs.google.com/presentation/d/{file_id}/export/pdf", "application/pdf", f"GoogleSlides_{file_id[:8]}.pdf"),
        # Google Drive public binary download
        (f"https://drive.google.com/uc?export=download&id={file_id}", "application/octet-stream", f"GoogleDriveFile_{file_id[:8]}.pdf"),
    ]

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for url, mime, filename in export_targets:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 100:
                    # Check if response is not an HTML login/permission page
                    content_type = resp.headers.get("content-type", "").lower()
                    if "text/html" in content_type and b"<html" in resp.content[:200].lower():
                        continue
                    return filename, mime, resp.content
            except Exception as e:
                logger.debug(f"[GoogleDocPublicExport] Failed {url}: {e}")

    return None


class GoogleDriveService:
    """Service to interact with Google Drive API v3 for downloading documents and exporting reports."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or ""

    def _get_drive_client(self):
        """Construct authenticated Google Drive API v3 service."""
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        if self.access_token:
            creds = Credentials(token=self.access_token)
            return build("drive", "v3", credentials=creds, cache_discovery=False)
        elif config.google_refresh_token and config.google_client_id and config.google_client_secret:
            creds = Credentials(
                token=None,
                refresh_token=config.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=config.google_client_id,
                client_secret=config.google_client_secret,
            )
            return build("drive", "v3", credentials=creds, cache_discovery=False)
        elif config.google_api_key:
            return build("drive", "v3", developerKey=config.google_api_key, cache_discovery=False)
        else:
            raise ValueError(
                "Neither Google OAuth credentials nor GOOGLE_API_KEY is configured. "
                "Authenticate via Google OAuth or configure credentials in .env."
            )

    async def fetch_document(self, file_id: str) -> Dict[str, Any]:
        """Fetch file metadata and download or export content from Google Drive.
        
        Handles Google Docs, Sheets, Slides, and binary uploaded files (PDF, DOCX, CSV, TXT).
        """
        # Try authenticated Google Drive API first if credentials are present
        if self.access_token or config.google_api_key:
            try:
                return await self._fetch_via_api(file_id)
            except Exception as e:
                logger.warning(f"[GoogleDrive] Authenticated Drive API fetch failed: {e}. Trying public fallback.")

        # Fallback to public document export
        public_result = await download_public_google_doc_export(file_id)
        if public_result:
            filename, mime, file_bytes = public_result
            return {
                "file_id": file_id,
                "filename": filename,
                "mime_type": mime,
                "file_bytes": file_bytes,
                "source": "google_drive_public",
            }

        raise ValueError(
            f"Unable to access Google Drive file '{file_id}'. "
            "Ensure the document is shared ('Anyone with the link can view') or connect your Google account."
        )

    async def _fetch_via_api(self, file_id: str) -> Dict[str, Any]:
        """Internal synchronous API call executed in executor for async compatibility."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_fetch_via_api, file_id)

    def _sync_fetch_via_api(self, file_id: str) -> Dict[str, Any]:
        from googleapiclient.http import MediaIoBaseDownload

        drive = self._get_drive_client()
        # 1. Fetch metadata
        meta = drive.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size",
            supportsAllDrives=True,
        ).execute()

        name = meta.get("name", f"GoogleDrive_{file_id}")
        mime_type = meta.get("mimeType", "")
        file_bytes = b""

        # 2. Check if Google Workspace document (Doc, Sheet, Slide)
        if mime_type == "application/vnd.google-apps.document":
            # Export as clean plain text
            request = drive.files().export_media(fileId=file_id, mimeType="text/plain")
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            file_bytes = fh.getvalue()
            if not name.endswith(".txt"):
                name += ".txt"

        elif mime_type == "application/vnd.google-apps.spreadsheet":
            # Export first sheet as CSV
            request = drive.files().export_media(fileId=file_id, mimeType="text/csv")
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            file_bytes = fh.getvalue()
            if not name.endswith(".csv"):
                name += ".csv"

        elif mime_type == "application/vnd.google-apps.presentation":
            # Export presentation as PDF
            request = drive.files().export_media(fileId=file_id, mimeType="application/pdf")
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            file_bytes = fh.getvalue()
            if not name.endswith(".pdf"):
                name += ".pdf"

        else:
            # Binary file (PDF, DOCX, TXT uploaded to drive)
            request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            file_bytes = fh.getvalue()

        return {
            "file_id": file_id,
            "filename": name,
            "mime_type": mime_type,
            "file_bytes": file_bytes,
            "source": "google_drive_api",
        }

    async def export_debrief_pdf(
        self,
        pdf_bytes: bytes,
        filename: str = "Miles_Debrief_Report.pdf",
    ) -> Dict[str, Any]:
        """Upload the generated Executive Debrief PDF into the user's Google Drive."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_export_pdf, pdf_bytes, filename)

    def _sync_export_pdf(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
        from googleapiclient.http import MediaIoBaseUpload

        if not self.access_token:
            raise ValueError("Google OAuth access_token is required to upload files to Google Drive.")

        drive = self._get_drive_client()
        file_metadata = {
            "name": filename,
            "mimeType": "application/pdf",
        }
        media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=True)
        file_obj = drive.files().create(body=file_metadata, media_body=media, fields="id, name, webViewLink").execute()

        logger.info(f"[GoogleDrive] Successfully uploaded debrief PDF to Drive: {file_obj.get('id')}")
        return {
            "file_id": file_obj.get("id"),
            "name": file_obj.get("name"),
            "web_view_link": file_obj.get("webViewLink"),
        }
