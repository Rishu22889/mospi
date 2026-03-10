# MoSPI Scraper + LLaMA RAG Chatbot

A production-grade pipeline that scrapes public statistical data from the Ministry of Statistics and Programme Implementation (MoSPI) website and powers a local LLaMA-based Q&A chatbot using Retrieval-Augmented Generation (RAG).

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Quick Start](#quick-start)
3. [Setup & Installation](#setup--installation)
4. [Run Commands](#run-commands)
5. [Project Structure](#project-structure)
6. [Components](#components)
7. [Configuration](#configuration)
8. [Tests](#tests)
9. [Assumptions & Known Limits](#assumptions--known-limits)
10. [Trade-offs & Design Decisions](#trade-offs--design-decisions)
11. [Future Improvements](#future-improvements)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        MoSPI Website                         │
│   REST APIs (discovered via DevTools):                       │
│   POST /api/latest-release/get-web-latest-release-list       │
│   POST /api/publications-reports/get-web-publications-...    │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP POST (JSON)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    SCRAPER  (/scraper)                        │
│  • api_scraper.py   — hits MoSPI REST APIs                   │
│  • crawl.py         — CLI: python -m scraper.crawl           │
│  • parse.py         — CLI: python -m scraper.parse           │
│  • report.py        — CLI: python -m scraper.report          │
│  • storage.py       — SQLite: documents, files, tables       │
│  • Incremental fetch via SHA-256 content fingerprinting      │
│  • PDF download → /data/raw/pdf/                             │
│  • pdfplumber: text + table extraction                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ SQLite DB
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    PIPELINE  (/pipeline)                      │
│  • validate.py  — title, URL, content, dedup checks         │
│  • chunk.py     — 800–1200 token chunks with overlap         │
│  • embed.py     — SentenceTransformers (all-MiniLM-L6-v2)   │
│  • catalog.py   — datasets/catalog.json manifest            │
│  • export.py    — Parquet: documents.parquet, tables.parquet │
│  • run.py       — orchestrates full ETL in one command       │
└──────────────────────┬──────────────────────────────────────┘
                       │ FAISS index + Parquet
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     RAG  (/rag)                               │
│  • retriever.py — FAISS + MMR retrieval (configurable k)    │
│  • llm.py       — Ollama client (LLaMA 3.2 / LLaMA 3)      │
│  • prompt.py    — system prompt with citation instructions   │
│  • api.py       — FastAPI: /ask, /ingest, /health           │
│  • ui/app.py    — Streamlit: input, streaming, sources       │
└─────────────────────────────────────────────────────────────┘
```

**Data flow:**
```
MoSPI APIs → SQLite → Validate → Chunk → Embed → FAISS Index
                                                        ↓
User Question → Retrieve k chunks → LLaMA prompt → Answer + Citations
```

---

## Quick Start

```bash
# Clone and enter project
git clone <repo-url> && cd mospi_project

# Copy env config
cp .env.example .env

# Start everything with Docker
docker compose up -d

# Seed initial data
docker compose run --rm scraper python -m scraper.crawl --max-pages 3
docker compose run --rm pipeline python -m pipeline.run

# Open the chatbot UI
open http://localhost:8501
```

---

## Setup & Installation

### Prerequisites

- Docker Desktop (recommended) OR Python 3.11+
- 4GB RAM minimum (for LLaMA model)
- 5GB disk space (for model + data)

### Option A — Docker (Recommended)

```bash
cp .env.example .env
docker compose up -d

# Pull the LLaMA model (first time only, ~1.3GB)
docker exec mospi_ollama ollama pull llama3.2:1b

# Verify all services are healthy
curl http://localhost:8000/health
```

### Option B — Local Python

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-dev.txt

# Install and start Ollama separately
brew install ollama
ollama serve &
ollama pull llama3.2:1b

# Run scraper + pipeline
make crawl
make etl
make index

# Start API + UI
uvicorn rag.api:app --port 8000 &
streamlit run rag/ui/app.py --server.port 8501
```

---

## Run Commands

### Scraper (Part A)

```bash
# Crawl latest releases + publications (idempotent)
python -m scraper.crawl \
  --seed-url https://www.mospi.gov.in/press-releases \
             https://www.mospi.gov.in/publications-reports \
  --max-pages 5

# Crawl only releases
python -m scraper.crawl --content-type releases --max-pages 3

# Download PDFs and extract text + tables
python -m scraper.parse --max-pdfs 20

# Show run summary
python -m scraper.report

# Show report as JSON
python -m scraper.report --json
```

### ETL Pipeline (Part B)

```bash
# Run full ETL pipeline (validate → chunk → embed → index → catalog)
make etl

# Or individually
python -m pipeline.run

# Rebuild FAISS index only
make index
```

### RAG Chatbot (Part C)

```bash
# Start all services together
make up
# OR
docker compose up

# Test the API directly
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is India GDP growth rate?", "k": 5}'

# Rebuild the vector index (after new data)
curl -X POST http://localhost:8000/ingest

# Health check
curl http://localhost:8000/health
```

### Makefile Targets

```bash
make crawl     # Run scraper
make parse     # Download + parse PDFs
make etl       # Full ETL pipeline
make index     # Rebuild FAISS index
make up        # Start Docker services
make test      # Run all tests
make format    # black + isort
make lint      # mypy type checking
make report    # Show scraper summary
make clean     # Remove generated data
```

---

## Project Structure

```
mospi_project/
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── requirements-dev.txt
│
├── scraper/                  # Part A — Web Scraper
│   ├── api_scraper.py        # Core scraping logic (MoSPI REST APIs)
│   ├── crawl.py              # CLI: python -m scraper.crawl
│   ├── parse.py              # CLI: python -m scraper.parse
│   ├── report.py             # CLI: python -m scraper.report
│   ├── models.py             # Pydantic models (Document, FileLink, etc.)
│   ├── storage.py            # SQLite operations
│   ├── config.py             # Pydantic settings (env vars)
│   ├── utils.py              # Logging, fingerprinting
│   └── tests/
│       ├── test_parser.py
│       ├── test_normalizer.py
│       └── test_utils.py
│
├── pipeline/                 # Part B — ETL & Data Quality
│   ├── run.py                # Orchestrator (validate→chunk→embed→index)
│   ├── validate.py           # Data quality checks + deduplication
│   ├── chunk.py              # Token-based chunking with overlap
│   ├── embed.py              # SentenceTransformer embeddings
│   ├── catalog.py            # datasets/catalog.json generation
│   ├── export.py             # Parquet export
│   └── tests/
│       ├── test_chunk.py
│       ├── test_pipeline.py
│       └── test_validate.py
│
├── rag/                      # Part C — LLaMA RAG Chatbot
│   ├── api.py                # FastAPI: /ask, /ingest, /health
│   ├── retriever.py          # FAISS + MMR retrieval
│   ├── llm.py                # Ollama client (streaming)
│   ├── prompt.py             # System prompt builder
│   ├── config.py             # RAG settings
│   ├── ui/
│   │   └── app.py            # Streamlit UI
│   └── tests/
│       └── test_api.py
│
├── tests/
│   └── test_integration.py   # End-to-end integration tests
│
├── infra/
│   ├── Dockerfile.scraper
│   ├── Dockerfile.api
│   ├── Dockerfile.ui
│   └── Dockerfile.pipeline
│
├── data/
│   ├── raw/pdf/              # Downloaded PDFs
│   └── processed/
│       ├── documents.parquet
│       ├── tables.parquet
│       └── faiss_index/
│           ├── index.faiss
│           └── chunks.pkl
│
└── datasets/
    └── catalog.json          # Data manifest by category/date
```

---

## Components

### Part A — Web Scraper

**Content Types Scraped:**

1. **Latest Releases** (listing/index style) — `POST /api/latest-release/get-web-latest-release-list`
   - Press releases, IIP estimates, GDP notes, CPI data
   - Pagination support via `page_no` parameter
   - PDF + XLSX file links extracted per release

2. **Publications & Reports** (detail pages) — `POST /api/publications-reports/get-web-publications-report-list`
   - Annual reports, statistical publications
   - Full PDF text extracted as document summary/abstract

**Key design decisions:**

- MoSPI's website is a React SPA — `requests` only returns an empty shell. The internal REST APIs were discovered via Chrome DevTools (Network → Fetch/XHR tab) and are used directly.
- Content fingerprinting: `SHA-256(title + item_id)` stored per document to ensure idempotent runs.
- Rate limiting: 1.5s delay between requests with exponential backoff on failures.
- PDF primary URL: Since MoSPI has no individual detail pages, the first PDF link is used as the canonical document URL.

**SQLite Schema:**

```sql
documents(id, title, url, date_published, summary, category, hash, raw_text, created_at)
files(id, document_id, file_url, file_path, file_hash, file_type, pages, created_at)
tables_extracted(id, document_id, source_file_url, table_json, n_rows, n_cols, created_at)
```

### Part B — ETL Pipeline

- **Validation:** Non-empty title, valid URL scheme, content length check, deduplication by URL
- **Chunking:** Word-based sliding window, ~800–1200 tokens, 10% overlap, full doc→chunk lineage preserved
- **Embeddings:** `all-MiniLM-L6-v2` via SentenceTransformers (384-dim)
- **Vector Index:** FAISS `IndexFlatL2` — fast exact search, no external service needed
- **Catalog:** `datasets/catalog.json` with counts by category, year, month, and file manifest
- **Exports:** `documents.parquet` + `tables.parquet` via PyArrow

### Part C — RAG Chatbot

- **Generator:** LLaMA 3.2 1B Instruct via Ollama (configurable model)
- **Retrieval:** MMR (Maximal Marginal Relevance) via configurable `k` (default: 5)
- **System prompt:** Answers strictly from context; cites sources with title + URL
- **Streaming:** Token-by-token streaming from Ollama → FastAPI → Streamlit
- **UI features:** k-slider, temperature control, source snippets, clickable PDF links

---

## Configuration

All settings via `.env` (see `.env.example`):

```bash
# Scraper
SEED_URLS=https://www.mospi.gov.in/press-releases,https://www.mospi.gov.in/publications-reports
MAX_PAGES=5
RATE_LIMIT_SECONDS=1.5
MAX_RETRIES=3
DB_PATH=./data/mospi.db
PDF_DIR=./data/raw/pdf

# RAG
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
EMBEDDING_MODEL=all-MiniLM-L6-v2
TOP_K=5
TEMPERATURE=0.1
VECTOR_INDEX_PATH=./data/processed/faiss_index

# Pipeline
CHUNK_SIZE=1000
CHUNK_OVERLAP=100
```

---

## Tests

```bash
# Run all tests
make test

# Run with coverage
PYTHONPATH=. pytest --cov=scraper --cov=pipeline --cov=rag -v

# Run specific suite
PYTHONPATH=. pytest scraper/tests/ -v          # Unit: parser, normalizer
PYTHONPATH=. pytest pipeline/tests/ -v         # Unit: chunker, validator
PYTHONPATH=. pytest rag/tests/ -v              # Unit: API endpoints
PYTHONPATH=. pytest tests/test_integration.py -v  # Integration: end-to-end
```

**Test coverage:**

| Suite | Tests | What's covered |
|-------|-------|---------------|
| `scraper/tests/test_parser.py` | 13 | HTML cleaning, category inference, date parsing, file link extraction |
| `scraper/tests/test_normalizer.py` | 8 | All normalizer edge cases |
| `pipeline/tests/test_chunk.py` | 8 | Chunking, lineage, overlap, size bounds |
| `pipeline/tests/test_pipeline.py` | 7 | Validator, deduplication, chunk text |
| `rag/tests/test_api.py` | 7 | /ask, /health, /ingest endpoints |
| `tests/test_integration.py` | 25 | Full pipeline mock-to-index, idempotency, API |

---

## Assumptions & Known Limits

### Assumptions

1. **MoSPI API stability:** The internal REST APIs (`/api/latest-release/...`, `/api/publications-reports/...`) are undocumented. They were discovered via browser DevTools and may change without notice.

2. **No authentication needed:** The APIs work with standard browser-like headers and a POST body — no API keys or login required as of March 2026.

3. **PDF as canonical URL:** MoSPI does not expose individual HTML detail pages per release. The primary PDF file URL is used as the document's canonical URL for citations.

4. **RAM constraint:** LLaMA 3 8B requires ~8GB RAM. The default config uses LLaMA 3.2 1B (~1.3GB) to work on standard developer machines. Change `OLLAMA_MODEL=llama3:instruct` in `.env` if you have ≥8GB available RAM.

### Known Limits

- **Empty chunks:** Documents without PDF text (title-only records) produce no chunks and do not appear in RAG retrieval results. Running `python -m scraper.parse` first downloads PDFs and enriches these records.
- **PDF size limit:** PDFs over 20MB are skipped to avoid excessive download times. These are logged as warnings.
- **Table extraction:** Complex multi-page tables in PDFs may not extract cleanly with pdfplumber. camelot would improve accuracy but requires Ghostscript.
- **Hindi content:** Some MoSPI publications are in Hindi (Devanagari script). Text extraction works but the embedding model is English-optimized, so Hindi document retrieval quality may be lower.
- **No JS rendering:** The scraper uses direct API calls, not browser automation. If MoSPI adds token-based authentication to their APIs, Playwright-based scraping would be needed.
- **Vector search is exact (IndexFlatL2):** Works well for corpus sizes up to ~100K chunks. For larger corpora, switch to `IndexIVFFlat` with clustering.

---

## Trade-offs & Design Decisions

### Why direct API calls instead of HTML scraping?

MoSPI's website is a React SPA — `requests` returns only a 2KB HTML shell with `<div id="root"></div>`. Playwright could render the JS, but it's slow and brittle. Using the internal REST APIs (discovered via DevTools) is faster, more reliable, and returns clean structured JSON.

**Trade-off:** These APIs are undocumented and may change. The workaround is documented in `scraper/api_scraper.py` with a fallback to the home page API which has remained stable.

### Why SQLite over Postgres?

SQLite requires zero infrastructure setup — no Docker service, no connection string, no migrations. For a corpus of ~1000–10000 documents, SQLite is fast enough. The schema is identical to what Postgres would use, so migration is straightforward if needed.

**Trade-off:** SQLite doesn't support concurrent writes, so the scraper runs sequentially rather than in parallel threads.

### Why FAISS over Chroma?

FAISS is a pure file-based index — no server process, no port conflicts, works identically in Docker and locally. Chroma is more feature-rich (metadata filtering, collections) but adds operational complexity.

**Trade-off:** FAISS requires reloading the entire index into memory on startup. For large indices this adds 5–10 seconds to cold start.

### Why LLaMA 3.2 1B over LLaMA 3 8B?

The 8B model requires ~4.7GB RAM, which exceeds the available memory on most developer machines when running alongside the API, UI, and Ollama containers. The 1B model fits in ~1.3GB and still produces coherent, citation-aware answers for factual statistical queries.

**Trade-off:** The 1B model occasionally gives shorter or less detailed answers. Setting `OLLAMA_MODEL=llama3:instruct` in `.env` enables the full 8B model on machines with ≥8GB free RAM.

### Why pdfplumber over camelot?

pdfplumber works out of the box — no Ghostscript dependency, no Java runtime. It handles both text and table extraction in one library. camelot produces better table extraction for complex bordered tables but requires Ghostscript which is not always available in Docker environments.

---

## Future Improvements

1. **Prefect/Airflow DAG** — Replace the one-shot `make etl` with a scheduled DAG that runs nightly, downloads new releases incrementally, and sends alerts on failure.

2. **Playwright fallback** — If the MoSPI APIs add authentication, fall back to headless Chromium rendering with Playwright.

3. **Better embeddings** — Upgrade to `bge-large-en` or `e5-large` for higher retrieval accuracy. Add embedding cache so unchanged documents aren't re-embedded on each ETL run.

4. **Reranker** — Add a cross-encoder reranker (e.g., `ms-marco-MiniLM`) after FAISS retrieval to improve top-k precision before passing context to LLaMA.

5. **Metadata filtering** — Filter FAISS results by `category`, `date_range`, or `doc_type` before MMR reranking, enabling queries like "What are the latest GDP releases from 2025?"

6. **Quality eval** — Build a golden Q&A set (20–50 questions with known answers from MoSPI) and measure RAG accuracy (hit rate, MRR) after each pipeline change.

7. **Grafana dashboard** — Expose scraper metrics (docs/hour, PDF download success rate, index size, query latency) via Prometheus and visualize in Grafana.

8. **Great Expectations** — Replace the custom validator with GE data docs for richer profiling, drift detection, and HTML reports.

9. **Multilingual support** — Use a multilingual embedding model (e.g., `paraphrase-multilingual-MiniLM-L12-v2`) to improve retrieval for Hindi-language MoSPI publications.

10. **camelot for tables** — Switch PDF table extraction to camelot for more accurate bordered-table parsing, especially for GDP and IIP statistical tables.

---

## What Worked, What Didn't, What's Next

### What worked well
- Discovering MoSPI's internal REST APIs via DevTools — far more reliable than HTML scraping a React SPA
- The full Docker Compose stack (Ollama + FastAPI + Streamlit) works with a single `docker compose up`
- FAISS + MMR retrieval gives good source diversity in answers
- Incremental scraping with SHA-256 fingerprinting correctly skips already-scraped documents

### What didn't work / workarounds needed
- `llama3:instruct` (8B) ran out of RAM on a MacBook Air — switched to `llama3.2:1b`
- MoSPI's `/api/latest-release/get-web-latest-release-list` returns 403 on GET — must use POST with an empty JSON body `{}`
- Some documents have no PDF text (title-only) and produce no FAISS-retrievable chunks — mitigated by running `python -m scraper.parse` first

### What's next
- Schedule nightly incremental scrapes via Prefect
- Add a cross-encoder reranker for better top-k precision
- Expand to more MoSPI content types (release calendar, survey data, NSSO reports)