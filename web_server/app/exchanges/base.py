"""
크립토 거래소 기본 클래스

# @FEAT:exchange-integration @COMP:exchange @TYPE:core

암호화폐 거래소 통합을 위한 공통 인터페이스를 제공합니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


# 예외 클래스들
# @FEAT:exchange-integration @COMP:model @TYPE:core
class ExchangeError(Exception):
    """거래소 API 에러"""
    # @FEAT:exchange-integration @COMP:model @TYPE:core
    def __init__(self, message: str, code: int = None, response: Dict = None):
        super().__init__(message)
        self.code = code
        self.response = response


# @FEAT:exchange-integration @COMP:model @TYPE:core
class NetworkError(ExchangeError):
    """네트워크 에러"""
    pass


# @FEAT:exchange-integration @COMP:model @TYPE:core
class AuthenticationError(ExchangeError):
    """인증 에러"""
    pass


# @FEAT:exchange-integration @COMP:model @TYPE:core
class InsufficientFunds(ExchangeError):
    """잔액 부족 에러"""
    pass


# @FEAT:exchange-integration @COMP:model @TYPE:core
class InvalidOrder(ExchangeError):
    """잘못된 주문 에러"""
    pass


# @FEAT:exchange-integration @COMP:exchange @TYPE:core
class BaseExchange(ABC):
    """
    크립토 거래소 공통 인터페이스

    특징:
    - 메타데이터 기반 기능 검증
    - features 기반 선택적 메서드
    - 표준 응답 포맷 통일
    """

    # @FEAT:exchange-integration @COMP:exchange @TYPE:core
    def __init__(self):
        self.api_key = None
        self.api_secret = None
        self.testnet = False
        self.name = self.__class__.__name__.replace('Exchange', '').lower()

        # 메타데이터 로드
        from app.exchanges.metadata import ExchangeMetadata, ExchangeRegion
        self.metadata = ExchangeMetadata.get_metadata(self.name)

        if not self.metadata:
            logger.warning(f"Exchange metadata not found: {self.name}")
            self.region = ExchangeRegion.GLOBAL
            self.supported_markets = []
            self.features = {}
        else:
            self.region = self.metadata.get('region', ExchangeRegion.GLOBAL)
            self.supported_markets = self.metadata.get('supported_markets', [])
            self.features = self.metadata.get('features', {})

        logger.info(f"✅ {self.__class__.__name__} 초기화 (region={self.region})")

    # === 필수 메서드 (모든 거래소 구현 - 동기) ===

    @abstractmethod
    def load_markets(self, market_type: str = 'spot', reload: bool = False):
        """
        마켓 정보 로드 (동기 - 필수 구현)

        모든 거래소는 이 동기 메서드를 구현해야 합니다.
        """
        pass

    @abstractmethod
    def fetch_balance(self, market_type: str = 'spot'):
        """
        잔액 조회 (동기 - 필수 구현)

        Returns:
            {'free': float, 'used': float, 'total': float}
        """
        pass

    @abstractmethod
    def create_order(self, symbol: str, order_type: str, side: str,
                     amount: Decimal, price: Optional[Decimal] = None,
                     market_type: str = 'spot', **params):
        """
        주문 생성 (동기 - 필수 구현)

        Returns:
            {'order_id': str, 'status': str, 'filled_quantity': float, 'average_price': float}
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str, market_type: str = 'spot'):
        """주문 취소 (동기 - 필수 구현)"""
        pass

    @abstractmethod
    def fetch_open_orders(self, symbol: Optional[str] = None, market_type: str = 'spot'):
        """미체결 주문 조회 (동기 - 필수 구현)"""
        pass

    @abstractmethod
    def create_batch_orders(self, orders: List[Dict[str, Any]], market_type: str = 'spot') -> Dict[str, Any]:
        """
        배치 주문 생성 (동기 - 필수 구현)

        Args:
            orders: 주문 리스트
                [
                    {
                        'symbol': 'BTC/USDT',
                        'side': 'buy',
                        'type': 'LIMIT',
                        'amount': Decimal('0.01'),
                        'price': Decimal('95000'),
                        'params': {...}
                    },
                    ...
                ]
            market_type: 'spot' or 'futures'

        Returns:
            {
                'success': True,
                'results': [
                    {'order_index': 0, 'success': True, 'order_id': '...', 'order': {...}},
                    {'order_index': 1, 'success': False, 'error': '...'},
                    ...
                ],
                'summary': {
                    'total': 5,
                    'successful': 4,
                    'failed': 1
                },
                'implementation': 'NATIVE_BATCH' | 'SEQUENTIAL_FALLBACK'
            }

        Note:
            - 거래소가 배치 API를 지원하면 네이티브 배치 사용
            - 지원하지 않으면 내부적으로 순차 처리 (폴백)
            - 응답 포맷은 통일 (구현 차이 캡슐화)
            - 청크 분할 (5건 초과)은 각 거래소 구현에서 처리
        """
        pass

    # === 선택적 비동기 래퍼 (WebSocket 등에서 사용) ===

    async def load_markets_async(self, market_type: str = 'spot', reload: bool = False):
        """
        마켓 정보 로드 (비동기 래퍼 - 선택적)

        기본 구현: 동기 메서드를 호출
        거래소별로 필요시 재정의 가능
        """
        return self.load_markets(market_type, reload)

    async def fetch_balance_async(self, market_type: str = 'spot'):
        """
        잔액 조회 (비동기 래퍼 - 선택적)

        기본 구현: 동기 메서드를 호출
        거래소별로 필요시 재정의 가능
        """
        return self.fetch_balance(market_type)

    async def create_order_async(self, symbol: str, order_type: str, side: str,
                                  amount: Decimal, price: Optional[Decimal] = None,
                                  market_type: str = 'spot', **params):
        """
        주문 생성 (비동기 래퍼 - 선택적)

        기본 구현: 동기 메서드를 호출
        거래소별로 필요시 재정의 가능
        """
        return self.create_order(symbol, order_type, side, amount, price, market_type, **params)

    async def cancel_order_async(self, order_id: str, symbol: str, market_type: str = 'spot'):
        """
        주문 취소 (비동기 래퍼 - 선택적)

        기본 구현: 동기 메서드를 호출
        거래소별로 필요시 재정의 가능
        """
        return self.cancel_order(order_id, symbol, market_type)

    async def fetch_open_orders_async(self, symbol: Optional[str] = None, market_type: str = 'spot'):
        """
        미체결 주문 조회 (비동기 래퍼 - 선택적)

        기본 구현: 동기 메서드를 호출
        거래소별로 필요시 재정의 가능
        """
        return self.fetch_open_orders(symbol, market_type)

    async def create_batch_orders_async(self, orders: List[Dict[str, Any]], market_type: str = 'spot') -> Dict[str, Any]:
        """
        배치 주문 생성 (비동기 래퍼 - 선택적)

        기본 구현: 동기 메서드를 호출
        거래소별로 필요시 재정의 가능
        """
        return self.create_batch_orders(orders, market_type)

    # === 공통 편의 메서드 ===

    # @FEAT:exchange-integration @COMP:exchange @TYPE:helper
    def is_domestic(self) -> bool:
        """국내 거래소 여부"""
        from app.exchanges.metadata import ExchangeRegion
        return self.region == ExchangeRegion.DOMESTIC

    # @FEAT:exchange-integration @COMP:exchange @TYPE:helper
    def supports_market(self, market_type: str) -> bool:
        """특정 마켓 타입 지원 여부"""
        from app.exchanges.metadata import MarketType
        # 문자열을 MarketType Enum으로 변환
        try:
            mt = MarketType(market_type.lower())
            return mt in self.supported_markets
        except ValueError:
            return False

    # @FEAT:exchange-integration @COMP:exchange @TYPE:helper
    def supports_feature(self, feature: str) -> bool:
        """특정 기능 지원 여부"""
        return self.features.get(feature, False)

    # @FEAT:exchange-integration @COMP:exchange @TYPE:helper
    def get_base_currency(self) -> str:
        """기본 기준 통화"""
        currencies = self.metadata.get('base_currency', [])
        return currencies[0] if currencies else 'USDT'

    # === 선택적 메서드 (Futures/Perpetual 지원 거래소만 구현 - 동기) ===

    def set_leverage(self, symbol: str, leverage: int, **params) -> Dict:
        """레버리지 설정 (동기 - 선택적)"""
        if not self.supports_feature('leverage'):
            raise NotImplementedError(f"{self.name} does not support leverage")
        raise NotImplementedError("set_leverage not implemented")

    def set_position_mode(self, dual_side: bool, **params) -> Dict:
        """포지션 모드 설정 (단방향/양방향) (동기 - 선택적)"""
        if not self.supports_feature('position_mode'):
            raise NotImplementedError(f"{self.name} does not support position mode")
        raise NotImplementedError("set_position_mode not implemented")

    def fetch_positions(self, symbol: Optional[str] = None, **params) -> List[Dict]:
        """포지션 조회 (선물/마진) (동기 - 선택적)"""
        from app.exchanges.metadata import MarketType
        if not (self.supports_market('futures') or self.supports_market('perpetual')):
            raise NotImplementedError(f"{self.name} does not support futures/perpetual")
        raise NotImplementedError("fetch_positions not implemented")

    def fetch_funding_rate(self, symbol: str) -> Dict:
        """펀딩비 조회 (무기한 선물) (동기 - 선택적)"""
        if not self.supports_feature('funding_rate'):
            raise NotImplementedError(f"{self.name} does not support funding rate")
        raise NotImplementedError("fetch_funding_rate not implemented")

    def get_balance(self, currency: str = 'USDT', market_type: str = 'spot') -> float:
        """사용 가능 잔액 조회 (편의 메서드) (동기 - 선택적)"""
        balance = self.fetch_balance(market_type)
        return balance.get('free', 0)

    def close(self):
        """리소스 정리 (필요시 하위 클래스에서 구현) (동기 - 선택적)"""
        pass

    # === 선택적 메서드 비동기 래퍼 ===

    async def set_leverage_async(self, symbol: str, leverage: int, **params) -> Dict:
        """레버리지 설정 (비동기 래퍼 - 선택적)"""
        return self.set_leverage(symbol, leverage, **params)

    async def set_position_mode_async(self, dual_side: bool, **params) -> Dict:
        """포지션 모드 설정 (비동기 래퍼 - 선택적)"""
        return self.set_position_mode(dual_side, **params)

    async def fetch_positions_async(self, symbol: Optional[str] = None, **params) -> List[Dict]:
        """포지션 조회 (비동기 래퍼 - 선택적)"""
        return self.fetch_positions(symbol, **params)

    async def fetch_funding_rate_async(self, symbol: str) -> Dict:
        """펀딩비 조회 (비동기 래퍼 - 선택적)"""
        return self.fetch_funding_rate(symbol)

    async def get_balance_async(self, currency: str = 'USDT', market_type: str = 'spot') -> float:
        """사용 가능 잔액 조회 (비동기 래퍼 - 선택적)"""
        return self.get_balance(currency, market_type)

    async def close_async(self):
        """리소스 정리 (비동기 래퍼 - 선택적)"""
        return self.close()
