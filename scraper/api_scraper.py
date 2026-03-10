"""
MoSPI Complete Scraper - Part A
Scrapes 2 content types:
  1. Latest Releases (listing/index style)
  2. Publications & Reports (detail pages)
With PDF download, text extraction, and table extraction.
"""
from __future__ import annotations
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pdfplumber
import requests

from scraper.models import Document, ExtractedTable, FileLink
from scraper.storage import (
    get_all_documents,
    init_db,
    upsert_document,
    upsert_table,
    document_exists,
    get_connection,
)
from scraper.utils import setup_logging, fingerprint_str

logger = logging.getLogger(__name__)

BASE_URL = "https://www.mospi.gov.in"
PDF_DIR = Path("./data/raw/pdf")

HEADERS = {
    "User-Agent": "MoSPI-Research-Bot/1.0 (academic research; contact@example.com)",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://mospi.gov.in",
    "Referer": "https://mospi.gov.in/",
}

RATE_LIMIT = 1.5  # seconds between requests


# ── Helpers ───────────────────────────────────────────────────────────

def clean_html(text: str) -> str:
    """Remove HTML tags and clean whitespace."""
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def infer_category(title: str) -> str:
    t = title.lower()
    if "gdp" in t or "national income" in t or "gva" in t: return "gdp"
    if "cpi" in t or "consumer price" in t:                 return "cpi"
    if "iip" in t or "industrial production" in t:          return "iip"
    if "wpi" in t or "wholesale price" in t:                return "wpi"
    if "plfs" in t or "labour force" in t or "employment" in t: return "employment"
    if "trade" in t or "export" in t or "import" in t:      return "trade"
    if "census" in t or "population" in t:                  return "census"
    if "publication" in t or "report" in t or "annual" in t: return "publication"
    return "general"


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"]:
        try:
            return datetime.strptime(date_str[:19], fmt[:len(date_str[:19])])
        except:
            continue
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except:
        return None


def build_file_links(item: dict) -> List[FileLink]:
    links = []
    for key in ["file_one", "file_two", "file_three"]:
        f = item.get(key)
        if not f or not isinstance(f, dict):
            continue
        path = f.get("path", "")
        if not path:
            continue
        full_url = f"{BASE_URL}/{path}"
        mime = f.get("filemime", "")
        if "pdf" in mime or path.endswith(".pdf"):
            ftype = "pdf"
        elif "excel" in mime or "spreadsheet" in mime or path.endswith((".xls", ".xlsx")):
            ftype = "xlsx"
        else:
            ftype = path.rsplit(".", 1)[-1] if "." in path else "file"
        links.append(FileLink(url=full_url, file_type=ftype))
    return links


# ── PDF Handling ──────────────────────────────────────────────────────

