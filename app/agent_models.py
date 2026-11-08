"""Pluggable chat models for the agent: Ollama (development) and the Claude API (final runs).

Each model owns its conversation transcript in its provider's native format, so provider-specific
blocks (Claude thinking/fallback blocks, Ollama tool messages) are appended back exactly as received.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import Settings
from app.llm import LLMError


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolResult:
    call: ToolCall
    content: dict
    is_error: bool = False


class AgentModel(Protocol):
    name: str

    def add_user(self, text: str) -> None: ...
    def add_assistant_text(self, text: str) -> None: ...
    def step(self, system: str, tools: list[dict]) -> Turn: ...
    def add_tool_results(self, results: list[ToolResult]) -> None: ...


class OllamaModel:
    """Local model through Ollama's /api/chat tool calling."""

    def __init__(self, settings: Settings, model: str | None = None):
        self.settings = settings
        self.name = model or settings.ollama_model
        self.messages: list[dict] = []

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant_text(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def step(self, system: str, tools: list[dict]) -> Turn:
        payload = {
            "model": self.name,
            "messages": [{"role": "system", "content": system}, *self.messages],
            "tools": [{"type": "function", "function": t} for t in tools],
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self.settings.num_ctx},
        }
        try:
            resp = httpx.post(f"{self.settings.ollama_host}/api/chat", json=payload,
                              timeout=self.settings.request_timeout_s)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        msg = resp.json()["message"]
        self.messages.append(msg)
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            calls.append(ToolCall(id=tc.get("id") or f"call_{len(self.messages)}_{i}", name=fn.get("name", ""),
                                  arguments=args))
        return Turn(text=msg.get("content") or "", tool_calls=calls)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            self.messages.append({"role": "tool", "tool_name": r.call.name,
                                  "content": json.dumps(r.content, ensure_ascii=False)})


class ClaudeModel:
    """Claude through the official `anthropic` SDK (needs ANTHROPIC_API_KEY or an `ant auth login` profile)."""

    def __init__(self, settings: Settings, model: str | None = None, client=None):
        if client is None:
            import anthropic  # imported lazily so development without the SDK configured still works
            client = anthropic.Anthropic()
        self.client = client
        self.settings = settings
        self.name = model or settings.claude_model
        self.messages: list[dict] = []

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant_text(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def step(self, system: str, tools: list[dict]) -> Turn:
        resp = self.client.beta.messages.create(
            model=self.name,
            max_tokens=16000,
            system=system,
            tools=[{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools],
            messages=self.messages,
            output_config={"effort": self.settings.claude_effort},
            # Server-side fallback: if a safety classifier declines, the API retries on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise LLMError("Claude declined the request (stop_reason=refusal).")
        # Append the content exactly as returned (thinking / fallback blocks included): append-only history.
        self.messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in resp.content if b.type == "tool_use"]
        return Turn(text=text, tool_calls=calls)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        # All results of one assistant turn go back in a single user message.
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r.call.id, "is_error": r.is_error,
             "content": json.dumps(r.content, ensure_ascii=False)}
            for r in results
        ]})


def make_model(settings: Settings) -> AgentModel:
    if settings.agent_provider == "anthropic":
        return ClaudeModel(settings)
    if settings.agent_provider == "ollama":
        return OllamaModel(settings)
    raise ValueError(f"Unknown AGENT_PROVIDER '{settings.agent_provider}' (use 'ollama' or 'anthropic').")
