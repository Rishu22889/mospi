"""Unit tests for normalizer/cleaning functions."""
import pytest
from datetime import datetime
from scraper.api_scraper import clean_html, infer_category, parse_date


class TestCleanHtml:
    def test_removes_tags(self):
        assert clean_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_trims_whitespace(self):
        assert clean_html("  hello   world  ") == "hello world"

    def test_empty_string(self):
        assert clean_html("") == ""

    def test_none_returns_empty(self):
        assert clean_html(None) == ""

    def test_nested_tags(self):
        result = clean_html("<div><p>GDP <span>Report</span></p></div>")
        assert result == "GDP Report"

    def test_multiple_spaces_collapsed(self):
        result = clean_html("<p>GDP    growth   rate</p>")
        assert "  " not in result


class TestInferCategory:
    def test_gdp(self):
        assert infer_category("GDP growth rate Q2 2024") == "gdp"

    def test_cpi(self):
        assert infer_category("CPI for January 2024") == "cpi"

    def test_iip(self):
        assert infer_category("IIP Base 2011-12 December") == "iip"

    def test_wpi(self):
        assert infer_category("WPI Wholesale Price Index") == "wpi"

    def test_employment(self):
        assert infer_category("PLFS Labour Force Survey") == "employment"

    def test_general_fallback(self):
        assert infer_category("Annual Report of Ministry") in ("general", "publication")

    def test_case_insensitive(self):
        assert infer_category("gdp GROWTH rate") == "gdp"


class TestParseDate:
    def test_iso_format(self):
        result = parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_iso_with_time(self):
        result = parse_date("2024-01-15T00:00:00.000Z")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_empty_string(self):
        assert parse_date("") is None

    def test_none(self):
        assert parse_date(None) is None

    def test_invalid_format(self):
        assert parse_date("not-a-date") is None

    def test_year_only(self):
        result = parse_date("2024-06-01")
        assert result is not None
        assert result.year == 2024
