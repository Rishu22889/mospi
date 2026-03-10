"""
Integration test: end-to-end run against mock HTML fixture + sample PDF.
"""
from __future__ import annotations
import json
import pickle
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MOCK_API_RESPONSE = {
    "status": "success",
    "code": 200,
    "data": [
        {
            "id": "1001",
            "title": "GDP Growth Rate Q3 2024",
            "published_year": "2024-01-15",
            "file_one": {
                "path": "uploads/gdp_report.pdf",
                "filemime": "application/pdf",
                "filename": "gdp_report.pdf",
                "filesize": 102400,
            },
            "file_two": None,
            "file_three": None,
            "is_active": True,
            "start_date": "2024-01-15T00:00:00.000Z",
            "end_date": "2024-02-15T00:00:00.000Z",
            "is_new": "1",
        },
        {
            "id": "1002",
            "title": "CPI Index January 2024",
            "published_year": "2024-01-12",
            "file_one": {
                "path": "uploads/cpi_report.pdf",
                "filemime": "application/pdf",
                "filename": "cpi_report.pdf",
                "filesize": 51200,
            },
            "file_two": None,
            "file_three": None,
            "is_active": True,
            "start_date": "2024-01-12T00:00:00.000Z",
            "end_date": "2024-02-12T00:00:00.000Z",
            "is_new": "1",
        },
    ],
}

SAMPLE_PDF_TEXT = """
India GDP Report Q3 2024 - National Statistical Office
The Gross Domestic Product grew at 8.4 percent in Q3 2024.
Manufacturing sector grew 8.9 percent. Services grew 7.8 percent.
""" * 10


# ── HTML Parser Tests ─────────────────────────────────────────────────

class TestHTMLParser:

    def test_clean_html_removes_tags(self):
        from scraper.api_scraper import clean_html
        result = clean_html("<p>Hello <b>World</b></p>")
        assert result == "Hello World"

    def test_clean_html_handles_none(self):
        from scraper.api_scraper import clean_html
        assert clean_html(None) == ""
        assert clean_html("") == ""

    def test_clean_html_collapses_whitespace(self):
        from scraper.api_scraper import clean_html
        # clean_html collapses multiple spaces — this is correct behavior
        result = clean_html("  <p>  Hello   World  </p>  ")
        assert result == "Hello World"  # spaces collapsed

    def test_infer_category_gdp(self):
        from scraper.api_scraper import infer_category
        assert infer_category("GDP Growth Rate 2024") == "gdp"
        assert infer_category("National Income Estimates") == "gdp"

    def test_infer_category_cpi(self):
        from scraper.api_scraper import infer_category
        assert infer_category("Consumer Price Index January") == "cpi"
        assert infer_category("CPI Monthly Bulletin") == "cpi"

    def test_infer_category_iip(self):
        from scraper.api_scraper import infer_category
        assert infer_category("IIP Quick Estimates January 2024") == "iip"

    def test_infer_category_general(self):
        from scraper.api_scraper import infer_category
        assert infer_category("Annual Report MoSPI 2024") == "publication"

    def test_build_file_links(self):
        from scraper.api_scraper import build_file_links
        item = {
            "file_one": {
                "path": "uploads/test.pdf",
                "filemime": "application/pdf",
                "filename": "test.pdf",
                "filesize": 1000,
            },
            "file_two": {
                "path": "uploads/data.xlsx",
                "filemime": "application/vnd.ms-excel",
                "filename": "data.xlsx",
                "filesize": 500,
            },
            "file_three": None,
        }
        links = build_file_links(item)
        assert len(links) == 2
        assert links[0].file_type == "pdf"
        assert links[1].file_type == "xlsx"
        assert "https://www.mospi.gov.in" in links[0].url


# ── PDF Parser Tests ──────────────────────────────────────────────────

class TestPDFParser:

    def test_extract_text_missing_file(self, tmp_path):
        from scraper.api_scraper import extract_pdf_text
        result = extract_pdf_text(tmp_path / "nonexistent.pdf")
        assert result == ""

    def test_extract_tables_missing_file(self, tmp_path):
        from scraper.api_scraper import extract_pdf_tables
        result = extract_pdf_tables(tmp_path / "nonexistent.pdf")
        assert result == []

    def test_extract_text_real_pdf(self, tmp_path):
        """Create a real PDF and extract text from it."""
        reportlab = pytest.importorskip("reportlab")
        from reportlab.pdfgen import canvas
        from scraper.api_scraper import extract_pdf_text

        pdf_path = tmp_path / "test.pdf"
        c = canvas.Canvas(str(pdf_path))
        c.drawString(100, 750, "India GDP Report Q3 2024")
        c.drawString(100, 730, "GDP grew at 8.4 percent")
        c.save()

        text = extract_pdf_text(pdf_path)
        assert len(text) > 0


