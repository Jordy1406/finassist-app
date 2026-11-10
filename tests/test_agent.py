from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import AgentSession
from app.agent_models import ClaudeModel, ToolCall, ToolResult, Turn
from app.broker import JAKARTA, MockBroker
from app.config import get_settings
from app.llm import LLMError

OPEN = datetime(2026, 11, 10, 10, 0, tzinfo=JAKARTA)      # Tuesday 10:00 WIB
CLOSED = datetime(2026, 11, 14, 10, 0, tzinfo=JAKARTA)    # Saturday


class ScriptedModel:
    """Fake model: returns the scripted turns in order and records what the agent sent back."""

    name = "scripted"

    def __init__(self, turns):
        self.turns = list(turns)
        self.users, self.assistant_texts, self.tool_results = [], [], []

    def add_user(self, text):
        self.users.append(text)

    def add_assistant_text(self, text):
        self.assistant_texts.append(text)

    def step(self, system, tools):
        if not self.turns:
            raise AssertionError("model was called more times than scripted")
        return self.turns.pop(0)

    def add_tool_results(self, results):
        self.tool_results.append(results)


def call(name, **args):
    return ToolCall(id=f"c-{name}", name=name, arguments=args)


def session(turns, when=OPEN, **settings_overrides):
    settings = replace(get_settings(), **settings_overrides) if settings_overrides else get_settings()
    return AgentSession(settings, model=ScriptedModel(turns), broker=MockBroker(now=lambda: when))


BUY_KOPX = Turn("", [call("place_order", ticker="KOPX", side="buy", quantity=100)])


# --- read-only tools ------------------------------------------------------------------

def test_quote_tool_is_executed_logged_and_returned_to_model():
    s = session([Turn("", [call("get_quote", ticker="KOPX")]), Turn("Harga KOPX Rp1.250.", [])])
    out = s.handle("Berapa harga KOPX?")
    assert out.reply == "Harga KOPX Rp1.250."
    assert [(e["tool"], e["status"], e["arguments"]) for e in out.tool_calls] == [("get_quote", "ok", {"ticker": "KOPX"})]
    assert out.tool_calls[0]["result"]["price"] == 1250
    assert s.model.tool_results[0][0].content["price"] == 1250


def test_tool_error_is_logged_with_code_and_sent_back_as_error():
    s = session([Turn("", [call("get_quote", ticker="BBCA")]), Turn("Kode tidak dikenal.", [])])
    out = s.handle("Harga BBCA?")
    entry = out.tool_calls[0]
    assert entry["status"] == "error" and entry["error_code"] == "UNKNOWN_TICKER"
    assert s.model.tool_results[0][0].is_error is True


def test_unknown_tool_is_rejected():
    s = session([Turn("", [call("transfer_funds", amount=1)]), Turn("Tidak bisa.", [])])
    assert s.handle("Transfer uang").tool_calls[0]["error_code"] == "UNKNOWN_TOOL"


# --- confirmation before orders ----------------------------------------------------------

def test_order_request_asks_confirmation_and_does_not_execute():
    s = session([BUY_KOPX])
    out = s.handle("beli 100 lembar KOPX")
    assert "Konfirmasi order" in out.reply and "BELI 100 lembar (1 lot) KOPX" in out.reply
    assert out.pending_order == {"ticker": "KOPX", "side": "buy", "quantity": 100, "price": 1250, "value": 125_000}
    assert out.tool_calls[0]["status"] == "pending_confirmation"
    assert s.broker.order_history() == [] and s.broker.cash == 100_000_000
    # the model is told the order is pending, not filled
    assert s.model.tool_results[0][0].content["status"] == "pending_confirmation"


@pytest.mark.parametrize("answer", ["ya", "Ya!", "iya", "ok", "setuju", "konfirmasi", "ya lanjut", "lanjutkan"])
def test_explicit_confirmation_executes_exactly_the_pending_order(answer):
    s = session([BUY_KOPX])
    s.handle("beli 100 lembar KOPX")
    out = s.handle(answer)
    assert out.pending_order is None
    assert "terisi" in out.reply and "KOPX" in out.reply
    [order] = s.broker.order_history()
    assert (order["ticker"], order["side"], order["quantity"], order["price"]) == ("KOPX", "buy", 100, 1250)
    assert [e["status"] for e in out.tool_calls] == ["executed"]
    assert s.model.turns == []        # confirmation is handled in code: no extra model call


