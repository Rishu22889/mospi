"""
Unit tests for scraper parsing utilities.
"""
from scraper.api_scraper import (
    clean_html,
    infer_category,
    parse_date,
    build_file_links,
)


def test_clean_html_removes_tags():
    assert clean_html("<p>Hello <b>World</b></p>") == "Hello World"

def test_clean_html_none():
    assert clean_html(None) == ""

def test_clean_html_empty():
    assert clean_html("") == ""

def test_clean_html_collapses_spaces():
    result = clean_html("<p>  Hello   World  </p>")
    assert result == "Hello World"

def test_infer_category_gdp():
    assert infer_category("GDP Growth Rate 2024") == "gdp"
    assert infer_category("National Income Estimates") == "gdp"

def test_infer_category_cpi():
    assert infer_category("CPI Monthly Bulletin") == "cpi"
    assert infer_category("Consumer Price Index 2024") == "cpi"

def test_infer_category_iip():
    assert infer_category("IIP Quick Estimates January") == "iip"

def test_infer_category_employment():
    assert infer_category("PLFS Monthly Bulletin") == "employment"

def test_infer_category_general():
    assert infer_category("Annual Report MoSPI 2024") == "publication"

def test_parse_date_standard():
    result = parse_date("2024-01-15")
    assert result is not None
    assert result.year == 2024
    assert result.month == 1
    assert result.day == 15

def test_parse_date_with_time():
    result = parse_date("2024-01-15T00:00:00.000Z")
    assert result is not None
    assert result.year == 2024

def test_parse_date_empty():
    assert parse_date("") is None
    assert parse_date(None) is None

def test_build_file_links_pdf():
    item = {
        "file_one": {
            "path": "uploads/test.pdf",
            "filemime": "application/pdf",
            "filename": "test.pdf",
            "filesize": 1000,
        },
        "file_two": None,
        "file_three": None,
    }
    links = build_file_links(item)
    assert len(links) == 1
    assert links[0].file_type == "pdf"
    assert "mospi.gov.in" in links[0].url

def test_build_file_links_mixed():
    item = {
        "file_one": {
            "path": "uploads/report.pdf",
            "filemime": "application/pdf",
            "filename": "report.pdf",
            "filesize": 5000,
        },
        "file_two": {
            "path": "uploads/data.xlsx",
            "filemime": "application/vnd.ms-excel",
            "filename": "data.xlsx",
            "filesize": 2000,
        },
        "file_three": None,
    }
    links = build_file_links(item)
    assert len(links) == 2
    assert links[0].file_type == "pdf"
    assert links[1].file_type == "xlsx"

def test_build_file_links_empty():
    item = {"file_one": None, "file_two": None, "file_three": None}
    links = build_file_links(item)
    assert links == []
