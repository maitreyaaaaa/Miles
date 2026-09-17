from __future__ import annotations

import io
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MAX_CHAR_LIMIT = 60000


def _clean_extracted_text(text: str) -> str:
    """Normalize whitespace and strip unprintable characters."""
    if not text:
        return ""
    # Normalize multiple newlines/spaces
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Truncate if exceeds safe limit
    if len(text) > MAX_CHAR_LIMIT:
        text = text[:MAX_CHAR_LIMIT] + "\n\n[... Truncated for token safety ...]"
    return text.strip()


def extract_text_from_pdf_bytes(file_bytes: bytes) -> Dict[str, Any]:
    """Extract text and metadata from PDF bytes using PyMuPDF or pdfplumber/pypdf."""
    pages_text = []
    page_count = 0

    # 1. Try PyMuPDF (fitz)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(doc)
        for i in range(page_count):
            page = doc[i]
            t = page.get_text()
            if t.strip():
                pages_text.append(f"--- Page {i + 1} ---\n{t.strip()}")
        doc.close()
        if pages_text:
            combined = "\n\n".join(pages_text)
            return {
                "text": _clean_extracted_text(combined),
                "page_count": page_count,
                "extractor": "pymupdf",
            }
    except Exception as e:
        logger.debug(f"[Extractor] PyMuPDF failed: {e}. Trying pdfplumber fallback.")

    # 2. Try pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                # Also extract tables if present
                tables = page.extract_tables()
                table_lines = []
                for table in tables:
                    for row in table:
                        clean_row = [str(c or "").strip() for c in row if c is not None]
                        if any(clean_row):
                            table_lines.append(" | ".join(clean_row))
                if table_lines:
                    t += "\n" + "\n".join(table_lines)
                if t.strip():
                    pages_text.append(f"--- Page {i + 1} ---\n{t.strip()}")
        if pages_text:
            combined = "\n\n".join(pages_text)
            return {
                "text": _clean_extracted_text(combined),
                "page_count": page_count,
                "extractor": "pdfplumber",
            }
    except Exception as e:
        logger.debug(f"[Extractor] pdfplumber failed: {e}. Trying pypdf fallback.")

    # 3. Try pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            if t.strip():
                pages_text.append(f"--- Page {i + 1} ---\n{t.strip()}")
        if pages_text:
            combined = "\n\n".join(pages_text)
            return {
                "text": _clean_extracted_text(combined),
                "page_count": page_count,
                "extractor": "pypdf",
            }
    except Exception as e:
        logger.warning(f"[Extractor] All PDF extractors failed: {e}")

    return {
        "text": _clean_extracted_text("\n\n".join(pages_text)),
        "page_count": page_count,
        "extractor": "none",
    }


def extract_text_from_docx_bytes(file_bytes: bytes) -> Dict[str, Any]:
    """Extract text and tables from Word (.docx) file bytes."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        
        # Also parse tables
        table_lines = []
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    table_lines.append(" | ".join(cells))
        
        combined_parts = paragraphs
        if table_lines:
            combined_parts.append("\n=== Data Tables ===\n" + "\n".join(table_lines))
            
        full_text = "\n\n".join(combined_parts)
        return {
            "text": _clean_extracted_text(full_text),
            "page_count": max(1, len(full_text) // 2500),
            "extractor": "python-docx",
        }
    except Exception as e:
        logger.error(f"[Extractor] docx extraction failed: {e}")
        return {"text": "", "page_count": 0, "extractor": "error"}


def extract_text_from_csv_bytes(file_bytes: bytes) -> Dict[str, Any]:
    """Extract and format tabular CSV data."""
    try:
        import csv
        text_content = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text_content))
        lines = []
        for row in reader:
            if any(cell.strip() for cell in row):
                lines.append(" | ".join(cell.strip() for cell in row))
        table_str = "\n".join(lines[:500])  # limit rows
        return {
            "text": _clean_extracted_text(table_str),
            "page_count": 1,
            "extractor": "csv",
        }
    except Exception as e:
        logger.error(f"[Extractor] CSV extraction failed: {e}")
        return {"text": "", "page_count": 0, "extractor": "error"}


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Universal extractor routing by filename extension."""
    lower = filename.lower().strip()
    ext = os.path.splitext(lower)[1]

    if ext == ".pdf":
        res = extract_text_from_pdf_bytes(file_bytes)
    elif ext in (".docx", ".doc"):
        res = extract_text_from_docx_bytes(file_bytes)
    elif ext in (".csv", ".tsv"):
        res = extract_text_from_csv_bytes(file_bytes)
    elif ext in (".txt", ".md", ".json", ".markdown"):
        decoded = file_bytes.decode("utf-8", errors="replace")
        res = {"text": _clean_extracted_text(decoded), "page_count": 1, "extractor": "text"}
    else:
        # Generic decode attempt
        try:
            decoded = file_bytes.decode("utf-8", errors="replace")
            res = {"text": _clean_extracted_text(decoded), "page_count": 1, "extractor": "generic_text"}
        except Exception:
            res = {"text": "", "page_count": 0, "extractor": "unknown"}

    text = res.get("text", "")
    words = len(text.split()) if text else 0
    return {
        "filename": filename,
        "format": ext.lstrip(".") or "txt",
        "text": text,
        "page_count": res.get("page_count", 1),
        "word_count": words,
        "char_count": len(text),
        "extractor": res.get("extractor", "unknown"),
    }


def extract_text_from_file(file_path: str) -> Dict[str, Any]:
    """Read a local file from disk and extract its text."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    return extract_text_from_bytes(file_bytes, filename)
