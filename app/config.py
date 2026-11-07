"""Settings loaded from environment variables (and an optional .env file)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    ollama_model: str
    request_timeout_s: float


def get_settings() -> Settings:
    return Settings(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        request_timeout_s=float(os.getenv("REQUEST_TIMEOUT_S", "120")),
    )