@pytest.mark.parametrize("answer", ["batal", "tidak", "jangan", "nggak jadi", "cancel"])
def test_cancel_drops_pending_order(answer):
    s = session([BUY_KOPX])
    s.handle("beli 100 lembar KOPX")
    out = s.handle(answer)
    assert "dibatalkan" in out.reply and out.pending_order is None
    assert s.broker.order_history() == []
    assert out.tool_calls[0]["status"] == "cancelled"


@pytest.mark.parametrize("answer", ["ya tapi 200 lembar", "mungkin", "ya, beli yang lain saja", "y e s"])
def test_ambiguous_reply_is_not_a_confirmation(answer):
    s = session([BUY_KOPX, Turn("Baik.", [])])
    s.handle("beli 100 lembar KOPX")
    s.handle(answer)
    assert s.broker.order_history() == [], f"'{answer}' must not execute an order"
    assert s.pending is None


def test_confirmation_without_pending_order_executes_nothing():
    s = session([Turn("Tidak ada order yang menunggu.", [])])
    out = s.handle("ya")
    assert s.broker.order_history() == [] and out.tool_calls == []


def test_confirmation_must_be_the_next_message():
    s = session([BUY_KOPX, Turn("Saldo Anda Rp100 juta.", []), Turn("Tidak ada order yang menunggu.", [])])
    s.handle("beli 100 lembar KOPX")
    s.handle("berapa saldo saya?")      # drops the pending order
    s.handle("ya")                      # too late: goes to the model as a normal message
    assert s.broker.order_history() == []
    assert [e.status for e in s.log] == ["pending_confirmation", "cancelled"]


def test_invalid_order_is_rejected_before_asking_confirmation():
    s = session([Turn("", [call("place_order", ticker="KOPX", side="buy", quantity=150)]), Turn("Harus kelipatan 100.", [])])
    out = s.handle("beli 150 lembar KOPX")
    assert out.pending_order is None and "Konfirmasi" not in out.reply
    assert out.tool_calls[0]["error_code"] == "LOT_SIZE"


def test_second_order_in_same_turn_is_rejected_while_one_is_pending():
    turn = Turn("", [call("place_order", ticker="KOPX", side="buy", quantity=100),
                     call("place_order", ticker="TANX", side="buy", quantity=100)])
    s = session([turn])
    out = s.handle("beli KOPX dan TANX")
    assert [e["status"] for e in out.tool_calls] == ["pending_confirmation", "error"]
    assert out.tool_calls[1]["error_code"] == "PENDING_EXISTS"
    assert out.pending_order["ticker"] == "KOPX"


def test_market_closing_between_request_and_confirmation_is_reported():
    clock = {"now": OPEN}
    s = AgentSession(get_settings(), model=ScriptedModel([BUY_KOPX]), broker=MockBroker(now=lambda: clock["now"]))
    s.handle("beli 100 lembar KOPX")
    clock["now"] = CLOSED
    out = s.handle("ya")
    assert "gagal" in out.reply and out.tool_calls[0]["error_code"] == "MARKET_CLOSED"
    assert s.broker.order_history() == []


def test_string_numbers_from_small_models_are_accepted():
    s = session([Turn("", [call("place_order", ticker="kopx", side="buy", quantity="200")])])
    assert s.handle("beli 2 lot KOPX").pending_order["quantity"] == 200


def test_step_limit_stops_runaway_tool_loops():
    loop = [Turn("", [call("get_portfolio")])] * 3
    s = session(loop, agent_max_steps=3)
    out = s.handle("cek terus")
    assert "terlalu banyak langkah" in out.reply and len(out.tool_calls) == 3


