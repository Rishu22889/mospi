"""
Data quality validation for scraped documents.
Performs basic checks: non-empty title, valid date, deduped records.
"""
from __future__ import annotations
import logging
import re
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ValidationError:
    def __init__(self, doc_id: str, field: str, message: str):
        self.doc_id = doc_id
        self.field = field
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationError(doc={self.doc_id}, field={self.field}, msg={self.message})"


def validate_document(doc: dict) -> List[ValidationError]:
    errors: List[ValidationError] = []
    doc_id = doc.get("id", "unknown")

    # Check non-empty title
    title = doc.get("title", "")
    if not title or not title.strip():
        errors.append(ValidationError(doc_id, "title", "Title is empty"))
    elif len(title.strip()) < 5:
        errors.append(ValidationError(doc_id, "title", f"Title too short: '{title}'"))

    # Check valid URL
    url = doc.get("url", "")
    if not url:
        errors.append(ValidationError(doc_id, "url", "URL is missing"))
    else:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            errors.append(ValidationError(doc_id, "url", f"Invalid URL: {url}"))

    # Check date (warn if missing but don't fail)
    date_pub = doc.get("date_published")
    if not date_pub:
        logger.warning({"event": "validation_warn", "doc_id": doc_id,
                        "field": "date_published", "msg": "Missing date"})

    # Check for minimum content
    raw_text = doc.get("raw_text", "") or ""
    summary = doc.get("summary", "") or ""
    if len(raw_text) < 20 and len(summary) < 20:
        errors.append(ValidationError(doc_id, "content",
                                       "Both raw_text and summary are too short"))

    return errors


def validate_all_documents(docs: List[dict]) -> Tuple[List[dict], List[ValidationError]]:
    """Validate a list of documents. Returns (valid_docs, all_errors)."""
    valid_docs = []
    all_errors: List[ValidationError] = []
    seen_urls: set = set()

    for doc in docs:
        errors = validate_document(doc)

        # Deduplication check
        url = doc.get("url", "")
        if url in seen_urls:
            errors.append(ValidationError(doc.get("id", "?"), "url",
                                           f"Duplicate URL: {url}"))
        else:
            seen_urls.add(url)

        if errors:
            all_errors.extend(errors)
            logger.warning({"event": "validation_failed", "doc_id": doc.get("id"),
                             "errors": [str(e) for e in errors]})
        else:
            valid_docs.append(doc)

    logger.info({"event": "validation_complete",
                 "total": len(docs), "valid": len(valid_docs),
                 "invalid": len(docs) - len(valid_docs)})
    return valid_docs, all_errors
