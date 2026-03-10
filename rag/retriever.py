"""
Retriever: wraps FAISSIndex with MMR search and citation extraction.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from pipeline.chunk import Chunk
from pipeline.embed import FAISSIndex
from rag.config import rag_settings

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    title: str
    url: str
    snippet: str


class Retriever:
    def __init__(
        self,
        vector_index_path: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        self.vector_index_path = vector_index_path or rag_settings.vector_index_path
        self.embedding_model = embedding_model or rag_settings.embedding_model
        self._index: Optional[FAISSIndex] = None

    def _get_index(self) -> FAISSIndex:
        if self._index is None:
            self._index = FAISSIndex(self.vector_index_path)
            self._index.load()
        return self._index

    def retrieve(
        self,
        query: str,
        k: int = None,
        use_mmr: bool = True,
        lambda_param: float = None,
    ) -> List[Chunk]:
        k = k or rag_settings.top_k
        lambda_param = lambda_param or rag_settings.mmr_lambda
        index = self._get_index()

        if use_mmr:
            chunks = index.mmr_search(
                query, k=k, lambda_param=lambda_param,
                model_name=self.embedding_model
            )
        else:
            chunks = index.search(query, k=k, model_name=self.embedding_model)

        logger.info({"event": "retrieved", "query": query[:60], "chunks": len(chunks)})
        return chunks

    def extract_citations(self, chunks: List[Chunk]) -> List[Citation]:
        """Deduplicate and format citations from chunks."""
        seen_urls = set()
        citations = []
        for chunk in chunks:
            if chunk.doc_url not in seen_urls:
                seen_urls.add(chunk.doc_url)
                citations.append(Citation(
                    title=chunk.doc_title,
                    url=chunk.doc_url,
                    snippet=chunk.text[:200] + "..." if len(chunk.text) > 200 else chunk.text,
                ))
        return citations

    def rebuild_index(self) -> None:
        """Reload the index from disk (after pipeline re-run)."""
        self._index = None
        logger.info({"event": "index_reloaded"})

# Alias for backwards compatibility
FAISSRetriever = Retriever

