"""
주문 실행 전용 서비스
거래소별 주문 실행 로직 관리
"""

import logging
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_DOWN
from app.models import Account
from app.constants import MarketType, OrderType
from app.services.precision_cache_service import precision_cache_service

logger = logging.getLogger(__name__)


class OrderExecutionService:
    """주문 실행 전용 서비스"""

    def __init__(self):
        self._connection_service = None

    def set_connection_service(self, connection_service):
        """연결 서비스 설정 (의존성 주입)"""
        self._connection_service = connection_service

    def execute_order(self,
                     account: Account,
                     symbol: str,
                     side: str,
                     quantity: Decimal,
                     order_type: str,
                     market_type: str,
                     price: Optional[Decimal] = None,
                     stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        주문 실행

        Args:
            account: 계정 정보
            symbol: 거래 심볼
            side: 매수/매도 (BUY/SELL)
            quantity: 수량
            order_type: 주문 유형 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT)
            market_type: 마켓 유형 (spot/futures)
            price: 지정가 (LIMIT 주문시 필수)
            stop_price: 스탑 가격 (STOP 주문시 필수)

        Returns:
            주문 실행 결과
        """
        try:
            if not self._connection_service:
                raise Exception("Connection service not set")

            # 거래소 인스턴스 가져오기
            exchange_instance = self._connection_service.get_exchange_instance(account)
            if not exchange_instance:
                return {
                    'success': False,
                    'error': '거래소 연결 실패',
                    'error_type': 'connection_error'
                }

            # 수량 및 가격 정밀도 적용
            processed_params = self._apply_precision(
                exchange_instance, account.exchange, symbol, market_type,
                quantity, price, stop_price
            )

            if not processed_params['success']:
                return processed_params

            # 거래소별 주문 실행
            return self._execute_exchange_order(
                exchange_instance,
                account.exchange,
                symbol,
                side,
                processed_params['quantity'],
                order_type,
                market_type,
                processed_params.get('price'),
                processed_params.get('stop_price')
            )

        except Exception as e:
            logger.error(f"주문 실행 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'execution_error'
            }

    def _apply_precision(self,
                        exchange_instance: Any,
                        exchange_name: str,
                        symbol: str,
                        market_type: str,
                        quantity: Decimal,
                        price: Optional[Decimal],
                        stop_price: Optional[Decimal]) -> Dict[str, Any]:
        """수량 및 가격에 정밀도 적용"""
        try:
            # precision 정보 가져오기
            precision_info = precision_cache_service.get_precision_info(
                exchange_name, symbol, market_type
            )

            if not precision_info:
                # 캐시에 없으면 거래소에서 직접 조회
                try:
                    # Native 구현체에서 precision 정보 조회
                    if hasattr(exchange_instance, 'get_symbol_info'):
                        symbol_info = exchange_instance.get_symbol_info(symbol)
                        if symbol_info:
                            precision_info = {
                                'amount': symbol_info.get('baseAssetPrecision', 8),
                                'price': symbol_info.get('quotePrecision', 8),
                                'limits': symbol_info.get('filters', {})
                            }
                        else:
                            precision_info = {'amount': 8, 'price': 8, 'limits': {}}
                    else:
                        precision_info = {'amount': 8, 'price': 8, 'limits': {}}

                    # 캐시에 저장
                    if precision_info:
                        precision_cache_service.set_precision_info(
                            exchange_name, symbol, market_type, precision_info
                        )
                except Exception as e:
                    logger.warning(f"Precision 정보 조회 실패, 기본값 사용: {e}")
                    precision_info = {'amount': 8, 'price': 8, 'limits': {}}

            # 수량 정밀도 적용
            amount_precision = precision_info.get('amount', 8)
            if isinstance(amount_precision, int):
                decimal_places = amount_precision
            else:
                # float인 경우 (예: 0.001) 소수점 자리수 계산
                decimal_places = len(str(amount_precision).split('.')[-1]) if '.' in str(amount_precision) else 0

            precision_quantity = quantity.quantize(
                Decimal('0.1') ** decimal_places,
                rounding=ROUND_DOWN
            )

            # 가격 정밀도 적용
            processed_price = None
            processed_stop_price = None

            if price is not None:
                price_precision = precision_info.get('price', 8)
                if isinstance(price_precision, int):
                    price_decimal_places = price_precision
                else:
                    price_decimal_places = len(str(price_precision).split('.')[-1]) if '.' in str(price_precision) else 0

                processed_price = price.quantize(
                    Decimal('0.1') ** price_decimal_places,
                    rounding=ROUND_DOWN
                )

            if stop_price is not None:
                price_precision = precision_info.get('price', 8)
                if isinstance(price_precision, int):
                    price_decimal_places = price_precision
                else:
                    price_decimal_places = len(str(price_precision).split('.')[-1]) if '.' in str(price_precision) else 0

                processed_stop_price = stop_price.quantize(
                    Decimal('0.1') ** price_decimal_places,
                    rounding=ROUND_DOWN
                )

            # 최소 수량 검증
            limits = precision_info.get('limits', {})
            min_amount = limits.get('amount', {}).get('min', 0)
            if min_amount and precision_quantity < Decimal(str(min_amount)):
                return {
                    'success': False,
                    'error': f'최소 주문 수량({min_amount})보다 작습니다: {precision_quantity}',
                    'error_type': 'min_amount_error'
                }

            return {
                'success': True,
                'quantity': precision_quantity,
                'price': processed_price,
                'stop_price': processed_stop_price
            }

        except Exception as e:
            logger.error(f"정밀도 적용 실패: {e}")
            return {
                'success': False,
                'error': f'정밀도 적용 실패: {str(e)}',
                'error_type': 'precision_error'
            }

    def _execute_exchange_order(self,
                              exchange_instance: Any,
                              exchange_name: str,
                              symbol: str,
                              side: str,
                              quantity: Decimal,
                              order_type: str,
                              market_type: str,
                              price: Optional[Decimal],
                              stop_price: Optional[Decimal]) -> Dict[str, Any]:
        """거래소별 주문 실행"""
        try:
            # 마켓 타입에 따른 거래소 설정
            # Native 구현체는 초기화시 마켓 타입이 설정되므로 추가 설정 불필요

            # Native 파라미터 구성
            order_params = {
                'symbol': symbol,
                'side': side.upper(),
                'quantity': quantity,
                'type': order_type.upper()
            }

            # 가격 설정
            if order_type in ['LIMIT', 'STOP_LIMIT'] and price:
                order_params['price'] = price

            # 스탑 가격 설정
            if order_type in ['STOP_MARKET', 'STOP_LIMIT'] and stop_price:
                order_params['stopPrice'] = stop_price

            # 주문 실행
            logger.info(f"🔄 주문 실행 중 - {exchange_name}: {symbol} {side} {quantity} {order_type}")

            # Native 구현체 주문 실행
            order_result = exchange_instance.create_order(**order_params)

            # 결과 파싱
            return self._parse_order_result(order_result, exchange_name)

        except Exception as e:
            logger.error(f"거래소 주문 실행 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'exchange_error',
                'exchange': exchange_name
            }

    def _parse_order_result(self, order_result: Dict[str, Any], exchange_name: str) -> Dict[str, Any]:
        """주문 결과 파싱 및 표준화"""
        try:
            # 공통 필드 추출
            order_id = order_result.get('id', '')
            status = order_result.get('status', 'unknown').upper()
            filled_quantity = Decimal(str(order_result.get('filled', 0)))
            average_price = Decimal(str(order_result.get('average', 0))) if order_result.get('average') else None

            # 상태 표준화
            if status in ['CLOSED', 'FILLED']:
                final_status = 'FILLED'
            elif status in ['OPEN', 'NEW']:
                final_status = 'OPEN'
            elif status in ['CANCELED', 'CANCELLED']:
                final_status = 'CANCELED'
            else:
                final_status = status

            # 수수료 정보
            fee_info = order_result.get('fee', {})

            return {
                'success': True,
                'order_id': order_id,
                'status': final_status,
                'filled_quantity': filled_quantity,
                'average_price': average_price,
                'fee': fee_info,
                'raw_response': order_result,
                'exchange': exchange_name
            }

        except Exception as e:
            logger.error(f"주문 결과 파싱 실패: {e}")
            return {
                'success': False,
                'error': f'주문 결과 파싱 실패: {str(e)}',
                'error_type': 'parsing_error',
                'raw_response': order_result
            }


# 싱글톤 인스턴스
order_execution_service = OrderExecutionService()