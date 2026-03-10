"""
MoSPI Crawler - CLI Entry Point

Usage:
    python -m scraper.crawl --seed-url https://www.mospi.gov.in/press-releases --max-pages 5
    python -m scraper.crawl --max-pages 3
"""
from __future__ import annotations
import argparse
import json
import sys
from scraper.api_scraper import scrape_latest_releases, scrape_publications
from scraper.storage import init_db
from scraper.utils import setup_logging
from scraper.config import settings


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="MoSPI Crawler - incrementally scrapes press releases and publications")
    parser.add_argument("--seed-url", nargs="+", default=None, dest="seed_urls",
                        help="Seed URLs (used for category detection). Default: all content types")
    parser.add_argument("--max-pages", type=int, default=settings.max_pages,
                        help=f"Max pages per content type (default: {settings.max_pages})")
    parser.add_argument("--db-path", default=settings.db_path,
                        help=f"SQLite DB path (default: {settings.db_path})")
    parser.add_argument("--content-type", choices=["releases", "publications", "all"],
                        default="all", help="Which content type to scrape")
    args = parser.parse_args()

    init_db(args.db_path)

    # Determine what to scrape based on seed URL or content-type flag
    scrape_releases = True
    scrape_pubs = True

    if args.seed_urls:
        scrape_releases = any("press" in u or "release" in u or "latest" in u
                              for u in args.seed_urls)
        scrape_pubs = any("publication" in u or "report" in u
                          for u in args.seed_urls)
        # If neither matched, scrape both
        if not scrape_releases and not scrape_pubs:
            scrape_releases = scrape_pubs = True

    if args.content_type == "releases":
        scrape_releases, scrape_pubs = True, False
    elif args.content_type == "publications":
        scrape_releases, scrape_pubs = False, True

    stats = {"releases": {}, "publications": {}}

    if scrape_releases:
        print("\n📡 Scraping Latest Releases (Content Type 1)...")
        stats["releases"] = scrape_latest_releases(args.db_path, args.max_pages)

    if scrape_pubs:
        print("\n📡 Scraping Publications & Reports (Content Type 2)...")
        stats["publications"] = scrape_publications(args.db_path, args.max_pages)

    total_new = sum(s.get("new", 0) for s in stats.values())
    total_skip = sum(s.get("skipped", 0) for s in stats.values())

    print(f"\n✅ Crawl complete! New: {total_new} | Skipped: {total_skip}")
    print(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    main()
