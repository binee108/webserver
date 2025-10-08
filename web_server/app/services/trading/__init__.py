
"""High-level trading service interface composed of modular components."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import sessionmaker

from app import db
from app.models import Account, Strategy, StrategyAccount
from app.services.utils import to_decimal

from .core import TradingCore
from .event_emitter import EventEmitter
from .order_manager import OrderManager
from .position_manager import PositionManager
from .quantity_calculator import QuantityCalculator, QuantityCalculationError
from .record_manager import RecordManager
from .exchange_limit_tracker import ExchangeLimitTracker
from .order_queue_manager import OrderQueueManager

logger = logging.getLogger(__name__)


class TradingError(Exception):
    """Raised when trading workflow fails irrecoverably."""


class OrderError(Exception):
    """Raised when order lifecycle operations fail."""


class PositionError(Exception):
    """Raised when position lifecycle operations fail."""


class TradingService:
    """Facade that exposes trading behaviours composed from specialized managers."""

    def __init__(self) -> None:
        self.session = db.session
        self._SessionLocal = None

        self.record_manager = RecordManager(service=self)
        self.quantity_calculator = QuantityCalculator(service=self)
        self.position_manager = PositionManager(service=self)
        self.order_manager = OrderManager(service=self)
        self.core = TradingCore(service=self)
        self.event_emitter = EventEmitter(service=self)
        self.exchange_limit_tracker = ExchangeLimitTracker  # classmethod만 있는 유틸리티 클래스
        self.order_queue_manager = OrderQueueManager(service=self)

        logger.info("✅ 통합 트레이딩 서비스 초기화 완료 (모듈형 구성 + 대기열 관리)")

    @property
    def SessionLocal(self):
        """Lazy initialized SessionLocal reference."""
        if self._SessionLocal is None:
            self._SessionLocal = sessionmaker(bind=db.engine)
        return self._SessionLocal

    # Core execution -------------------------------------------------
    def execute_trade(self, strategy: Strategy, symbol: str, side: str,
                      quantity: Decimal, order_type: str,
                      price: Optional[Decimal] = None,
                      stop_price: Optional[Decimal] = None,
                      strategy_account_override: Optional[StrategyAccount] = None,
                      schedule_refresh: bool = True,
                      timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.core.execute_trade(
            strategy=strategy,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_price=stop_price,
            strategy_account_override=strategy_account_override,
            schedule_refresh=schedule_refresh,
            timing_context=timing_context,
        )

    def _execute_exchange_order(self, account: Account, symbol: str, side: str,
                                quantity: Decimal, order_type: str, market_type: str,
                                price: Optional[Decimal] = None,
                                stop_price: Optional[Decimal] = None,
                                timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.core._execute_exchange_order(
            account=account,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            market_type=market_type,
            price=price,
            stop_price=stop_price,
            timing_context=timing_context,
        )

    def _to_decimal(self, value: Any, default: Decimal = Decimal('0')) -> Decimal:
        return to_decimal(value, default)

    def _merge_order_with_exchange(self, account: Account, symbol: str,
                                   market_type: str, order_result: Dict[str, Any]) -> Dict[str, Any]:
        return self.core._merge_order_with_exchange(account, symbol, market_type, order_result)

    def process_trading_signal(self, signal_data: Dict[str, Any],
                               timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.core.process_trading_signal(signal_data, timing_context)

    def process_batch_trading_signal(self, signal_data: Dict[str, Any],
                                     timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.core.process_batch_trading_signal(signal_data, timing_context)

    # Order management -----------------------------------------------
    def create_order(self, strategy_id: int, symbol: str, side: str,
                      quantity: Decimal, order_type: str = 'MARKET',
                      price: Optional[Decimal] = None,
                      stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        return self.order_manager.create_order(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_price=stop_price,
        )

    def cancel_order(self, order_id: str, symbol: str, account_id: int) -> Dict[str, Any]:
        return self.order_manager.cancel_order(order_id, symbol, account_id)

    def cancel_order_by_user(self, order_id: str, user_id: int) -> Dict[str, Any]:
        return self.order_manager.cancel_order_by_user(order_id, user_id)

    def get_open_orders(self, account_id: int, symbol: Optional[str] = None,
                        market_type: str = 'spot') -> Dict[str, Any]:
        return self.order_manager.get_open_orders(account_id, symbol, market_type)

    def cancel_all_orders(self, strategy_id: int, symbol: Optional[str] = None,
                          account_id: Optional[int] = None,
                          side: Optional[str] = None,
                          timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.order_manager.cancel_all_orders(strategy_id, symbol, account_id, side, timing_context)

    def cancel_all_orders_by_user(self, user_id: int, strategy_id: int,
                                  account_id: Optional[int] = None,
                                  symbol: Optional[str] = None) -> Dict[str, Any]:
        return self.order_manager.cancel_all_orders_by_user(user_id, strategy_id, account_id, symbol)

    def get_user_open_orders(self, user_id: int, strategy_id: Optional[int] = None,
                             symbol: Optional[str] = None) -> Dict[str, Any]:
        return self.order_manager.get_user_open_orders(user_id, strategy_id, symbol)

    def update_open_orders_status(self) -> None:
        return self.order_manager.update_open_orders_status()

    # Position management ------------------------------------------------
    def calculate_unrealized_pnl(self) -> None:
        return self.position_manager.calculate_unrealized_pnl()

    def get_user_open_orders_with_positions(self, user_id: int) -> Dict[str, Any]:
        return self.position_manager.get_user_open_orders_with_positions(user_id)

    def get_position_and_orders_by_symbol(self, user_id: int, symbol: str) -> Dict[str, Any]:
        return self.position_manager.get_position_and_orders_by_symbol(user_id, symbol)

    def close_position_by_id(self, position_id: int, user_id: int) -> Dict[str, Any]:
        return self.position_manager.close_position_by_id(position_id, user_id)

    def get_positions(self, strategy_id: int) -> list:
        return self.position_manager.get_positions(strategy_id)

    def process_order_fill(self, strategy_account, order_id: str, **kwargs) -> Dict[str, Any]:
        return self.position_manager.process_order_fill(strategy_account, order_id, **kwargs)


    # Trade record queries
    def get_trade_history(self, strategy_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """전략의 거래 내역 조회
        
        Args:
            strategy_id: 전략 ID
            limit: 조회할 최대 거래 수 (기본 100)
            
        Returns:
            거래 내역 리스트 (최신순)
        """
        return self.record_manager.get_trade_history(strategy_id, limit)
    
    def get_trading_stats(self, strategy_id: int) -> Dict[str, Any]:
        """전략의 거래 통계 조회
        
        Args:
            strategy_id: 전략 ID
            
        Returns:
            Dict with keys: total_trades, active_positions, open_orders, last_trade_time
        """
        return self.record_manager.get_trading_stats(strategy_id)

trading_service = TradingService()

__all__ = [
    'TradingService',
    'trading_service',
    'TradingError',
    'OrderError',
    'PositionError',
    'QuantityCalculationError',
]
