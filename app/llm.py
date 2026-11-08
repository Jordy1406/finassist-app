"""Minimal Ollama client: chat completions (optionally JSON-constrained) and embeddings."""

from __future__ import annotations

import json

import httpx

from app.config import Settings


class LLMError(RuntimeError):
    """Raised when the model backend is unreachable or returns something unusable."""


def _post(settings: Settings, path: str, payload: dict) -> dict:
    try:
        resp = httpx.post(f"{settings.ollama_host}{path}", json=payload, timeout=settings.request_timeout_s)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc
    return resp.json()


def chat(message: str, settings: Settings) -> str:
    """Plain single-turn chat (kept for quick manual checks)."""
    data = _post(settings, "/api/chat", {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    })
    return data["message"]["content"]


def chat_json(system: str, user: str, schema: dict, settings: Settings) -> dict:
    """Chat constrained to a JSON schema, temperature 0. Raises LLMError if the reply is not a JSON object."""
    data = _post(settings, "/api/chat", {
        "model": settings.ollama_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": settings.num_ctx},
    })
    content = data["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON: {content[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise LLMError(f"Model returned JSON that is not an object: {content[:200]!r}")
    return parsed


def embed(texts: list[str], settings: Settings) -> list[list[float]]:
    data = _post(settings, "/api/embed", {"model": settings.embed_model, "input": texts})
    return data["embeddings"]
