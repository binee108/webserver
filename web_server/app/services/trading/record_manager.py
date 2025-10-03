
"""Trade record management extracted from the legacy trading service."""

from __future__ import annotations

import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app import db
from app.models import (
    Strategy,
    Account,
    StrategyAccount,
    StrategyPosition,
    Trade,
    TradeExecution,
    OpenOrder,
)
from app.services.utils import calculate_is_entry, decimal_to_float, to_decimal

logger = logging.getLogger(__name__)


class RecordManager:
    """Encapsulates trade and execution record persistence logic."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    # ------------------------------------------------------------------
    # Trade record helpers
    # ------------------------------------------------------------------
    def create_trade_record(
        self,
        strategy: Strategy,
        account: Account,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        order_id: str,
        order_type: str,
        order_price: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Create or update a ``Trade`` record for the given execution."""
        try:
            strategy_account = StrategyAccount.query.filter_by(
                strategy_id=strategy.id
            ).first()

            if not strategy_account:
                logger.error(
                    "전략 %s에 연결된 StrategyAccount를 찾을 수 없음", strategy.id
                )
                return {'success': False, 'error': 'strategy_account not found'}

            existing_trade = Trade.query.filter_by(
                strategy_account_id=strategy_account.id,
                exchange_order_id=str(order_id)
            ).first()

            quantity_float = decimal_to_float(quantity)
            price_float = decimal_to_float(price) if price and price > 0 else 0.0
            order_price_float = (
                decimal_to_float(order_price) if order_price and order_price > 0 else None
            )
            side_upper = side.upper()

            if existing_trade:
                previous_quantity = to_decimal(existing_trade.quantity)
                quantity_delta = quantity - previous_quantity

                changed = False

                if quantity_delta != Decimal('0'):
                    existing_trade.quantity = quantity_float
                    changed = True

                if price_float > 0 and price_float != existing_trade.price:
                    existing_trade.price = price_float
                    changed = True

                if order_price_float is not None:
                    if existing_trade.order_price != order_price_float:
                        existing_trade.order_price = order_price_float
                        changed = True

                if existing_trade.side != side_upper:
                    existing_trade.side = side_upper
                    changed = True

                if existing_trade.order_type != order_type:
                    existing_trade.order_type = order_type
                    changed = True

                if changed:
                    existing_trade.timestamp = datetime.utcnow()
                    existing_trade.is_entry = self._calculate_is_entry_for_trade(
                        strategy.id, symbol, side
                    )
                    db.session.commit()
                    logger.info(
                        "Trade 기록 업데이트: %s %s %s @ %s",
                        symbol,
                        side_upper,
                        existing_trade.quantity,
                        existing_trade.price,
                    )
                    return {
                        'success': True,
                        'trade_id': existing_trade.id,
                        'status': 'updated',
                        'quantity_delta': quantity_delta,
                    }

                logger.debug("Trade 기록 변경 없음: order_id=%s", order_id)
                return {
                    'success': True,
                    'trade_id': existing_trade.id,
                    'status': 'unchanged',
                    'quantity_delta': Decimal('0'),
                }

            trade = Trade(
                strategy_account_id=strategy_account.id,
                symbol=symbol,
                side=side_upper,
                quantity=quantity_float,
                price=price_float,
                exchange_order_id=str(order_id),
                order_type=order_type,
                is_entry=self._calculate_is_entry_for_trade(
                    strategy.id, symbol, side
                ),
                timestamp=datetime.utcnow(),
            )

            if order_price_float is not None:
                trade.order_price = order_price_float

            db.session.add(trade)
            db.session.commit()

            logger.info(
                "Trade 기록 생성: %s %s %s @ %s",
                symbol,
                side_upper,
                quantity,
                price,
            )

            return {
                'success': True,
                'trade_id': trade.id,
                'status': 'created',
                'quantity_delta': quantity,
            }

        except Exception as exc:  # pragma: no cover - defensive logging
            db.session.rollback()
            logger.error("Trade 기록 생성/업데이트 실패: %s", exc)
            return {
                'success': False,
                'error': str(exc),
            }

    def create_trade_execution_record(
        self,
        strategy_account: StrategyAccount,
        order_result: Dict[str, Any],
        symbol: str,
        side: str,
        order_type: str,
        trade_id: Optional[int] = None,
        realized_pnl: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Create or update a ``TradeExecution`` entry."""
        try:
            order_id = order_result.get('order_id')
            if not order_id:
                return {'success': False, 'error': 'missing_order_id'}

            filled_decimal = to_decimal(order_result.get('filled_quantity'))
            if filled_decimal <= Decimal('0'):
                return {'success': False, 'reason': 'no_fill'}

            execution_price_decimal = to_decimal(
                order_result.get('average_price')
                or order_result.get('adjusted_average_price')
                or order_result.get('price')
            )

            execution_quantity = float(filled_decimal)
            execution_price = (
                float(execution_price_decimal) if execution_price_decimal > 0 else 0.0
            )

            exchange_trade_id = order_result.get('exchange_trade_id', str(order_id))

            existing_execution = TradeExecution.query.filter_by(
                strategy_account_id=strategy_account.id,
                exchange_order_id=str(order_id),
            ).first()

            if existing_execution:
                changed = False

                if execution_quantity != existing_execution.execution_quantity:
                    existing_execution.execution_quantity = execution_quantity
                    changed = True

                if execution_price > 0 and execution_price != existing_execution.execution_price:
                    existing_execution.execution_price = execution_price
                    changed = True

                if existing_execution.side != side.upper():
                    existing_execution.side = side.upper()
                    changed = True

                new_market_type = strategy_account.strategy.market_type or 'SPOT'
                if existing_execution.market_type != new_market_type:
                    existing_execution.market_type = new_market_type
                    changed = True

                if realized_pnl is not None and (
                    existing_execution.realized_pnl is None
                    or float(realized_pnl) != existing_execution.realized_pnl
                ):
                    existing_execution.realized_pnl = float(realized_pnl)
                    changed = True

                if changed:
                    existing_execution.execution_time = datetime.utcnow()
                    existing_execution.trade_id = trade_id or existing_execution.trade_id
                    db.session.commit()
                    logger.info(
                        "TradeExecution 업데이트: order_id=%s qty=%s",
                        order_id,
                        execution_quantity,
                    )

                    # Phase 3.2: 실시간 성과 업데이트 Hook
                    self._trigger_performance_update(strategy_account.strategy_id)

                    return {
                        'success': True,
                        'trade_execution_id': existing_execution.id,
                        'status': 'updated',
                        'execution_price': execution_price,
                        'execution_quantity': execution_quantity,
                        'realized_pnl': existing_execution.realized_pnl,
                    }

                return {
                    'success': True,
                    'trade_execution_id': existing_execution.id,
                    'status': 'unchanged',
                    'realized_pnl': existing_execution.realized_pnl,
                }

            trade_execution = TradeExecution(
                trade_id=trade_id,
                strategy_account_id=strategy_account.id,
                exchange_trade_id=exchange_trade_id,
                exchange_order_id=str(order_id),
                symbol=symbol,
                side=side.upper(),
                execution_price=execution_price,
                execution_quantity=execution_quantity,
                commission=float(order_result.get('commission', 0) or 0),
                commission_asset=order_result.get('commission_asset'),
                execution_time=datetime.utcnow(),
                is_maker=order_result.get('is_maker'),
                realized_pnl=(
                    float(realized_pnl)
                    if realized_pnl is not None
                    else order_result.get('realized_pnl')
                ),
                market_type=strategy_account.strategy.market_type or 'SPOT',
                meta_data={
                    'order_type': order_type,
                    'raw_response': str(order_result.get('raw_response', {})),
                },
            )

            db.session.add(trade_execution)
            db.session.commit()

            logger.info(
                "📊 TradeExecution 레코드 생성: %s %s %s @ %s",
                symbol,
                side,
                execution_quantity,
                execution_price,
            )

            # Phase 3.2: 실시간 성과 업데이트 Hook
            self._trigger_performance_update(strategy_account.strategy_id)

            response: Dict[str, Any] = {
                'success': True,
                'trade_execution_id': trade_execution.id,
                'status': 'created',
                'execution_price': execution_price,
                'execution_quantity': execution_quantity,
            }
            if trade_execution.realized_pnl is not None:
                response['realized_pnl'] = trade_execution.realized_pnl

            return response

        except Exception as exc:  # pragma: no cover - defensive logging
            db.session.rollback()
            logger.error("TradeExecution 레코드 생성/업데이트 실패: %s", exc)
            return {
                'success': False,
                'error': str(exc),
            }

    # ------------------------------------------------------------------
    # Trade queries
    # ------------------------------------------------------------------
    def get_trade_history(
        self,
        strategy_id: int,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return the most recent trades for the supplied strategy."""
        try:
            strategy_account_ids = self._get_strategy_account_ids(strategy_id)
            if not strategy_account_ids:
                return []

            trades = (
                Trade.query
                .filter(Trade.strategy_account_id.in_(strategy_account_ids))
                .order_by(Trade.timestamp.desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    'id': trade.id,
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'quantity': to_decimal(trade.quantity),
                    'price': to_decimal(trade.price),
                    'order_id': trade.exchange_order_id,
                    'order_type': trade.order_type,
                    'is_entry': trade.is_entry,
                    'executed_at': trade.timestamp,
                }
                for trade in trades
            ]

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("거래 내역 조회 실패: %s", exc)
            return []

    def get_trading_stats(self, strategy_id: int) -> Dict[str, Any]:
        """Return aggregate trading statistics for a strategy."""
        try:
            strategy_account_ids = self._get_strategy_account_ids(strategy_id)
            if not strategy_account_ids:
                return {
                    'total_trades': 0,
                    'active_positions': 0,
                    'open_orders': 0,
                    'last_trade_time': None,
                }

            recent_trades = (
                Trade.query
                .filter(Trade.strategy_account_id.in_(strategy_account_ids))
                .count()
            )

            active_positions = (
                StrategyPosition.query
                .filter(
                    StrategyPosition.strategy_account_id.in_(strategy_account_ids),
                    StrategyPosition.quantity != 0,
                )
                .count()
            )

            open_orders = (
                OpenOrder.query
                .filter(OpenOrder.strategy_account_id.in_(strategy_account_ids))
                .count()
            )

            return {
                'total_trades': recent_trades,
                'active_positions': active_positions,
                'open_orders': open_orders,
                'last_trade_time': self._get_last_trade_time(strategy_id),
            }

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("거래 통계 조회 실패: %s", exc)
            return {
                'total_trades': 0,
                'active_positions': 0,
                'open_orders': 0,
                'last_trade_time': None,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_last_trade_time(self, strategy_id: int) -> Optional[datetime]:
        try:
            strategy_account_ids = self._get_strategy_account_ids(strategy_id)
            if not strategy_account_ids:
                return None

            last_trade = (
                Trade.query
                .filter(Trade.strategy_account_id.in_(strategy_account_ids))
                .order_by(Trade.timestamp.desc())
                .first()
            )

            return last_trade.timestamp if last_trade else None

        except Exception:  # pragma: no cover - defensive logging
            return None

    def _get_strategy_account_ids(self, strategy_id: int) -> List[int]:
        accounts = StrategyAccount.query.filter_by(strategy_id=strategy_id).all()
        return [account.id for account in accounts]

    def _calculate_is_entry_for_trade(
        self,
        strategy_id: int,
        symbol: str,
        side: str,
    ) -> bool:
        try:
            strategy_account_ids = self._get_strategy_account_ids(strategy_id)
            if not strategy_account_ids:
                return True

            total_quantity = (
                db.session.query(func.sum(StrategyPosition.quantity))
                .filter(
                    StrategyPosition.strategy_account_id.in_(strategy_account_ids),
                    StrategyPosition.symbol == symbol,
                )
                .scalar()
            )

            current_qty = Decimal(str(total_quantity)) if total_quantity else Decimal('0')
            return calculate_is_entry(current_qty, side)
        except AttributeError as exc:
            logger.warning("포지션 속성 오류: %s, 기본값(진입) 반환", exc)
            return True
        except (ValueError, TypeError) as exc:
            logger.warning("수량 변환 오류: %s, 기본값(진입) 반환", exc)
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("진입/청산 판단 예상치 못한 오류: %s, 기본값(진입) 반환", exc)
            return True

    def _trigger_performance_update(self, strategy_id: int) -> None:
        """
        Phase 3.2: 거래 기록 후 실시간 성과 업데이트 Hook

        거래 실행 기록이 생성/업데이트될 때 자동으로 당일 성과를 재계산합니다.
        """
        try:
            from app.services.performance_tracking import performance_tracking_service

            today = date.today()
            performance = performance_tracking_service.calculate_daily_performance(
                strategy_id=strategy_id,
                target_date=today
            )

            if performance:
                logger.info(
                    "📈 실시간 성과 업데이트 완료: 전략 %s, 일일 PnL: %s, 누적 PnL: %s",
                    strategy_id,
                    performance.daily_pnl,
                    performance.cumulative_pnl
                )
            else:
                logger.warning("실시간 성과 업데이트 실패: 전략 %s", strategy_id)

        except Exception as exc:
            # 성과 업데이트 실패는 거래 기록에 영향을 주지 않음 (비침습적 hook)
            logger.error(
                "실시간 성과 업데이트 중 오류 발생 (전략: %s): %s",
                strategy_id,
                exc
            )
