"""RAG configuration."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3:instruct"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 512
    top_k: int = 5
    mmr_lambda: float = 0.5
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_index_path: str = "./data/processed/faiss_index"
    api_host: str = "0.0.0.0"
    api_port: int = 8000


rag_settings = RAGConfig()
