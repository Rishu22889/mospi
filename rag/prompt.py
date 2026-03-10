"""Prompt templates for RAG."""
from __future__ import annotations
from typing import List
from pipeline.chunk import Chunk

SYSTEM_PROMPT = """You are a helpful assistant that answers questions about Indian statistical data
published by the Ministry of Statistics and Programme Implementation (MoSPI).

RULES:
1. Answer STRICTLY from the provided context below.
2. If the answer is not in the context, say exactly: "I don't have that in my data."
3. Be concise and factual.
4. At the end of your answer, include citations in this format:
   Sources:
   - [Title](URL)
   (list only the sources you actually used)
"""


def build_context(chunks: List[Chunk]) -> str:
    """Format retrieved chunks into a context string."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        date_str = f" ({chunk.doc_date})" if chunk.doc_date else ""
        parts.append(
            f"[{i}] {chunk.doc_title}{date_str}\n"
            f"URL: {chunk.doc_url}\n"
            f"Category: {chunk.doc_category}\n"
            f"---\n{chunk.text}\n"
        )
    return "\n\n".join(parts)


def build_user_prompt(question: str, chunks: List[Chunk]) -> str:
    """Build the user prompt with retrieved context."""
    context = build_context(chunks)
    return f"""Context:
{context}

Question: {question}

Answer (cite sources at the end):"""

# Alias for backwards compatibility  
def build_prompt(question: str, chunks: list) -> str:
    return format_prompt(question, chunks)

