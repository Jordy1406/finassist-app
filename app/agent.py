"""Tool-using agent over the MOCK broker.

Safety rule enforced in code, not left to the model: `place_order` is never executed when the model calls it.
A valid order becomes a *pending* order and the user is asked to confirm. It executes only if the user's NEXT
message is an explicit confirmation ("ya", "setuju", "konfirmasi", ...); anything else cancels it.

Every tool call is written to a structured per-session log (also emitted as JSON lines on the "finassist.agent"
logger) so tests can assert tool names, arguments, order and outcomes.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone

from app.agent_models import AgentModel, ToolCall, ToolResult, make_model
from app.broker import LOT_SIZE, BrokerConfig, BrokerError, MockBroker
from app.config import Settings

log = logging.getLogger("finassist.agent")

SYSTEM_PROMPT = """Kamu adalah FinAssist ID, asisten untuk akun broker MOCK berisi data fiktif.
- Pakai get_quote untuk harga saham, get_portfolio untuk saldo dan kepemilikan, place_order untuk order beli/jual.
- Kode saham yang tersedia hanya: KOPX, TANX, LAUX, BATX, DIGX.
- quantity di place_order dalam LEMBAR. 1 lot = 100 lembar, jadi "2 lot" berarti quantity 200.
- Saat user meminta order, panggil place_order dengan argumen dari permintaannya. Sistem akan meminta konfirmasi
  user sebelum order dieksekusi. Jangan pernah mengatakan order sudah dieksekusi kecuali hasil tool berkata "filled".
