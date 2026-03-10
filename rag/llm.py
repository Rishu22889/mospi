"""
LLM client for Ollama (LLaMA 3 Instruct).
Supports both streaming and non-streaming responses.
"""
from __future__ import annotations
import json
import logging
from typing import Generator, Optional

import httpx

from rag.config import rag_settings

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or rag_settings.ollama_base_url).rstrip("/")
        self.model = model or rag_settings.ollama_model

    def is_healthy(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        stream: bool = False,
    ) -> str:
        temperature = temperature if temperature is not None else rag_settings.llm_temperature
        max_tokens = max_tokens or rag_settings.llm_max_tokens

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("message", {}).get("content", "")
            logger.info({"event": "llm_response", "model": self.model,
                         "chars": len(answer)})
            return answer
        except httpx.HTTPStatusError as e:
            logger.error({"event": "llm_http_error", "status": e.response.status_code,
                          "error": str(e)})
            return "Error: LLM service returned an error. Please try again."
        except Exception as e:
            logger.error({"event": "llm_error", "error": str(e)})
            return f"Error: Could not connect to LLM service ({str(e)})."

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> Generator[str, None, None]:
        """Stream response tokens."""
        temperature = temperature if temperature is not None else rag_settings.llm_temperature
        max_tokens = max_tokens or rag_settings.llm_max_tokens

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        try:
            with httpx.stream("POST", f"{self.base_url}/api/chat",
                              json=payload, timeout=120) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
        except Exception as e:
            logger.error({"event": "stream_error", "error": str(e)})
            yield f"\n[Error streaming response: {str(e)}]"
