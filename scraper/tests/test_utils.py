"""Unit tests for scraper utilities."""
import pytest
from datetime import datetime
from scraper.utils import (
    clean_text, fingerprint, fingerprint_str,
    normalize_category, normalize_date, is_pdf_url, make_absolute
)


def test_clean_text_strips_whitespace():
    assert clean_text("  hello   world  ") == "hello world"


def test_clean_text_collapses_newlines():
    assert clean_text("hello\n\nworld") == "hello world"


def test_fingerprint_consistent():
    assert fingerprint(b"hello") == fingerprint(b"hello")


def test_fingerprint_different():
    assert fingerprint(b"hello") != fingerprint(b"world")


def test_normalize_date_iso():
    d = normalize_date("2024-01-15")
    assert d == datetime(2024, 1, 15)


def test_normalize_date_long_format():
    d = normalize_date("15 January 2024")
    assert d == datetime(2024, 1, 15)


def test_normalize_date_none():
    assert normalize_date(None) is None


def test_normalize_date_empty():
    assert normalize_date("") is None


def test_normalize_category_press():
    assert normalize_category("Press Release") == "press_release"


def test_normalize_category_unknown():
    result = normalize_category("Some Unknown Category")
    assert isinstance(result, str) and len(result) > 0


def test_is_pdf_url():
    assert is_pdf_url("https://example.com/report.pdf") is True
    assert is_pdf_url("https://example.com/page") is False


def test_make_absolute():
    result = make_absolute("https://mospi.gov.in/press", "/files/report.pdf")
    assert result == "https://mospi.gov.in/files/report.pdf"
