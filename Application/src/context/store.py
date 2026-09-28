from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from threading import RLock
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.context.analyzer import ContextDossier
from src.config import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_CONTEXTS_DIR = DATA_DIR / "contexts"


SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return isinstance(identifier, str) and bool(identifier and SAFE_ID_REGEX.match(identifier))


class ContextStore:
    """In-memory cache and persistent JSON storage for user-uploaded Context Dossiers."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DEFAULT_CONTEXTS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[tuple[str, str], ContextDossier] = {}
        self._loaded_owners: set[str] = set()
        self._lock = RLock()

    def _owner_directory(self, owner_id: str) -> Path:
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid owner_id.") from exc
        directory = (self.storage_dir / owner_id).resolve()
        if not directory.is_relative_to(self.storage_dir.resolve()):
            raise ValueError("Owner path escaped the context storage root.")
        return directory

    def _load_owner_from_disk(self, owner_id: str) -> None:
        """Load only the authenticated owner's context files into memory."""
        directory = self._owner_directory(owner_id)
        with self._lock:
            if owner_id in self._loaded_owners:
                return
            self._loaded_owners.add(owner_id)
        try:
            for file_path in directory.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        dossier = ContextDossier.from_dict(data)
                        self._cache[(owner_id, dossier.context_id)] = dossier
                except Exception as e:
                    logger.warning(f"[ContextStore] Failed to load {file_path}: {e}")
        except Exception as e:
            logger.error(f"[ContextStore] Error accessing a user's context directory: {e}")

    def save_context(self, owner_id: str, dossier: ContextDossier) -> str:
        """Store context dossier in memory and on disk."""
        if not is_safe_identifier(dossier.context_id):
            raise ValueError(f"Invalid context_id: {dossier.context_id}")

        owner_id = str(UUID(owner_id))
        directory = self._owner_directory(owner_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._load_owner_from_disk(owner_id)
        file_path = (directory / f"{dossier.context_id}.json").resolve()
        if not file_path.is_relative_to(directory):
            raise ValueError("Path traversal detected.")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(dossier.to_dict(), f, indent=2)
            with self._lock:
                self._cache[(owner_id, dossier.context_id)] = dossier
        except Exception as e:
            logger.error("[ContextStore] Failed to persist context dossier.", exc_info=True)
            raise OSError("Failed to persist context dossier.") from e
        return dossier.context_id

    def get_context(self, owner_id: str, context_id: str) -> Optional[ContextDossier]:
        """Retrieve context dossier by ID safely."""
        if not is_safe_identifier(context_id):
            logger.warning(f"[ContextStore] Rejected unsafe context_id: {context_id}")
            return None

        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return None
        self._load_owner_from_disk(owner_id)
        with self._lock:
            cached = self._cache.get((owner_id, context_id))
        if cached:
            return cached

        directory = self._owner_directory(owner_id)
        file_path = (directory / f"{context_id}.json").resolve()
        if not file_path.is_relative_to(directory):
            logger.warning(f"[ContextStore] Path traversal detected: {context_id}")
            return None

        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    dossier = ContextDossier.from_dict(data)
                    with self._lock:
                        self._cache[(owner_id, dossier.context_id)] = dossier
                    return dossier
            except Exception as e:
                logger.error(f"[ContextStore] Failed to read dossier {file_path}: {e}")
        return None

    def list_contexts(self, owner_id: str) -> List[Dict[str, Any]]:
        """Return metadata summary of the authenticated owner's contexts."""
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return []
        self._load_owner_from_disk(owner_id)
        with self._lock:
            owner_contexts = [d for (stored_owner, _), d in self._cache.items() if stored_owner == owner_id]
        results = []
        for dossier in sorted(owner_contexts, key=lambda d: d.created_at, reverse=True):
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

    def delete_context(self, owner_id: str, context_id: str) -> bool:
        """Remove one of the authenticated owner's contexts."""
        if not is_safe_identifier(context_id):
            return False
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return False
        directory = self._owner_directory(owner_id)
        with self._lock:
            self._cache.pop((owner_id, context_id), None)
        file_path = directory / f"{context_id}.json"
        if file_path.is_file():
            try:
                file_path.unlink()
                return True
            except Exception as e:
                logger.error(f"[ContextStore] Failed to delete {file_path}: {e}")
        return False


_STORE_INSTANCE: Optional[ContextStore] = None


def get_context_store() -> ContextStore:
    """Return the configured persistent context store."""
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        from src.storage import use_postgres_storage

        if use_postgres_storage():
            from src.storage.postgres_stores import PostgresContextStore

            _STORE_INSTANCE = PostgresContextStore()
        else:
            _STORE_INSTANCE = ContextStore()
    return _STORE_INSTANCE
