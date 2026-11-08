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
    embed_model: str
    docs_dir: str
    index_path: str
    chunk_max_words: int
    chunk_max_words_law: int
    chunk_overlap_words: int
    top_k: int
    min_score: float
    num_ctx: int
    agent_provider: str
    claude_model: str
    claude_effort: str
    agent_max_steps: int
    broker_always_open: bool


def get_settings() -> Settings:
    return Settings(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        request_timeout_s=float(os.getenv("REQUEST_TIMEOUT_S", "120")),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
        docs_dir=os.getenv("DOCS_DIR", "docs"),
        index_path=os.getenv("INDEX_PATH", "data/index.json"),
        chunk_max_words=int(os.getenv("CHUNK_MAX_WORDS", "300")),
        chunk_max_words_law=int(os.getenv("CHUNK_MAX_WORDS_LAW", "400")),
        chunk_overlap_words=int(os.getenv("CHUNK_OVERLAP_WORDS", "50")),
        top_k=int(os.getenv("TOP_K", "4")),
        min_score=float(os.getenv("MIN_SCORE", "0.5")),
        num_ctx=int(os.getenv("NUM_CTX", "8192")),
        agent_provider=os.getenv("AGENT_PROVIDER", "ollama").lower(),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_effort=os.getenv("CLAUDE_EFFORT", "medium"),
        agent_max_steps=int(os.getenv("AGENT_MAX_STEPS", "6")),
        broker_always_open=os.getenv("BROKER_ALWAYS_OPEN", "false").lower() in ("1", "true", "yes"),
    )
