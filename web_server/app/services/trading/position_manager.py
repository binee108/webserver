# @FEAT:position-tracking @COMP:service @TYPE:core @DEPS:order-tracking,exchange-integration,event-sse,price-cache
"""Position management logic extracted from the legacy trading service."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Account,
    OpenOrder,
    Strategy,
    StrategyAccount,
    StrategyPosition,
    Trade,
)
from app.services.utils import decimal_to_float, to_decimal

logger = logging.getLogger(__name__)


# @FEAT:position-tracking @COMP:service @TYPE:core
class PositionManager:
    """Encapsulates position update and query behaviour."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    # @FEAT:position-tracking @COMP:service @TYPE:helper
    def _fetch_fallback_execution_price(self, account: Account, symbol: str, market_type: str) -> Optional[Decimal]:
        """Fallback to the latest market price when the exchange omits execution price."""
        from app.services.exchange import exchange_service

        try:
            price_result = exchange_service.get_current_price(
                account_id=account.id,
                symbol=symbol,
                market_type=market_type,
            )
            if price_result.get('success') and price_result.get('price'):
                fallback_value = self.service._to_decimal(price_result['price'])
                if fallback_value > Decimal('0'):
                    logger.warning(
                        "체결가 미보고로 현재가를 대체 사용합니다 - account=%s symbol=%s price=%s",
                        account.id,
                        symbol,
                        fallback_value,
                    )
                    return fallback_value
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "체결가 보정값 조회 실패 - account=%s symbol=%s error=%s",
                account.id,
                symbol,
                exc,
            )
        return None

    # @FEAT:position-tracking @FEAT:order-tracking @COMP:service @TYPE:core
    def process_order_fill(self, strategy_account: StrategyAccount, order_id: str,
                           symbol: Optional[str] = None, side: Optional[str] = None,
                           order_type: Optional[str] = None,
                           order_result: Optional[Dict[str, Any]] = None,
                           market_type: Optional[str] = None) -> Dict[str, Any]:
        """체결 주문 데이터를 통합 처리 (주문 조회 → DB 저장 → SSE 발송)"""
        try:
            strategy = strategy_account.strategy
            account = strategy_account.account

            if not strategy or not account:
                return {
                    'success': False,
                    'error': 'strategy_account_incomplete'
                }

            working_result = order_result if order_result is not None else {}
            working_result.setdefault('order_id', order_id)
            if symbol:
                working_result.setdefault('symbol', symbol)

            symbol_value = working_result.get('symbol') or symbol
            if not symbol_value:
                return {
                    'success': False,
                    'error': 'symbol_missing'
                }

            # market_type 표준화
            market_type_value = market_type or strategy.market_type or 'SPOT'
            exchange_market_type = 'futures' if market_type_value.upper() == 'FUTURES' else 'spot'

            merged_order = self.service._merge_order_with_exchange(
                account=account,
                symbol=symbol_value,
                market_type=exchange_market_type,
                order_result=working_result
            )

            side_value = (merged_order.get('side') or side or '').upper()
            order_type_value = (merged_order.get('order_type') or order_type or 'MARKET').upper()

            from app.constants import OrderStatus

            filled_decimal = self.service._to_decimal(merged_order.get('filled_quantity'))
            average_decimal = self.service._to_decimal(merged_order.get('average_price'))
            merged_order['filled_quantity'] = filled_decimal
            merged_order['average_price'] = average_decimal
            merged_order['order_type'] = order_type_value
            if side_value:
                merged_order['side'] = side_value

            order_status_value = (merged_order.get('status') or '').upper()
            has_fill = filled_decimal > Decimal('0')

            if not has_fill:
                if OrderStatus.is_open(order_status_value):
                    logger.info(
                        "🆕 미체결 주문 상태 동기화: account=%s order_id=%s symbol=%s status=%s",
                        account.id, order_id, symbol_value, order_status_value
                    )

                    if average_decimal <= Decimal('0'):
                        limit_price = self.service._to_decimal(
                            merged_order.get('adjusted_price') or merged_order.get('price')
                        )
                        if limit_price > Decimal('0'):
                            merged_order['average_price'] = limit_price
                            average_decimal = limit_price

                    return {
                        'success': True,
                        'order_result': merged_order,
                        'filled_quantity': filled_decimal,
                        'average_price': average_decimal,
                        'trade_id': None,
                        'trade_status': None,
                        'execution_status': None,
                        'position_result': {'success': True},
                        'quantity_delta': Decimal('0'),
                        'events_emitted': False
                    }

                logger.critical(
                    "비정상 체결: 체결 수량 0 - account=%s order_id=%s symbol=%s status=%s",
                    account.id, order_id, symbol_value, order_status_value
                )
                return {
                    'success': False,
                    'order_result': merged_order,
                    'filled_quantity': filled_decimal,
                    'average_price': average_decimal,
                    'trade_id': None,
                    'quantity_delta': Decimal('0'),
                    'events_emitted': False
                }

            if average_decimal <= Decimal('0'):
                logger.critical(
                    "거래소 체결가 누락 감지 - account=%s order_id=%s symbol=%s",
                    account.id, order_id, symbol_value
                )
                fallback_price = self._fetch_fallback_execution_price(
                    account=account,
                    symbol=symbol_value,
                    market_type=exchange_market_type
                )
                if fallback_price and fallback_price > Decimal('0'):
                    average_decimal = fallback_price
                    merged_order['average_price'] = fallback_price
                    merged_order['adjusted_average_price'] = fallback_price
                    merged_order['actual_execution_price'] = float(fallback_price)
                else:
                    logger.critical(
                        "체결가 대체값 조회 실패 - account=%s order_id=%s symbol=%s",
                        account.id, order_id, symbol_value
                    )
                    return {
                        'success': False,
                        'error': 'execution_price_unavailable',
                        'order_result': merged_order
                    }

            executed_price = average_decimal if average_decimal > Decimal('0') else self.service._to_decimal(merged_order.get('price'))
            order_price_decimal = self.service._to_decimal(merged_order.get('adjusted_price') or merged_order.get('price'))

            trade_result = self.service.record_manager.create_trade_record(
                strategy=strategy,
                account=account,
                symbol=symbol_value,
                side=side_value,
                quantity=filled_decimal,
                price=executed_price,
                order_id=str(order_id),
                order_type=order_type_value,
                order_price=order_price_decimal if order_price_decimal > Decimal('0') else None
            )

            trade_id = trade_result.get('trade_id') if trade_result.get('success') else None
            quantity_delta = trade_result.get('quantity_delta', Decimal('0'))
            if quantity_delta < Decimal('0'):
                quantity_delta = Decimal('0')

            position_result = {'success': True}
            if quantity_delta > Decimal('0') and average_decimal > Decimal('0'):
                position_result = self._update_position(
                    strategy_account_id=strategy_account.id,
                    symbol=symbol_value,
                    side=side_value,
                    quantity=quantity_delta,
                    price=average_decimal
                )
                if not position_result.get('success'):
                    logger.critical(
                        "포지션 업데이트 실패 - account=%s order_id=%s reason=%s",
                        account.id,
                        order_id, position_result.get('error')
                    )
                    return {
                        'success': False,
                        'error': 'position_update_failed',
                        'order_result': merged_order,
                        'position_result': position_result
                    }

                realized_pnl_value = position_result.get('realized_pnl')
                if realized_pnl_value is not None:
                    merged_order['realized_pnl'] = float(realized_pnl_value)

                    if trade_id and realized_pnl_value != Decimal('0'):
                        trade_record = Trade.query.get(trade_id)
                        if trade_record:
                            current_trade_pnl = Decimal(str(trade_record.pnl or 0))
                            trade_record.pnl = float(current_trade_pnl + realized_pnl_value)
                            db.session.commit()

            execution_result = self.service.record_manager.create_trade_execution_record(
                strategy_account=strategy_account,
                order_result=merged_order,
                symbol=symbol_value,
                side=side_value,
                order_type=order_type_value,
                trade_id=trade_id,
                realized_pnl=position_result.get('realized_pnl') if position_result.get('success') else None
            )

            if execution_result.get('execution_price'):
                merged_order['actual_execution_price'] = execution_result['execution_price']
            if execution_result.get('execution_quantity'):
                merged_order['actual_execution_quantity'] = execution_result['execution_quantity']

            if execution_result.get('realized_pnl') is not None:
                merged_order['realized_pnl'] = execution_result['realized_pnl']

            should_emit_events = quantity_delta > Decimal('0')

            if should_emit_events:
                self.service.event_emitter.emit_order_events_smart(
                    strategy=strategy,
                    symbol=symbol_value,
                    side=side_value,
                    quantity=filled_decimal,
                    order_result=merged_order
                )

            return {
                'success': True,
                'order_result': merged_order,
                'filled_quantity': filled_decimal,
                'average_price': average_decimal,
                'trade_id': trade_id,
                'trade_status': trade_result.get('status'),
                'execution_status': execution_result.get('status'),
                'position_result': position_result,
                'quantity_delta': quantity_delta,
                'events_emitted': should_emit_events
            }

        except Exception as e:
            logger.error(f"체결 처리 중 오류 발생: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    # @FEAT:position-tracking @COMP:service @TYPE:core
    def close_position_by_id(self, position_id: int, user_id: int) -> Dict[str, Any]:
        """포지션 ID 기반 시장가 청산"""
        try:
            position = (
                StrategyPosition.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    StrategyPosition.id == position_id,
                    or_(
                        Strategy.user_id == user_id,
                        Account.user_id == user_id
                    ),
                    Account.is_active == True
                )
                .first()
            )

            if not position:
                logger.warning(f"포지션 청산 실패 - 포지션 미발견: position_id={position_id}, user_id={user_id}")
                return {
                    'success': False,
                    'error': '포지션을 찾을 수 없습니다.'
                }

            strategy_account = position.strategy_account
            strategy = strategy_account.strategy if strategy_account else None
            account = strategy_account.account if strategy_account else None

            if not strategy_account or not strategy or not account:
                logger.warning(
                    "포지션 청산 실패 - 전략 또는 계좌 누락: position_id=%s",
                    position_id
                )
                return {
                    'success': False,
                    'error': '전략 계좌 정보를 찾을 수 없습니다.'
                }

            position_qty = self.service._to_decimal(position.quantity)
            if position_qty == 0:
                logger.info(f"포지션 청산 스킵 - 수량 0: position_id={position_id}")
                return {
                    'success': False,
                    'error': '청산할 포지션이 없습니다.'
                }

            side = 'SELL' if position_qty > 0 else 'BUY'
            close_quantity = position_qty.copy_abs()

            quantized_close, min_qty, step_unit, min_notional = self.service.quantity_calculator.quantize_quantity_for_symbol(
                strategy_account, position.symbol, close_quantity
            )
            if quantized_close != close_quantity:
                logger.debug(
                    "포지션 청산 수량 정밀도 보정: %s -> %s (%s)",
                    close_quantity, quantized_close, position.symbol
                )

            if quantized_close <= Decimal('0'):
                if min_qty:
                    message = '거래소 최소 거래 수량 미만으로 청산할 수 없습니다.'
                    message += f' (최소 수량: {min_qty})'
                    logger.warning(
                        "포지션 청산 불가 - 최소 수량 미만: position_id=%s symbol=%s quantity=%s min_qty=%s",
                        position_id, position.symbol, close_quantity, min_qty
                    )
                else:
                    message = '거래소 최소 거래 금액 조건으로 청산할 수 없습니다.'
                    if min_notional:
                        message += f' (최소 거래금액: {min_notional})'
                    logger.warning(
                        "포지션 청산 불가 - 최소 금액 미달: position_id=%s symbol=%s quantity=%s min_notional=%s",
                        position_id, position.symbol, close_quantity, min_notional
                    )
                return {
                    'success': False,
                    'error': message,
                    'requested_quantity': float(close_quantity),
                    'min_quantity': float(min_qty) if min_qty else None,
                    'min_notional': float(min_notional) if min_notional else None,
                    'step_size': float(step_unit) if step_unit else None
                }

            close_quantity = quantized_close

            logger.info(
                "포지션 청산 주문 생성 - user=%s position_id=%s symbol=%s side=%s quantity=%s",
                user_id, position_id, position.symbol, side, close_quantity
            )

            trade_result = self.service.execute_trade(
                strategy=strategy,
                symbol=position.symbol,
                side=side,
                quantity=close_quantity,
                order_type='MARKET',
                strategy_account_override=strategy_account
            )

            if not trade_result.get('success'):
                logger.warning(
                    "포지션 청산 주문 실패 - position_id=%s error=%s",
                    position_id,
                    trade_result.get('error')
                )
                return {
                    'success': False,
                    'error': trade_result.get('error', '포지션 청산에 실패했습니다.'),
                    'details': trade_result
                }

            return {
                'success': True,
                'position_id': position_id,
                'symbol': position.symbol,
                'side': side,
                'requested_quantity': float(close_quantity),
                'order_id': trade_result.get('order_id'),
                'filled_quantity': trade_result.get('filled_quantity'),
                'average_price': trade_result.get('average_price'),
                'result_payload': trade_result
            }

        except Exception as e:
            logger.error(f"포지션 청산 처리 중 오류 - position_id={position_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'포지션 청산 실패: {str(e)}'
            }

    # @FEAT:position-tracking @COMP:service @TYPE:core
    def get_user_open_orders_with_positions(self, user_id: int) -> Dict[str, Any]:
        """사용자의 포지션과 열린 주문을 심볼별로 집계"""
        try:
            active_positions = (
                StrategyPosition.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    or_(
                        Strategy.user_id == user_id,
                        Account.user_id == user_id
                    ),
                    StrategyPosition.quantity != 0,
                    Account.is_active == True
                )
                .all()
            )

            open_orders = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    or_(
                        Strategy.user_id == user_id,
                        Account.user_id == user_id
                    ),
                    OpenOrder.status.in_(['NEW', 'OPEN', 'PARTIALLY_FILLED']),
                    Account.is_active == True
                )
                .order_by(OpenOrder.created_at.desc())
                .all()
            )

            symbol_data = defaultdict(lambda: {
                'positions': [],
                'open_orders': [],
                'total_position_value': 0.0,
                'total_order_value': 0.0
            })

            for position in active_positions:
                strategy_account = position.strategy_account
                strategy = strategy_account.strategy if strategy_account else None
                account = strategy_account.account if strategy_account else None

                quantity_decimal = self.service._to_decimal(position.quantity)
                quantized_quantity, _, _, _ = self.service.quantity_calculator.quantize_quantity_for_symbol(
                    strategy_account, position.symbol, quantity_decimal
                )
                quantity_decimal = quantized_quantity

                entry_price_decimal = self.service._to_decimal(position.entry_price)
                position_value = float(abs(quantity_decimal * entry_price_decimal))

                symbol_entry = symbol_data[position.symbol]
                symbol_entry['positions'].append({
                    'id': position.id,
                    'position_id': position.id,
                    'quantity': float(quantity_decimal),
                    'entry_price': float(entry_price_decimal),
                    'last_updated': position.last_updated.isoformat() if position.last_updated else None,
                    'strategy': {
                        'id': strategy.id if strategy else None,
                        'name': strategy.name if strategy else None,
                        'group_name': strategy.group_name if strategy else None,
                        'market_type': strategy.market_type if strategy else None
                    },
                    'account': {
                        'id': account.id if account else None,
                        'name': account.name if account else None,
                        'exchange': account.exchange if account else None
                    }
                })
                symbol_entry['total_position_value'] += position_value

            for order in open_orders:
                strategy_account = order.strategy_account
                strategy = strategy_account.strategy if strategy_account else None
                account = strategy_account.account if strategy_account else None

                order_price = self.service._to_decimal(order.price) if order.price else Decimal('0')
                order_qty = self.service._to_decimal(order.quantity)
                order_value = float(order_price * order_qty)

                symbol_entry = symbol_data[order.symbol]
                symbol_entry['open_orders'].append({
                    'id': order.id,
                    'order_id': order.exchange_order_id,
                    'exchange_order_id': order.exchange_order_id,
                    'side': order.side,
                    'quantity': float(order.quantity),
                    'price': float(order.price) if order.price is not None else None,
                    'filled_quantity': order.filled_quantity,
                    'status': order.status,
                    'order_type': order.order_type,
                    'market_type': order.market_type,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                    'strategy': {
                        'id': strategy.id if strategy else None,
                        'name': strategy.name if strategy else None,
                        'group_name': strategy.group_name if strategy else None,
                        'market_type': strategy.market_type if strategy else None
                    },
                    'account': {
                        'id': account.id if account else None,
                        'name': account.name if account else None,
                        'exchange': account.exchange if account else None
                    }
                })
                symbol_entry['total_order_value'] += order_value

            summary = {
                'total_positions': len(active_positions),
                'total_open_orders': len(open_orders),
                'active_symbols': len(symbol_data),
                'total_position_value': float(sum(item['total_position_value'] for item in symbol_data.values())),
                'total_order_value': float(sum(item['total_order_value'] for item in symbol_data.values()))
            }

            logger.info(
                "포지션/주문 통합 조회 - user=%s positions=%s orders=%s symbols=%s",
                user_id,
                summary['total_positions'],
                summary['total_open_orders'],
                summary['active_symbols']
            )

            return {
                'success': True,
                'symbol_data': dict(symbol_data),
                'summary': summary
            }

        except Exception as e:
            logger.error(f"포지션/주문 통합 조회 실패 - user={user_id}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'symbol_data': {},
                'summary': {}
            }

    # @FEAT:position-tracking @COMP:service @TYPE:core
    def get_position_and_orders_by_symbol(self, user_id: int, symbol: str) -> Dict[str, Any]:
        """특정 심볼에 대한 포지션 및 주문 조회"""
        try:
            positions = (
                StrategyPosition.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    StrategyPosition.symbol == symbol,
                    StrategyPosition.quantity != 0,
                    or_(
                        Strategy.user_id == user_id,
                        Account.user_id == user_id
                    ),
                    Account.is_active == True
                )
                .all()
            )

            open_orders = (
                OpenOrder.query
                .join(StrategyAccount)
                .join(Strategy)
                .join(Account)
                .options(
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(OpenOrder.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(
                    OpenOrder.symbol == symbol,
                    OpenOrder.status.in_(['NEW', 'OPEN', 'PARTIALLY_FILLED']),
                    or_(
                        Strategy.user_id == user_id,
                        Account.user_id == user_id
                    ),
                    Account.is_active == True
                )
                .order_by(OpenOrder.created_at.desc())
                .all()
            )

            position_list = []
            for position in positions:
                strategy_account = position.strategy_account
                strategy = strategy_account.strategy if strategy_account else None
                account = strategy_account.account if strategy_account else None

                quantity_decimal = self.service._to_decimal(position.quantity)
                quantized_quantity, _, _, _ = self.service.quantity_calculator.quantize_quantity_for_symbol(
                    strategy_account, position.symbol, quantity_decimal
                )
                quantity_decimal = quantized_quantity

                entry_price_decimal = self.service._to_decimal(position.entry_price)

                position_list.append({
                    'id': position.id,
                    'position_id': position.id,
                    'quantity': float(quantity_decimal),
                    'entry_price': float(entry_price_decimal),
                    'last_updated': position.last_updated.isoformat() if position.last_updated else None,
                    'strategy': {
                        'id': strategy.id if strategy else None,
                        'name': strategy.name if strategy else None,
                        'group_name': strategy.group_name if strategy else None,
                        'market_type': strategy.market_type if strategy else None
                    },
                    'account': {
                        'id': account.id if account else None,
                        'name': account.name if account else None,
                        'exchange': account.exchange if account else None
                    }
                })

            order_list = []
            for order in open_orders:
                strategy_account = order.strategy_account
                strategy = strategy_account.strategy if strategy_account else None
                account = strategy_account.account if strategy_account else None

                order_list.append({
                    'id': order.id,
                    'order_id': order.exchange_order_id,
                    'exchange_order_id': order.exchange_order_id,
                    'side': order.side,
                    'quantity': order.quantity,
                    'price': order.price,
                    'filled_quantity': order.filled_quantity,
                    'status': order.status,
                    'order_type': order.order_type,
                    'market_type': order.market_type,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                    'strategy': {
                        'id': strategy.id if strategy else None,
                        'name': strategy.name if strategy else None,
                        'group_name': strategy.group_name if strategy else None,
                        'market_type': strategy.market_type if strategy else None
                    },
                    'account': {
                        'id': account.id if account else None,
                        'name': account.name if account else None,
                        'exchange': account.exchange if account else None
                    }
                })

            logger.info(
                "심볼별 포지션/주문 조회 - user=%s symbol=%s positions=%s orders=%s",
                user_id, symbol, len(position_list), len(order_list)
            )

            return {
                'success': True,
                'symbol': symbol,
                'positions': position_list,
                'open_orders': order_list
            }

        except Exception as e:
            logger.error(f"심볼별 포지션/주문 조회 실패 - user={user_id}, symbol={symbol}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'symbol': symbol,
                'positions': [],
                'open_orders': []
            }

    # @FEAT:position-tracking @COMP:service @TYPE:core @ISSUE:38
    def _update_position(self, strategy_account_id: int, symbol: str, side: str,
                        quantity: Decimal, price: Decimal) -> Dict[str, Any]:
        """포지션 업데이트 (평균가 계산 + 실현 손익 산출 + Row-Level Locking)

        WebSocket과 Scheduler가 동일 포지션을 동시 업데이트할 때
        수량 손실을 방지합니다 (Issue #38: Trade Race Condition Fix).

        @FEAT:position-tracking @COMP:service @TYPE:core @ISSUE:38
        """
        try:
            strategy_account = StrategyAccount.query.get(strategy_account_id)
            if not strategy_account:
                logger.error(f"포지션 업데이트 실패 - 전략 계좌 없음: {strategy_account_id}")
                return {
                    'success': False,
                    'error': 'strategy_account_not_found',
                    'error_type': 'position_error'
                }

            # Row-Level Lock 획득 (skip_locked=True)
            # 참조: order_manager.py - OpenOrder 락 패턴
            position = StrategyPosition.query.filter_by(
                strategy_account_id=strategy_account_id,
                symbol=symbol
            ).with_for_update(skip_locked=True).first()

            if not position:
                # 두 가지 경우:
                # 1. 포지션이 실제로 없음 (첫 Trade)
                # 2. 다른 스레드가 락 보유 중 (lock contention)

                # 락 없이 다시 조회 (존재 여부만 확인)
                position_exists = StrategyPosition.query.filter_by(
                    strategy_account_id=strategy_account_id,
                    symbol=symbol
                ).count() > 0

                if position_exists:
                    # 케이스 2: 락 경합 - graceful skip (블로킹 없음)
                    logger.warning(
                        f"⏭️ 포지션 업데이트 스킵 (락 경합): "
                        f"symbol={symbol}, strategy_account_id={strategy_account_id}"
                    )
                    return {
                        'success': True,
                        'skipped': True,
                        'reason': 'lock_contention'
                    }
                else:
                    # 케이스 1: 새 포지션 생성 필요
                    position = StrategyPosition(
                        strategy_account_id=strategy_account_id,
                        symbol=symbol,
                        quantity=0,
                        entry_price=0
                    )
                    db.session.add(position)

            current_qty = to_decimal(position.quantity)
            current_price = to_decimal(position.entry_price)
            side_upper = side.upper()

            logger.info(
                "포지션 업데이트 - 심볼: %s, strategy_account_id: %s, 현재: %s @ %s, 추가: %s %s @ %s",
                symbol,
                strategy_account_id,
                current_qty,
                current_price,
                side_upper,
                quantity,
                price
            )

            previous_qty = current_qty
            trade_qty = quantity if side_upper == 'BUY' else -quantity
            realized_pnl = Decimal('0')

            if current_qty == Decimal('0'):
                new_qty = trade_qty
                new_price = price
            elif current_qty * trade_qty > 0:
                # 기존 포지션과 동일한 방향으로 추가 진입
                new_qty = current_qty + trade_qty
                total_abs = abs(current_qty) + abs(trade_qty)
                if total_abs > 0:
                    weighted_price = (
                        abs(current_qty) * current_price + abs(trade_qty) * price
                    ) / total_abs
                else:
                    weighted_price = price
                new_price = weighted_price
            else:
                # 포지션 일부 또는 전체 청산
                closing_qty = min(abs(current_qty), abs(trade_qty))
                if closing_qty > 0:
                    if current_qty > 0:
                        realized_pnl = closing_qty * (price - current_price)
                    else:
                        realized_pnl = closing_qty * (current_price - price)

                residual_qty = current_qty + trade_qty

                if residual_qty == 0:
                    new_qty = Decimal('0')
                    new_price = Decimal('0')
                elif current_qty * residual_qty > 0:
                    # 부분 청산 후 동일 방향 유지
                    new_qty = residual_qty
                    new_price = current_price
                else:
                    # 포지션 반전 (새 방향으로 전환)
                    new_qty = residual_qty
                    new_price = price

            normalized_qty, min_qty, step_unit, _ = self.service.quantity_calculator.quantize_quantity_for_symbol(
                strategy_account, symbol, new_qty
            )
            if normalized_qty != new_qty:
                logger.debug(
                    "포지션 수량 정밀도 보정: %s -> %s (%s)",
                    new_qty, normalized_qty, symbol
                )
            new_qty = normalized_qty

            min_threshold = Decimal('0.000001')
            if min_qty and min_qty > 0:
                min_threshold = max(min_threshold, min_qty)
            if step_unit and step_unit > 0:
                min_threshold = max(min_threshold, step_unit)

            position.quantity = decimal_to_float(new_qty)
            position.entry_price = decimal_to_float(new_price)
            position.last_updated = datetime.utcnow()

            position_deleted = abs(new_qty) < min_threshold

            db.session.flush()
            position_id = getattr(position, 'id', None)

            if position_deleted:
                db.session.delete(position)
                logger.info(f"포지션 완전 청산으로 삭제: {symbol}")
            else:
                logger.info(
                    f"✅ 포지션 업데이트 완료 (락 획득): "
                    f"symbol={symbol}, qty={previous_qty} → {new_qty} @ {new_price}"
                )

            db.session.commit()

            # @FEAT:capital-reallocation @COMP:service @TYPE:integration
            # 트랜잭션 분리: 포지션 청산 후 자본 재할당 트리거 (plan-reviewer Issue 3 반영)
            # 분리 이유: Race condition 방지, 에러 격리
            # 1. 포지션 삭제 커밋 완료 (Line 841) → DB 반영됨
            # 2. 별도 try-except로 재할당 시도 (Line 846-863)
            # 3. 재할당 실패 시에도 포지션 삭제는 유지됨 (행-level 원자성 보장)
            # 목적: 포지션 삭제 성공은 보장하되, 재할당 로직 오류는 격리
            if position_deleted:
                try:
                    from app.services.capital_service import capital_allocation_service

                    account_id = strategy_account.account_id if strategy_account.account else None
                    if not account_id:
                        logger.warning(f"포지션 청산 후 재할당 스킵 - 계좌 ID 없음: {symbol}")
                    else:
                        check_result = capital_allocation_service.should_rebalance(account_id)
                        if check_result['should_rebalance']:
                            logger.info(f"🔄 포지션 청산 트리거 - 계좌 ID: {account_id}, 사유: {check_result['reason']}")
                            capital_allocation_service.recalculate_strategy_capital(
                                account_id=account_id,
                                use_live_balance=True
                            )
                        else:
                            logger.debug(f"재할당 스킵 - {check_result['reason']}")
                except Exception as e:
                    logger.error(f"❌ 포지션 청산 후 재할당 실패 - 계좌 ID: {account_id}, 오류: {e}")
                    # 포지션 삭제는 이미 커밋됨 → 재할당 오류는 독립적으로 처리

            if strategy_account.strategy:
                self.service.event_emitter.emit_position_event(
                    strategy_account=strategy_account,
                    position_id=position_id,
                    symbol=symbol,
                    previous_qty=previous_qty,
                    new_qty=new_qty,
                    new_price=new_price,
                    position_closed=position_deleted
                )

            return {
                'success': True,
                'previous_quantity': previous_qty,
                'new_quantity': new_qty,
                'new_price': new_price,
                'realized_pnl': realized_pnl
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"포지션 업데이트 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'position_error'
            }

    # @FEAT:position-tracking @COMP:service @TYPE:helper
    def _get_strategy_account_ids(self, strategy_id: int) -> List[int]:
        """전략과 연결된 StrategyAccount ID 목록 반환"""
        accounts = StrategyAccount.query.filter_by(strategy_id=strategy_id).all()
        return [account.id for account in accounts]

    # @FEAT:position-tracking @COMP:service @TYPE:core
    def get_positions(self, strategy_id: int) -> List[Dict[str, Any]]:
        """전략 포지션 목록 조회"""
        try:
            strategy_account_ids = self._get_strategy_account_ids(strategy_id)
            if not strategy_account_ids:
                return []

            positions = (
                StrategyPosition.query
                .filter(StrategyPosition.strategy_account_id.in_(strategy_account_ids))
                .all()
            )

            return [
                {
                    'id': pos.id,
                    'symbol': pos.symbol,
                    'quantity': to_decimal(pos.quantity),
                    'entry_price': to_decimal(pos.entry_price),
                    'unrealized_pnl': Decimal('0'),
                    'updated_at': pos.last_updated
                }
                for pos in positions
            ]

        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            return []

    # @FEAT:position-tracking @FEAT:background-scheduler @COMP:job @TYPE:core @DEPS:price-cache
    def calculate_unrealized_pnl(self) -> None:
        """백그라운드 작업: 모든 포지션의 미실현 손익 계산 및 업데이트"""
        from app.services.price_cache import price_cache

        try:
            # 모든 열린 포지션 조회
            positions = (
                StrategyPosition.query
                .options(
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.strategy),
                    joinedload(StrategyPosition.strategy_account)
                    .joinedload(StrategyAccount.account)
                )
                .filter(StrategyPosition.quantity != 0)
                .all()
            )

            if not positions:
                logger.debug("미실현 손익 계산: 열린 포지션 없음")
                return

            updated_count = 0
            error_count = 0

            for position in positions:
                try:
                    strategy_account = position.strategy_account
                    if not strategy_account or not strategy_account.strategy:
                        continue

                    strategy = strategy_account.strategy
                    symbol = position.symbol

                    # 현재가 조회
                    market_type = strategy.market_type.lower() if strategy.market_type else 'spot'
                    current_price = price_cache.get_price(symbol, market_type)

                    if not current_price or current_price <= 0:
                        continue

                    # 미실현 손익 계산
                    quantity = self.service._to_decimal(position.quantity)
                    entry_price = self.service._to_decimal(position.entry_price)
                    current_price_decimal = Decimal(str(current_price))

                    if quantity > 0:
                        # 롱 포지션
                        unrealized_pnl = quantity * (current_price_decimal - entry_price)
                    else:
                        # 숏 포지션
                        unrealized_pnl = abs(quantity) * (entry_price - current_price_decimal)

                    # 포지션 업데이트 (unrealized_pnl 필드가 있다면)
                    if hasattr(position, 'unrealized_pnl'):
                        position.unrealized_pnl = float(unrealized_pnl)
                        updated_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"포지션 PnL 계산 실패 - position_id: {position.id}, error: {e}")
                    continue

            # 일괄 커밋
            if updated_count > 0:
                db.session.commit()
                logger.info(f"미실현 손익 계산 완료 - 업데이트: {updated_count}, 오류: {error_count}")
            else:
                logger.debug("미실현 손익 계산: 업데이트할 포지션 없음")

        except Exception as e:
            db.session.rollback()
            logger.error(f"미실현 손익 계산 실패: {e}")

