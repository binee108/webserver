
"""Core trading execution logic extracted from the legacy trading service."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from flask import current_app

from app import db
from app.models import Account, Strategy, StrategyAccount
from app.constants import Exchange, MarketType, OrderType
from app.services.exchange import exchange_service
from app.services.security import security_service

logger = logging.getLogger(__name__)


class TradingCore:
    """Encapsulates trading execution, signal processing, and exchange coordination."""

    def __init__(self, service: Optional[object] = None) -> None:
        self.service = service

    def execute_trade(self, strategy: Strategy, symbol: str, side: str,
                     quantity: Decimal, order_type: str,
                     price: Optional[Decimal] = None,
                     stop_price: Optional[Decimal] = None,
                     strategy_account_override: Optional[StrategyAccount] = None,
                     schedule_refresh: bool = True,
                     timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        거래 실행 (통합된 로직, 안전장치 제거됨)

        Args:
            strategy: 전략 객체
            symbol: 심볼
            side: 매수/매도 방향 (BUY/SELL)
            quantity: 수량
            order_type: 주문 유형 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            price: 가격 (지정가 주문시)
            stop_price: 스탑 가격 (스탑 주문시)
            strategy_account_override: 특정 전략 계좌로 거래를 강제할 때 사용

        Returns:
            거래 실행 결과
        """
        try:
            logger.info(f"거래 실행 시작 - 전략: {strategy.name}, 심볼: {symbol}, "
                       f"주문: {side} {quantity} {order_type}")

            # 계정 정보 조회
            strategy_account = strategy_account_override or StrategyAccount.query.filter_by(
                strategy_id=strategy.id
            ).first()

            if not strategy_account or not strategy_account.account:
                return {
                    'success': False,
                    'error': '전략에 연결된 계정이 없습니다',
                    'error_type': 'account_error'
                }

            account = strategy_account.account

            # 마켓 타입 결정 (대소문자 구분 없이)
            strategy_market_type = getattr(strategy, 'market_type', 'SPOT').upper()
            market_type = 'futures' if strategy_market_type == 'FUTURES' else 'spot'

            logger.info(f"📊 전략 마켓타입: {strategy_market_type} → 거래소 마켓타입: {market_type}")

            # 거래소 주문 실행 (타이밍 정보 포함)
            order_result = self._execute_exchange_order(
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

            order_result['account_id'] = account.id

            if not order_result['success']:
                return order_result

            # 조정된 수량/가격 보관 (거래소 제한 반영)
            adjusted_quantity = order_result.get('adjusted_quantity', quantity)
            adjusted_price = order_result.get('adjusted_price', price)
            adjusted_stop_price = order_result.get('adjusted_stop_price', stop_price)

            fill_summary = self.service.position_manager.process_order_fill(
                strategy_account=strategy_account,
                order_id=order_result.get('order_id'),
                symbol=symbol,
                side=side,
                order_type=order_type,
                order_result=order_result,
                market_type=market_type
            )

            if not fill_summary.get('success'):
                logger.warning(
                    "체결 처리를 완료하지 못했습니다 - order_id=%s reason=%s",
                    order_result.get('order_id'),
                    fill_summary.get('error')
                )
                return {
                    'action': 'trading_signal',
                    'success': False,
                    'error': fill_summary.get('error'),
                    'order_id': order_result.get('order_id'),
                    'account_id': account.id,
                    'order_result': fill_summary.get('order_result')
                }

            order_result = fill_summary.get('order_result', order_result)
            filled_decimal = fill_summary.get('filled_quantity', Decimal('0'))
            average_decimal = fill_summary.get('average_price', Decimal('0'))

            # OpenOrder 레코드 생성 (미체결 주문인 경우)
            open_order_result = self.service.order_manager.create_open_order_record(
                strategy_account=strategy_account,
                order_result=order_result,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=adjusted_quantity,
                price=adjusted_price,
                stop_price=adjusted_stop_price
            )
            if open_order_result['success']:
                logger.info(f"📝 미체결 주문 OpenOrder 저장: {order_result.get('order_id')}")
            else:
                logger.debug(f"OpenOrder 저장 스킵: {open_order_result.get('reason', 'unknown')}")

            if not fill_summary.get('events_emitted'):
                self.service.event_emitter.emit_order_events_smart(strategy, symbol, side, adjusted_quantity, order_result)

            # 응답 데이터 구성 (filled_quantity를 숫자로 변환, 실제 체결가 사용)
            filled_qty_num = 0.0
            avg_price_num = 0.0

            try:
                if filled_decimal and filled_decimal > Decimal('0'):
                    filled_qty_num = float(filled_decimal)
            except (ValueError, TypeError):
                filled_qty_num = 0.0

            # average_price 결정 (실제 체결가 우선)
            if average_decimal and average_decimal > Decimal('0'):
                avg_price_num = float(average_decimal)
            else:
                avg_price_num = float(order_result.get('actual_execution_price', 0) or 0)
                if avg_price_num <= 0:
                    avg_price_num = float(order_result.get('average_price', 0) or 0)
                if avg_price_num <= 0:
                    avg_price_num = float(order_result.get('adjusted_average_price', 0) or 0)

            # results 배열 구성 (시장가 주문 체결 정보)
            results = []
            if filled_qty_num > 0 and avg_price_num > 0:
                results.append({
                    'symbol': symbol,
                    'side': side,
                    'executed_qty': filled_qty_num,
                    'executed_price': avg_price_num,
                    'trade_id': fill_summary.get('trade_id'),
                    'order_id': order_result.get('order_id'),
                    'timestamp': datetime.utcnow().isoformat()
                })

            result_payload = {
                'action': 'trading_signal',
                'success': True,
                'trade_id': fill_summary.get('trade_id'),
                'order_id': order_result.get('order_id'),
                'filled_quantity': filled_qty_num,  # 숫자로 반환
                'average_price': avg_price_num,  # 실제 체결가 반환
                'status': order_result.get('status'),
                'trade_status': fill_summary.get('trade_status'),
                'execution_status': fill_summary.get('execution_status'),
                'account_id': account.id,
                'results': results  # 체결 상세 정보 배열
            }


            if schedule_refresh:
                security_service.refresh_account_balance_async(account.id)

            return result_payload

        except Exception as e:
            logger.error(f"거래 실행 실패: {e}")
            failure_payload = {
                'action': 'trading_signal',
                'success': False,
                'error': str(e),
                'error_type': 'execution_error'
            }
            if 'account_id' not in failure_payload and 'account' in locals() and account:
                failure_payload['account_id'] = account.id
            return failure_payload


