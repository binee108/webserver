"""
Rate Limiter

거래소 API Rate Limit 준수를 위한 비동기 Rate Limiter
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    비동기 Rate Limiter

    Token bucket 알고리즘 기반
    거래소별 API 요청 제한을 준수합니다.
    """

    def __init__(
        self,
        requests_per_second: float,
        burst_size: Optional[int] = None
    ):
        """
        Args:
            requests_per_second: 초당 허용 요청 수
            burst_size: 버스트 크기 (기본: requests_per_second)
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.burst_size = burst_size or int(requests_per_second)

        self.last_request_time: Optional[datetime] = None
        self.lock = asyncio.Lock()

        logger.debug(
            f"RateLimiter initialized: "
            f"{requests_per_second} req/s, "
            f"min_interval={self.min_interval:.3f}s"
        )

    async def acquire(self) -> None:
        """
        Rate limit 확인 후 통과

        필요 시 대기 후 통과
        """
        async with self.lock:
            now = datetime.utcnow()

            if self.last_request_time:
                elapsed = (now - self.last_request_time).total_seconds()

                if elapsed < self.min_interval:
                    wait_time = self.min_interval - elapsed
                    logger.debug(f"Rate limit: waiting {wait_time:.3f}s")
                    await asyncio.sleep(wait_time)

            self.last_request_time = datetime.utcnow()
            logger.debug("Rate limit: acquired")

    async def __aenter__(self):
        """Context manager 진입"""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        pass
