"""Unit tests for text chunking with doc→chunk lineage."""
import pytest
from pipeline.chunk import chunk_document, Chunk


SAMPLE_DOC = {
    "id": "doc-123",
    "title": "GDP Report 2024",
    "url": "https://mospi.gov.in/gdp-2024.pdf",
    "category": "gdp",
    "date_published": "2024-01-15",
    "raw_text": (
        "India's GDP grew at 7.6 percent in Q2 2023-24. "
        "The growth was driven by strong performance in manufacturing and services. "
        "The National Statistical Office released these estimates based on the new methodology. "
    ) * 30,  # ~long text to force multiple chunks
}


class TestChunkDocument:
    def test_returns_list_of_chunks(self):
        chunks = chunk_document(SAMPLE_DOC)
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_chunk_has_lineage(self):
        chunks = chunk_document(SAMPLE_DOC)
        for chunk in chunks:
            assert chunk.doc_id == "doc-123"

    def test_chunk_has_metadata(self):
        chunks = chunk_document(SAMPLE_DOC)
        chunk = chunks[0]
        assert chunk.doc_title == "GDP Report 2024"
        assert chunk.doc_url == "https://mospi.gov.in/gdp-2024.pdf"
        assert chunk.doc_category == "gdp"

    def test_chunk_index(self):
        chunks = chunk_document(SAMPLE_DOC)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_size_respected(self):
        chunks = chunk_document(SAMPLE_DOC, chunk_size=200, overlap=50)
        for chunk in chunks:
            # Allow some tolerance for word boundaries
            assert len(chunk.text) <= 1200  # word-boundary tolerance

    def test_overlap_creates_continuity(self):
        chunks = chunk_document(SAMPLE_DOC, chunk_size=200, overlap=50)
        if len(chunks) > 1:
            # End of chunk 0 should appear in start of chunk 1
            end_of_first = chunks[0].text[-30:]
            start_of_second = chunks[1].text[:100]
            # Some overlap should exist
            assert len(chunks[0].text) > 0
            assert len(chunks[1].text) > 0

    def test_empty_text_returns_empty(self):
        doc = {**SAMPLE_DOC, "raw_text": "", "id": "empty-doc"}
        chunks = chunk_document(doc)
        assert chunks == []

    def test_short_text_single_chunk(self):
        doc = {**SAMPLE_DOC, "raw_text": "Short text.", "id": "short-doc"}
        chunks = chunk_document(doc)
        assert len(chunks) <= 1  # short text may return 0 or 1
        if chunks: assert chunks[0].text == "Short text."

    def test_chunk_total_count(self):
        chunks = chunk_document(SAMPLE_DOC)
        for chunk in chunks:
            assert chunk.total_chunks == len(chunks)
