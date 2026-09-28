from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.config import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_DEBRIEFS_DIR = DATA_DIR / "debriefs"
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return isinstance(identifier, str) and bool(identifier and SAFE_ID_REGEX.match(identifier))


class DebriefReportStore:
    """In-memory cache and persistent JSON storage for shareable Debrief Reports."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DEFAULT_DEBRIEFS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._report_cache: Dict[tuple[str, str], Dict[str, Any]] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        try:
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        share_id = data.get("share_id") or file_path.stem
                        self._cache[share_id] = data
                except Exception as e:
                    logger.warning(f"[DebriefReportStore] Failed to load {file_path}: {e}")
        except Exception as e:
            logger.error(f"[DebriefReportStore] Error reading {self.storage_dir}: {e}")

    def save_debrief(
        self,
        report: Dict[str, Any],
        owner_id: str,
    ) -> str:
        share_id = f"deb_{secrets.token_urlsafe(18)}"
        while self.get_debrief(share_id) is not None:
            share_id = f"deb_{secrets.token_urlsafe(18)}"

        report_copy = dict(report)
        report_copy["share_id"] = share_id
        if owner_id:
            report_copy["owner_id"] = owner_id
        report_copy.setdefault("share_created_at", time.time())
        report_copy.setdefault("share_scope", "unguessable_read_only_link")

        self._cache[share_id] = report_copy
        file_path = (self.storage_dir / f"{share_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_dir.resolve()):
            raise ValueError("Path traversal detected.")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_copy, f, indent=2)
            logger.info(f"[DebriefReportStore] Saved shareable debrief {share_id} to {file_path}")
        except Exception as e:
            logger.error(f"[DebriefReportStore] Failed to write debrief {share_id}: {e}", exc_info=True)
            raise

        return share_id

    def save_report(self, report: Dict[str, Any], owner_id: str) -> None:
        """Persist a private debate report under its verified owner's directory."""
        session_id = report.get("session_id")
        if not is_safe_identifier(session_id):
            raise ValueError("A valid session_id is required to store a private report.")
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid report owner.") from exc

        owner_dir = (self.storage_dir / "reports" / owner_id).resolve()
        reports_root = (self.storage_dir / "reports").resolve()
        if not owner_dir.is_relative_to(reports_root):
            raise ValueError("Report owner path escaped the storage root.")
        owner_dir.mkdir(parents=True, exist_ok=True)
        file_path = (owner_dir / f"{session_id}.json").resolve()
        if not file_path.is_relative_to(owner_dir):
            raise ValueError("Report path escaped the owner directory.")

        report_copy = dict(report)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=owner_dir, prefix=f".{session_id}.", suffix=".tmp", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(report_copy, temp_file, indent=2)
            os.replace(temp_path, file_path)
            self._report_cache[(owner_id, session_id)] = report_copy
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    def get_report(self, session_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        """Read a private report only when both owner and session match."""
        if not is_safe_identifier(session_id):
            return None
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return None

        cached = self._report_cache.get((owner_id, session_id))
        if cached is not None:
            return dict(cached)

        reports_root = (self.storage_dir / "reports").resolve()
        owner_dir = (reports_root / owner_id).resolve()
        file_path = (owner_dir / f"{session_id}.json").resolve()
        if not owner_dir.is_relative_to(reports_root) or not file_path.is_relative_to(owner_dir) or not file_path.is_file():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as report_file:
                report = json.load(report_file)
            if report.get("session_id") != session_id:
                return None
            self._report_cache[(owner_id, session_id)] = report
            return dict(report)
        except Exception as exc:
            logger.error("[DebriefReportStore] Could not read private report %s: %s", session_id, exc)
            return None

    def get_debrief(self, share_id: str, owner_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not is_safe_identifier(share_id):
            return None

        if share_id in self._cache:
            report = self._cache[share_id]
            return report if owner_id is None or report.get("owner_id") == owner_id else None

        file_path = (self.storage_dir / f"{share_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_dir.resolve()) or not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._cache[share_id] = data
                return data if owner_id is None or data.get("owner_id") == owner_id else None
        except Exception as e:
            logger.error(f"[DebriefReportStore] Error loading {file_path}: {e}")
            return None


_GLOBAL_STORE: Optional[DebriefReportStore] = None


def get_debrief_store() -> DebriefReportStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        from src.storage import use_postgres_storage

        if use_postgres_storage():
            from src.storage.postgres_stores import PostgresDebriefReportStore

            _GLOBAL_STORE = PostgresDebriefReportStore()
        else:
            _GLOBAL_STORE = DebriefReportStore()
    return _GLOBAL_STORE
