import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.order_fill_monitor import OrderFillMonitor
from app.services import order_fill_monitor as ofm_module
from app.services.order_mapping_cache import order_mapping_cache


@pytest.mark.asyncio
async def test_confirm_order_uses_cache_when_open_order_missing(monkeypatch):
    """
    OpenOrder가 없을 때 캐시에 저장된 market_type을 사용해 futures로 조회해야 한다.
    """
    # App context 모킹
    mock_app = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = None
    mock_ctx.__exit__.return_value = None
    mock_app.app_context.return_value = mock_ctx

    # Account/OpenOrder 모킹 (모듈 레벨 클래스 대체)
    class DummyAccount:
        exchange = 'BINANCE'
        id = 1

    class DummyAccountModel:
        class query:  # noqa: D401 - 간단한 더미 쿼리 객체
            @staticmethod
            def get(_id):
                return DummyAccount

    class DummyOpenOrderFilter:
        def first(self):
            return None

    class DummyOpenOrderModel:
        class query:
            @staticmethod
            def filter_by(**kwargs):
                return DummyOpenOrderFilter()

    monkeypatch.setattr(ofm_module, "Account", DummyAccountModel)
    monkeypatch.setattr(ofm_module, "OpenOrder", DummyOpenOrderModel)

    # 캐시 초기화 후 등록
    order_mapping_cache._cache.clear()
    order_mapping_cache.register(
        exchange_order_id="ex123",
        account_id=1,
        exchange="binance",
        market_type="futures",
        symbol="BTC/USDT",
    )

    fetched_call = {}

    def fake_fetch_order(account, symbol, order_id, market_type):
        fetched_call["account"] = account
        fetched_call["symbol"] = symbol
        fetched_call["order_id"] = order_id
        fetched_call["market_type"] = market_type
        return {
            'success': True,
            'status': 'FILLED',
            'filled_quantity': Decimal('0.01'),
            'average_price': Decimal('100'),
            'side': 'BUY',
            'order_type': 'MARKET',
        }

    monkeypatch.setattr(ofm_module.exchange_service, "fetch_order", fake_fetch_order)

    monitor = OrderFillMonitor(mock_app)
    result = await monitor._confirm_order_status(1, "ex123", "BTC/USDT")

    assert result is not None
    assert fetched_call["market_type"] == 'futures'
    assert fetched_call["symbol"] == "BTC/USDT"
    assert result['status'] == 'FILLED'
