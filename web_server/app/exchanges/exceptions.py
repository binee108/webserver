"""
거래소 공통 예외 클래스

Crypto와 Securities 모두 사용하는 기본 예외를 정의합니다.

@FEAT:framework @FEAT:exchange-integration @COMP:model @TYPE:boilerplate
"""


class ExchangeError(Exception):
    """거래소 API 기본 에러"""
    def __init__(self, message: str, code: int = None, response: dict = None):
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


class OrderNotFound(ExchangeError):
    """주문을 찾을 수 없음"""
    pass


class ExchangeRateUnavailableError(ExchangeError):
    """환율 조회 실패 - API 장애로 신뢰할 수 있는 환율을 얻을 수 없음"""
    pass
