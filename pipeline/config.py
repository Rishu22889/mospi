"""Pipeline configuration."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "./data/mospi.db"
    data_processed_dir: str = "./data/processed"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    min_chunk_chars: int = 100
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_index_path: str = "./data/processed/faiss_index"


pipeline_settings = PipelineConfig()
