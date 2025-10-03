"""
통합 트레이딩 서비스

Trading + Order + Position + Orchestrator 관련 모든 기능 통합
1인 사용자를 위한 단순하고 효율적인 트레이딩 관리 서비스입니다.
"""

import logging
import time
import threading
import os
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import current_app
from sqlalchemy.orm import sessionmaker, joinedload
from sqlalchemy import and_, or_, func

from app import db
from app.models import (
    Strategy, Account, StrategyAccount, StrategyCapital,
    StrategyPosition, Trade, OpenOrder, WebhookLog, TradeExecution
)
from app.services.utils import to_decimal, decimal_to_float, calculate_is_entry
from app.constants import MarketType, Exchange, OrderType
from app.services.exchange import exchange_service
from app.services.price_cache import price_cache
from app.services.security import security_service
from app.services.order_tracking import OrderTrackingService
from .record_manager import RecordManager
from .event_emitter import EventEmitter
from .quantity_calculator import QuantityCalculator, QuantityCalculationError
from .position_manager import PositionManager
from .order_manager import OrderManager
from .core import TradingCore

logger = logging.getLogger(__name__)


class TradingError(Exception):
    """트레이딩 관련 오류"""
    pass


class OrderError(Exception):
    """주문 관련 오류"""
    pass


class PositionError(Exception):
    """포지션 관련 오류"""
    pass


class TradingService:
    """
    통합 트레이딩 서비스

    기존 서비스들 통합:
    - trading_service.py
    - order_service.py
    - order_execution_service.py
    - position_service.py
    - trading_orchestrator.py
    - strategy_order_service.py (부분)
    """

    def __init__(self):
        self.session = db.session
        self._SessionLocal = None
        self.record_manager = RecordManager(service=self)
        self.quantity_calculator = QuantityCalculator(service=self)
        self.position_manager = PositionManager(service=self)
        self.order_manager = OrderManager(service=self)
        self.core = TradingCore(service=self)
        self.event_emitter = EventEmitter(service=self)
        logger.info("✅ 통합 트레이딩 서비스 초기화 완료 (안전장치 제거됨)")

    @property
    def SessionLocal(self):
        """지연 초기화된 SessionLocal"""
        if self._SessionLocal is None:
            self._SessionLocal = sessionmaker(bind=db.engine)
        return self._SessionLocal

    # === 핵심 트레이딩 실행 ===

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
            timing_context=timing_context
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
            timing_context=timing_context
        )

    def _to_decimal(self, value: Any, default: Decimal = Decimal('0')) -> Decimal:
        return self.core._to_decimal(value, default)

    def _merge_order_with_exchange(self, account: Account, symbol: str,
                                   market_type: str, order_result: Dict[str, Any]) -> Dict[str, Any]:
        return self.core._merge_order_with_exchange(account, symbol, market_type, order_result)

    def process_trading_signal(self, signal_data: Dict[str, Any],
                               timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.core.process_trading_signal(signal_data, timing_context)

    def process_batch_trading_signal(self, signal_data: Dict[str, Any],
                                     timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.core.process_batch_trading_signal(signal_data, timing_context)

    # === 주문 관리 ===

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
            stop_price=stop_price
        )

    def cancel_order(self, order_id: str, symbol: str, account_id: int) -> Dict[str, Any]:
        return self.order_manager.cancel_order(order_id, symbol, account_id)

    def cancel_order_by_user(self, order_id: str, user_id: int) -> Dict[str, Any]:
        return self.order_manager.cancel_order_by_user(order_id, user_id)

    def get_open_orders(self, account_id: int, symbol: Optional[str] = None,
                        market_type: str = 'spot') -> Dict[str, Any]:
        return self.order_manager.get_open_orders(account_id, symbol, market_type)

    def cancel_all_orders(self, strategy_id: int, symbol: Optional[str] = None,
                          timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        return self.order_manager.cancel_all_orders(strategy_id, symbol, timing_context)

    def cancel_all_orders_by_user(self, user_id: int, strategy_id: int,
                                  symbol: Optional[str] = None) -> Dict[str, Any]:
        return self.order_manager.cancel_all_orders_by_user(user_id, strategy_id, symbol)

    def get_user_open_orders(self, user_id: int, strategy_id: Optional[int] = None,
                             symbol: Optional[str] = None) -> Dict[str, Any]:
        return self.order_manager.get_user_open_orders(user_id, strategy_id, symbol)

