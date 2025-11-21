import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.trading import core as core_module


class DummySession:
    def __init__(self):
        self.committed = 0
        self.added = []
        self.rolled_back = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


class DummyQuery:
    def __init__(self, obj):
        self.obj = obj

    def get(self, _id):
        return self.obj

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.obj


@pytest.mark.asyncio
async def test_exchange_order_id_committed_before_websocket(monkeypatch):
    """
    거래소 주문 응답 직후 exchange_order_id가 OpenOrder에 기록되어 WebSocket 선행 도착 시 매칭 가능함을 검증.
    """

    # Arrange: Dummy DB session
    dummy_session = DummySession()
    monkeypatch.setattr(core_module.db, "session", dummy_session)

    # Arrange: Dummy Strategy/Account
    class DummyStrategy:
        id = 1
        name = "strat"
        market_type = "FUTURES"

    class DummyAccount:
        id = 1
        exchange = "binance"
        name = "acc"
        api_key = "k"
        secret_api = "s"

    # Dummy StrategyAccount with query.stub
    class DummyStrategyAccount:
        id = 10
        account = DummyAccount()
        is_active = True

    dummy_sa = DummyStrategyAccount()

    class DummyStrategyAccountModel:
        class query(DummyQuery):
            pass

    monkeypatch.setattr(core_module, "StrategyAccount", DummyStrategyAccountModel)
    monkeypatch.setattr(DummyStrategyAccountModel, "query", DummyQuery(dummy_sa))

    # Arrange: Dummy OpenOrder class to capture exchange_order_id
    class DummyOpenOrder:
        def __init__(self, **kwargs):
            self.id = 1
            self.exchange_order_id = kwargs.get("exchange_order_id")
            self.status = kwargs.get("status")
            self.symbol = kwargs.get("symbol")
            self.side = kwargs.get("side")
            self.order_type = kwargs.get("order_type")
            self.quantity = kwargs.get("quantity")
            self.price = kwargs.get("price")
            self.market_type = kwargs.get("market_type")
            self.filled_quantity = kwargs.get("filled_quantity")
            self.stop_price = kwargs.get("stop_price")

    dummy_order = DummyOpenOrder(
        exchange_order_id="PENDING-uuid",
        status="PENDING",
        symbol="BTC/USDT",
        side="SELL",
        order_type="MARKET",
        quantity=0.01,
        price=None,
        market_type="futures",
        filled_quantity=0.0,
        stop_price=None,
    )

    class DummyOpenOrderQuery(DummyQuery):
        pass

    monkeypatch.setattr(core_module, "OpenOrder", DummyOpenOrder)
    monkeypatch.setattr(DummyOpenOrder, "query", DummyOpenOrderQuery(dummy_order), raising=False)

    # Arrange: stub exchange_service.create_order to return real order_id immediately
    def fake_create_order(account, symbol, side, quantity, order_type, market_type, price=None, stop_price=None):
        return {
            'success': True,
            'order_id': 'EX-123',
            'status': 'OPEN',
            'filled_quantity': Decimal('0'),
        }

    monkeypatch.setattr(core_module.exchange_service, "create_order", fake_create_order)

    # Dummy service to satisfy callbacks inside execute_trade
    dummy_service = MagicMock()
    dummy_service.position_manager.process_order_fill.return_value = {
        'success': True,
        'trade_id': 'T1',
        'execution_status': None,
        'trade_status': None,
        'order_result': {
            'order_id': 'EX-123',
            'average_price': Decimal('0'),
            'filled_quantity': Decimal('0'),
        },
        'filled_quantity': Decimal('0'),
        'average_price': Decimal('0'),
        'events_emitted': True,
    }
    dummy_service.order_manager.create_open_order_record.return_value = {'success': True}
    dummy_service.subscribe_symbol = lambda account_id, symbol: None
    dummy_service.event_emitter.emit_order_events_smart = lambda *args, **kwargs: None

    trading_core = core_module.TradingCore(service=dummy_service)

    # Act
    result = trading_core.execute_trade(
        strategy=DummyStrategy(),
        symbol="BTC/USDT",
        side="SELL",
        quantity=Decimal('0.01'),
        order_type="MARKET",
        price=None,
        stop_price=None,
        strategy_account_override=dummy_sa,
        schedule_refresh=False,
    )

    # Assert
    assert result['success'] is True
    # exchange_order_id should be updated to real exchange id
    assert dummy_order.exchange_order_id == 'EX-123'
    # status should transition to OPEN
    assert dummy_order.status == 'OPEN'
    # DB commit should have been attempted
    assert dummy_session.committed > 0
