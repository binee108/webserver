"""
새로운 통합 거래소 서비스
5개의 전문 서비스를 조율하는 Facade 패턴
"""

import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from app.models import Account
from app.constants import MarketType
from app.services.security_service import require_trading_permission
from app.utils.logging_security import get_secure_logger

# 분리된 서비스들 import
# exchange_connection_service 제거됨 - Enhanced Factory 사용
from app.services.precision_cache_service import precision_cache_service
from app.services.order_execution_service import order_execution_service
from app.services.rate_limit_service import rate_limit_service
from app.services.exchange_adapter_factory import exchange_adapter_factory

logger = get_secure_logger(__name__)


class NewExchangeService:
    """
    새로운 통합 거래소 서비스 (Facade 패턴)
    기존 ExchangeService의 모든 기능을 5개 전문 서비스로 분산하여 처리
    """

    def __init__(self):
        # Enhanced Factory만 사용
        logger.info("✅ 새로운 거래소 서비스 초기화 완료")

    # === 거래소 연결 관련 메서드 ===

    def get_exchange(self, account: Account) -> Optional[Any]:
        """Enhanced Factory 어댑터 반환"""
        try:
            # Enhanced Factory 사용
            adapter = exchange_adapter_factory.get_adapter(account)
            return adapter

        except Exception as e:
            logger.error(f"거래소 인스턴스 획득 실패: {e}")
            return None

    def test_connection(self, account: Account) -> bool:
        """거래소 연결 테스트"""
        try:
            exchange_instance = self.get_exchange(account)
            if not exchange_instance:
                return False

            # 잔고 조회로 연결 테스트
            balance = exchange_instance.fetch_balance()
            return balance is not None

        except Exception as e:
            logger.error(f"거래소 연결 테스트 실패: {e}")
            return False

    # === 주문 실행 관련 메서드 ===

    @require_trading_permission(account_param='account', symbol_param='symbol')
    def create_order(self,
                    account: Account,
                    symbol: str,
                    side: str,
                    quantity: Decimal,
                    order_type: str,
                    market_type: str = MarketType.SPOT,
                    price: Optional[Decimal] = None,
                    stop_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        주문 생성 (Rate limiting 포함)
        """
        try:
            # Rate limiting 체크
            wait_time = rate_limit_service.wait_if_needed(account.exchange)
            if wait_time > 0:
                logger.debug(f"⏳ Rate limit 대기 완료: {account.exchange} - {wait_time:.3f}초")

            # 주문 실행
            return order_execution_service.execute_order(
                account=account,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                market_type=market_type,
                price=price,
                stop_price=stop_price
            )

        except Exception as e:
            logger.error(f"주문 생성 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'order_creation_error'
            }

    def cancel_order(self, account: Account, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        try:
            # Rate limiting 체크
            rate_limit_service.wait_if_needed(account.exchange)

            exchange_instance = self.get_exchange(account)
            if not exchange_instance:
                return {
                    'success': False,
                    'error': '거래소 연결 실패',
                    'error_type': 'connection_error'
                }

            result = exchange_instance.cancel_order(order_id, symbol)
            return {
                'success': True,
                'result': result
            }

        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'cancel_error'
            }

    def fetch_order(self, account: Account, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 조회"""
        try:
            # Rate limiting 체크
            rate_limit_service.wait_if_needed(account.exchange)

            exchange_instance = self.get_exchange(account)
            if not exchange_instance:
                return {
                    'success': False,
                    'error': '거래소 연결 실패',
                    'error_type': 'connection_error'
                }

            result = exchange_instance.fetch_order(order_id, symbol)
            return {
                'success': True,
                'order': result
            }

        except Exception as e:
            logger.error(f"주문 조회 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'fetch_error'
            }

    # === Precision 관련 메서드 ===

    def get_precision_info(self, account: Account, symbol: str, market_type: str) -> Optional[Dict[str, Any]]:
        """Precision 정보 조회"""
        return precision_cache_service.get_precision_info(
            account.exchange, symbol, market_type
        )

    def warm_up_precision_cache(self):
        """Precision 캐시 웜업"""
        precision_cache_service.warm_up_cache(self)

    def get_precision_cache_stats(self) -> Dict[str, Any]:
        """Precision 캐시 통계"""
        return precision_cache_service.get_cache_stats()

    # === 잔고 관련 메서드 ===

    def fetch_balance(self, account: Account) -> Dict[str, Any]:
        """잔고 조회"""
        try:
            # Rate limiting 체크
            rate_limit_service.wait_if_needed(account.exchange)

            exchange_instance = self.get_exchange(account)
            if not exchange_instance:
                return {
                    'success': False,
                    'error': '거래소 연결 실패',
                    'error_type': 'connection_error'
                }

            balance = exchange_instance.fetch_balance()
            return {
                'success': True,
                'balance': balance
            }

        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': 'balance_error'
            }

    # === 통계 및 관리 메서드 ===

    def get_service_stats(self) -> Dict[str, Any]:
        """전체 서비스 통계"""
        return {
            'precision_cache_stats': precision_cache_service.get_cache_stats(),
            'rate_limit_stats': rate_limit_service.get_rate_limit_stats(),
            'adapter_stats': exchange_adapter_factory.get_adapter_stats()
        }

    def clear_all_caches(self):
        """모든 캐시 클리어"""
        precision_cache_service.clear_cache()
        rate_limit_service.clear_history()
        exchange_adapter_factory.clear_all_adapters()
        logger.info("🗑️ 모든 거래소 서비스 캐시 클리어 완료")

    def refresh_account(self, account: Account):
        """특정 계정 관련 캐시 새로고침"""
        exchange_adapter_factory.clear_adapter(account.id)
        rate_limit_service.clear_history(account.exchange)
        logger.info(f"🔄 계정 {account.id}({account.exchange}) 캐시 새로고침 완료")

    # === 기존 호환성 메서드 (점진적 마이그레이션용) ===

    def create_market_order(self, account: Account, symbol: str, side: str, quantity: Decimal) -> Dict[str, Any]:
        """마켓 주문 생성 (기존 호환성)"""
        return self.create_order(
            account=account,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type='MARKET'
        )

    def create_limit_order(self, account: Account, symbol: str, side: str,
                          quantity: Decimal, price: Decimal) -> Dict[str, Any]:
        """지정가 주문 생성 (기존 호환성)"""
        return self.create_order(
            account=account,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type='LIMIT',
            price=price
        )


# 기존 exchange_service와 호환성을 위한 인스턴스
# 점진적 마이그레이션을 위해 같은 이름 사용
new_exchange_service = NewExchangeService()