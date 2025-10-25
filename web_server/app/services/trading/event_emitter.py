# @FEAT:event-sse @COMP:service @TYPE:helper
"""Event emission helpers extracted from the legacy trading service."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from app.constants import OrderEventType, OrderStatus, OrderType
from app.models import OpenOrder, Strategy, StrategyAccount

logger = logging.getLogger(__name__)


# @FEAT:event-sse @COMP:service @TYPE:helper
class EventEmitter:
    """Encapsulates trading-related event emission."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    # @FEAT:event-sse @FEAT:order-tracking @COMP:service @TYPE:integration
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
            from app.models import Account

            # order_result에서 account_id 추출 (다중 계좌 지원)
            account_id = order_result.get('account_id')
            if not account_id:
                logger.error("order_result에 account_id 누락, SSE 이벤트 발송 불가")
                return

            # 해당 계좌 직접 조회
            account = Account.query.get(account_id)
            if not account:
                logger.warning("계좌 정보를 찾을 수 없음: account_id=%s", account_id)
                return

            # @FEAT:order-tracking @COMP:service @TYPE:core
            # 단일 소스 원칙: core.py Line 265에서 제공하는 stop_price 직접 사용
            # 폴백 로직 제거 (CLAUDE.md 준수)
            stop_price_value = None
            stop_price = order_result.get('stop_price')

            if stop_price is not None:
                try:
                    stop_price_value = float(stop_price)
                except (ValueError, TypeError) as e:
                    order_type = order_result.get('order_type', '')
                    order_id = order_result.get('order_id')
                    logger.error(
                        f"❌ stop_price 변환 실패: order_id={order_id}, "
                        f"value={stop_price}, type={order_type}, error={e}"
                    )
                    # STOP 주문인데 변환 실패 시 명시적 에러
                    if order_type in ['STOP_LIMIT', 'STOP_MARKET']:
                        raise ValueError(
                            f"STOP 주문 stop_price 변환 실패: order_id={order_id}, "
                            f"value={stop_price}"
                        )

            # 🆕 가격 정보 추출 (OpenOrder 모델의 get_display_price() 로직 사용)
            price = self._extract_display_price(order_result)

            event = OrderEvent(
                event_type=event_type,
                order_id=order_result.get('order_id', ''),
                symbol=symbol,
                strategy_id=strategy.id,
                user_id=strategy.user_id,
                side=side.upper(),
                quantity=float(quantity),
                price=price,
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
                "📡 이벤트 발송 완료: %s - %s %s %s (price=%s)",
                event_type,
                symbol,
                side,
                quantity,
                price,
            )

        except ValueError as exc:
            # 가격 정보 누락 시 명시적 에러 처리
            logger.error(
                "❌ SSE 이벤트 발송 실패 - 가격 정보 누락\n"
                "order_id=%s, type=%s, status=%s\n"
                "에러: %s",
                order_result.get('order_id'),
                order_result.get('order_type'),
                order_result.get('status'),
                str(exc),
            )
            # Telegram 알림 (관리자 즉시 인지)
            try:
                from app.services.telegram_service import send_admin_alert
                send_admin_alert(
                    f"🚨 SSE 가격 데이터 누락\n"
                    f"주문 ID: {order_result.get('order_id')}\n"
                    f"타입: {order_result.get('order_type')}\n"
                    f"에러: {str(exc)}"
                )
            except Exception:
                pass  # Telegram 서비스 없어도 에러 로그는 남김
            raise  # 에러 전파 (SSE 이벤트 발송 중단)

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("이벤트 발송 실패: %s", exc)

    def _extract_display_price(self, order_result: Dict[str, object]) -> float:
        """order_result에서 표시할 가격 추출

        @FEAT:order-tracking @COMP:service @TYPE:core

        Raises:
            ValueError: 필수 가격 정보가 누락된 경우

        Returns:
            float: 표시할 가격
        """
        from decimal import Decimal, InvalidOperation

        order_id = order_result.get('order_id')
        order_type = order_result.get('order_type', 'UNKNOWN')
        status = order_result.get('status', 'UNKNOWN')

        # MARKET 미체결은 가격 미정 (정상 케이스)
        if order_type == 'MARKET' and status in ['OPEN', 'NEW']:
            return 0.0

        # 1. 체결 가격 우선 (체결된 주문)
        average_price = order_result.get('average_price')
        if average_price is not None and average_price > 0:
            try:
                avg_decimal = Decimal(str(average_price))
                if avg_decimal > 0:
                    return float(avg_decimal)
            except (ValueError, InvalidOperation, TypeError) as e:
                raise ValueError(
                    f"Invalid average_price format: {average_price}, "
                    f"order_id={order_id}, error: {e}"
                )

        # 2. 미체결 주문: 타입별 필수 가격 정보
        if order_type in ['LIMIT', 'STOP_LIMIT']:
            price = order_result.get('price')
            adjusted_price = order_result.get('adjusted_price')

            # 명시적 우선순위: adjusted_price → price
            if adjusted_price is not None and adjusted_price > 0:
                try:
                    price_decimal = Decimal(str(adjusted_price))
                    if price_decimal > 0:
                        return float(price_decimal)
                except (ValueError, InvalidOperation, TypeError) as e:
                    raise ValueError(
                        f"Invalid adjusted_price format: {adjusted_price}, "
                        f"order_id={order_id}, error: {e}"
                    )
            elif price is not None and price > 0:
                try:
                    price_decimal = Decimal(str(price))
                    if price_decimal > 0:
                        return float(price_decimal)
                except (ValueError, InvalidOperation, TypeError) as e:
                    raise ValueError(
                        f"Invalid price format: {price}, "
                        f"order_id={order_id}, error: {e}"
                    )
            else:
                raise ValueError(
                    f"{order_type} 주문(order_id={order_id})에 price가 없습니다. "
                    f"status={status}, available_fields={list(order_result.keys())}"
                )

        elif order_type == 'STOP_MARKET':
            # @FEAT:order-tracking @COMP:service @TYPE:core
            # 단일 소스 원칙: core.py Line 265에서 제공하는 stop_price 직접 사용
            stop_price = order_result.get('stop_price')

            if stop_price is not None and stop_price > 0:
                try:
                    stop_decimal = Decimal(str(stop_price))
                    if stop_decimal > 0:
                        return float(stop_decimal)
                except (ValueError, InvalidOperation, TypeError) as e:
                    raise ValueError(
                        f"Invalid stop_price format: {stop_price}, "
                        f"order_id={order_id}, error={e}"
                    )
            else:
                raise ValueError(
                    f"STOP_MARKET 주문(order_id={order_id})에 stop_price가 없습니다. "
                    f"status={status}, available_fields={list(order_result.keys())}"
                )

        # MARKET 체결된 경우인데 average_price가 없으면 에러
        if order_type == 'MARKET':
            raise ValueError(
                f"MARKET 체결 주문(order_id={order_id})에 average_price가 없습니다. "
                f"status={status}, available_fields={list(order_result.keys())}"
            )

        # 알 수 없는 주문 타입
        raise ValueError(
            f"알 수 없는 주문 타입: {order_type} (order_id={order_id}), "
            f"available_fields={list(order_result.keys())}"
        )

    # @FEAT:event-sse @FEAT:order-tracking @COMP:service @TYPE:core
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

    # @FEAT:event-sse @FEAT:position-tracking @COMP:service @TYPE:integration
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
                    'account_id': account.id,  # Standardized field name (consistent with OrderEvent)
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

    # @FEAT:event-sse @FEAT:order-tracking @COMP:service @TYPE:integration
    def emit_order_cancelled_event(
        self,
        order_id: str,
        symbol: str,
        account_id: int,
    ) -> None:
        """Emit the order cancelled notification."""
        try:
            from app.services.event_service import event_service, OrderEvent
            from app.models import Account, OpenOrder

            # 계좌 정보 조회
            account = Account.query.get(account_id)
            if not account:
                logger.warning("계좌를 찾을 수 없어 이벤트 발송 스킵: %s", account_id)
                return

            # OpenOrder에서 strategy_id 추출 시도
            open_order = OpenOrder.query.filter_by(exchange_order_id=order_id).first()
            strategy_id = 0

            if open_order and open_order.strategy_account:
                strategy_account = open_order.strategy_account
                if strategy_account.strategy_id:
                    strategy_id = strategy_account.strategy_id
                    logger.debug(f"OpenOrder에서 strategy_id 추출: {strategy_id}")

            # strategy_id 검증
            if strategy_id <= 0:
                logger.warning(
                    f"OpenOrder {order_id}에 유효한 strategy_id 없음 - SSE 발송 스킵"
                )
                return

            # OrderEvent 객체 생성
            from datetime import datetime

            order_event = OrderEvent(
                event_type='order_cancelled',
                order_id=order_id,
                symbol=symbol,
                strategy_id=strategy_id,  # OpenOrder에서 추출한 strategy_id 사용
                user_id=account.user_id,
                side='',  # 취소 이벤트는 방향 불필요
                quantity=0.0,
                price=0.0,
                status='CANCELED',
                timestamp=datetime.utcnow().isoformat(),
                order_type='',  # 취소 이벤트는 주문 타입 불필요
                stop_price=None,
                account={  # Added missing account field
                    'account_id': account.id,
                    'name': account.name,
                    'exchange': account.exchange,
                }
            )

            event_service.emit_order_event(order_event)
            logger.info("✅ 주문 취소 이벤트 발송 완료: %s (전략: %s)", order_id, strategy_id)

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("주문 취소 이벤트 발송 실패: %s", exc)

    # @FEAT:event-sse @FEAT:order-queue @COMP:service @TYPE:integration
    def emit_pending_order_event(
        self,
        event_type: str,
        pending_order,
        user_id: int,
    ) -> None:
        """Emit pending order event via SSE.

        Args:
            event_type: 'order_created' (대기열 추가) or 'order_cancelled' (대기열 제거)
            pending_order: PendingOrder 모델 인스턴스
            user_id: 사용자 ID (전략 소유자)
        """
        try:
            from app.services.event_service import event_service, OrderEvent
            from app.models import Account

            # 계좌 정보 조회
            account = Account.query.get(pending_order.account_id)
            if not account:
                logger.warning(
                    "계좌를 찾을 수 없어 PendingOrder 이벤트 발송 스킵: %s",
                    pending_order.account_id
                )
                return

            # strategy_id 추출 (pending_order.strategy_account → strategy_id)
            strategy_account = pending_order.strategy_account
            if not strategy_account or not strategy_account.strategy_id:
                logger.warning(
                    f"PendingOrder {pending_order.id}에 strategy_account 또는 strategy_id 없음 - SSE 발송 스킵"
                )
                return

            strategy_id = strategy_account.strategy_id

            # OrderEvent 생성 (PendingOrder용)
            order_event = OrderEvent(
                event_type=event_type,
                order_id=f'p_{pending_order.id}',  # PendingOrder는 'p_' prefix
                symbol=pending_order.symbol,
                strategy_id=strategy_id,  # pending_order.strategy_account.strategy_id 사용
                user_id=user_id,
                side=pending_order.side.upper(),
                quantity=float(pending_order.quantity),
                price=float(pending_order.price) if pending_order.price else 0.0,
                status='PENDING_QUEUE',  # PendingOrder 상태
                timestamp=datetime.utcnow().isoformat(),
                order_type=pending_order.order_type,
                stop_price=float(pending_order.stop_price) if pending_order.stop_price else None,
                account={
                    'account_id': account.id,
                    'name': account.name,
                    'exchange': account.exchange,
                }
            )

            event_service.emit_order_event(order_event)
            logger.info(
                "✅ PendingOrder 이벤트 발송 완료: %s - %s (ID: p_%s, 전략: %s)",
                event_type,
                pending_order.symbol,
                pending_order.id,
                strategy_id
            )

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("PendingOrder 이벤트 발송 실패: %s", exc)

    # @FEAT:event-sse @FEAT:webhook-order @COMP:service @TYPE:core
    def emit_order_batch_update(self, user_id: int, strategy_id: int, batch_results: List[Dict[str, Any]]):
        """Aggregate batch order results and emit single SSE event

        Phase 2: Backend Batch SSE - Aggregate by order_type and event_type

        Args:
            user_id: User ID for SSE routing
            strategy_id: Strategy ID for validation
            batch_results: List of order results with metadata
                Example: [
                    {'success': True, 'order_type': 'LIMIT', 'event_type': 'order_created'},
                    {'success': True, 'order_type': 'LIMIT', 'event_type': 'order_cancelled'},
                    ...
                ]

        Aggregation Logic:
            - Group by order_type
            - Count 'order_created' → created
            - Count 'order_cancelled' → cancelled
            - Filter out empty (created=0, cancelled=0)
        """
        from collections import defaultdict
        from datetime import datetime

        # Aggregate by order_type
        aggregation = defaultdict(lambda: {'created': 0, 'cancelled': 0})

        for result in batch_results:
            if not result.get('success'):
                continue

            order_type = result.get('order_type')
            event_type = result.get('event_type')

            if not order_type or not event_type:
                continue

            if event_type == 'order_created':
                aggregation[order_type]['created'] += 1
            elif event_type == 'order_cancelled':
                aggregation[order_type]['cancelled'] += 1

        # Convert to summaries list (filter out empty)
        summaries = [
            {
                'order_type': ot,
                'created': counts['created'],
                'cancelled': counts['cancelled']
            }
            for ot, counts in aggregation.items()
            if counts['created'] > 0 or counts['cancelled'] > 0
        ]

        if summaries:
            from app.services.event_service import event_service, OrderBatchEvent
            batch_event = OrderBatchEvent(
                summaries=summaries,
                strategy_id=strategy_id,
                user_id=user_id,
                timestamp=datetime.utcnow().isoformat() + 'Z'
            )
            event_service.emit_order_batch_event(batch_event)
            logger.debug(f'Batch aggregation: {len(summaries)} order types')
        else:
            logger.debug('No successful orders - batch SSE skipped')
