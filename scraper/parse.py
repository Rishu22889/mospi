"""
MoSPI PDF Parser - CLI Entry Point
Downloads PDFs and extracts text + tables for all documents in DB.

Usage:
    python -m scraper.parse
    python -m scraper.parse --db-path ./data/mospi.db --max-pdfs 10
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from pathlib import Path

import pdfplumber

from scraper.api_scraper import download_pdf, extract_pdf_text, extract_pdf_tables
from scraper.config import settings
from scraper.models import ExtractedTable
from scraper.storage import (
    get_all_documents,
    get_files_for_document,
    get_connection,
    init_db,
    upsert_table,
)
from scraper.utils import setup_logging

import logging
logger = logging.getLogger(__name__)


def parse_all(db_path: str = None, max_pdfs: int = 50) -> dict:
    db_path = db_path or settings.db_path
    init_db(db_path)

    docs = get_all_documents(db_path)
    stats = {"pdfs_downloaded": 0, "pdfs_skipped": 0,
             "tables_extracted": 0, "text_chars": 0, "errors": 0}

    print(f"\n📄 Parsing PDFs for {len(docs)} documents...")

    for doc in docs:
        if stats["pdfs_downloaded"] >= max_pdfs:
            print(f"  ⚠️  Reached max_pdfs limit ({max_pdfs}), stopping.")
            break

        files = get_files_for_document(db_path, doc["id"])
        pdf_files = [f for f in files if f.get("file_type") == "pdf"]

        for file_rec in pdf_files:
            url = file_rec["file_url"]

            # Skip if already downloaded
            if file_rec.get("file_path") and Path(file_rec["file_path"]).exists():
                stats["pdfs_skipped"] += 1
                continue

            print(f"\n  📥 {doc['title'][:60]}")
            print(f"     URL: {url[:70]}")

            # Download
            local_path = download_pdf(url)
            if not local_path:
                stats["errors"] += 1
                continue

            # Hash + pages
            content = local_path.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
            pages = 0
            try:
                with pdfplumber.open(str(local_path)) as pdf:
                    pages = len(pdf.pages)
            except Exception:
                pass

            # Update files table
            conn = get_connection(db_path)
            with conn:
                conn.execute("""
                    UPDATE files SET file_path=?, file_hash=?, pages=?
                    WHERE document_id=? AND file_url=?
                """, (str(local_path), file_hash, pages, doc["id"], url))
            conn.close()

            # Extract text
            text = extract_pdf_text(local_path)
            stats["text_chars"] += len(text)
            print(f"     ✅ Pages: {pages} | Text: {len(text):,} chars")

            # Update document raw_text if empty
            if text and not doc.get("raw_text"):
                conn = get_connection(db_path)
                with conn:
                    conn.execute(
                        "UPDATE documents SET raw_text=?, summary=? WHERE id=?",
                        (text, text[:500], doc["id"])
                    )
                conn.close()

            # Extract tables
            tables = extract_pdf_tables(local_path)
            for tbl_data in tables:
                tbl = ExtractedTable(
                    document_id=doc["id"],
                    source_file_url=url,
                    table_json=json.dumps(tbl_data),
                    n_rows=tbl_data["n_rows"],
                    n_cols=tbl_data["n_cols"],
                )
                upsert_table(db_path, tbl)
                stats["tables_extracted"] += 1

            if tables:
                print(f"     📊 Tables extracted: {len(tables)}")

            stats["pdfs_downloaded"] += 1
            time.sleep(1.5)

    print(f"\n✅ Parse complete!")
    print(f"   PDFs downloaded : {stats['pdfs_downloaded']}")
    print(f"   PDFs skipped    : {stats['pdfs_skipped']}")
    print(f"   Tables extracted: {stats['tables_extracted']}")
    print(f"   Total text chars: {stats['text_chars']:,}")
    return stats


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Download PDFs and extract text + tables")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--max-pdfs", type=int, default=50,
                        help="Max PDFs to process per run (default: 50)")
    args = parser.parse_args()
    result = parse_all(db_path=args.db_path, max_pdfs=args.max_pdfs)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