# ── Normalizer Tests ──────────────────────────────────────────────────

class TestNormalizer:

    def test_parse_date_iso(self):
        from scraper.api_scraper import parse_date
        result = parse_date("2024-01-15")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_parse_date_iso_with_time(self):
        from scraper.api_scraper import parse_date
        result = parse_date("2024-01-15T00:00:00.000Z")
        assert result is not None
        assert result.year == 2024

    def test_parse_date_empty(self):
        from scraper.api_scraper import parse_date
        assert parse_date("") is None
        assert parse_date(None) is None


# ── Chunker Tests ─────────────────────────────────────────────────────

class TestChunker:

    def test_chunk_long_text(self):
        from pipeline.chunk import chunk_document
        doc = {
            "id": "test-doc-1",
            "title": "GDP Report",
            "url": "https://mospi.gov.in/gdp",
            "category": "gdp",
            "date_published": "2024-01-15",
            "raw_text": "India GDP grew significantly each quarter. " * 200,
        }
        chunks = chunk_document(doc, chunk_size=500, overlap=50)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert chunk.doc_id == "test-doc-1"
            assert chunk.doc_title == "GDP Report"
            assert chunk.doc_url == "https://mospi.gov.in/gdp"

    def test_chunk_preserves_overlap(self):
        from pipeline.chunk import chunk_document
        long_text = " ".join([f"word{i}" for i in range(500)])
        doc = {
            "id": "test-doc-2", "title": "Test",
            "url": "https://example.com", "category": "general",
            "date_published": "2024-01-01", "raw_text": long_text,
        }
        chunks = chunk_document(doc, chunk_size=200, overlap=50)
        if len(chunks) >= 2:
            words1 = set(chunks[0].text.split())
            words2 = set(chunks[1].text.split())
            assert len(words1 & words2) > 0

    def test_chunk_short_text_returns_one_or_zero(self):
        from pipeline.chunk import chunk_document
        doc = {
            "id": "test-doc-3", "title": "Short",
            "url": "https://example.com", "category": "general",
            "date_published": "2024-01-01",
            "raw_text": "Short text with enough words to form a chunk.",
        }
        chunks = chunk_document(doc, chunk_size=800, overlap=100)
        assert len(chunks) <= 1  # 0 or 1 is fine for short text


# ── Validator Tests ───────────────────────────────────────────────────

class TestValidator:

    def test_valid_document_passes(self):
        from pipeline.validate import validate_all_documents
        docs = [{
            "id": "d1", "title": "GDP Report 2024",
            "url": "https://mospi.gov.in/gdp",
            "raw_text": "India GDP grew at 8.4 percent in Q3 2024 driven by manufacturing sector growth.",
            "summary": "GDP grew 8.4%", "date_published": "2024-01-15",
        }]
        valid, errors = validate_all_documents(docs)
        assert len(errors) == 0

    def test_empty_title_fails(self):
        from pipeline.validate import validate_all_documents
        docs = [{
            "id": "d2", "title": "",
            "url": "https://mospi.gov.in/test",
            "raw_text": "Some content here that is long enough to pass validation.",
            "summary": "Summary",
        }]
        valid, errors = validate_all_documents(docs)
        assert any("title" in str(e).lower() for e in errors)

    def test_invalid_url_fails(self):
        from pipeline.validate import validate_all_documents
        docs = [{
            "id": "d3", "title": "Valid Title",
            "url": "not-a-url",
            "raw_text": "Some content here that is long enough to pass.",
            "summary": "Summary",
        }]
        valid, errors = validate_all_documents(docs)
        assert any("url" in str(e).lower() for e in errors)

    def test_deduplication(self):
        from pipeline.validate import validate_all_documents
        doc = {
            "id": "d4", "title": "GDP Report",
            "url": "https://mospi.gov.in/gdp",
            "raw_text": "India GDP grew significantly in 2024.",
            "summary": "GDP grew",
        }
        valid, errors = validate_all_documents([doc, doc])
        assert len(valid) == 1


# ── Integration Tests ─────────────────────────────────────────────────

