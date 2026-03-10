"""
Produce datasets/catalog.json with counts by category/date
and a manifest of processed files.
"""
from __future__ import annotations
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List

from scraper.storage import get_all_documents, get_summary_stats

logger = logging.getLogger(__name__)


def build_catalog(db_path: str, output_dir: str) -> dict:
    """Build and save catalog.json."""
    docs = get_all_documents(db_path)
    stats = get_summary_stats(db_path)

    by_category: dict = defaultdict(int)
    by_year: dict = defaultdict(int)
    by_month: dict = defaultdict(int)
    manifest: List[dict] = []

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for doc in docs:
        cat = doc.get("category") or "general"
        by_category[cat] += 1

        date_str = doc.get("date_published") or ""
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                by_year[str(dt.year)] += 1
                by_month[f"{dt.year}-{dt.month:02d}"] += 1
            except Exception:
                pass

        manifest.append({
            "id": doc.get("id"),
            "title": doc.get("title"),
            "url": doc.get("url"),
            "category": cat,
            "date_published": date_str,
        })

    catalog = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": stats,
        "by_category": dict(by_category),
        "by_year": dict(by_year),
        "by_month": dict(by_month),
        "manifest": manifest,
    }

    catalog_file = Path("datasets") / "catalog.json"
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    with open(catalog_file, "w") as f:
        json.dump(catalog, f, indent=2, default=str)

    logger.info({"event": "catalog_built", "path": str(catalog_file),
                 "docs": len(manifest)})
    return catalog
