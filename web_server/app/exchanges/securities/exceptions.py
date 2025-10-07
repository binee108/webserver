"""
증권 거래소 예외 클래스

증권사 API 호출 시 발생할 수 있는 예외를 정의합니다.
"""

from typing import Dict, Optional


class SecuritiesError(Exception):
    """증권사 API 기본 에러"""
    def __init__(self, message: str, code: Optional[str] = None, response: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.response = response


class NetworkError(SecuritiesError):
    """네트워크 연결 에러"""
    pass


class AuthenticationError(SecuritiesError):
    """OAuth 인증 에러 (토큰 만료, 잘못된 인증 정보)"""
    pass


class TokenExpiredError(AuthenticationError):
    """OAuth 토큰 만료 에러"""
    pass


class InsufficientBalance(SecuritiesError):
    """주문 가능 잔액 부족 에러"""
    pass


class InvalidOrder(SecuritiesError):
    """잘못된 주문 파라미터 에러 (수량, 가격 등)"""
    pass


class OrderNotFound(SecuritiesError):
    """주문 조회 실패 (존재하지 않는 주문)"""
    pass


class MarketClosed(SecuritiesError):
    """장 마감 시간 주문 시도 에러"""
    pass
