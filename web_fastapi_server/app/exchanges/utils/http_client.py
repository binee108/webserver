"""
Async HTTP Client

httpx 기반 비동기 HTTP 클라이언트
자동 재시도 및 에러 처리 포함
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import httpx

from app.exchanges.exceptions import (
    ExchangeAPIError,
    ExchangeServerError,
    ExchangeNetworkError,
    RateLimitExceededError
)

logger = logging.getLogger(__name__)


class AsyncHTTPClient:
    """
    비동기 HTTP 클라이언트

    Features:
    - httpx.AsyncClient 래퍼
    - 자동 재시도 (exponential backoff)
    - 5xx 에러 재시도 (500, 502, 503, 504)
    - 429 Rate Limit 처리
    - 요청/응답 로깅
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        base_delay: float = 1.0
    ):
        """
        Args:
            timeout: 요청 타임아웃 (초)
            max_retries: 최대 재시도 횟수
            base_delay: 기본 재시도 지연 (초, exponential backoff 기준)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.client = httpx.AsyncClient(timeout=timeout)

        logger.debug(
            f"AsyncHTTPClient initialized: "
            f"timeout={timeout}s, max_retries={max_retries}"
        )

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[Any, Any]:
        """
        HTTP 요청 실행 (재시도 포함)

        Args:
            method: HTTP 메서드 (GET, POST, DELETE 등)
            url: 요청 URL
            headers: HTTP 헤더
            params: Query 파라미터
            json: JSON 바디
            data: Form 데이터

        Returns:
            응답 JSON

        Raises:
            ExchangeAPIError: 4xx 에러
            ExchangeServerError: 5xx 에러 (재시도 소진)
            ExchangeNetworkError: 네트워크 에러
            RateLimitExceededError: 429 Rate Limit
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                # 재시도 시 로깅
                if attempt > 0:
                    logger.info(
                        f"Retry attempt {attempt}/{self.max_retries - 1}: "
                        f"{method} {url}"
                    )

                # 요청 실행
                response = await self.client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data
                )

                # 로깅
                logger.debug(
                    f"{method} {url} -> {response.status_code} "
                    f"({len(response.content)} bytes)"
                )

                # 성공 (2xx)
                if 200 <= response.status_code < 300:
                    return response.json()

                # Rate Limit (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(
                        f"Rate limit exceeded: {url}, "
                        f"retry after {retry_after}s"
                    )

                    # 마지막 시도면 예외 발생
                    if attempt == self.max_retries - 1:
                        raise RateLimitExceededError(
                            message=f"Rate limit exceeded: {url}",
                            retry_after=retry_after,
                            details={
                                "url": url,
                                "status_code": 429,
                                "retry_after": retry_after
                            }
                        )

                    # 재시도 (Retry-After 시간만큼 대기)
                    await asyncio.sleep(retry_after)
                    continue

                # 클라이언트 에러 (4xx) - 재시도 불필요
                if 400 <= response.status_code < 500:
                    error_body = response.text[:500]  # 처음 500자만
                    logger.error(
                        f"API error {response.status_code}: {method} {url}\n"
                        f"Response: {error_body}"
                    )

                    raise ExchangeAPIError(
                        message=f"API error: {response.status_code}",
                        status_code=response.status_code,
                        details={
                            "url": url,
                            "method": method,
                            "status_code": response.status_code,
                            "response": error_body
                        }
                    )

                # 서버 에러 (5xx) - 재시도 가능
                # 사용자 요청: 500, 502, 503, 504 모두 재시도
                if 500 <= response.status_code < 600:
                    error_body = response.text[:500]
                    logger.warning(
                        f"Server error {response.status_code}: {method} {url}\n"
                        f"Response: {error_body}"
                    )

                    last_exception = ExchangeServerError(
                        message=f"Server error: {response.status_code}",
                        status_code=response.status_code,
                        details={
                            "url": url,
                            "method": method,
                            "status_code": response.status_code,
                            "response": error_body
                        }
                    )

                    # 마지막 시도면 예외 발생
                    if attempt == self.max_retries - 1:
                        logger.error(f"Max retries exceeded for {url}")
                        raise last_exception

                    # 재시도 (exponential backoff)
                    delay = self.base_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue

            except httpx.TimeoutException as e:
                logger.warning(f"Timeout: {method} {url}")

                last_exception = ExchangeNetworkError(
                    message=f"Request timeout: {url}",
                    details={
                        "url": url,
                        "method": method,
                        "error": str(e)
                    }
                )

                # 마지막 시도면 예외 발생
                if attempt == self.max_retries - 1:
                    raise last_exception

                # 재시도
                delay = self.base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                continue

            except httpx.RequestError as e:
                logger.warning(f"Network error: {method} {url} - {e}")

                last_exception = ExchangeNetworkError(
                    message=f"Network error: {url}",
                    details={
                        "url": url,
                        "method": method,
                        "error": str(e)
                    }
                )

                # 마지막 시도면 예외 발생
                if attempt == self.max_retries - 1:
                    raise last_exception

                # 재시도
                delay = self.base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                continue

        # 모든 재시도 소진 (도달하지 않아야 함)
        if last_exception:
            raise last_exception

        raise ExchangeNetworkError(
            message="Max retries exceeded",
            details={"url": url, "method": method}
        )

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[Any, Any]:
        """GET 요청"""
        return await self.request("GET", url, headers=headers, params=params)

    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[Any, Any]:
        """POST 요청"""
        return await self.request(
            "POST", url, headers=headers, params=params, json=json, data=data
        )

    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[Any, Any]:
        """DELETE 요청"""
        return await self.request("DELETE", url, headers=headers, params=params)

    async def close(self) -> None:
        """클라이언트 종료"""
        await self.client.aclose()
        logger.debug("AsyncHTTPClient closed")

    async def __aenter__(self):
        """Context manager 진입"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        await self.close()
