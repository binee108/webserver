
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

    def process_trading_signal(self, webhook_data: Dict[str, Any],
                               timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """거래 신호 처리"""
        from app.services.utils import to_decimal

        # 필수 필드 검증
        required_fields = ['group_name', 'exchange', 'market_type', 'currency', 'symbol', 'order_type', 'side']
        for field in required_fields:
            if field not in webhook_data:
                raise Exception(f"필수 필드 누락: {field}")

        group_name = webhook_data['group_name']
        exchange = webhook_data['exchange']
        market_type = webhook_data['market_type']
        currency = webhook_data['currency']
        symbol = webhook_data['symbol']
        order_type = webhook_data['order_type']
        side = webhook_data['side']
        price = to_decimal(webhook_data.get('price')) if webhook_data.get('price') else None
        stop_price = to_decimal(webhook_data.get('stop_price')) if webhook_data.get('stop_price') else None
        qty_per = to_decimal(webhook_data.get('qty_per', 100))

        # STOP_LIMIT 주문 필수 필드 검증
        if order_type == 'STOP_LIMIT':
            if not stop_price:
                raise Exception("STOP_LIMIT 주문: stop_price가 필수입니다")
            if not price:
                raise Exception("STOP_LIMIT 주문: price가 필수입니다")

        logger.info(f"거래 신호 처리 시작 - 전략: {group_name}, 거래소: {exchange}, 심볼: {symbol}, "
                   f"사이드: {side}, 주문타입: {order_type}, 수량비율: {qty_per}%")

        # 전략 조회
        strategy = Strategy.query.filter_by(group_name=group_name, is_active=True).first()
        if not strategy:
            raise Exception(f"활성 전략을 찾을 수 없습니다: {group_name}")

        logger.info(f"전략 조회 성공 - ID: {strategy.id}, 이름: {strategy.name}, 마켓타입: {strategy.market_type}")

        # 전략에 연결된 계좌들 조회
        strategy_accounts = strategy.strategy_accounts
        if not strategy_accounts:
            raise Exception(f"전략에 연결된 계좌가 없습니다: {group_name}")

        logger.info(f"전략에 연결된 계좌 수: {len(strategy_accounts)}")

        # 계좌 필터링
        filtered_accounts = []
        for sa in strategy_accounts:
            account = sa.account

            if hasattr(sa, 'is_active') and not sa.is_active:
                continue
            if not account or not account.is_active:
                continue
            if account.exchange.upper() != exchange.upper():
                continue

            filtered_accounts.append((strategy, account, sa))

        logger.info(f"거래 실행 대상 계좌: {len(filtered_accounts)}")

        # 병렬 거래 실행
        results = []
        if filtered_accounts:
            results = self._execute_trades_parallel(
                filtered_accounts, symbol, side, order_type, price, stop_price, qty_per, currency, market_type, timing_context
            )

        successful_trades = [r for r in results if r.get('success', False)]
        failed_trades = [r for r in results if not r.get('success', False)]

        logger.info(f"거래 신호 처리 완료 - 성공: {len(successful_trades)}, 실패: {len(failed_trades)}")

        # 표준 응답 포맷 (process_cancel_all_orders와 동일한 구조)
        return {
            'action': side.lower(),  # 'buy' or 'sell'
            'strategy': group_name,
            'market_type': market_type,
            'success': len(successful_trades) > 0,
            'results': results,
            'summary': {
                'total_accounts': len(filtered_accounts),
                'executed_accounts': len(results),
                'successful_trades': len(successful_trades),
                'failed_trades': len(failed_trades),
                'inactive_accounts': len(strategy_accounts) - len(filtered_accounts)
            }
        }

    def _execute_trades_parallel(self, filtered_accounts: List[tuple], symbol: str,
                                 side: str, order_type: str, price: Optional[Decimal],
                                 stop_price: Optional[Decimal], qty_per: Decimal,
                                 currency: str, market_type: str,
                                 timing_context: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """병렬 거래 실행 (qty_per → quantity 변환 포함)"""
        results = []
        max_workers = min(10, len(filtered_accounts))

        # Flask app context를 미리 캡처
        app = current_app._get_current_object()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for strategy, account, sa in filtered_accounts:
                # qty_per를 실제 주문 수량으로 변환
                try:
                    calculated_quantity = self.service.quantity_calculator.calculate_order_quantity(
                        strategy_account=sa,
                        qty_per=qty_per,
                        symbol=symbol,
                        order_type=order_type,
                        market_type=market_type,
                        price=price,
                        stop_price=stop_price,
                        side=side
                    )

                    if calculated_quantity == Decimal('0'):
                        logger.warning(f"계좌 {account.id}: 수량 계산 결과 0, 주문 스킵")
                        results.append({
                            'success': False,
                            'error': '계산된 주문 수량이 0입니다',
                            'account_id': account.id,
                            'skipped': True
                        })
                        continue

                    logger.debug(f"계좌 {account.id}: qty_per {qty_per}% → quantity {calculated_quantity}")

                except Exception as calc_error:
                    logger.error(f"계좌 {account.id}: 수량 계산 실패 - {calc_error}")
                    results.append({
                        'success': False,
                        'error': f'수량 계산 실패: {calc_error}',
                        'account_id': account.id
                    })
                    continue

                # 변환된 수량으로 거래 실행 (Flask app context 포함)
                def execute_in_context(app, strategy, account, sa, symbol, side, calculated_quantity, order_type, price, stop_price, timing_context):
                    with app.app_context():
                        return self.execute_trade(
                            strategy=strategy,
                            symbol=symbol,
                            side=side,
                            quantity=calculated_quantity,  # ✅ 변환된 수량 사용
                            order_type=order_type,
                            price=price,
                            stop_price=stop_price,
                            strategy_account_override=sa,
                            timing_context=timing_context
                        )

                future = executor.submit(
                    execute_in_context,
                    app, strategy, account, sa, symbol, side, calculated_quantity, order_type, price, stop_price, timing_context
                )
                futures[future] = (strategy, account, sa)

            for future in as_completed(futures):
                strategy, account, sa = futures[future]
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except Exception as e:
                    logger.error(f"거래 실행 실패 (계좌 {account.id}): {e}")
                    results.append({
                        'success': False,
                        'error': str(e),
                        'account_id': account.id
                    })

        return results

    def process_batch_trading_signal(self, webhook_data: Dict[str, Any],
                                     timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """배치 거래 신호 처리"""
        from app.services.utils import to_decimal

        # 필수 필드 검증
        required_fields = ['group_name', 'exchange', 'market_type', 'currency', 'orders']
        for field in required_fields:
            if field not in webhook_data:
                raise Exception(f"필수 필드 누락: {field}")

        group_name = webhook_data['group_name']
        orders = webhook_data['orders']

        if not isinstance(orders, list) or len(orders) == 0:
            raise Exception("orders 필드는 비어있지 않은 배열이어야 합니다")

        logger.info(f"배치 거래 신호 처리 시작 - 전략: {group_name}, 주문 수: {len(orders)}")

        # 각 주문에 대해 process_trading_signal 호출
        results = []
        for idx, order in enumerate(orders):
            try:
                # 공통 필드 병합
                order_data = {
                    'group_name': group_name,
                    'exchange': webhook_data['exchange'],
                    'market_type': webhook_data['market_type'],
                    'currency': webhook_data['currency'],
                    **order
                }

                result = self.process_trading_signal(order_data, timing_context)
                results.append({
                    'order_index': idx,
                    'success': result.get('success', False),
                    'result': result
                })
            except Exception as e:
                logger.error(f"배치 주문 {idx} 처리 실패: {e}")
                results.append({
                    'order_index': idx,
                    'success': False,
                    'error': str(e)
                })

        successful = [r for r in results if r.get('success', False)]
        failed = [r for r in results if not r.get('success', False)]

        logger.info(f"배치 거래 신호 처리 완료 - 성공: {len(successful)}, 실패: {len(failed)}")

        # 표준 응답 포맷 (process_cancel_all_orders와 동일한 구조)
        return {
            'action': 'batch_order',
            'strategy': group_name,
            'market_type': webhook_data['market_type'],
            'success': len(successful) > 0,
            'results': results,
            'summary': {
                'total_orders': len(orders),
                'executed_orders': len(results),
                'successful_orders': len(successful),
                'failed_orders': len(failed)
            }
        }


    def _execute_exchange_order(self, account: Account, symbol: str, side: str,
                                quantity: Decimal, order_type: str, market_type: str,
                                price: Optional[Decimal] = None,
                                stop_price: Optional[Decimal] = None,
                                timing_context: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        거래소에 주문을 전송하고 결과를 반환합니다.
        
        Args:
            account: 거래 계좌
            symbol: 거래 심볼
            side: 주문 방향 (BUY/SELL)
            quantity: 주문 수량 (Decimal)
            order_type: 주문 타입 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            market_type: 마켓 타입 (spot/futures)
            price: 지정가 (LIMIT 주문 시)
            stop_price: 스탑 가격 (STOP 주문 시)
            timing_context: 타이밍 측정용 딕셔너리
            
        Returns:
            Dict with keys:
                - success (bool): 성공 여부
                - order_id (str): 주문 ID
                - adjusted_quantity (Decimal): 조정된 수량
                - adjusted_price (Decimal): 조정된 가격
                - raw_result (dict): 원본 응답
                - error (str): 에러 메시지 (실패 시)
        """
        from app.services.utils import decimal_to_float
        
        try:
            # 타이밍 기록 시작
            if timing_context is not None:
                timing_context['exchange_call_start'] = time.time()
            
            logger.info(f"거래소 주문 전송 - 마켓타입: {market_type}, 수량: {quantity}, 가격: {price}")
            
            # 거래소 주문 실행
            order_result = exchange_service.create_order(
                account=account,
                symbol=symbol,
                side=side.upper(),
                quantity=quantity,  # Decimal 타입 그대로 전달
                order_type=order_type,
                market_type=market_type,
                price=price,  # Decimal 타입 그대로 전달
                stop_price=stop_price  # Decimal 타입 그대로 전달
            )
            
            # 타이밍 기록 종료
            if timing_context is not None:
                timing_context['exchange_call_end'] = time.time()
            
            # 주문 ID 확인 (exchange_service는 항상 'order_id'를 반환 - 단일 진실 소스)
            order_id = order_result.get('order_id')
            if not order_id:
                logger.error(f"주문 응답에 order_id 없음. success={order_result.get('success')}, error={order_result.get('error')}")
                return {
                    'success': False,
                    'error': order_result.get('error', '주문 ID를 받지 못했습니다'),
                    'error_type': 'exchange_error'
                }

            # 성공 응답 포맷팅
            return {
                'success': True,
                'order_id': order_id,
                'adjusted_quantity': quantity,
                'adjusted_price': price,
                'adjusted_stop_price': stop_price,
                'raw_result': order_result
            }
            
        except Exception as e:
            logger.error(f"거래소 주문 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'exchange_error'
            }
    def _merge_order_with_exchange(self, account: Account, symbol: str,
                                   market_type: str, order_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        거래소의 주문 상태를 조회하여 order_result에 병합합니다.
        
        Args:
            account: 거래 계좌
            symbol: 거래 심볼
            market_type: 마켓 타입 (spot/futures)
            order_result: 기존 주문 결과 딕셔너리
            
        Returns:
            병합된 주문 정보 딕셔너리
            
        Note:
            거래소에서 최신 주문 정보를 가져와 filled_quantity, average_price 등을 업데이트합니다.
        """
        try:
            order_id = order_result.get('order_id') or order_result.get('id')
            if not order_id:
                logger.warning("주문 ID가 없어 거래소 주문 병합을 건너뜁니다")
                return order_result
            
            # 거래소에서 최신 주문 상태 조회
            logger.debug(f"거래소 주문 상태 조회 - order_id: {order_id}, symbol: {symbol}")
            exchange_order = exchange_service.fetch_order(
                account=account,
                symbol=symbol,
                order_id=order_id,
                market_type=market_type
            )
            
            if exchange_order and isinstance(exchange_order, dict):
                # 거래소 응답에서 중요 필드 추출하여 병합
                merged = order_result.copy()

                # 체결 정보 업데이트 (exchange.py 표준 응답 키 사용)
                if 'filled_quantity' in exchange_order:
                    merged['filled_quantity'] = exchange_order['filled_quantity']
                if 'average_price' in exchange_order:
                    merged['average_price'] = exchange_order['average_price']
                elif 'limit_price' in exchange_order:
                    merged['average_price'] = exchange_order['limit_price']

                # 상태 정보 업데이트
                if 'status' in exchange_order:
                    merged['status'] = exchange_order['status']

                # 수수료 정보 업데이트 (fee는 exchange 응답에 없으므로 제거)
                # exchange.py fetch_order는 fee를 반환하지 않음

                # 원본 응답 저장
                if 'raw_result' not in merged:
                    merged['raw_result'] = exchange_order

                logger.debug(f"거래소 주문 병합 완료 - filled: {merged.get('filled_quantity')}, "
                           f"avg_price: {merged.get('average_price')}")
                return merged
            else:
                logger.warning(f"거래소 주문 조회 실패 또는 응답 없음 - order_id: {order_id}")
                return order_result
                
        except Exception as e:
            logger.warning(f"거래소 주문 병합 실패: {e}, 원본 결과 사용")
            return order_result

    def _to_decimal(self, value: Any, default: Decimal = Decimal('0')) -> Decimal:
        """
        값을 안전하게 Decimal로 변환합니다.
        
        Args:
            value: 변환할 값 (int, float, str, Decimal 등)
            default: 변환 실패 시 기본값
            
        Returns:
            Decimal 타입의 값
            
        Example:
            >>> self._to_decimal(100)
            Decimal('100')
            >>> self._to_decimal('50.5')
            Decimal('50.5')
            >>> self._to_decimal(None)
            Decimal('0')
            >>> self._to_decimal('invalid', Decimal('999'))
            Decimal('999')
        """
        from app.services.utils import to_decimal as utils_to_decimal
        
        if value is None:
            return default
        
        try:
            return utils_to_decimal(value)
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.debug(f"Decimal 변환 실패: {value} (타입: {type(value).__name__}), 기본값 사용: {default}")
            return default
