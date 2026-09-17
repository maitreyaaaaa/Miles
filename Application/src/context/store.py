from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from src.context.analyzer import ContextDossier

logger = logging.getLogger(__name__)

DEFAULT_CONTEXTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "contexts"


SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return bool(identifier and SAFE_ID_REGEX.match(identifier))


class ContextStore:
    """In-memory cache and persistent JSON storage for user-uploaded Context Dossiers."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DEFAULT_CONTEXTS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, ContextDossier] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        """Pre-load existing JSON files from disk on initialization."""
        try:
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        dossier = ContextDossier.from_dict(data)
                        self._cache[dossier.context_id] = dossier
                except Exception as e:
                    logger.warning(f"[ContextStore] Failed to load {file_path}: {e}")
        except Exception as e:
            logger.error(f"[ContextStore] Error accessing storage directory {self.storage_dir}: {e}")

    def save_context(self, dossier: ContextDossier) -> str:
        """Store context dossier in memory and on disk."""
        if not is_safe_identifier(dossier.context_id):
            raise ValueError(f"Invalid context_id: {dossier.context_id}")

        self._cache[dossier.context_id] = dossier
        file_path = (self.storage_dir / f"{dossier.context_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_dir.resolve()):
            raise ValueError("Path traversal detected.")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(dossier.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"[ContextStore] Failed to persist dossier to {file_path}: {e}")
        return dossier.context_id

    def get_context(self, context_id: str) -> Optional[ContextDossier]:
        """Retrieve context dossier by ID safely."""
        if not is_safe_identifier(context_id):
            logger.warning(f"[ContextStore] Rejected unsafe context_id: {context_id}")
            return None

        if context_id in self._cache:
            return self._cache[context_id]

        file_path = (self.storage_dir / f"{context_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_dir.resolve()):
            logger.warning(f"[ContextStore] Path traversal detected: {context_id}")
            return None

        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    dossier = ContextDossier.from_dict(data)
                    self._cache[dossier.context_id] = dossier
                    return dossier
            except Exception as e:
                logger.error(f"[ContextStore] Failed to read dossier {file_path}: {e}")
        return None

    def list_contexts(self) -> List[Dict[str, Any]]:
        """Return metadata summary of all stored contexts."""
        results = []
        for dossier in sorted(self._cache.values(), key=lambda d: d.created_at, reverse=True):
            results.append({
                "context_id": dossier.context_id,
                "filename": dossier.filename,
                "doc_type": dossier.doc_type,
                "title": dossier.title,
                "metric_count": len(dossier.numeric_metrics),
                "claim_count": len(dossier.core_claims),
                "recommended_scenario": dossier.recommended_scenario,
                "created_at": dossier.created_at,
            })
        return results

    def delete_context(self, context_id: str) -> bool:
        """Remove a context by ID."""
        self._cache.pop(context_id, None)
        file_path = self.storage_dir / f"{context_id}.json"
        if file_path.is_file():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"[ContextStore] Failed to delete {file_path}: {e}")
        return False


_STORE_INSTANCE: Optional[ContextStore] = None


def get_context_store() -> ContextStore:
    """Return the global ContextStore singleton."""
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = ContextStore()
    return _STORE_INSTANCE
