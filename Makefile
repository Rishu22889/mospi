.PHONY: help setup crawl parse etl index up down test lint fmt clean

PYTHON := python
DB_PATH := ./data/mospi.db

help:
	@echo "MoSPI Scraper + RAG Chatbot"
	@echo "============================"
	@echo ""
	@echo "  make setup     - Install dependencies"
	@echo "  make crawl     - Run web scraper"
	@echo "  make parse     - Download PDFs & extract text/tables"
	@echo "  make report    - Show scraper summary"
	@echo "  make etl       - Run full ETL pipeline (chunk + embed + index)"
	@echo "  make index     - Rebuild FAISS index only"
	@echo "  make up        - Start all services with Docker Compose"
	@echo "  make down      - Stop all services"
	@echo "  make test      - Run all tests"
	@echo "  make lint      - Run mypy type checks"
	@echo "  make fmt       - Format code with black + isort"
	@echo "  make clean     - Remove generated data"

setup:
	pip install -r requirements-dev.txt

crawl:
	$(PYTHON) -m scraper.crawl --max-pages $${MAX_PAGES:-5}

parse:
	$(PYTHON) -m scraper.parse

report:
	$(PYTHON) -m scraper.report

etl:
	$(PYTHON) -m pipeline.run

index:
	$(PYTHON) -c "from pipeline.run import run_pipeline; run_pipeline()"

up:
	docker compose up --build -d api ui ollama
	@echo ""
	@echo "✅ Services started:"
	@echo "   UI:  http://localhost:8501"
	@echo "   API: http://localhost:8000/docs"

down:
	docker compose down

scraper-docker:
	docker compose --profile scraper up scraper

pipeline-docker:
	docker compose --profile pipeline up pipeline

test:
	PYTHONPATH=. pytest scraper/tests/ pipeline/tests/ rag/tests/ -v --tb=short

test-unit:
	PYTHONPATH=. pytest scraper/tests/test_utils.py pipeline/tests/ -v

test-integration:
	PYTHONPATH=. pytest scraper/tests/test_parser.py rag/tests/ -v

lint:
	mypy scraper/ pipeline/ rag/ --ignore-missing-imports --no-strict-optional

fmt:
	black scraper/ pipeline/ rag/ --line-length 100
	isort scraper/ pipeline/ rag/ --profile black

clean:
	rm -rf data/raw/pdf/*.pdf
	rm -rf data/processed/
	rm -f data/mospi.db
	rm -f datasets/catalog.json
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

format:
	black scraper/ pipeline/ rag/ --line-length 100
	isort scraper/ pipeline/ rag/ --profile black
