"""
거래소 어댑터 팩토리 서비스
CCXT와 Enhanced Factory 통합 관리
"""

import logging
from typing import Dict, Any, Optional
from app.models import Account
from app.constants import Exchange

logger = logging.getLogger(__name__)


class ExchangeAdapterFactory:
    """거래소 어댑터 팩토리 - CCXT와 Enhanced Factory 통합"""

    def __init__(self):
        # Enhanced Factory 사용 가능 여부 확인
        self.enhanced_factory_available = False
        self.enhanced_factory = None
        self.should_use_custom_exchange = None

        try:
            from app.exchanges.enhanced_factory import enhanced_factory
            from app.exchanges.config import should_use_custom_exchange
            self.enhanced_factory = enhanced_factory
            self.should_use_custom_exchange = should_use_custom_exchange
            self.enhanced_factory_available = True
            logger.info("✅ Enhanced Factory 사용 가능")
        except ImportError as e:
            logger.warning(f"⚠️ Enhanced Factory 사용 불가 (레거시 모드): {e}")

        # 어댑터 캐시
        self._adapters = {}  # {account_id: adapter_instance}

    def get_adapter(self, account: Account, connection_service) -> Optional[Any]:
        """
        계정에 맞는 거래소 어댑터 반환
        Enhanced Factory 또는 CCXT 어댑터 자동 선택
        """
        try:
            account_id = account.id

            # 캐싱된 어댑터 확인
            if account_id in self._adapters:
                return self._adapters[account_id]

            # 어댑터 생성
            adapter = self._create_adapter(account, connection_service)
            if adapter:
                self._adapters[account_id] = adapter
                logger.info(f"✅ 거래소 어댑터 생성: {account.exchange} (account_id: {account_id})")

            return adapter

        except Exception as e:
            logger.error(f"❌ 거래소 어댑터 생성 실패: {e}")
            return None

    def _create_adapter(self, account: Account, connection_service) -> Optional[Any]:
        """거래소 어댑터 생성"""
        try:
            exchange_name = account.exchange.lower()

            # Enhanced Factory 사용 여부 결정
            use_enhanced = (
                self.enhanced_factory_available and
                self.should_use_custom_exchange and
                self.should_use_custom_exchange(exchange_name)
            )

            if use_enhanced:
                logger.info(f"🔧 Enhanced Factory 사용: {exchange_name}")
                return self._create_enhanced_adapter(account)
            else:
                logger.info(f"🔧 CCXT 사용: {exchange_name}")
                return self._create_ccxt_adapter(account, connection_service)

        except Exception as e:
            logger.error(f"거래소 어댑터 생성 중 오류: {e}")
            return None

    def _create_enhanced_adapter(self, account: Account) -> Optional[Any]:
        """Enhanced Factory 어댑터 생성"""
        try:
            if not self.enhanced_factory:
                return None

            adapter = self.enhanced_factory.create_exchange(
                account=account,
                cache_markets=True  # 마켓 정보 캐싱 활성화
            )

            if adapter:
                logger.info(f"✅ Enhanced Factory 어댑터 생성 완료: {account.exchange}")
                return EnhancedFactoryWrapper(adapter, account)
            else:
                logger.error(f"Enhanced Factory 어댑터 생성 실패: {account.exchange}")
                return None

        except Exception as e:
            logger.error(f"Enhanced Factory 어댑터 생성 중 오류: {e}")
            return None

    def _create_ccxt_adapter(self, account: Account, connection_service) -> Optional[Any]:
        """CCXT 어댑터 생성"""
        try:
            ccxt_instance = connection_service.get_exchange_instance(account)
            if ccxt_instance:
                return CCXTAdapter(ccxt_instance, account)
            else:
                return None

        except Exception as e:
            logger.error(f"CCXT 어댑터 생성 중 오류: {e}")
            return None

    def clear_adapter(self, account_id: int):
        """특정 계정의 어댑터 제거"""
        if account_id in self._adapters:
            del self._adapters[account_id]
            logger.info(f"거래소 어댑터 제거: account_id {account_id}")

    def clear_all_adapters(self):
        """모든 어댑터 제거"""
        self._adapters.clear()
        logger.info("모든 거래소 어댑터 제거 완료")

    def get_adapter_stats(self) -> Dict[str, Any]:
        """어댑터 통계"""
        enhanced_count = sum(1 for adapter in self._adapters.values()
                           if isinstance(adapter, EnhancedFactoryWrapper))
        ccxt_count = sum(1 for adapter in self._adapters.values()
                        if isinstance(adapter, CCXTAdapter))

        return {
            'total_adapters': len(self._adapters),
            'enhanced_factory_adapters': enhanced_count,
            'ccxt_adapters': ccxt_count,
            'enhanced_factory_available': self.enhanced_factory_available
        }


class EnhancedFactoryWrapper:
    """Enhanced Factory 어댑터 래퍼"""

    def __init__(self, enhanced_instance, account: Account):
        self.instance = enhanced_instance
        self.account = account
        self.adapter_type = 'enhanced_factory'

    def create_order(self, symbol: str, order_type: str, side: str, amount: float,
                    price: Optional[float] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """통합 주문 생성 인터페이스"""
        try:
            return self.instance.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
                params=params or {}
            )
        except Exception as e:
            logger.error(f"Enhanced Factory 주문 생성 실패: {e}")
            raise

    def fetch_balance(self) -> Dict[str, Any]:
        """잔고 조회"""
        return self.instance.fetch_balance()

    def load_markets(self) -> Dict[str, Any]:
        """마켓 정보 로드"""
        return self.instance.load_markets()

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 조회"""
        return self.instance.fetch_order(order_id, symbol)

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        return self.instance.cancel_order(order_id, symbol)


class CCXTAdapter:
    """CCXT 어댑터 래퍼"""

    def __init__(self, ccxt_instance, account: Account):
        self.instance = ccxt_instance
        self.account = account
        self.adapter_type = 'ccxt'

    def create_order(self, symbol: str, order_type: str, side: str, amount: float,
                    price: Optional[float] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """통합 주문 생성 인터페이스"""
        try:
            if order_type.lower() == 'market':
                if side.lower() == 'buy':
                    return self.instance.create_market_buy_order(symbol, amount)
                else:
                    return self.instance.create_market_sell_order(symbol, amount)
            elif order_type.lower() == 'limit':
                if not price:
                    raise ValueError("Limit order requires price")
                return self.instance.create_limit_order(symbol, side, amount, price)
            else:
                # 기타 주문 유형
                return self.instance.create_order(symbol, order_type, side, amount, price, params or {})

        except Exception as e:
            logger.error(f"CCXT 주문 생성 실패: {e}")
            raise

    def fetch_balance(self) -> Dict[str, Any]:
        """잔고 조회"""
        return self.instance.fetch_balance()

    def load_markets(self) -> Dict[str, Any]:
        """마켓 정보 로드"""
        return self.instance.load_markets()

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 조회"""
        return self.instance.fetch_order(order_id, symbol)

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """주문 취소"""
        return self.instance.cancel_order(order_id, symbol)


# 싱글톤 인스턴스
exchange_adapter_factory = ExchangeAdapterFactory()