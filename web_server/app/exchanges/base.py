"""
단순화된 거래소 기본 클래스

1인 사용자를 위한 최소한의 거래소 기본 클래스입니다.
복잡한 추상화와 캐싱 시스템을 제거하고 핵심 기능만 유지합니다.
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
    단순화된 거래소 기본 클래스

    특징:
    - 최소한의 추상화
    - 복잡한 캐싱 시스템 제거
    - 직관적이고 간단한 인터페이스
    - 1인 사용자 최적화
    """

    def __init__(self):
        self.api_key = None
        self.api_secret = None
        self.testnet = False

        logger.info(f"✅ {self.__class__.__name__} 기본 클래스 초기화")

    @abstractmethod
    async def load_markets(self, market_type: str = 'spot', reload: bool = False):
        """마켓 정보 로드"""
        pass

    @abstractmethod
    async def fetch_balance(self, market_type: str = 'spot'):
        """잔액 조회"""
        pass

    @abstractmethod
    async def create_order(self, symbol: str, order_type: str, side: str,
                          amount: Decimal, price: Optional[Decimal] = None,
                          market_type: str = 'spot', **params):
        """주문 생성"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str, market_type: str = 'spot'):
        """주문 취소"""
        pass

    @abstractmethod
    async def fetch_open_orders(self, symbol: Optional[str] = None, market_type: str = 'spot'):
        """미체결 주문 조회"""
        pass

    async def close(self):
        """리소스 정리 (필요시 하위 클래스에서 구현)"""
        pass