def download_pdf(url: str) -> Optional[Path]:
    """Download PDF to /data/raw/pdf/. Returns local path or None."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    dest = PDF_DIR / f"{url_hash}.pdf"

    if dest.exists():
        logger.info({"event": "pdf_exists", "path": str(dest)})
        return dest

    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": HEADERS["User-Agent"]},
                timeout=60,
                stream=True,
            )
            resp.raise_for_status()
            # Skip very large files (>20MB)
            size = int(resp.headers.get("content-length", 0))
            if size > 20 * 1024 * 1024:
                logger.warning({"event": "pdf_too_large", "url": url, "size": size})
                return None
            dest.write_bytes(resp.content)
            logger.info({"event": "pdf_downloaded", "url": url, "path": str(dest)})
            return dest
        except Exception as e:
            logger.error({"event": "pdf_error", "url": url, "attempt": attempt, "error": str(e)})
            time.sleep(2 ** attempt)
    return None


def extract_pdf_text(path: Path) -> str:
    """Extract all text from PDF."""
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            return "\n".join(pages_text)
    except Exception as e:
        logger.error({"event": "pdf_text_error", "path": str(path), "error": str(e)})
        return ""


def extract_pdf_tables(path: Path) -> List[dict]:
    """Extract tables from PDF using pdfplumber."""
    tables = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                for tbl in page.extract_tables() or []:
                    if not tbl or len(tbl) < 2:
                        continue
                    headers = [str(h).strip() if h else f"col_{i}"
                               for i, h in enumerate(tbl[0])]
                    rows = []
                    for row in tbl[1:]:
                        rows.append({
                            headers[i]: str(cell).strip() if cell else ""
                            for i, cell in enumerate(row) if i < len(headers)
                        })
                    tables.append({
                        "page": page_num + 1,
                        "headers": headers,
                        "rows": rows,
                        "n_rows": len(rows),
                        "n_cols": len(headers),
                    })
        logger.info({"event": "tables_extracted", "path": str(path), "count": len(tables)})
    except Exception as e:
        logger.error({"event": "table_error", "path": str(path), "error": str(e)})
    return tables


def process_pdf(doc_id: str, file_link: FileLink, db_path: str) -> Optional[str]:
    """
    Download PDF, extract text + tables.
    Returns extracted text or None.
    """
    local_path = download_pdf(file_link.url)
    if not local_path:
        return None

    # Update file record
    file_hash = hashlib.sha256(local_path.read_bytes()).hexdigest()
    pages = 0
    try:
        with pdfplumber.open(str(local_path)) as pdf:
            pages = len(pdf.pages)
    except:
        pass

    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            UPDATE files SET file_path=?, file_hash=?, pages=?
            WHERE document_id=? AND file_url=?
        """, (str(local_path), file_hash, pages, doc_id, file_link.url))
    conn.close()

    # Extract text
    text = extract_pdf_text(local_path)

    # Extract tables and store them
    tables = extract_pdf_tables(local_path)
    for tbl_data in tables:
        tbl = ExtractedTable(
            document_id=doc_id,
            source_file_url=file_link.url,
            table_json=json.dumps(tbl_data),
            n_rows=tbl_data["n_rows"],
            n_cols=tbl_data["n_cols"],
        )
        upsert_table(db_path, tbl)

    logger.info({
        "event": "pdf_processed",
        "url": file_link.url,
        "pages": pages,
        "text_chars": len(text),
        "tables": len(tables),
    })
    return text


# ── Content Type 1: Latest Releases ──────────────────────────────────

def scrape_latest_releases(db_path: str, max_pages: int = 5) -> dict:
    """
    Content Type 1: Listing/index style page.
    API: POST /api/latest-release/get-web-latest-release-list
    """
    stats = {"new": 0, "skipped": 0, "errors": 0, "pdfs": 0}
    pdf_done = False  # ensure at least 1 PDF per run

    for page in range(1, max_pages + 1):
        payload = {
            "page_no": page, "page_size": 20,
            "search_term": "", "sort_field": "published_year",
            "sort_order": "DESC", "from_date": "", "to_date": "",
            "lang": "en", "data_source": "web",
        }

        try:
            resp = requests.post(
                f"{BASE_URL}/api/latest-release/get-web-latest-release-list",
                headers=HEADERS, json=payload, timeout=30,
            )
            resp.raise_for_status()
            items = resp.json().get("data", [])
        except Exception as e:
            logger.error({"event": "releases_api_error", "page": page, "error": str(e)})
            stats["errors"] += 1
            break

        if not items:
            break

        logger.info({"event": "releases_page", "page": page, "items": len(items)})

        for item in items:
            title = clean_html(item.get("title", "")).replace("\r\n", " ").strip()
            if not title:
                continue

            item_id = item.get("id", "")
            file_links = build_file_links(item)
            pdf_links = [f for f in file_links if f.file_type == "pdf"]

            # Use PDF URL as primary URL
            doc_url = pdf_links[0].url if pdf_links else f"{BASE_URL}/press-releases/{item_id}"
            content_hash = fingerprint_str(title + item_id)

            if document_exists(db_path, doc_url, content_hash):
                stats["skipped"] += 1
                continue

            date_pub = parse_date(
                item.get("published_year") or item.get("start_date", "")
            )
            category = infer_category(title)

            doc = Document(
                url=doc_url,
                title=title,
                date_published=date_pub,
                category=category,
                summary=title,
                raw_text=title,
                file_links=file_links,
                hash=content_hash,
            )
            upsert_document(db_path, doc)
            stats["new"] += 1

            print(f"  ✓ [release/{category}] {title[:65]}")

            # Download + extract first PDF (requirement: at least 1 per run)
            if pdf_links and not pdf_done:
                print(f"    📄 Downloading PDF...")
                text = process_pdf(doc.id, pdf_links[0], db_path)
                if text:
                    # Update doc with extracted text
                    conn = get_connection(db_path)
                    with conn:
                        conn.execute(
                            "UPDATE documents SET raw_text=?, summary=? WHERE id=?",
                            (text, text[:500], doc.id)
                        )
                    conn.close()
                    stats["pdfs"] += 1
                    pdf_done = True
                    print(f"    ✅ PDF extracted: {len(text)} chars")

            time.sleep(RATE_LIMIT)

        time.sleep(RATE_LIMIT)

    return stats