- Jangan memberi rekomendasi beli/jual. Jawab singkat dalam Bahasa Indonesia."""

TOOLS = [
    {
        "name": "get_quote",
        "description": "Harga terakhir, fraksi harga dan status pasar untuk satu kode saham fiktif.",
        "parameters": {"type": "object", "properties": {"ticker": {"type": "string", "description": "Kode saham, mis. KOPX"}},
                       "required": ["ticker"]},
    },
    {
        "name": "get_portfolio",
        "description": "Saldo kas, posisi saham dan nilai total akun mock.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "place_order",
        "description": "Ajukan order beli/jual. Order TIDAK langsung dieksekusi: sistem meminta konfirmasi user dulu.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "quantity": {"type": "integer", "description": "Jumlah lembar, kelipatan 100"},
                "price": {"type": "integer", "description": "Harga limit dalam Rupiah (opsional; default harga terakhir)"},
            },
            "required": ["ticker", "side", "quantity"],
        },
    },
]

CONFIRM = re.compile(r"^\s*(ya|iya|y|yes|ok|oke|okay|setuju|konfirmasi|lanjut|lanjutkan|benar|betul)\b[\s.!,]*"
                     r"(order|lanjut|eksekusi|ya|saja|aja)?[\s.!]*$", re.I)
CANCEL = re.compile(r"^\s*(tidak|nggak|enggak|gak|ga|batal|batalkan|jangan|no|cancel)\b", re.I)


@dataclass
class LogEntry:
    seq: int
    turn: int
    tool: str
    arguments: dict
    status: str            # ok | error | pending_confirmation | executed | cancelled
    result: dict | None = None
    error_code: str | None = None
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


@dataclass
class AgentReply:
    session_id: str
    reply: str
    pending_order: dict | None
    tool_calls: list[dict]


class AgentSession:
    def __init__(self, settings: Settings, model: AgentModel | None = None, broker: MockBroker | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.settings = settings
        self.model = model or make_model(settings)
        self.broker = broker or MockBroker(_broker_config(settings))
        self.log: list[LogEntry] = []
        self.pending: dict | None = None
        self.turn = 0

    # --- public ---------------------------------------------------------------------
    def handle(self, message: str) -> AgentReply:
        self.turn += 1
        start = len(self.log)

        if self.pending is not None:
            order, self.pending = self.pending, None
            if CONFIRM.match(message):
                self.model.add_user(message)
                reply = self._execute_confirmed(order)
                self.model.add_assistant_text(reply)
                return self._reply(reply, start)
            self._record(order, "cancelled", {"reason": "user did not confirm"})
            if CANCEL.match(message):
                self.model.add_user(message)
                reply = "Order dibatalkan. Tidak ada order yang dikirim."
                self.model.add_assistant_text(reply)
                return self._reply(reply, start)
            # Any other message: the pending order is dropped and the message is handled normally.

        self.model.add_user(message)
        reply = self._run_loop()
        return self._reply(reply, start)

    # --- loop -----------------------------------------------------------------------
    def _run_loop(self) -> str:
        for _ in range(self.settings.agent_max_steps):
            turn = self.model.step(SYSTEM_PROMPT, TOOLS)
            if not turn.tool_calls:
                return turn.text.strip() or "Maaf, saya belum bisa menjawab permintaan itu."

            results, confirmation = [], None
            for call in turn.tool_calls:
                result, is_error, confirm_text = self._dispatch(call)
                results.append(ToolResult(call, result, is_error))
                confirmation = confirmation or confirm_text
            self.model.add_tool_results(results)
            if confirmation:
                self.model.add_assistant_text(confirmation)
                return confirmation
        return "Maaf, permintaan ini butuh terlalu banyak langkah. Coba pecah menjadi permintaan yang lebih sederhana."

    def _dispatch(self, call: ToolCall) -> tuple[dict, bool, str | None]:
        args = _coerce_ints(call.arguments, ("quantity", "price"))
        try:
            if call.name == "get_quote":
                result = self.broker.get_quote(args.get("ticker", ""))
            elif call.name == "get_portfolio":
                result = self.broker.get_portfolio()
            elif call.name == "place_order":
                if self.pending is not None:
                    result = {"status": "rejected", "reason": "Sudah ada order yang menunggu konfirmasi."}
                    self._log(call.name, args, "error", result, "PENDING_EXISTS")
                    return result, True, None
                order = self.broker.check_order(args.get("ticker", ""), args.get("side", ""),
                                                args.get("quantity"), args.get("price"))
                self.pending = order
                result = {"status": "pending_confirmation", "order": order,
                          "message": "Order belum dieksekusi; menunggu konfirmasi user."}
                self._log(call.name, args, "pending_confirmation", result)
                return result, False, _confirmation_text(order)
            else:
                result = {"error": f"Tool '{call.name}' tidak dikenal."}
                self._log(call.name, args, "error", result, "UNKNOWN_TOOL")
                return result, True, None
        except BrokerError as exc:
            result = {"error": exc.message, "code": exc.code}
            self._log(call.name, args, "error", result, exc.code)
            return result, True, None
        self._log(call.name, args, "ok", result)
        return result, False, None

    def _execute_confirmed(self, order: dict) -> str:
        args = {k: order[k] for k in ("ticker", "side", "quantity", "price")}
        try:
            fill = self.broker.place_order(**args)
        except BrokerError as exc:  # e.g. the market closed between the request and the confirmation
            self._log("place_order", args, "error", {"error": exc.message, "code": exc.code}, exc.code)
            return f"Order gagal dieksekusi: {exc.message}"
        self._log("place_order", args, "executed", fill)
        verb = "Beli" if fill["side"] == "buy" else "Jual"
        return (f"Order {fill['order_id']} terisi: {verb} {fill['quantity']:,} lembar {fill['ticker']} "
                f"@ Rp{fill['price']:,} = Rp{fill['value']:,}.").replace(",", ".")

    # --- logging --------------------------------------------------------------------
    def _log(self, tool: str, args: dict, status: str, result: dict | None, code: str | None = None) -> None:
        entry = LogEntry(len(self.log) + 1, self.turn, tool, args, status, result, code)
        self.log.append(entry)
        log.info(json.dumps({"session": self.id, **asdict(entry)}, ensure_ascii=False, default=str))

    def _record(self, order: dict, status: str, result: dict) -> None:
        self._log("place_order", {k: order[k] for k in ("ticker", "side", "quantity", "price")}, status, result)

    def _reply(self, text: str, start: int) -> AgentReply:
        return AgentReply(self.id, text, self.pending, [asdict(e) for e in self.log[start:]])


class SessionStore:
    """In-memory sessions (process-local; fine for a demo/test target)."""

    def __init__(self, max_sessions: int = 200):
        self.sessions: dict[str, AgentSession] = {}
        self.max_sessions = max_sessions

    def get_or_create(self, session_id: str | None, settings: Settings) -> AgentSession:
        if session_id:
            if session_id not in self.sessions:
                raise KeyError(session_id)
            return self.sessions[session_id]
        if len(self.sessions) >= self.max_sessions:
            self.sessions.pop(next(iter(self.sessions)))
        session = AgentSession(settings)
        self.sessions[session.id] = session
        return session

    def get(self, session_id: str) -> AgentSession:
        return self.sessions[session_id]


def _broker_config(settings: Settings) -> BrokerConfig:
    if settings.broker_always_open:
        return BrokerConfig(open_time=time(0, 0), close_time=time.max, trading_days=frozenset(range(7)))
    return BrokerConfig()


def _coerce_ints(args: dict, keys: tuple[str, ...]) -> dict:
    """Small models often send numbers as strings ("100"); accept plain integer strings only."""
    out = dict(args)
    for k in keys:
        v = out.get(k)
        if isinstance(v, str) and re.fullmatch(r"\s*\d+\s*", v):
            out[k] = int(v)
    return out


def _confirmation_text(order: dict) -> str:
    verb = "BELI" if order["side"] == "buy" else "JUAL"
    lots = order["quantity"] // LOT_SIZE
    text = (f"Konfirmasi order: {verb} {order['quantity']:,} lembar ({lots} lot) {order['ticker']} "
            f"@ Rp{order['price']:,} = Rp{order['value']:,}.").replace(",", ".")
    return f"{text} Balas 'ya' untuk mengeksekusi, atau 'batal' untuk membatalkan."
