"""Tests for RAG API."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from pipeline.chunk import Chunk


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_chunk():
    return Chunk(
        id="chunk-1", doc_id="doc-1",
        doc_title="CPI January 2024",
        doc_url="https://mospi.gov.in/cpi-jan-2024",
        doc_category="cpi", doc_date="2024-01-15",
        text="Consumer Price Index for January 2024 stands at 189.4 (2012=100).",
        chunk_index=0, total_chunks=1,
    )


@pytest.fixture
def client(mock_chunk):
    with (
        patch("rag.api.retriever") as mock_retriever,
        patch("rag.api.llm_client") as mock_llm,
    ):
        mock_retriever.retrieve.return_value = [mock_chunk]
        mock_retriever._get_index.return_value = MagicMock()
        mock_retriever.extract_citations.return_value = [
            MagicMock(title="CPI January 2024",
                      url="https://mospi.gov.in/cpi-jan-2024",
                      snippet="CPI stands at 189.4...")
        ]
        mock_llm.is_healthy.return_value = True
        mock_llm.generate.return_value = "The CPI for January 2024 is 189.4.\n\nSources:\n- [CPI January 2024](https://mospi.gov.in/cpi-jan-2024)"

        from rag.api import app
        yield TestClient(app)


# ── Tests ──────────────────────────────────────────────────────────────

def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "ollama_healthy" in data


def test_ask_endpoint(client):
    resp = client.post("/ask", json={"question": "What is CPI for January 2024?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "citations" in data
    assert data["chunks_used"] >= 1


def test_ask_empty_question(client):
    resp = client.post("/ask", json={"question": ""})
    assert resp.status_code == 400


def test_ask_returns_citations(client):
    resp = client.post("/ask", json={"question": "What is CPI?"})
    data = resp.json()
    assert len(data["citations"]) >= 1
    assert "title" in data["citations"][0]
    assert "url" in data["citations"][0]
