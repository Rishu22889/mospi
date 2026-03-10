# Submission Notes

## What Worked Well

- **MoSPI API Discovery** — The site is a React SPA so `requests` returns
  an empty shell. Using Chrome DevTools (Network → Fetch/XHR), discovered
  internal REST APIs (`POST /api/latest-release/...`) that return clean JSON.
  Much faster and more reliable than HTML scraping.

- **Full Docker stack** — `docker compose up` brings up Ollama + FastAPI +
  Streamlit together. Works on a fresh machine with no extra setup.

- **RAG pipeline** — FAISS + MMR retrieval + LLaMA 3 gives accurate,
  citation-aware answers. Correctly says "I don't have that in my data"
  for out-of-corpus questions.

- **Incremental scraping** — SHA-256 fingerprinting makes repeated runs
  idempotent. Running `make crawl` twice never duplicates records.

- **92 tests passing** — Unit tests for parser, normalizer, chunker,
  validator + full end-to-end integration tests with mocked API responses.

## What Didn't Work / Workarounds

- **LLaMA 3 8B ran out of RAM** — MacBook Air (8GB) couldn't run
  `llama3:instruct` (needs 4.7GB) alongside Docker containers. Switched to
  `llama3.2:1b` (~1.3GB). Change `OLLAMA_MODEL=llama3:instruct` in `.env`
  on machines with ≥8GB free RAM.

- **MoSPI API auth** — `GET /api/latest-release/...` returns 403. Must use
  `POST` with an empty JSON body `{}`. Discovered via DevTools payload tab.

- **Cold start latency** — First LLaMA query took ~2 minutes (model loading
  from disk). Fixed by adding a startup warmup task in `rag/api.py` that
  pre-loads the model with `keep_alive: 24h` on API startup.

- **Empty chunks** — Documents without downloaded PDFs have no RAG-retrievable
  text. Fixed by running `python -m scraper.parse` to download PDFs first.

## What I'd Do Next

1. **Prefect DAG** — Schedule nightly incremental scrapes with backfill
   and alerting on failure.

2. **Cross-encoder reranker** — Add `ms-marco-MiniLM` reranker after FAISS
   retrieval to improve top-k precision before LLaMA context window.

3. **Metadata filtering** — Filter by category/date before MMR retrieval
   for queries like "latest GDP releases from 2025".

4. **Playwright fallback** — If MoSPI adds API authentication, fall back
   to headless Chromium rendering.

5. **Quality eval** — Build a 20-question golden set and measure RAG
   accuracy (hit rate, MRR) after each pipeline change.

6. **Multilingual embeddings** — Use `paraphrase-multilingual-MiniLM` to
   improve retrieval for Hindi-language MoSPI publications.