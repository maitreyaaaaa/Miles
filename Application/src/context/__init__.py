"""Context ingestion, structured knowledge extraction, and real-time fact auditing."""

from src.context.extractor import extract_text_from_file, extract_text_from_bytes
from src.context.analyzer import analyze_context_document, ContextDossier, NumericMetric
from src.context.store import ContextStore, get_context_store
from src.context.fact_auditor import FactAuditor, FactCheckResult

__all__ = [
    "extract_text_from_file",
    "extract_text_from_bytes",
    "analyze_context_document",
    "ContextDossier",
    "NumericMetric",
    "ContextStore",
    "get_context_store",
    "FactAuditor",
    "FactCheckResult",
]