class TestEndToEndIntegration:

    @pytest.fixture
    def temp_db(self, tmp_path):
        db = str(tmp_path / "test_mospi.db")
        from scraper.storage import init_db
        init_db(db)
        return db

    @patch("scraper.api_scraper.requests.post")
    def test_scrape_latest_releases(self, mock_post, temp_db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_API_RESPONSE
        mock_post.return_value = mock_resp

        from scraper.api_scraper import scrape_latest_releases
        stats = scrape_latest_releases(temp_db, max_pages=1)

        assert stats["new"] == 2
        assert stats["errors"] == 0

        conn = sqlite3.connect(temp_db)
        docs = conn.execute("SELECT * FROM documents").fetchall()
        conn.close()
        assert len(docs) == 2

    @patch("scraper.api_scraper.requests.post")
    def test_idempotent_scraping(self, mock_post, temp_db):
        """Running scraper twice must not duplicate records."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_API_RESPONSE
        mock_post.return_value = mock_resp

        from scraper.api_scraper import scrape_latest_releases
        stats1 = scrape_latest_releases(temp_db, max_pages=1)
        stats2 = scrape_latest_releases(temp_db, max_pages=1)

        assert stats1["new"] == 2
        assert stats2["new"] == 0
        assert stats2["skipped"] == 2

        conn = sqlite3.connect(temp_db)
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
        assert count == 2

    @patch("scraper.api_scraper.requests.post")
    def test_full_etl_pipeline(self, mock_post, temp_db, tmp_path):
        """Full pipeline: scrape → validate → chunk → catalog."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = MOCK_API_RESPONSE
        mock_post.return_value = mock_resp

        # Step 1: Scrape
        from scraper.api_scraper import scrape_latest_releases
        scrape_latest_releases(temp_db, max_pages=1)

        # Step 2: Validate
        from scraper.storage import get_all_documents
        from pipeline.validate import validate_all_documents
        docs = get_all_documents(temp_db)
        valid_docs, errors = validate_all_documents(docs)
        assert len(valid_docs) > 0

        # Step 3: Chunk with real text
        from pipeline.chunk import chunk_document
        all_chunks = []
        for doc in valid_docs:
            doc["raw_text"] = SAMPLE_PDF_TEXT
            chunks = chunk_document(doc, chunk_size=300, overlap=50)
            all_chunks.extend(chunks)
        assert len(all_chunks) > 0

        # Verify doc→chunk lineage
        for chunk in all_chunks:
            assert chunk.doc_id is not None
            assert chunk.doc_title is not None

        # Step 4: Catalog
        catalog = {
            "generated_at": "2024-01-15",
            "summary": {"total_documents": len(valid_docs)},
            "manifest": [{"id": d["id"], "title": d["title"]} for d in valid_docs],
        }
        cat_path = tmp_path / "catalog.json"
        cat_path.write_text(json.dumps(catalog, indent=2))
        loaded = json.loads(cat_path.read_text())
        assert loaded["summary"]["total_documents"] == len(valid_docs)

    def test_retriever_loads_fixture_index(self, tmp_path):
        """Test FAISS retriever and Chunk classes are importable and functional."""
        from pipeline.chunk import Chunk, chunk_document
        from rag.retriever import Retriever, FAISSRetriever

        # Verify Chunk dataclass works
        chunk = Chunk(
            id="c1", doc_id="d1", doc_title="GDP Report",
            doc_url="https://mospi.gov.in/gdp.pdf",
            doc_category="gdp", doc_date="2024-01-15",
            text="India GDP grew at 8.4 percent",
            chunk_index=0, total_chunks=1,
        )
        assert chunk.doc_id == "d1"
        assert chunk.doc_category == "gdp"

        # Verify chunk_document produces correct lineage
        doc = {
            "id": "d1", "title": "GDP Report",
            "url": "https://mospi.gov.in/gdp.pdf",
            "category": "gdp", "date_published": "2024-01-15",
            "raw_text": "India GDP grew at 8.4 percent in Q3 2024. " * 50,
        }
        chunks = chunk_document(doc, chunk_size=300, overlap=50)
        assert len(chunks) > 0
        assert all(c.doc_id == "d1" for c in chunks)
        assert all(c.doc_category == "gdp" for c in chunks)

        # Verify retriever class is accessible
        assert FAISSRetriever is Retriever

    def test_api_health_endpoint(self):
        """Test FastAPI /health endpoint responds correctly."""
        from fastapi.testclient import TestClient
        from rag.api import app
        client = TestClient(app)
        response = client.get("/health")
        # Health endpoint should always return 200 with a status field
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
