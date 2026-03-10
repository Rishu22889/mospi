"""
Text chunking with overlap. Maintains doc->chunk lineage.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import List
import uuid

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    id: str
    doc_id: str
    doc_title: str
    doc_url: str
    doc_category: str
    doc_date: str
    text: str
    chunk_index: int
    total_chunks: int


def count_tokens(text: str) -> int:
    """Approximate token count (word-based ~ 0.75 tokens/word)."""
    words = len(text.split())
    return int(words * 1.3)


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences."""
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
    min_chars: int = 100,
) -> List[str]:
    """
    Chunk text by token count with sentence-boundary awareness and overlap.
    """
    if not text or not text.strip():
        return []

    sentences = split_into_sentences(text)
    if not sentences:
        return []

    chunks: List[str] = []
    current_sentences: List[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if current_tokens + sentence_tokens > chunk_size and current_sentences:
            chunk_text_str = " ".join(current_sentences)
            if len(chunk_text_str) >= min_chars:
                chunks.append(chunk_text_str)

            # Keep overlap sentences
            overlap_tokens = 0
            overlap_sents: List[str] = []
            for s in reversed(current_sentences):
                tok = count_tokens(s)
                if overlap_tokens + tok <= overlap:
                    overlap_sents.insert(0, s)
                    overlap_tokens += tok
                else:
                    break
            current_sentences = overlap_sents
            current_tokens = overlap_tokens

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    # Last chunk
    if current_sentences:
        chunk_text_str = " ".join(current_sentences)
        if len(chunk_text_str) >= min_chars:
            chunks.append(chunk_text_str)

    return chunks


def chunk_document(
    doc: dict,
    chunk_size: int = 1000,
    overlap: int = 150,
    min_chars: int = 100,
) -> List[Chunk]:
    """Chunk a document dict into Chunk objects with full lineage."""
    text = doc.get("raw_text") or doc.get("summary") or ""
    text_chunks = chunk_text(text, chunk_size, overlap, min_chars)

    if not text_chunks:
        logger.warning({"event": "empty_chunks", "doc_id": doc.get("id"),
                        "title": doc.get("title")})
        return []

    date_str = doc.get("date_published") or ""
    if hasattr(date_str, "isoformat"):
        date_str = date_str.isoformat()

    chunks = [
        Chunk(
            id=str(uuid.uuid4()),
            doc_id=doc["id"],
            doc_title=doc.get("title", ""),
            doc_url=doc.get("url", ""),
            doc_category=doc.get("category", ""),
            doc_date=str(date_str),
            text=chunk_text_str,
            chunk_index=i,
            total_chunks=len(text_chunks),
        )
        for i, chunk_text_str in enumerate(text_chunks)
    ]

    logger.info({"event": "chunked", "doc_id": doc.get("id"),
                 "chunks": len(chunks)})
    return chunks
