"""Short-lived capabilities used by Recall's hosted meeting webpage."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class InvalidBridgeTicket(ValueError):
    pass


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_bridge_ticket(
    *, meeting_id: str, owner_id: str, secret: str, expires_at: int
) -> str:
    if len(secret) < 32:
        raise ValueError("RECALL_AUDIO_BRIDGE_SECRET must contain at least 32 characters.")
    payload = _encode(json.dumps(
        {"meeting_id": meeting_id, "owner_id": owner_id, "expires_at": int(expires_at)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8"))
    signature = _encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_bridge_ticket(token: str, secret: str, *, now: int | None = None) -> Dict[str, Any]:
    if len(secret) < 32:
        raise InvalidBridgeTicket("Meeting audio bridge is not configured.")
    try:
        payload, supplied_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise InvalidBridgeTicket("Invalid meeting audio bridge ticket.")
        claims = json.loads(_decode(payload))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, InvalidBridgeTicket):
            raise
        raise InvalidBridgeTicket("Invalid meeting audio bridge ticket.") from exc

    expires_at = claims.get("expires_at")
    if (
        not isinstance(claims.get("meeting_id"), str)
        or not isinstance(claims.get("owner_id"), str)
        or not isinstance(expires_at, int)
        or expires_at <= (int(time.time()) if now is None else now)
    ):
        raise InvalidBridgeTicket("Meeting audio bridge ticket is invalid or expired.")
    return claims


def add_ticket_to_bridge_url(base_url: str, ticket: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError("RECALL_AUDIO_BRIDGE_URL must be a public HTTPS URL.")
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "ticket"]
    query.append(("ticket", ticket))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