# ── Content Type 2: Publications & Reports ────────────────────────────

def scrape_publications(db_path: str, max_pages: int = 5) -> dict:
    """
    Content Type 2: Detail pages for publications/reports.
    API: POST /api/publications-reports/get-web-publications-report-list
    Captures: title, date, summary (from PDF text), file_links, category.
    """
    stats = {"new": 0, "skipped": 0, "errors": 0, "pdfs": 0}

    for page in range(1, max_pages + 1):
        payload = {
            "page_no": page, "page_size": 20,
            "search_term": "", "sort_field": "published_year",
            "sort_order": "DESC", "from_date": "", "to_date": "",
            "lang": "en", "data_source": "web",
        }

        try:
            resp = requests.post(
                f"{BASE_URL}/api/publications-reports/get-web-publications-report-list",
                headers=HEADERS, json=payload, timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
        except Exception as e:
            logger.error({"event": "publications_api_error", "page": page, "error": str(e)})
            stats["errors"] += 1
            break

        if not items:
            break

        logger.info({"event": "publications_page", "page": page, "items": len(items)})

        for item in items:
            title = clean_html(item.get("title", "")).strip()
            if not title:
                continue

            item_id = item.get("id", "")
            file_links = build_file_links(item)
            pdf_links = [f for f in file_links if f.file_type == "pdf"]

            doc_url = pdf_links[0].url if pdf_links else f"{BASE_URL}/publications-reports/{item_id}"
            content_hash = fingerprint_str(title + item_id)

            if document_exists(db_path, doc_url, content_hash):
                stats["skipped"] += 1
                continue

            date_pub = parse_date(item.get("published_year", ""))
            category = infer_category(title)

            # Extract PDF text as the "summary/abstract" for detail page
            pdf_text = ""
            if pdf_links and stats["pdfs"] < 3:  # limit PDF downloads per run
                print(f"    📄 Extracting publication PDF...")
                pdf_text = process_pdf(item_id, pdf_links[0], db_path) or ""
                if pdf_text:
                    stats["pdfs"] += 1
                    print(f"    ✅ {len(pdf_text)} chars extracted")

            summary = pdf_text[:500] if pdf_text else title
            raw_text = pdf_text if pdf_text else title

            doc = Document(
                url=doc_url,
                title=title,
                date_published=date_pub,
                category=category,
                summary=summary,
                raw_text=raw_text,
                file_links=file_links,
                hash=content_hash,
            )
            upsert_document(db_path, doc)
            stats["new"] += 1

            print(f"  ✓ [publication/{category}] {title[:65]}")
            time.sleep(RATE_LIMIT)

        time.sleep(RATE_LIMIT)

    return stats


# ── Main Runner ───────────────────────────────────────────────────────

def run(db_path: str = "./data/mospi.db", max_pages: int = 5) -> dict:
    setup_logging()
    init_db(db_path)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*60)
    print("📡 CONTENT TYPE 1: Latest Releases (Listing/Index)")
    print("="*60)
    stats1 = scrape_latest_releases(db_path, max_pages)

    print("\n" + "="*60)
    print("📡 CONTENT TYPE 2: Publications & Reports (Detail Pages)")
    print("="*60)
    stats2 = scrape_publications(db_path, max_pages)

    total = {
        "content_type_1_latest_releases": stats1,
        "content_type_2_publications": stats2,
        "total_new": stats1["new"] + stats2["new"],
        "total_skipped": stats1["skipped"] + stats2["skipped"],
        "total_pdfs_processed": stats1["pdfs"] + stats2["pdfs"],
    }

    print("\n" + "="*60)
    print("✅ SCRAPE COMPLETE")
    print(f"   New documents : {total['total_new']}")
    print(f"   Skipped       : {total['total_skipped']}")
    print(f"   PDFs processed: {total['total_pdfs_processed']}")
    print("="*60)

    return total


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "./data/mospi.db"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    result = run(db_path=db, max_pages=pages)
    print(json.dumps(result, indent=2))
