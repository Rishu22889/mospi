"""
FastAPI RAG API.

Endpoints:
    POST /ask           - Q&A with citations
    POST /ask/stream    - Streaming Q&A
    POST /ingest        - Rebuild vector index
    GET  /health        - Health check
"""
from __future__ import annotations
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pipeline.run import run_pipeline
from rag.config import rag_settings
from rag.llm import OllamaClient
from rag.prompt import SYSTEM_PROMPT, build_user_prompt
from rag.retriever import Citation, Retriever
from scraper.utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MoSPI RAG Chatbot API",
    description="Q&A over MoSPI statistical publications using LLaMA 3",
    version="1.0.0",
)


@app.on_event("startup")
async def warmup_model():
    """Pre-warm LLaMA model on API startup so first user query is fast."""
    import asyncio
    import httpx
    import logging
    logger = logging.getLogger(__name__)
    
    async def _warmup():
        await asyncio.sleep(5)  # wait for Ollama to be ready
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                logger.info({"event": "model_warmup_start"})
                await client.post(
                    f"{rag_settings.ollama_base_url}/api/chat",
                    json={
                        "model": rag_settings.ollama_model,
                        "keep_alive": "24h",
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                        "options": {"num_predict": 1},
                    }
                )
                logger.info({"event": "model_warmup_done"})
        except Exception as e:
            logger.warning({"event": "model_warmup_failed", "error": str(e)})
    
    asyncio.create_task(_warmup())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons
retriever = Retriever()
llm_client = OllamaClient()


# ── Schemas ───────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    k: Optional[int] = None
    temperature: Optional[float] = None
    use_mmr: bool = True


class CitationResponse(BaseModel):
    title: str
    url: str
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    chunks_used: int


class IngestResponse(BaseModel):
    status: str
    stats: dict


class HealthResponse(BaseModel):
    status: str
    ollama_healthy: bool
    index_loaded: bool


# ── Endpoints ─────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    ollama_ok = llm_client.is_healthy()
    try:
        _ = retriever._get_index()
        index_ok = True
    except Exception:
        index_ok = False

    return HealthResponse(
        status="ok" if (ollama_ok and index_ok) else "degraded",
        ollama_healthy=ollama_ok,
        index_loaded=index_ok,
    )


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        chunks = retriever.retrieve(
            req.question,
            k=req.k or rag_settings.top_k,
            use_mmr=req.use_mmr,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Vector index not found. Run /ingest first."
        )

    if not chunks:
        return AskResponse(
            answer="I don't have that in my data.",
            citations=[],
            chunks_used=0,
        )

    user_prompt = build_user_prompt(req.question, chunks)
    answer = llm_client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=req.temperature,
    )

    citations = retriever.extract_citations(chunks)
    citation_responses = [
        CitationResponse(title=c.title, url=c.url, snippet=c.snippet)
        for c in citations
    ]

    logger.info({"event": "ask_served", "question": req.question[:60],
                 "chunks": len(chunks), "citations": len(citations)})

    return AskResponse(
        answer=answer,
        citations=citation_responses,
        chunks_used=len(chunks),
    )


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """Streaming endpoint for real-time token generation."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        chunks = retriever.retrieve(
            req.question,
            k=req.k or rag_settings.top_k,
            use_mmr=req.use_mmr,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Vector index not found.")

    if not chunks:
        async def no_data():
            yield "I don't have that in my data."
        return StreamingResponse(no_data(), media_type="text/event-stream")

    user_prompt = build_user_prompt(req.question, chunks)
    citations = retriever.extract_citations(chunks)

    import json as _json

    def generate():
        for token in llm_client.generate_stream(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=req.temperature,
        ):
            yield f"data: {_json.dumps({'token': token})}\n\n"

        # Send citations at end
        cit_data = [{"title": c.title, "url": c.url} for c in citations]
        yield f"data: {_json.dumps({'citations': cit_data, 'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/ingest", response_model=IngestResponse)
async def ingest(background_tasks: BackgroundTasks):
    """Trigger ETL pipeline to rebuild the vector index."""
    def _run():
        try:
            stats = run_pipeline()
            retriever.rebuild_index()
            logger.info({"event": "ingest_complete", "stats": stats})
        except Exception as e:
            logger.error({"event": "ingest_error", "error": str(e)})

    background_tasks.add_task(_run)
    return IngestResponse(
        status="ingestion started in background",
        stats={},
    )
