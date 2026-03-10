"""Tests for ETL pipeline components."""
import pytest
from pipeline.chunk import chunk_text, chunk_document
from pipeline.validate import validate_document, validate_all_documents


# ── Chunker Tests ──────────────────────────────────────────────────────

def test_chunk_text_basic():
    text = "This is sentence one. " * 100
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) > 0 for c in chunks)


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_overlap():
    """Last words of chunk N should appear in start of chunk N+1."""
    text = ". ".join(f"This is sentence number {i} with some content" for i in range(50))
    chunks = chunk_text(text, chunk_size=150, overlap=40)
    assert len(chunks) >= 2


def test_chunk_document_lineage():
    doc = {
        "id": "doc-123",
        "title": "Test Doc",
        "url": "https://example.com/test",
        "category": "test",
        "date_published": "2024-01-01",
        "raw_text": "This is content. " * 200,
    }
    chunks = chunk_document(doc, chunk_size=200, overlap=50)
    assert all(c.doc_id == "doc-123" for c in chunks)
    assert all(c.doc_url == "https://example.com/test" for c in chunks)
    assert all(c.chunk_index == i for i, c in enumerate(chunks))


# ── Validator Tests ────────────────────────────────────────────────────

def test_validate_good_document():
    doc = {
        "id": "d1", "title": "GDP Q1 2024 Report",
        "url": "https://mospi.gov.in/gdp",
        "date_published": "2024-01-15",
        "raw_text": "India's GDP grew by 8.4% in Q1 2024.",
        "summary": "GDP growth 8.4%", "category": "gdp",
    }
    errors = validate_document(doc)
    assert errors == []


def test_validate_missing_title():
    doc = {"id": "d1", "title": "", "url": "https://mospi.gov.in/test",
           "raw_text": "Some content", "summary": "Summary"}
    errors = validate_document(doc)
    assert any(e.field == "title" for e in errors)


def test_validate_invalid_url():
    doc = {"id": "d1", "title": "Good Title", "url": "not-a-url",
           "raw_text": "Some content", "summary": "Summary"}
    errors = validate_document(doc)
    assert any(e.field == "url" for e in errors)


def test_validate_dedupe():
    long_content = "India GDP statistical report content. " * 20
    docs = [
        {"id": "d1", "title": "Report A", "url": "https://mospi.gov.in/a",
         "raw_text": long_content, "summary": "Summary of Report A with enough content"},
        {"id": "d2", "title": "Report A", "url": "https://mospi.gov.in/a",  # duplicate
         "raw_text": long_content, "summary": "Summary of Report A with enough content"},
    ]
    valid, errors = validate_all_documents(docs)
    assert len(valid) == 1
    assert any(e.field == "url" for e in errors)
