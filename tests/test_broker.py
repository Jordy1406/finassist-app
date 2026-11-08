from datetime import datetime, time

import pytest

from app.broker import JAKARTA, LOT_SIZE, BrokerConfig, BrokerError, MockBroker, tick_size

TUESDAY_10AM = datetime(2026, 11, 10, 10, 0, tzinfo=JAKARTA)


def broker_at(when: datetime = TUESDAY_10AM, **config) -> MockBroker:
    return MockBroker(BrokerConfig(**config) if config else None, now=lambda: when)


def error_code(fn, *args, **kwargs) -> str:
    with pytest.raises(BrokerError) as exc:
        fn(*args, **kwargs)
    assert exc.value.message, "every rejection needs a human-readable message"
    return exc.value.code


# --- quotes ---------------------------------------------------------------------

def test_quote_returns_fictional_price_tick_and_lot():
    q = broker_at().get_quote("kopx")
    assert q == {"ticker": "KOPX", "name": "PT Kopi Nusantara Fiktif Tbk", "price": 1250, "tick_size": 5,
                 "lot_size": 100, "market_open": True}


def test_quote_unknown_ticker_lists_available_codes():
    with pytest.raises(BrokerError) as exc:
        broker_at().get_quote("BBCA")
    assert exc.value.code == "UNKNOWN_TICKER"
    assert "KOPX" in exc.value.message


@pytest.mark.parametrize("price,tick", [(1, 1), (199, 1), (200, 2), (498, 2), (500, 5), (1995, 5),
                                        (2000, 10), (4990, 10), (5000, 25), (7850, 25)])
def test_tick_size_bands(price, tick):
    assert tick_size(price) == tick


# --- portfolio ------------------------------------------------------------------

def test_starting_portfolio():
    p = broker_at().get_portfolio()
    assert p["cash"] == 100_000_000
    assert p["positions"] == [{"ticker": "KOPX", "shares": 500, "lots": 5, "avg_price": 1200, "last_price": 1250,
                               "market_value": 625_000, "unrealized_pl": 25_000}]
    assert p["total_value"] == 100_625_000


# --- happy path -----------------------------------------------------------------

def test_buy_fills_at_last_price_and_updates_cash_position_and_history():
    b = broker_at()
    fill = b.place_order("TANX", "buy", 1000)
    assert fill["status"] == "filled" and fill["price"] == 386 and fill["value"] == 386_000
    assert fill["order_id"] == "ORD-0001" and fill["timestamp"].startswith("2026-11-10T10:00:00")
    assert b.cash == 100_000_000 - 386_000
    assert {p["ticker"]: p["shares"] for p in b.get_portfolio()["positions"]} == {"KOPX": 500, "TANX": 1000}
    assert len(b.order_history()) == 1


def test_buy_more_updates_weighted_average_price():
    b = broker_at()
    b.place_order("KOPX", "buy", 500, price=1300)
    pos = next(p for p in b.get_portfolio()["positions"] if p["ticker"] == "KOPX")
    assert pos["shares"] == 1000 and pos["avg_price"] == 1250    # (500*1200 + 500*1300) / 1000


def test_sell_all_removes_position_and_adds_cash():
    b = broker_at()
    b.place_order("KOPX", "sell", 500)
    assert b.get_portfolio()["positions"] == []
    assert b.cash == 100_000_000 + 500 * 1250


def test_reset_restores_starting_state():
    b = broker_at()
    b.place_order("TANX", "buy", 100)
    b.reset()
    assert b.cash == 100_000_000 and len(b.order_history()) == 0
    assert [p["ticker"] for p in b.get_portfolio()["positions"]] == ["KOPX"]


def test_rejected_order_changes_nothing():
    b = broker_at()
    before = (b.cash, b.get_portfolio(), b.order_history())
    error_code(b.place_order, "TANX", "buy", 150)
    assert (b.cash, b.get_portfolio(), b.order_history()) == before


