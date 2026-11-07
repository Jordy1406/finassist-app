"""Minimal Ollama chat client."""

import httpx

from app.config import Settings


class LLMError(RuntimeError):
    """Raised when the model backend is unreachable or returns an error."""


def chat(message: str, settings: Settings) -> str:
    payload = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    try:
        resp = httpx.post(
            f"{settings.ollama_host}/api/chat",
            json=payload,
            timeout=settings.request_timeout_s,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc
    return resp.json()["message"]["content"]
