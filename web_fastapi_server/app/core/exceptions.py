"""
커스텀 예외 클래스

애플리케이션 전반에서 사용하는 예외들을 정의합니다.
"""

from typing import Any, Dict, Optional


class AppException(Exception):
    """애플리케이션 기본 예외"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseException(AppException):
    """데이터베이스 관련 예외"""

    def __init__(self, message: str = "Database error occurred", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class ValidationException(AppException):
    """검증 실패 예외"""

    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class AuthenticationException(AppException):
    """인증 실패 예외"""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=401, details=details)


class AuthorizationException(AppException):
    """권한 부족 예외"""

    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=403, details=details)


class NotFoundException(AppException):
    """리소스 없음 예외"""

    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=404, details=details)


class ExchangeException(AppException):
    """거래소 API 관련 예외"""

    def __init__(self, message: str = "Exchange API error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=502, details=details)


class OrderException(AppException):
    """주문 처리 관련 예외"""

    def __init__(self, message: str = "Order processing error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)