# --- one test per rule --------------------------------------------------------------

def test_rule_unknown_ticker():
    assert error_code(broker_at().place_order, "XXXX", "buy", 100) == "UNKNOWN_TICKER"


@pytest.mark.parametrize("side", ["hold", "", "short"])
def test_rule_invalid_side(side):
    assert error_code(broker_at().place_order, "KOPX", side, 100) == "INVALID_SIDE"


@pytest.mark.parametrize("qty", [0, -100, 100.0, "100", True])
def test_rule_invalid_quantity(qty):
    assert error_code(broker_at().place_order, "KOPX", "buy", qty) == "INVALID_QUANTITY"


@pytest.mark.parametrize("qty", [1, 50, 150, 1001])
def test_rule_lot_size(qty):
    assert error_code(broker_at().place_order, "KOPX", "buy", qty) == "LOT_SIZE"


@pytest.mark.parametrize("price", [0, -5, 1250.0])
def test_rule_invalid_price(price):
    assert error_code(broker_at().place_order, "KOPX", "buy", 100, price=price) == "INVALID_PRICE"


@pytest.mark.parametrize("ticker,price", [("KOPX", 1252), ("TANX", 387), ("LAUX", 4525), ("BATX", 7860)])
def test_rule_tick_size(ticker, price):
    assert error_code(broker_at().place_order, ticker, "buy", 100, price=price) == "TICK_SIZE"


@pytest.mark.parametrize("when", [
    datetime(2026, 11, 10, 8, 59, tzinfo=JAKARTA),    # before open
    datetime(2026, 11, 10, 15, 50, tzinfo=JAKARTA),   # at close (end is exclusive)
    datetime(2026, 11, 14, 10, 0, tzinfo=JAKARTA),    # Saturday
    datetime(2026, 11, 15, 10, 0, tzinfo=JAKARTA),    # Sunday
])
def test_rule_market_closed(when):
    assert error_code(broker_at(when).place_order, "KOPX", "buy", 100) == "MARKET_CLOSED"


def test_market_hours_are_judged_in_jakarta_time():
    from datetime import timezone
    utc_3am = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)   # 10:00 WIB
    assert broker_at(utc_3am).market_open() is True


def test_market_hours_are_configurable():
    b = broker_at(datetime(2026, 11, 10, 8, 0, tzinfo=JAKARTA), open_time=time(7, 0))
    assert b.place_order("KOPX", "buy", 100)["status"] == "filled"


def test_rule_order_limit():
    # 5 000 lots of BATX at 7 850 = Rp 3.925 bn, far above the default Rp 50 m limit
    assert error_code(broker_at().place_order, "BATX", "buy", 5000 * LOT_SIZE) == "ORDER_LIMIT"


def test_order_limit_boundary_is_inclusive():
    b = broker_at(max_order_value=125_000)
    assert b.place_order("KOPX", "buy", 100)["value"] == 125_000          # exactly at the limit
    assert error_code(b.place_order, "KOPX", "buy", 100, price=1255) == "ORDER_LIMIT"


def test_rule_insufficient_funds():
    b = broker_at(starting_cash=100_000)
    assert error_code(b.place_order, "KOPX", "buy", 100) == "INSUFFICIENT_FUNDS"   # needs 125 000


def test_rule_insufficient_shares():
    b = broker_at()
    assert error_code(b.place_order, "KOPX", "sell", 600) == "INSUFFICIENT_SHARES"
    assert error_code(b.place_order, "TANX", "sell", 100) == "INSUFFICIENT_SHARES"   # not held at all


def test_rule_order_lot_check_runs_before_market_hours():
    # A malformed order is reported as malformed even when the market is closed.
    b = broker_at(datetime(2026, 11, 14, 10, 0, tzinfo=JAKARTA))
    assert error_code(b.place_order, "KOPX", "buy", 150) == "LOT_SIZE"
