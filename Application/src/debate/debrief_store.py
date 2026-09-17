from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import secrets
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DEBRIEFS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "debriefs"
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return bool(identifier and SAFE_ID_REGEX.match(identifier))


class DebriefReportStore:
    """In-memory cache and persistent JSON storage for shareable Debrief Reports."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DEFAULT_DEBRIEFS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
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

    def save_debrief(self, report: Dict[str, Any], custom_share_id: Optional[str] = None) -> str:
        share_id = custom_share_id or f"deb_{secrets.token_urlsafe(18)}"
        if not is_safe_identifier(share_id):
            raise ValueError(f"Invalid share_id: {share_id}")

        report_copy = dict(report)
        report_copy["share_id"] = share_id
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

    def get_debrief(self, share_id: str) -> Optional[Dict[str, Any]]:
        if not is_safe_identifier(share_id):
            return None

        if share_id in self._cache:
            return self._cache[share_id]

        file_path = (self.storage_dir / f"{share_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_dir.resolve()) or not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._cache[share_id] = data
                return data
        except Exception as e:
            logger.error(f"[DebriefReportStore] Error loading {file_path}: {e}")
            return None


_GLOBAL_STORE: Optional[DebriefReportStore] = None


def get_debrief_store() -> DebriefReportStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = DebriefReportStore()
    return _GLOBAL_STORE
