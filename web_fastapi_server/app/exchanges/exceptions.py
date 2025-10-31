"""
Exchange Exceptions

거래소 API 호출 시 발생할 수 있는 예외 정의
"""


class ExchangeException(Exception):
    """거래소 예외 기본 클래스"""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ExchangeAPIError(ExchangeException):
    """
    API 에러 (4xx)

    클라이언트 에러로 재시도 불필요
    - 400 Bad Request
    - 401 Unauthorized
    - 403 Forbidden
    - 404 Not Found
    - 429 Too Many Requests
    """

    def __init__(self, message: str, status_code: int = None, details: dict = None):
        self.status_code = status_code
        super().__init__(message, details)


class ExchangeServerError(ExchangeException):
    """
    서버 에러 (5xx)

    서버 측 에러로 재시도 가능
    - 500 Internal Server Error
    - 502 Bad Gateway
    - 503 Service Unavailable
    - 504 Gateway Timeout
    """

    def __init__(self, message: str, status_code: int = None, details: dict = None):
        self.status_code = status_code
        super().__init__(message, details)


class ExchangeNetworkError(ExchangeException):
    """
    네트워크 에러

    연결 실패, 타임아웃 등
    재시도 가능
    """

    pass


class ExchangeAuthError(ExchangeException):
    """
    인증 에러

    API Key/Secret 오류
    재시도 불필요
    """

    pass


class OrderNotFoundException(ExchangeException):
    """
    주문 없음

    조회한 주문이 존재하지 않음
    """

    def __init__(self, order_id: str, exchange: str = None):
        message = f"Order not found: {order_id}"
        if exchange:
            message = f"[{exchange}] {message}"
        super().__init__(message, {"order_id": order_id, "exchange": exchange})


class InsufficientBalanceError(ExchangeException):
    """
    잔고 부족

    주문 생성 시 잔고 부족
    """

    pass


class RateLimitExceededError(ExchangeException):
    """
    Rate Limit 초과

    너무 많은 요청
    재시도 필요 (지연 후)
    """

    def __init__(self, message: str, retry_after: int = None, details: dict = None):
        self.retry_after = retry_after  # 재시도 가능 시간 (초)
        super().__init__(message, details)
