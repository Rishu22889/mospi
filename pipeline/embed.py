"""
Embedding generation and FAISS index management.
"""
from __future__ import annotations
import json
import logging
import pickle
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from pipeline.chunk import Chunk
from pipeline.config import pipeline_settings

logger = logging.getLogger(__name__)

_model: Optional[SentenceTransformer] = None


def get_embedding_model(model_name: Optional[str] = None) -> SentenceTransformer:
    global _model
    if _model is None:
        name = model_name or pipeline_settings.embedding_model
        logger.info({"event": "loading_embedding_model", "model": name})
        _model = SentenceTransformer(name)
    return _model


def embed_texts(texts: List[str], model_name: Optional[str] = None) -> np.ndarray:
    model = get_embedding_model(model_name)
    embeddings = model.encode(texts, show_progress_bar=True,
                               normalize_embeddings=True, batch_size=32)
    return np.array(embeddings, dtype=np.float32)


class FAISSIndex:
    def __init__(self, index_path: str):
        self.index_path = Path(index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)
        self.faiss_file = self.index_path / "index.faiss"
        self.chunks_file = self.index_path / "chunks.pkl"
        self.index: Optional[faiss.Index] = None
        self.chunks: List[Chunk] = []

    def build(self, chunks: List[Chunk], model_name: Optional[str] = None) -> None:
        """Build FAISS index from chunks."""
        if not chunks:
            logger.warning({"event": "build_skipped", "reason": "no_chunks"})
            return

        texts = [c.text for c in chunks]
        logger.info({"event": "embedding_start", "n_chunks": len(texts)})
        embeddings = embed_texts(texts, model_name)

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)  # Inner product (cosine with normalized)
        self.index.add(embeddings)
        self.chunks = chunks

        faiss.write_index(self.index, str(self.faiss_file))
        with open(self.chunks_file, "wb") as f:
            pickle.dump(chunks, f)

        logger.info({"event": "index_built", "vectors": self.index.ntotal,
                     "dim": dim, "path": str(self.index_path)})

    def load(self) -> None:
        """Load existing index from disk."""
        if not self.faiss_file.exists():
            raise FileNotFoundError(f"No FAISS index at {self.faiss_file}")
        self.index = faiss.read_index(str(self.faiss_file))
        with open(self.chunks_file, "rb") as f:
            self.chunks = pickle.load(f)
        logger.info({"event": "index_loaded", "vectors": self.index.ntotal})

    def search(self, query: str, k: int = 5,
               model_name: Optional[str] = None) -> List[Chunk]:
        """Retrieve top-k chunks for a query."""
        if self.index is None:
            self.load()

        q_vec = embed_texts([query], model_name)
        scores, indices = self.index.search(q_vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = self.chunks[idx]
            results.append(chunk)

        logger.info({"event": "search_done", "query": query[:60], "k": k,
                     "results": len(results)})
        return results

    def mmr_search(self, query: str, k: int = 5, lambda_param: float = 0.5,
                   fetch_k: int = 20, model_name: Optional[str] = None) -> List[Chunk]:
        """
        Maximal Marginal Relevance search to reduce redundancy.
        lambda_param: 1.0 = pure relevance, 0.0 = pure diversity
        """
        if self.index is None:
            self.load()

        q_vec = embed_texts([query], model_name)

        # Fetch broader candidates
        actual_fetch = min(fetch_k, self.index.ntotal)
        scores, indices = self.index.search(q_vec, actual_fetch)

        candidate_indices = [i for i in indices[0] if i != -1]
        if not candidate_indices:
            return []

        # Get embeddings for candidates
        candidate_embeds = np.array([
            faiss.rev_swig_ptr(self.index.get_xb(), self.index.ntotal * self.index.d)
            .reshape(self.index.ntotal, self.index.d)[i]
            for i in candidate_indices
        ], dtype=np.float32)

        selected: List[int] = []
        remaining = list(range(len(candidate_indices)))

        for _ in range(min(k, len(candidate_indices))):
            if not remaining:
                break
            # Relevance scores
            rel_scores = np.dot(candidate_embeds[remaining], q_vec[0])

            if not selected:
                best = remaining[int(np.argmax(rel_scores))]
            else:
                # Redundancy: max similarity to already selected
                sel_embeds = candidate_embeds[selected]
                sim_to_selected = np.max(
                    np.dot(candidate_embeds[remaining], sel_embeds.T), axis=1
                )
                mmr_scores = lambda_param * rel_scores - (1 - lambda_param) * sim_to_selected
                best = remaining[int(np.argmax(mmr_scores))]

            selected.append(best)
            remaining.remove(best)

        return [self.chunks[candidate_indices[i]] for i in selected]
