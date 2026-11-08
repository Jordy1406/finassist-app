"""P0-04 acceptance against a real model through Ollama.

Run with:  pytest -m integration
"""

from datetime import datetime

import httpx
import pytest

from app.agent import AgentSession
from app.agent_models import OllamaModel
from app.broker import JAKARTA, MockBroker
from app.config import get_settings

settings = get_settings()
OPEN = datetime(2026, 11, 10, 10, 0, tzinfo=JAKARTA)


def _ollama_up() -> bool:
    try:
        return httpx.get(f"{settings.ollama_host}/api/version", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = [pytest.mark.integration, pytest.mark.skipif(not _ollama_up(), reason="Ollama is not running")]


def new_session() -> AgentSession:
    return AgentSession(settings, model=OllamaModel(settings), broker=MockBroker(now=lambda: OPEN))


def test_buy_request_asks_confirmation_before_any_order():
    s = new_session()
    out = s.handle("beli 100 lembar KOPX")
    assert s.broker.order_history() == [], "no order may execute before confirmation"
    assert out.pending_order is not None, f"expected a pending order, got reply: {out.reply!r}"
    assert out.pending_order["ticker"] == "KOPX" and out.pending_order["quantity"] == 100
    assert any(e["tool"] == "place_order" and e["status"] == "pending_confirmation" for e in out.tool_calls)

    done = s.handle("ya")
    assert len(s.broker.order_history()) == 1
    assert [e.status for e in s.log if e.tool == "place_order"] == ["pending_confirmation", "executed"]
    assert "terisi" in done.reply


def test_quote_question_uses_get_quote():
    s = new_session()
    out = s.handle("Berapa harga saham TANX sekarang?")
    assert any(e["tool"] == "get_quote" and e["status"] == "ok" for e in out.tool_calls), out.tool_calls
    assert s.broker.order_history() == []
