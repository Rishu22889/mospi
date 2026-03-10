"""
MoSPI Scraper Report - CLI Entry Point
Shows a summary of all scraped data.

Usage:
    python -m scraper.report
    python -m scraper.report --db-path ./data/mospi.db
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from scraper.config import settings
from scraper.storage import get_summary_stats, get_connection
from scraper.utils import setup_logging


def full_report(db_path: str) -> dict:
    stats = get_summary_stats(db_path)
    conn = get_connection(db_path)

    # Recent documents
    recent = conn.execute("""
        SELECT title, category, date_published, url
        FROM documents
        ORDER BY created_at DESC
        LIMIT 10
    """).fetchall()

    # Category breakdown
    cats = conn.execute("""
        SELECT category, COUNT(*) as cnt
        FROM documents
        GROUP BY category
        ORDER BY cnt DESC
    """).fetchall()

    # PDF stats
    pdf_stats = conn.execute("""
        SELECT
            COUNT(*) as total_files,
            SUM(CASE WHEN file_path IS NOT NULL THEN 1 ELSE 0 END) as downloaded,
            SUM(COALESCE(pages, 0)) as total_pages
        FROM files WHERE file_type='pdf'
    """).fetchone()

    # Table stats
    table_stats = conn.execute("""
        SELECT COUNT(*) as total, 
               SUM(n_rows) as total_rows,
               SUM(n_cols) as total_cols
        FROM tables_extracted
    """).fetchone()

    conn.close()

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": stats,
        "pdf_stats": {
            "total_pdf_files": pdf_stats["total_files"] if pdf_stats else 0,
            "downloaded": pdf_stats["downloaded"] if pdf_stats else 0,
            "total_pages": pdf_stats["total_pages"] if pdf_stats else 0,
        },
        "table_stats": {
            "total_tables": table_stats["total"] if table_stats else 0,
            "total_rows": table_stats["total_rows"] if table_stats else 0,
        },
        "by_category": {r["category"]: r["cnt"] for r in cats},
        "recent_10": [
            {
                "title": r["title"][:70],
                "category": r["category"],
                "date": r["date_published"],
                "url": r["url"][:60],
            }
            for r in recent
        ],
    }
    return report


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Show scraper run summary")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    db_path = args.db_path or settings.db_path
    report = full_report(db_path)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return

    # Pretty print
    print("\n" + "="*60)
    print("📊 MoSPI SCRAPER REPORT")
    print("="*60)
    print(f"  Total Documents : {report['summary']['total_documents']}")
    print(f"  Total PDF Files : {report['pdf_stats']['total_pdf_files']}")
    print(f"  PDFs Downloaded : {report['pdf_stats']['downloaded']}")
    print(f"  Total Pages     : {report['pdf_stats']['total_pages']}")
    print(f"  Tables Extracted: {report['table_stats']['total_tables']}")

    print("\n📁 By Category:")
    for cat, cnt in report["by_category"].items():
        print(f"  {cat:20} : {cnt}")

    print("\n🕐 Recent 10 Documents:")
    for doc in report["recent_10"]:
        print(f"  [{doc['category']:12}] {doc['title'][:55]}")
        print(f"              Date: {doc['date']} | {doc['url'][:50]}")

    print("\n" + "="*60)
    print(f"Generated: {report['generated_at']}")


if __name__ == "__main__":
    main()
