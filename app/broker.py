"""In-memory MOCK broker for FinAssist ID. All tickers, prices and accounts are fictional.

Rules enforced by `place_order` (each failure raises BrokerError with a stable `code`):
  UNKNOWN_TICKER      ticker not in the fictional list
  INVALID_SIDE        side is not "buy" or "sell"
  INVALID_QUANTITY    quantity is not a positive integer
  LOT_SIZE            quantity is not a multiple of LOT_SIZE (100 shares = 1 lot)
  INVALID_PRICE       price is not a positive integer (Rupiah)
  TICK_SIZE           price is not a multiple of the tick for its price band
  MARKET_CLOSED       outside the configured trading days/hours (Asia/Jakarta)
  ORDER_LIMIT         order value exceeds the per-order maximum
  INSUFFICIENT_FUNDS  buy value exceeds available cash
  INSUFFICIENT_SHARES sell quantity exceeds shares held

Orders fill immediately at the given price (default: last price). No fees, no partial fills, no order book.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Callable

# WIB has no daylight saving, so a fixed offset is exact and needs no tzdata package on Windows.
JAKARTA = timezone(timedelta(hours=7), "WIB")
LOT_SIZE = 100

# Fictional companies; the "X" suffix keeps codes apart from real IDX tickers.
DEFAULT_PRICES: dict[str, tuple[str, int]] = {
    "KOPX": ("PT Kopi Nusantara Fiktif Tbk", 1_250),
    "TANX": ("PT Tani Makmur Fiktif Tbk", 386),
    "LAUX": ("PT Laut Biru Fiktif Tbk", 4_520),
    "BATX": ("PT Batu Bara Fiktif Tbk", 7_850),
    "DIGX": ("PT Digital Kita Fiktif Tbk", 142),
}

# (lower bound inclusive, tick) — a simplified version of IDX price fractions.
TICK_TABLE: list[tuple[int, int]] = [(0, 1), (200, 2), (500, 5), (2_000, 10), (5_000, 25)]


class BrokerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BrokerConfig:
    starting_cash: int = 100_000_000
    starting_positions: dict[str, tuple[int, int]] = field(default_factory=lambda: {"KOPX": (500, 1_200)})
    max_order_value: int = 50_000_000
    open_time: time = time(9, 0)
    close_time: time = time(15, 50)
    trading_days: frozenset[int] = frozenset({0, 1, 2, 3, 4})  # Monday..Friday


@dataclass
class Position:
    ticker: str
    shares: int
    avg_price: float


@dataclass
class Order:
    order_id: str
    ticker: str
    side: str
    quantity: int
    price: int
    value: int
    timestamp: str


def tick_size(price: int) -> int:
    tick = TICK_TABLE[0][1]
    for lower, t in TICK_TABLE:
        if price >= lower:
            tick = t
    return tick


class MockBroker:
    def __init__(self, config: BrokerConfig | None = None, now: Callable[[], datetime] | None = None,
                 prices: dict[str, tuple[str, int]] | None = None):
        self.config = config or BrokerConfig()
        self._now = now or (lambda: datetime.now(JAKARTA))
        self._initial_prices = dict(prices or DEFAULT_PRICES)
        self.reset()

    # --- state -----------------------------------------------------------------
    def reset(self) -> None:
        """Back to the starting account, prices and an empty order history."""
        self.prices = dict(self._initial_prices)
        self.cash = self.config.starting_cash
        self.positions = {t: Position(t, s, float(p)) for t, (s, p) in self.config.starting_positions.items()}
        self.history: list[Order] = []

    def market_open(self, at: datetime | None = None) -> bool:
        at = (at or self._now()).astimezone(JAKARTA)
        return at.weekday() in self.config.trading_days and self.config.open_time <= at.time() < self.config.close_time

    # --- tools -----------------------------------------------------------------
    def get_quote(self, ticker: str) -> dict:
        t = self._ticker(ticker)
        name, price = self.prices[t]
        return {"ticker": t, "name": name, "price": price, "tick_size": tick_size(price), "lot_size": LOT_SIZE,
                "market_open": self.market_open()}

    def get_portfolio(self) -> dict:
        positions = []
        for p in sorted(self.positions.values(), key=lambda p: p.ticker):
            last = self.prices[p.ticker][1]
            positions.append({
                "ticker": p.ticker, "shares": p.shares, "lots": p.shares // LOT_SIZE,
                "avg_price": round(p.avg_price, 2), "last_price": last, "market_value": p.shares * last,
                "unrealized_pl": round(p.shares * (last - p.avg_price), 2),
            })
        equity = sum(p["market_value"] for p in positions)
        return {"cash": self.cash, "positions": positions, "equity_value": equity, "total_value": self.cash + equity}

    def place_order(self, ticker: str, side: str, quantity: int, price: int | None = None) -> dict:
        t = self._ticker(ticker)
        side = str(side).lower()
        if side not in ("buy", "sell"):
            raise BrokerError("INVALID_SIDE", f"Sisi order harus 'buy' atau 'sell', bukan '{side}'.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise BrokerError("INVALID_QUANTITY", "Jumlah lembar harus bilangan bulat positif.")
        if quantity % LOT_SIZE:
            raise BrokerError("LOT_SIZE", f"Jumlah harus kelipatan {LOT_SIZE} lembar (1 lot); diterima {quantity}.")
        if price is None:
            price = self.prices[t][1]
        if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
            raise BrokerError("INVALID_PRICE", "Harga harus bilangan bulat positif dalam Rupiah.")
        if price % tick_size(price):
            raise BrokerError("TICK_SIZE", f"Harga Rp{price:,} tidak sesuai fraksi harga Rp{tick_size(price)}.")
        if not self.market_open():
            raise BrokerError("MARKET_CLOSED", "Pasar sedang tutup; order hanya bisa dikirim pada jam perdagangan.")
        value = quantity * price
        if value > self.config.max_order_value:
            raise BrokerError("ORDER_LIMIT", f"Nilai order Rp{value:,} melebihi batas Rp{self.config.max_order_value:,} per transaksi.")
        if side == "buy" and value > self.cash:
            raise BrokerError("INSUFFICIENT_FUNDS", f"Saldo Rp{self.cash:,} tidak cukup untuk order Rp{value:,}.")
        held = self.positions.get(t).shares if t in self.positions else 0
        if side == "sell" and quantity > held:
            raise BrokerError("INSUFFICIENT_SHARES", f"Hanya memiliki {held} lembar {t}; tidak bisa menjual {quantity}.")

        if side == "buy":
            self.cash -= value
            pos = self.positions.get(t)
            if pos:
                pos.avg_price = (pos.shares * pos.avg_price + value) / (pos.shares + quantity)
                pos.shares += quantity
            else:
                self.positions[t] = Position(t, quantity, float(price))
        else:
            self.cash += value
            pos = self.positions[t]
            pos.shares -= quantity
            if pos.shares == 0:
                del self.positions[t]

        order = Order(f"ORD-{len(self.history) + 1:04d}", t, side, quantity, price, value,
                      self._now().astimezone(JAKARTA).isoformat(timespec="seconds"))
        self.history.append(order)
        return {"status": "filled", **asdict(order)}

    def order_history(self) -> list[dict]:
        return [asdict(o) for o in self.history]

    # --- helpers ---------------------------------------------------------------
    def _ticker(self, ticker: str) -> str:
        t = str(ticker).strip().upper()
        if t not in self.prices:
            known = ", ".join(sorted(self.prices))
            raise BrokerError("UNKNOWN_TICKER", f"Kode saham '{ticker}' tidak dikenal. Kode yang tersedia: {known}.")
        return t
