"""
Base Exchange Adapter

모든 거래소 어댑터의 기본 추상 클래스
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from app.exchanges.utils.http_client import AsyncHTTPClient
from app.exchanges.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class BaseExchangeAdapter(ABC):
    """
    거래소 어댑터 기본 인터페이스

    모든 거래소 어댑터는 이 클래스를 상속받아 구현합니다.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """
        Args:
            api_key: API Key
            api_secret: API Secret
            timeout: 요청 타임아웃 (초)
            max_retries: 최대 재시도 횟수
        """
        self.api_key = api_key
        self.api_secret = api_secret

        # HTTP 클라이언트
        self.http_client = AsyncHTTPClient(
            timeout=timeout,
            max_retries=max_retries
        )

        # Rate Limiter (서브클래스에서 초기화)
        self.rate_limiter: Optional[RateLimiter] = None

        # 거래소 이름 (서브클래스에서 설정)
        self.exchange_name: str = "unknown"

        logger.info(f"{self.exchange_name.upper()} adapter initialized")

    # === Phase 3: 필수 메서드 ===

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """
        주문 취소

        Args:
            symbol: 심볼 (예: "BTC/USDT")
            order_id: 주문 ID (거래소 order_id)

        Returns:
            정규화된 주문 정보

        Raises:
            OrderNotFoundException: 주문 없음
            ExchangeAPIError: API 에러
            ExchangeServerError: 서버 에러
        """
        pass

    @abstractmethod
    async def get_order(
        self,
        symbol: str,
        order_id: str
    ) -> Dict[str, Any]:
        """
        주문 조회

        Args:
            symbol: 심볼
            order_id: 주문 ID

        Returns:
            정규화된 주문 정보

        Raises:
            OrderNotFoundException: 주문 없음
            ExchangeAPIError: API 에러
        """
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        주문 생성

        Args:
            symbol: 심볼 (예: "BTC/USDT")
            side: 방향 ("buy" | "sell")
            order_type: 주문 타입 ("market" | "limit")
            quantity: 수량
            price: 가격 (limit 주문 시 필수)

        Returns:
            정규화된 주문 정보

        Raises:
            InsufficientBalanceError: 잔고 부족
            ExchangeAPIError: API 에러
        """
        pass

    @abstractmethod
    async def get_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        미체결 주문 조회

        Args:
            symbol: 심볼 (None이면 전체)

        Returns:
            정규화된 주문 목록

        Raises:
            ExchangeAPIError: API 에러
        """
        pass

    # === 인증 ===

    @abstractmethod
    def _sign_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        요청 서명

        거래소마다 서명 방식이 다르므로 서브클래스에서 구현

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            params: 파라미터

        Returns:
            서명된 파라미터 (또는 헤더)
        """
        pass

    # === 데이터 정규화 ===

    @abstractmethod
    def _normalize_symbol(self, symbol: str) -> str:
        """
        심볼을 거래소 형식으로 변환

        예:
        - Binance: "BTC/USDT" → "BTCUSDT"
        - Upbit: "BTC/KRW" → "KRW-BTC"

        Args:
            symbol: 표준 심볼 (slash 구분)

        Returns:
            거래소 형식 심볼
        """
        pass

    @abstractmethod
    def _normalize_order(self, raw_order: Dict[str, Any]) -> Dict[str, Any]:
        """
        거래소 주문 데이터를 공통 형식으로 변환

        공통 형식:
        {
            "exchange": str,           # 거래소 이름
            "order_id": str,           # 주문 ID
            "symbol": str,             # 심볼 (slash 구분)
            "side": str,               # "buy" | "sell"
            "type": str,               # "market" | "limit"
            "status": str,             # "OPEN" | "FILLED" | "CANCELLED" | "FAILED" | "EXPIRED"
            "quantity": float,         # 주문 수량
            "executed_quantity": float,# 체결 수량
            "price": float,            # 주문 가격
            "average_price": float,    # 평균 체결가
            "created_at": int          # 생성 시각 (timestamp ms)
        }

        Args:
            raw_order: 거래소 원본 주문 데이터

        Returns:
            정규화된 주문 데이터
        """
        pass

    @abstractmethod
    def _normalize_status(self, raw_status: str) -> str:
        """
        거래소 주문 상태를 공통 상태로 변환

        공통 상태:
        - OPEN: 미체결
        - FILLED: 체결 완료
        - CANCELLED: 취소됨
        - FAILED: 실패
        - EXPIRED: 만료

        Args:
            raw_status: 거래소 원본 상태

        Returns:
            공통 상태
        """
        pass

    # === 유틸리티 ===

    def _mask_api_key(self, api_key: str) -> str:
        """
        API Key 마스킹 (로깅용)

        Args:
            api_key: API Key

        Returns:
            마스킹된 API Key (앞 8자만 표시)
        """
        if len(api_key) <= 8:
            return "***"
        return f"{api_key[:8]}***"

    async def close(self) -> None:
        """클라이언트 종료"""
        await self.http_client.close()
        logger.info(f"{self.exchange_name.upper()} adapter closed")

    async def __aenter__(self):
        """Context manager 진입"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        await self.close()
