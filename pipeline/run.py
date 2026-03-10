"""
Main ETL pipeline runner.

Usage:
    python -m pipeline.run
    make etl
"""
from __future__ import annotations
import logging
from pathlib import Path

from pipeline.catalog import build_catalog
from pipeline.chunk import chunk_document
from pipeline.config import pipeline_settings
from pipeline.embed import FAISSIndex
from pipeline.export import export_to_parquet
from pipeline.validate import validate_all_documents
from scraper.storage import get_all_documents, init_db
from scraper.utils import setup_logging

logger = logging.getLogger(__name__)


def run_pipeline(
    db_path: str = None,
    processed_dir: str = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
    min_chunk_chars: int = None,
    embedding_model: str = None,
    vector_index_path: str = None,
) -> dict:
    db_path = db_path or pipeline_settings.db_path
    processed_dir = processed_dir or pipeline_settings.data_processed_dir
    chunk_size = chunk_size or pipeline_settings.chunk_size
    chunk_overlap = chunk_overlap or pipeline_settings.chunk_overlap
    min_chunk_chars = min_chunk_chars or pipeline_settings.min_chunk_chars
    embedding_model = embedding_model or pipeline_settings.embedding_model
    vector_index_path = vector_index_path or pipeline_settings.vector_index_path

    Path(processed_dir).mkdir(parents=True, exist_ok=True)
    init_db(db_path)

    # 1. Load documents
    docs = get_all_documents(db_path)
    logger.info({"event": "pipeline_start", "docs": len(docs)})

    # 2. Validate
    valid_docs, errors = validate_all_documents(docs)
    logger.info({"event": "validation_done", "valid": len(valid_docs),
                 "errors": len(errors)})

    # 3. Chunk
    all_chunks = []
    for doc in valid_docs:
        chunks = chunk_document(doc, chunk_size, chunk_overlap, min_chunk_chars)
        all_chunks.extend(chunks)
    logger.info({"event": "chunking_done", "total_chunks": len(all_chunks)})

    # 4. Embed + Index
    if all_chunks:
        index = FAISSIndex(vector_index_path)
        index.build(all_chunks, embedding_model)
    else:
        logger.warning({"event": "no_chunks_to_index"})

    # 5. Export to Parquet
    export_to_parquet(db_path, processed_dir)

    # 6. Build catalog
    catalog = build_catalog(db_path, processed_dir)

    stats = {
        "total_docs": len(docs),
        "valid_docs": len(valid_docs),
        "validation_errors": len(errors),
        "total_chunks": len(all_chunks),
        "catalog": catalog.get("summary", {}),
    }
    logger.info({"event": "pipeline_complete", **stats})
    return stats


def main() -> None:
    setup_logging()
    import argparse
    parser = argparse.ArgumentParser(description="MoSPI ETL Pipeline")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--chunk-size", type=int, default=None)
    args = parser.parse_args()
    result = run_pipeline(db_path=args.db_path,
                          chunk_size=args.chunk_size)
    import json
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
