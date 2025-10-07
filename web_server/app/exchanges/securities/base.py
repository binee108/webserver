"""
증권 거래소 기본 추상 클래스

다수의 증권사를 지원하기 위한 공통 인터페이스를 제공합니다.
각 증권사 어댑터는 이 클래스를 상속하여 구현합니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime

from app.exchanges.securities.models import StockOrder, StockBalance, StockPosition, StockQuote
from app.exchanges.securities.exceptions import (
    SecuritiesError,
    NetworkError,
    AuthenticationError,
    TokenExpiredError,
    InsufficientBalance,
    InvalidOrder,
    OrderNotFound,
    MarketClosed
)

logger = logging.getLogger(__name__)


class BaseSecuritiesExchange(ABC):
    """
    증권 거래소 공통 인터페이스

    특징:
    - OAuth 2.0 토큰 기반 인증
    - 증권사 독립적인 데이터 모델 반환
    - 국내주식부터 시작, 추후 해외주식/선물옵션 확장

    구현 예시:
    - KoreaInvestmentExchange (한국투자증권)
    - KiwoomExchange (키움증권)
    - LSExchange (LS증권)
    """

    def __init__(self, account: 'Account'):
        """
        Args:
            account (Account): 증권 계좌 모델 (DB)
        """
        self.account = account
        self.name = self.__class__.__name__.replace('Exchange', '').lower()

        # 증권 설정 로드
        self.config = account.securities_config or {}

        # 토큰 캐시
        self._token_cache = None

        logger.info(f"✅ {self.__class__.__name__} 초기화 (account_id={account.id})")

    # ========================================
    # OAuth 인증 (필수 구현)
    # ========================================

    @abstractmethod
    async def authenticate(self) -> Dict[str, Any]:
        """
        OAuth 토큰 발급

        Returns:
            {
                'access_token': str,
                'token_type': str,  # 'Bearer'
                'expires_in': int,  # 초 단위 (86400 = 24시간)
                'expires_at': datetime
            }

        Raises:
            AuthenticationError: 인증 실패
        """
        pass

    @abstractmethod
    async def refresh_token(self) -> Dict[str, Any]:
        """
        OAuth 토큰 갱신

        Returns:
            authenticate()와 동일한 포맷

        Raises:
            AuthenticationError: 갱신 실패
        """
        pass

    async def ensure_token(self) -> str:
        """
        유효한 토큰 보장 (자동 갱신)

        Race Condition 방지:
        - SELECT ... FOR UPDATE로 DB 레벨 락 사용
        - 동시 요청 시 첫 번째만 토큰 발급, 나머지는 대기 후 재사용

        Returns:
            str: 유효한 access_token

        Raises:
            AuthenticationError: 토큰 발급/갱신 실패
        """
        from app.models import SecuritiesToken
        from app import db

        try:
            # DB에서 토큰 캐시 조회 (FOR UPDATE 락 적용)
            token_cache = (
                SecuritiesToken.query
                .filter_by(account_id=self.account.id)
                .with_for_update()
                .first()
            )

            if not token_cache or token_cache.is_expired():
                # 토큰이 없거나 만료됨 → 재발급
                logger.info(f"🔄 토큰 재발급 필요 (account_id={self.account.id})")

                try:
                    token_data = await self.authenticate()
                except Exception as e:
                    logger.error(f"❌ 토큰 발급 실패 (account_id={self.account.id}): {e}")
                    raise AuthenticationError(f"OAuth 토큰 발급 실패: {e}")

                if token_cache:
                    # 기존 토큰 업데이트
                    token_cache.access_token = token_data['access_token']
                    token_cache.expires_at = token_data['expires_at']
                    token_cache.last_refreshed_at = datetime.utcnow()
                else:
                    # 새 토큰 생성
                    token_cache = SecuritiesToken(
                        account_id=self.account.id,
                        access_token=token_data['access_token'],
                        token_type=token_data.get('token_type', 'Bearer'),
                        expires_in=token_data['expires_in'],
                        expires_at=token_data['expires_at']
                    )
                    db.session.add(token_cache)

                try:
                    db.session.commit()
                    logger.info(f"✅ 토큰 발급 완료 (만료: {token_data['expires_at']})")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"❌ 토큰 저장 실패 (account_id={self.account.id}): {e}")
                    raise AuthenticationError(f"토큰 DB 저장 실패: {e}")

            elif token_cache.needs_refresh():
                # 토큰이 곧 만료 → 갱신
                logger.info(f"🔄 토큰 갱신 (account_id={self.account.id})")

                try:
                    token_data = await self.refresh_token()
                except Exception as e:
                    logger.error(f"❌ 토큰 갱신 실패 (account_id={self.account.id}): {e}")
                    raise AuthenticationError(f"OAuth 토큰 갱신 실패: {e}")

                token_cache.access_token = token_data['access_token']
                token_cache.expires_at = token_data['expires_at']
                token_cache.last_refreshed_at = datetime.utcnow()

                try:
                    db.session.commit()
                    logger.info(f"✅ 토큰 갱신 완료 (만료: {token_data['expires_at']})")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"❌ 토큰 갱신 저장 실패 (account_id={self.account.id}): {e}")
                    raise AuthenticationError(f"토큰 갱신 저장 실패: {e}")

            return token_cache.access_token

        except AuthenticationError:
            # 이미 AuthenticationError면 그대로 전파
            raise
        except Exception as e:
            # 예상치 못한 에러
            db.session.rollback()
            logger.error(f"❌ 토큰 관리 중 예외 (account_id={self.account.id}): {e}")
            raise AuthenticationError(f"토큰 관리 중 예외 발생: {e}")

    # ========================================
    # 국내주식 주문 (필수 구현)
    # ========================================

    @abstractmethod
    async def create_stock_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: int,
        price: Optional[Decimal] = None,
        **params
    ) -> StockOrder:
        """
        국내주식 주문 생성

        Args:
            symbol: 종목코드 (예: '005930' 삼성전자)
            side: 'BUY' or 'SELL'
            order_type: 'LIMIT' or 'MARKET'
            quantity: 주문 수량 (정수)
            price: 지정가 (LIMIT 주문 시 필수)
            **params: 증권사별 추가 파라미터

        Returns:
            StockOrder: 증권사 독립적인 주문 모델

        Raises:
            InvalidOrder: 잘못된 주문 파라미터
            InsufficientBalance: 잔액 부족
            MarketClosed: 장 마감
        """
        pass

    @abstractmethod
    async def cancel_stock_order(self, order_id: str, symbol: str) -> bool:
        """
        국내주식 주문 취소

        Args:
            order_id: 주문번호 (증권사 원본 주문번호)
            symbol: 종목코드

        Returns:
            bool: 취소 성공 여부

        Raises:
            OrderNotFound: 주문을 찾을 수 없음
        """
        pass

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> StockOrder:
        """
        국내주식 주문 조회

        Args:
            order_id: 주문번호
            symbol: 종목코드

        Returns:
            StockOrder: 주문 상세 정보

        Raises:
            OrderNotFound: 주문을 찾을 수 없음
        """
        pass

    @abstractmethod
    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[StockOrder]:
        """
        미체결 주문 조회

        Args:
            symbol: 종목코드 (None이면 전체 조회)

        Returns:
            List[StockOrder]: 미체결 주문 목록
        """
        pass

    # ========================================
    # 잔고/포지션 조회 (필수 구현)
    # ========================================

    @abstractmethod
    async def fetch_balance(self, currency: str = 'KRW') -> StockBalance:
        """
        현금 잔고 조회

        Args:
            currency: 통화 ('KRW', 'USD', 'JPY' 등)

        Returns:
            StockBalance: 잔고 정보
        """
        pass

    @abstractmethod
    async def fetch_positions(self, symbol: Optional[str] = None) -> List[StockPosition]:
        """
        보유 종목 조회

        Args:
            symbol: 종목코드 (None이면 전체 조회)

        Returns:
            List[StockPosition]: 보유 종목 목록
        """
        pass

    # ========================================
    # 시세 조회 (필수 구현)
    # ========================================

    @abstractmethod
    async def fetch_quote(self, symbol: str) -> StockQuote:
        """
        현재가 조회

        Args:
            symbol: 종목코드

        Returns:
            StockQuote: 시세 정보
        """
        pass

    # ========================================
    # 선택적 메서드 (증권사별 특수 기능)
    # ========================================

    async def generate_hashkey(self, data: Dict[str, Any]) -> str:
        """
        해시키 생성 (한국투자증권 전용)

        다른 증권사는 이 메서드를 구현하지 않아도 됨 (빈 문자열 반환)

        Args:
            data: 주문 파라미터

        Returns:
            str: 해시키 (한투만 반환, 나머지는 빈 문자열)
        """
        return ""

    # ========================================
    # 편의 메서드
    # ========================================

    def get_market_type(self) -> str:
        """
        계좌의 마켓 타입 반환

        Returns:
            str: 'DOMESTIC_STOCK', 'OVERSEAS_STOCK', etc.
        """
        return self.config.get('market_type', 'DOMESTIC_STOCK')

    async def close(self):
        """리소스 정리 (필요시 하위 클래스에서 구현)"""
        pass