def test_log_sequence_spans_turns():
    s = session([Turn("", [call("get_quote", ticker="KOPX")]), BUY_KOPX])
    s.handle("beli 100 lembar KOPX")
    s.handle("ya")
    assert [(e.seq, e.turn, e.tool, e.status) for e in s.log] == [
        (1, 1, "get_quote", "ok"), (2, 1, "place_order", "pending_confirmation"), (3, 2, "place_order", "executed")]


# --- HTTP endpoints ---------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    store = main.SessionStore()
    monkeypatch.setattr(main, "sessions", store)
    original = store.get_or_create

    def create(session_id, settings, owner="local"):
        if session_id is None:
            s = AgentSession(settings, model=ScriptedModel([BUY_KOPX]), broker=MockBroker(now=lambda: OPEN), owner=owner)
            store.sessions[s.id] = s
            return s
        return original(session_id, settings, owner)

    monkeypatch.setattr(store, "get_or_create", create)
    return TestClient(main.app)


def test_agent_endpoint_flow_with_log_and_state(client):
    first = client.post("/agent", json={"message": "beli 100 lembar KOPX"}).json()
    sid = first["session_id"]
    assert first["pending_order"]["ticker"] == "KOPX"
    assert client.get(f"/agent/{sid}/state").json()["orders"] == []

    second = client.post("/agent", json={"message": "ya", "session_id": sid}).json()
    assert second["pending_order"] is None and "terisi" in second["reply"]

    log = client.get(f"/agent/{sid}/log").json()["tool_calls"]
    assert [e["status"] for e in log] == ["pending_confirmation", "executed"]
    state = client.get(f"/agent/{sid}/state").json()
    assert len(state["orders"]) == 1 and state["portfolio"]["cash"] == 100_000_000 - 125_000


def test_unknown_session_is_404(client):
    assert client.post("/agent", json={"message": "ya", "session_id": "nope"}).status_code == 404
    assert client.get("/agent/nope/log").status_code == 404


def test_agent_endpoint_returns_503_when_model_fails(client, monkeypatch):
    def boom(self, message):
        raise LLMError("down")

    monkeypatch.setattr(AgentSession, "handle", boom)
    assert client.post("/agent", json={"message": "halo"}).status_code == 503


# --- Claude adapter (no network) ---------------------------------------------------------------

class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeAnthropic:
    def __init__(self, response):
        self.sent = None
        outer = self

        class _Messages:
            def create(self, **kwargs):
                outer.sent = kwargs
                return response

        self.beta = _Block(messages=_Messages())


def test_claude_model_request_shape_and_tool_parsing():
    response = _Block(stop_reason="tool_use", content=[
        _Block(type="thinking", thinking=""),
        _Block(type="text", text="Saya cek dulu."),
        _Block(type="tool_use", id="toolu_1", name="get_quote", input={"ticker": "KOPX"}),
    ])
    fake = _FakeAnthropic(response)
    m = ClaudeModel(get_settings(), client=fake)
    m.add_user("Harga KOPX?")
    turn = m.step("sys", [{"name": "get_quote", "description": "d", "parameters": {"type": "object", "properties": {}}}])

    assert fake.sent["model"] == "claude-opus-5-5"
    assert fake.sent["tools"][0] == {"name": "get_quote", "description": "d", "input_schema": {"type": "object", "properties": {}}}
    assert "tool_choice" not in fake.sent                       # forced tool choice is rejected by this model
    assert fake.sent["fallbacks"] == "default" and fake.sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert turn.text == "Saya cek dulu." and turn.tool_calls[0].name == "get_quote"
    assert m.messages[-1]["content"] is response.content       # appended exactly as returned

    m.add_tool_results([ToolResult(turn.tool_calls[0], {"price": 1250})])
    block = m.messages[-1]["content"][0]
    assert block["type"] == "tool_result" and block["tool_use_id"] == "toolu_1" and block["is_error"] is False


def test_claude_refusal_raises():
    fake = _FakeAnthropic(_Block(stop_reason="refusal", content=[]))
    m = ClaudeModel(get_settings(), client=fake)
    m.add_user("x")
    with pytest.raises(LLMError, match="refusal"):
        m.step("sys", [])
