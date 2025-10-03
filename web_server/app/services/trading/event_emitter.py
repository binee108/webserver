
"""Event emission helpers extracted from the legacy trading service."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from app.constants import OrderEventType, OrderStatus, OrderType
from app.models import OpenOrder, Strategy, StrategyAccount

logger = logging.getLogger(__name__)


class EventEmitter:
    """Encapsulates trading-related event emission."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    def emit_trading_event(
        self,
        event_type: str,
        strategy: Strategy,
        symbol: str,
        side: str,
        quantity: Decimal,
        order_result: Dict[str, object],
    ) -> None:
        """Emit a unified trading order event via the SSE event service."""
        try:
            from app.services.event_service import event_service, OrderEvent

            strategy_account = StrategyAccount.query.filter_by(
                strategy_id=strategy.id
            ).first()

            if not strategy_account or not strategy_account.account:
                logger.warning("전략 %s의 계정 정보를 찾을 수 없음", strategy.id)
                return

            account = strategy_account.account

            stop_price_value = None
            raw_response = order_result.get('raw_response')
            if raw_response and hasattr(raw_response, 'stop_price') and raw_response.stop_price is not None:
                stop_price_value = float(raw_response.stop_price)
            elif order_result.get('adjusted_stop_price') is not None:
                stop_price_value = float(order_result.get('adjusted_stop_price'))

            event = OrderEvent(
                event_type=event_type,
                order_id=order_result.get('order_id', ''),
                symbol=symbol,
                strategy_id=strategy.id,
                user_id=strategy.user_id,
                side=side.upper(),
                quantity=float(quantity),
                price=float(order_result.get('average_price', 0)),
                status='FILLED' if event_type == 'trade_executed' else order_result.get('status', 'UNKNOWN'),
                timestamp=datetime.utcnow().isoformat(),
                order_type=order_result.get('order_type', 'MARKET'),
                stop_price=stop_price_value,
                account={
                    'account_id': account.id,
                    'name': account.name,
                    'exchange': account.exchange,
                },
            )
            event_service.emit_order_event(event)
            logger.debug(
                "📡 이벤트 발송 완료: %s - %s %s %s",
                event_type,
                symbol,
                side,
                quantity,
            )

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("이벤트 발송 실패: %s", exc)

    def emit_trade_event(
        self,
        strategy: Strategy,
        symbol: str,
        side: str,
        quantity: Decimal,
        order_result: Dict[str, object],
    ) -> None:
        """Emit the trade executed event."""
        self.emit_trading_event('trade_executed', strategy, symbol, side, quantity, order_result)

    def emit_order_event(
        self,
        strategy: Strategy,
        symbol: str,
        side: str,
        quantity: Decimal,
        order_result: Dict[str, object],
    ) -> None:
        """Emit the order filled event for legacy compatibility."""
        self.emit_trading_event(OrderEventType.ORDER_FILLED, strategy, symbol, side, quantity, order_result)

    def emit_order_events_smart(
        self,
        strategy: Strategy,
        symbol: str,
        side: str,
        quantity: Decimal,
        order_result: Dict[str, object],
    ) -> None:
        """Emit context-aware order events based on the current order state."""
        logger.info("🚀 스마트 이벤트 발송 시작: %s %s %s", symbol, side, quantity)
        logger.debug("order_result: %s", order_result)

        status = order_result.get('status')
        filled_quantity = order_result.get('filled_quantity', 0)
        order_id = order_result.get('order_id')
        order_type = order_result.get('order_type')

        logger.info(
            "📊 주문 정보: ID=%s, 타입=%s, 상태=%s, 체결량=%s",
            order_id,
            order_type,
            status,
            filled_quantity,
        )

        if not order_id:
            logger.warning("order_id가 없어서 스마트 이벤트 발송 불가")
            return

        existing_order = OpenOrder.query.filter_by(
            exchange_order_id=str(order_id)
        ).first()

        events_to_emit = []

        if order_type == OrderType.MARKET:
            logger.info("💰 시장가 주문 처리: %s - ORDER_FILLED 이벤트만 발송", order_id)
            events_to_emit.append((OrderEventType.ORDER_FILLED, quantity))
        elif status in (OrderStatus.NEW, OrderStatus.OPEN):
            events_to_emit.append((OrderEventType.ORDER_CREATED, quantity))

        elif status == OrderStatus.PARTIALLY_FILLED:
            if not existing_order:
                events_to_emit.append((OrderEventType.ORDER_CREATED, quantity))
                if filled_quantity > 0:
                    events_to_emit.append((OrderEventType.ORDER_FILLED, filled_quantity))
            else:
                events_to_emit.append((OrderEventType.ORDER_UPDATED, quantity))
                new_filled = filled_quantity - existing_order.filled_quantity
                if new_filled > 0:
                    events_to_emit.append((OrderEventType.ORDER_FILLED, new_filled))

        elif status == OrderStatus.FILLED:
            if not existing_order:
                events_to_emit.append((OrderEventType.ORDER_FILLED, quantity))
            else:
                remaining = quantity - existing_order.filled_quantity
                if remaining > 0:
                    events_to_emit.append((OrderEventType.ORDER_FILLED, remaining))

        elif status == OrderStatus.CANCELLED:
            events_to_emit.append((OrderEventType.ORDER_CANCELLED, quantity))


        # DB 업데이트를 먼저 수행
        if (
            existing_order
            and status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED)
            and self.service is not None
        ):
            self.service.order_manager.update_open_order_status(order_id, order_result)  # noqa: SLF001

        # 그 다음 이벤트 발행
        for event_type, event_quantity in events_to_emit:
            self.emit_trading_event(event_type, strategy, symbol, side, event_quantity, order_result)
            logger.debug(
                "📡 스마트 이벤트 발송: %s - %s %s %s",
                event_type,
                symbol,
                side,
                event_quantity,
            )

    def emit_position_event(
        self,
        strategy_account: StrategyAccount,
        position_id: Optional[int],
        symbol: str,
        previous_qty: Decimal,
        new_qty: Decimal,
        new_price: Decimal,
        position_closed: bool,
    ) -> None:
        """Emit a position change event."""
        try:
            from app.services.event_service import event_service, PositionEvent

            strategy = strategy_account.strategy
            account = strategy_account.account

            if not strategy:
                logger.warning("포지션 이벤트 발송 실패 - 전략 정보 없음")
                return

            if position_id is None:
                logger.warning("포지션 이벤트 발송 실패 - position_id 없음")
                return

            event_type = (
                'position_closed'
                if position_closed
                else (
                    'position_created'
                    if previous_qty is None or abs(previous_qty) < Decimal('1e-12')
                    else 'position_updated'
                )
            )

            account_payload = None
            account_name = None
            exchange_name = None
            if account:
                account_payload = {
                    'id': account.id,
                    'name': account.name,
                    'exchange': account.exchange,
                }
                account_name = account.name
                exchange_name = account.exchange

            quantity_value = float(new_qty) if not position_closed else 0.0
            entry_price_value = float(new_price) if new_price is not None else 0.0

            position_event = PositionEvent(
                event_type=event_type,
                position_id=int(position_id or 0),
                symbol=symbol,
                strategy_id=strategy.id,
                user_id=strategy.user_id,
                quantity=quantity_value,
                entry_price=entry_price_value,
                timestamp=datetime.utcnow().isoformat(),
                previous_quantity=float(previous_qty) if previous_qty is not None else None,
                account=account_payload,
                account_name=account_name,
                exchange=exchange_name,
            )

            event_service.emit_position_event(position_event)

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("포지션 이벤트 발송 실패: %s", exc)

    def emit_order_cancelled_event(
        self,
        order_id: str,
        symbol: str,
        account_id: int,
    ) -> None:
        """Emit the order cancelled notification."""
        try:
            from app.services.event_service import event_service, OrderEvent
            from app.models import Account

            # 계좌 정보 조회
            account = Account.query.get(account_id)
            if not account:
                logger.warning("계좌를 찾을 수 없어 이벤트 발송 스킵: %s", account_id)
                return

            # OrderEvent 객체 생성
            from datetime import datetime

            order_event = OrderEvent(
                event_type='order_cancelled',
                order_id=order_id,
                symbol=symbol,
                strategy_id=0,  # 취소 이벤트는 전략 ID 불필요
                user_id=account.user_id,
                side='',  # 취소 이벤트는 방향 불필요
                quantity=0.0,
                price=0.0,
                status='CANCELED',
                timestamp=datetime.utcnow().isoformat(),
                order_type='',  # 취소 이벤트는 주문 타입 불필요
                stop_price=None
            )

            event_service.emit_order_event(order_event)
            logger.info("✅ 주문 취소 이벤트 발송 완료: %s", order_id)

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("주문 취소 이벤트 발송 실패: %s", exc)
