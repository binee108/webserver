"""
어댑터 레이어
기존 서비스와 새로운 서비스 간의 호환성 제공
"""

import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from app.models import Account
from app.constants import MarketType
from app.services.interfaces import IExchangeService

logger = logging.getLogger(__name__)


class ExchangeServiceAdapter(IExchangeService):
    """
    기존 exchange_service와 새로운 new_exchange_service 간의 어댑터
    점진적 마이그레이션을 위한 Facade 패턴
    """

    def __init__(self, new_exchange_service=None, legacy_exchange_service=None):
        self.new_service = new_exchange_service
        self.legacy_service = legacy_exchange_service
        self.use_new_service = self._should_use_new_service()

        logger.info(f"ExchangeServiceAdapter 초기화: {'new_service' if self.use_new_service else 'legacy_service'} 사용")

    def _should_use_new_service(self) -> bool:
        """새로운 서비스 사용 여부 결정"""
        import os

        # 환경변수로 제어
        use_new = os.environ.get('USE_NEW_EXCHANGE_SERVICE', 'true').lower() == 'true'

        # 새로운 서비스가 없으면 레거시 사용
        if use_new and not self.new_service:
            logger.warning("새로운 거래소 서비스를 사용하도록 설정되었지만 인스턴스가 없습니다. 레거시 서비스를 사용합니다.")
            return False

        return use_new and self.new_service is not None

    def get_exchange(self, account: Account) -> Optional[Any]:
        """거래소 인스턴스 반환"""
        try:
            if self.use_new_service:
                return self.new_service.get_exchange(account)
            else:
                # 레거시 서비스 사용
                if self.legacy_service:
                    return self.legacy_service.get_exchange(account)
                else:
                    # 직접 import (폴백)
                    from app.services.exchange_service import exchange_service
                    return exchange_service.get_exchange(account)

        except Exception as e:
            logger.error(f"거래소 인스턴스 획득 실패 ({self._get_current_service_name()}): {e}")

            # 폴백 시도
            if self.use_new_service and self.legacy_service:
                logger.info("새 서비스 실패, 레거시 서비스로 폴백")
                try:
                    return self.legacy_service.get_exchange(account)
                except Exception as fallback_error:
                    logger.error(f"폴백도 실패: {fallback_error}")

            return None

    def create_order(self, account: Account, symbol: str, side: str,
                    quantity: Decimal, order_type: str,
                    market_type: str = MarketType.SPOT,
                    price: Optional[Decimal] = None,
                    stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """주문 생성"""
        try:
            if self.use_new_service:
                return self.new_service.create_order(
                    account=account,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    market_type=market_type,
                    price=price,
                    stop_price=stop_price
                )
            else:
                # 레거시 서비스 사용
                if self.legacy_service:
                    return self._create_order_legacy(self.legacy_service, account, symbol, side, quantity, order_type, market_type, price, stop_price)
                else:
                    # 직접 import (폴백)
                    from app.services.exchange_service import exchange_service
                    return self._create_order_legacy(exchange_service, account, symbol, side, quantity, order_type, market_type, price, stop_price)

        except Exception as e:
            logger.error(f"주문 생성 실패 ({self._get_current_service_name()}): {e}")

            # 폴백 시도
            if self.use_new_service and self.legacy_service:
                logger.info("새 서비스 실패, 레거시 서비스로 폴백")
                try:
                    return self._create_order_legacy(self.legacy_service, account, symbol, side, quantity, order_type, market_type, price, stop_price)
                except Exception as fallback_error:
                    logger.error(f"폴백도 실패: {fallback_error}")

            return {
                'success': False,
                'error': str(e),
                'error_type': 'adapter_error'
            }

    def _create_order_legacy(self, exchange_service, account: Account, symbol: str, side: str,
                           quantity: Decimal, order_type: str, market_type: str,
                           price: Optional[Decimal], stop_price: Optional[Decimal]) -> Dict[str, Any]:
        """레거시 서비스를 통한 주문 생성"""
        # 레거시 서비스의 메서드 시그니처에 맞게 변환
        if order_type.upper() == 'MARKET':
            if hasattr(exchange_service, 'create_market_order'):
                return exchange_service.create_market_order(account, symbol, side, quantity)
            else:
                # 일반적인 create_order 메서드 사용
                return self._call_legacy_create_order(exchange_service, account, symbol, side, quantity, order_type, market_type, price, stop_price)
        elif order_type.upper() == 'LIMIT':
            if price and hasattr(exchange_service, 'create_limit_order'):
                return exchange_service.create_limit_order(account, symbol, side, quantity, price)
            else:
                return self._call_legacy_create_order(exchange_service, account, symbol, side, quantity, order_type, market_type, price, stop_price)
        else:
            return self._call_legacy_create_order(exchange_service, account, symbol, side, quantity, order_type, market_type, price, stop_price)

    def _safe_decimal_to_float(self, decimal_value: Optional[Decimal], precision: int = 8) -> Optional[float]:
        """안전한 Decimal → float 변환"""
        if decimal_value is None:
            return None

        try:
            # 정밀도 검증
            str_value = str(decimal_value)
            if '.' in str_value:
                decimal_places = len(str_value.split('.')[1])
                if decimal_places > precision:
                    logger.warning(f"정밀도 손실 가능: {decimal_value} (소수점 {decimal_places}자리)")

            # 안전한 변환
            float_value = float(decimal_value)

            # 변환 검증
            converted_back = Decimal(str(float_value))
            precision_loss = abs(decimal_value - converted_back)

            if precision_loss > Decimal('0.00000001'):  # 허용 오차
                logger.error(f"심각한 정밀도 손실 감지: 원본={decimal_value}, 변환후={float_value}, 손실={precision_loss}")
                raise ValueError(f"정밀도 손실로 인한 변환 실패: {decimal_value}")

            return float_value

        except (ValueError, TypeError, OverflowError) as e:
            logger.error(f"Decimal → float 변환 실패: {decimal_value}, 오류: {e}")
            raise ValueError(f"수치 변환 실패: {decimal_value}")

    def _call_legacy_create_order(self, exchange_service, account: Account, symbol: str, side: str,
                                 quantity: Decimal, order_type: str, market_type: str,
                                 price: Optional[Decimal], stop_price: Optional[Decimal]) -> Dict[str, Any]:
        """레거시 create_order 메서드 호출 - 안전한 타입 변환"""
        if hasattr(exchange_service, 'create_order'):
            try:
                # 안전한 타입 변환
                safe_quantity = self._safe_decimal_to_float(quantity)
                safe_price = self._safe_decimal_to_float(price) if price else None
                safe_stop_price = self._safe_decimal_to_float(stop_price) if stop_price else None

                # 변환 로그
                logger.debug(f"타입 변환 완료 - 수량: {quantity}→{safe_quantity}, "
                            f"가격: {price}→{safe_price}, 스탑가격: {stop_price}→{safe_stop_price}")

                return exchange_service.create_order(
                    account=account,
                    symbol=symbol,
                    order_type=order_type,
                    side=side,
                    amount=safe_quantity,
                    price=safe_price,
                    stop_price=safe_stop_price,
                    market_type=market_type
                )
            except ValueError as e:
                logger.error(f"정밀도 보호로 인한 주문 실패: {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'error_type': 'precision_protection'
                }
        else:
            logger.error("레거시 exchange_service에 create_order 메서드가 없습니다")
            return {
                'success': False,
                'error': 'Legacy service method not found',
                'error_type': 'method_not_found'
            }

    def cancel_order(self, account: Account, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        try:
            if self.use_new_service:
                return self.new_service.cancel_order(account, order_id, symbol)
            else:
                # 레거시 서비스 사용
                if self.legacy_service and hasattr(self.legacy_service, 'cancel_order'):
                    return self.legacy_service.cancel_order(account, order_id, symbol)
                else:
                    # 직접 import (폴백)
                    from app.services.exchange_service import exchange_service
                    if hasattr(exchange_service, 'cancel_order'):
                        return exchange_service.cancel_order(account, order_id, symbol)
                    else:
                        return {
                            'success': False,
                            'error': 'Cancel order method not available',
                            'error_type': 'method_not_available'
                        }

        except Exception as e:
            logger.error(f"주문 취소 실패 ({self._get_current_service_name()}): {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'cancel_error'
            }

    def fetch_balance(self, account: Account) -> Dict[str, Any]:
        """잔고 조회"""
        try:
            if self.use_new_service:
                return self.new_service.fetch_balance(account)
            else:
                # 레거시 서비스 사용
                if self.legacy_service and hasattr(self.legacy_service, 'fetch_balance'):
                    return self.legacy_service.fetch_balance(account)
                else:
                    # 직접 import (폴백)
                    from app.services.exchange_service import exchange_service
                    if hasattr(exchange_service, 'fetch_balance'):
                        return exchange_service.fetch_balance(account)
                    else:
                        return {
                            'success': False,
                            'error': 'Fetch balance method not available',
                            'error_type': 'method_not_available'
                        }

        except Exception as e:
            logger.error(f"잔고 조회 실패 ({self._get_current_service_name()}): {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'balance_error'
            }

    def _get_current_service_name(self) -> str:
        """현재 사용 중인 서비스 이름 반환"""
        return 'new_service' if self.use_new_service else 'legacy_service'

    def switch_to_new_service(self, new_service):
        """새로운 서비스로 전환"""
        self.new_service = new_service
        self.use_new_service = True
        logger.info("새로운 거래소 서비스로 전환 완료")

    def switch_to_legacy_service(self):
        """레거시 서비스로 전환"""
        self.use_new_service = False
        logger.info("레거시 거래소 서비스로 전환 완료")

    def get_service_stats(self) -> Dict[str, Any]:
        """서비스 통계"""
        stats = {
            'current_service': self._get_current_service_name(),
            'new_service_available': self.new_service is not None,
            'legacy_service_available': self.legacy_service is not None,
            'fallback_enabled': True
        }

        # 새로운 서비스 통계
        if self.new_service and hasattr(self.new_service, 'get_service_stats'):
            try:
                stats['new_service_stats'] = self.new_service.get_service_stats()
            except Exception as e:
                stats['new_service_stats_error'] = str(e)

        return stats


def create_exchange_service_adapter(new_exchange_service=None, legacy_exchange_service=None):
    """ExchangeServiceAdapter 팩토리 함수"""
    return ExchangeServiceAdapter(new_exchange_service, legacy_exchange_service)