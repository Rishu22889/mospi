"""SQLite storage layer for scraped documents."""
from __future__ import annotations
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional

from scraper.models import Document, ExtractedTable, FileLink

logger = logging.getLogger(__name__)


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                date_published TEXT,
                summary TEXT,
                category TEXT,
                hash TEXT,
                raw_text TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                file_path TEXT,
                file_hash TEXT,
                file_type TEXT,
                pages INTEGER,
                created_at TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS tables_extracted (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_file_url TEXT,
                table_json TEXT,
                n_rows INTEGER,
                n_cols INTEGER,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
            CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(hash);
            CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
        """)
    conn.close()
    logger.info({"event": "db_initialized", "path": db_path})


def document_exists(db_path: str, url: str, hash_val: str) -> bool:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM documents WHERE url=? OR hash=?", (url, hash_val)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def upsert_document(db_path: str, doc: Document) -> None:
    conn = get_connection(db_path)
    date_str = doc.date_published.isoformat() if doc.date_published else None
    with conn:
        conn.execute("""
            INSERT INTO documents (id, title, url, date_published, summary, category, hash, raw_text, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                date_published=excluded.date_published,
                summary=excluded.summary,
                category=excluded.category,
                hash=excluded.hash,
                raw_text=excluded.raw_text
        """, (doc.id, doc.title, doc.url, date_str, doc.summary,
              doc.category, doc.hash, doc.raw_text, doc.created_at.isoformat()))

        for fl in doc.file_links:
            import uuid
            conn.execute("""
                INSERT OR IGNORE INTO files (id, document_id, file_url, file_path, file_hash, file_type, pages, created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (str(uuid.uuid4()), doc.id, fl.url, fl.local_path,
                  fl.file_hash, fl.file_type, fl.pages, doc.created_at.isoformat()))
    conn.close()


def upsert_table(db_path: str, tbl: ExtractedTable) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT OR IGNORE INTO tables_extracted (id, document_id, source_file_url, table_json, n_rows, n_cols)
            VALUES (?,?,?,?,?,?)
        """, (tbl.id, tbl.document_id, tbl.source_file_url,
              tbl.table_json, tbl.n_rows, tbl.n_cols))
    conn.close()


def get_all_documents(db_path: str) -> List[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM documents").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_files_for_document(db_path: str, doc_id: str) -> List[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM files WHERE document_id=?", (doc_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_summary_stats(db_path: str) -> dict:
    conn = get_connection(db_path)
    try:
        docs = conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
        files = conn.execute("SELECT COUNT(*) as c FROM files").fetchone()["c"]
        tables = conn.execute("SELECT COUNT(*) as c FROM tables_extracted").fetchone()["c"]
        cats = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM documents GROUP BY category"
        ).fetchall()
        return {
            "total_documents": docs,
            "total_files": files,
            "total_tables": tables,
            "by_category": {r["category"]: r["cnt"] for r in cats},
        }
    finally:
        conn.close()
