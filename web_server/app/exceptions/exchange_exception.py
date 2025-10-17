"""거래소 관련 커스텀 예외 정의"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.exchanges.exceptions import ExchangeError as BaseExchangeError


class ExchangeError(BaseExchangeError):
    """거래소 API 오류를 표현하는 통합 예외"""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        exchange: Optional[str] = None,
        response: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message=message, code=error_code, response=response or {})
        self.error_code = error_code
        self.exchange = exchange
        self.response = response or {}


__all__ = ['ExchangeError']
