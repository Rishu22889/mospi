"""Data models for scraped content."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import uuid


@dataclass
class FileLink:
    url: str
    file_type: str = "pdf"
    local_path: Optional[str] = None
    file_hash: Optional[str] = None
    pages: Optional[int] = None


@dataclass
class Document:
    url: str
    title: str
    date_published: Optional[datetime] = None
    category: str = "general"
    summary: str = ""
    file_links: List[FileLink] = field(default_factory=list)
    hash: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    raw_text: str = ""


@dataclass
class ExtractedTable:
    document_id: str
    source_file_url: str
    table_json: str
    n_rows: int
    n_cols: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
