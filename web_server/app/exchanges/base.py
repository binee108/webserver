"""
크립토 거래소 기본 클래스

암호화폐 거래소 통합을 위한 공통 인터페이스를 제공합니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


# 예외 클래스들
class ExchangeError(Exception):
    """거래소 API 에러"""
    def __init__(self, message: str, code: int = None, response: Dict = None):
        super().__init__(message)
        self.code = code
        self.response = response


class NetworkError(ExchangeError):
    """네트워크 에러"""
    pass


class AuthenticationError(ExchangeError):
    """인증 에러"""
    pass


class InsufficientFunds(ExchangeError):
    """잔액 부족 에러"""
    pass


class InvalidOrder(ExchangeError):
    """잘못된 주문 에러"""
    pass


class BaseExchange(ABC):
    """
    크립토 거래소 공통 인터페이스

    특징:
    - 메타데이터 기반 기능 검증
    - features 기반 선택적 메서드
    - 표준 응답 포맷 통일
    """

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

    # === 필수 메서드 (모든 거래소 구현) ===

    @abstractmethod
    async def load_markets(self, market_type: str = 'spot', reload: bool = False):
        """마켓 정보 로드"""
        pass

    @abstractmethod
    async def fetch_balance(self, market_type: str = 'spot'):
        """
        잔액 조회

        Returns:
            {'free': float, 'used': float, 'total': float}
        """
        pass

    @abstractmethod
    async def create_order(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params):
        """
        주문 생성

        Returns:
            {'order_id': str, 'status': str, 'filled_quantity': float, 'average_price': float}
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str, market_type: str = 'spot'):
        """주문 취소"""
        pass

    @abstractmethod
    async def fetch_open_orders(self, symbol: Optional[str] = None, market_type: str = 'spot'):
        """미체결 주문 조회"""
        pass

    # === 공통 편의 메서드 ===

    def is_domestic(self) -> bool:
        """국내 거래소 여부"""
        from app.exchanges.metadata import ExchangeRegion
        return self.region == ExchangeRegion.DOMESTIC

    def supports_market(self, market_type: str) -> bool:
        """특정 마켓 타입 지원 여부"""
        from app.exchanges.metadata import MarketType
        # 문자열을 MarketType Enum으로 변환
        try:
            mt = MarketType(market_type.lower())
            return mt in self.supported_markets
        except ValueError:
            return False

    def supports_feature(self, feature: str) -> bool:
        """특정 기능 지원 여부"""
        return self.features.get(feature, False)

    def get_base_currency(self) -> str:
        """기본 기준 통화"""
        currencies = self.metadata.get('base_currency', [])
        return currencies[0] if currencies else 'USDT'

    # === 선택적 메서드 (Futures/Perpetual 지원 거래소만 구현) ===

    async def set_leverage(self, symbol: str, leverage: int, **params) -> Dict:
        """레버리지 설정"""
        if not self.supports_feature('leverage'):
            raise NotImplementedError(f"{self.name} does not support leverage")
        raise NotImplementedError("set_leverage not implemented")

    async def set_position_mode(self, dual_side: bool, **params) -> Dict:
        """포지션 모드 설정 (단방향/양방향)"""
        if not self.supports_feature('position_mode'):
            raise NotImplementedError(f"{self.name} does not support position mode")
        raise NotImplementedError("set_position_mode not implemented")

    async def fetch_positions(self, symbol: Optional[str] = None, **params) -> List[Dict]:
        """포지션 조회 (선물/마진)"""
        from app.exchanges.metadata import MarketType
        if not (self.supports_market('futures') or self.supports_market('perpetual')):
            raise NotImplementedError(f"{self.name} does not support futures/perpetual")
        raise NotImplementedError("fetch_positions not implemented")

    async def fetch_funding_rate(self, symbol: str) -> Dict:
        """펀딩비 조회 (무기한 선물)"""
        if not self.supports_feature('funding_rate'):
            raise NotImplementedError(f"{self.name} does not support funding rate")
        raise NotImplementedError("fetch_funding_rate not implemented")

    async def get_balance(self, currency: str = 'USDT', market_type: str = 'spot') -> float:
        """사용 가능 잔액 조회 (편의 메서드)"""
        balance = await self.fetch_balance(market_type)
        return balance.get('free', 0)

    async def close(self):
        """리소스 정리 (필요시 하위 클래스에서 구현)"""
        pass