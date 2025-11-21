import time

import pytest

from app.services.order_mapping_cache import OrderMappingCache


def test_register_and_get_returns_payload():
    cache = OrderMappingCache(ttl_seconds=60, max_size=10)

    cache.register(
        exchange_order_id="123",
        account_id=1,
        exchange="binance",
        market_type="futures",
        symbol="BTC/USDT",
    )

    result = cache.get("123")

    assert result is not None
    assert result["account_id"] == 1
    assert result["exchange"] == "BINANCE"
    assert result["market_type"] == "futures"
    assert result["symbol"] == "BTC/USDT"


def test_ttl_expiry(monkeypatch):
    cache = OrderMappingCache(ttl_seconds=1, max_size=10)

    cache.register(
        exchange_order_id="abc",
        account_id=1,
        exchange="binance",
        market_type="futures",
        symbol="BTC/USDT",
    )

    original_time = time.time
    monkeypatch.setattr(time, "time", lambda: original_time() + 2)

    # Fast-forward time beyond TTL
    assert cache.get("abc") is None


def test_max_size_eviction():
    cache = OrderMappingCache(ttl_seconds=60, max_size=2)

    cache.register("id1", 1, "binance", "futures", "BTC/USDT")
    cache.register("id2", 1, "binance", "futures", "ETH/USDT")
    cache.register("id3", 1, "binance", "futures", "XRP/USDT")

    remaining = {k for k in cache._cache.keys()}
    # max_size=2 -> 하나는 제거되어야 함
    assert len(remaining) == 2
    assert "id3" in remaining
