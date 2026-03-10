"""Export documents to Parquet and CSV."""
from __future__ import annotations
import logging
from pathlib import Path
import pandas as pd
from scraper.storage import get_all_documents, get_connection

logger = logging.getLogger(__name__)


def export_to_parquet(db_path: str, output_dir: str) -> None:
    """Export documents table to Parquet."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    docs = get_all_documents(db_path)
    if not docs:
        logger.warning({"event": "export_skipped", "reason": "no_documents"})
        return

    df = pd.DataFrame(docs)
    parquet_file = output_path / "documents.parquet"
    df.to_parquet(parquet_file, index=False)
    logger.info({"event": "exported_parquet", "path": str(parquet_file),
                 "rows": len(df)})

    # Also export tables
    conn = get_connection(db_path)
    try:
        tables_df = pd.read_sql("SELECT * FROM tables_extracted", conn)
        if not tables_df.empty:
            tables_df.to_parquet(output_path / "tables.parquet", index=False)
            logger.info({"event": "exported_tables_parquet",
                         "rows": len(tables_df)})
    finally:
        conn.close()
