"""Scraper configuration via pydantic-settings."""
from __future__ import annotations
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScraperConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    seed_urls: str = "https://mospi.gov.in/press-releases,https://mospi.gov.in/publication"
    max_pages: int = 10
    concurrency: int = 2
    rate_limit_delay: float = 1.5
    request_timeout: int = 30
    user_agent: str = "MoSPI-Research-Bot/1.0 (+research)"
    respect_robots: bool = True
    db_path: str = "./data/mospi.db"
    data_raw_dir: str = "./data/raw"
    data_processed_dir: str = "./data/processed"

    def get_seed_urls(self) -> List[str]:
        return [u.strip() for u in self.seed_urls.split(",") if u.strip()]


settings = ScraperConfig()
