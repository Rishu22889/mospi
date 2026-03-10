"""Utility helpers: fingerprinting, normalization, logging."""
from __future__ import annotations
import hashlib
import json
import logging
import re
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    class JSONFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_obj = {
                "ts": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if record.exc_info:
                log_obj["exc"] = self.formatException(record.exc_info)
            # Merge any extra dict fields
            for k, v in record.__dict__.items():
                if k not in ("msg", "args", "levelname", "levelno", "pathname",
                             "filename", "module", "exc_info", "exc_text",
                             "stack_info", "lineno", "funcName", "created",
                             "msecs", "relativeCreated", "thread", "threadName",
                             "processName", "process", "name", "message"):
                    log_obj[k] = v
            return json.dumps(log_obj, default=str)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fingerprint_str(text: str) -> str:
    return fingerprint(text.encode("utf-8"))


def normalize_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    formats = [
        "%d %B %Y", "%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d",
        "%d/%m/%Y", "%d %b %Y", "%b %d, %Y", "%d.%m.%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Try partial extraction
    m = re.search(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", raw)
    if m:
        d, mo, y = m.groups()
        y = int(y)
        if y < 100:
            y += 2000
        try:
            return datetime(y, int(mo), int(d))
        except ValueError:
            pass
    return None


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_category(cat: str) -> str:
    cat = cat.lower().strip()
    mapping = {
        "press release": "press_release",
        "press note": "press_note",
        "publication": "publication",
        "report": "report",
        "data release": "data_release",
        "advance estimate": "advance_estimate",
        "gdp": "gdp",
        "cpi": "cpi",
        "iip": "iip",
    }
    for k, v in mapping.items():
        if k in cat:
            return v
    return re.sub(r"\W+", "_", cat) or "general"


def is_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.lower().endswith(".pdf")


def make_absolute(base: str, href: str) -> str:
    return urljoin(base, href)
