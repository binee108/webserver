"""
Mock Exchange Service

Phase 2/3 테스트용 가상 거래소 서비스
실제 거래소 API는 Phase 3에서 구현
"""

import logging
from typing import Optional
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class MockExchangeService:
    """
    Mock 거래소 서비스

    Phase 2/3에서 실제 거래소 없이 테스트하기 위한 Mock 서비스
    """

    def __init__(self, success_rate: float = 1.0, delay_ms: int = 100):
        """
        Args:
            success_rate: 성공 확률 (0.0 ~ 1.0), 테스트용
            delay_ms: API 호출 지연 시간 (밀리초)
        """
        self.success_rate = success_rate
        self.delay_ms = delay_ms
        logger.info(f"MockExchangeService initialized (success_rate={success_rate})")

    async def cancel_order(
        self,
        exchange: str,
        exchange_order_id: str,
        symbol: Optional[str] = None
    ) -> bool:
        """
        주문 취소 (Mock)

        Args:
            exchange: 거래소 이름 (binance, bybit, upbit 등)
            exchange_order_id: 거래소 주문 ID
            symbol: 심볼 (선택)

        Returns:
            성공 여부

        Raises:
            Exception: 취소 실패 시
        """
        # API 지연 시뮬레이션
        await asyncio.sleep(self.delay_ms / 1000.0)

        logger.info(
            f"[MOCK] Cancelling order on {exchange}: "
            f"exchange_order_id={exchange_order_id}, symbol={symbol}"
        )

        # 성공률에 따라 성공/실패 결정
        import random
        if random.random() > self.success_rate:
            error_msg = f"Mock cancellation failed for {exchange_order_id}"
            logger.warning(error_msg)
            raise Exception(error_msg)

        logger.info(f"[MOCK] ✅ Successfully cancelled {exchange_order_id}")
        return True

    async def get_order_status(
        self,
        exchange: str,
        exchange_order_id: str,
        symbol: Optional[str] = None
    ) -> str:
        """
        주문 상태 조회 (Mock)

        Args:
            exchange: 거래소 이름
            exchange_order_id: 거래소 주문 ID
            symbol: 심볼 (선택)

        Returns:
            주문 상태 (OPEN, FILLED, CANCELLED, EXPIRED)
        """
        # API 지연 시뮬레이션
        await asyncio.sleep(self.delay_ms / 1000.0)

        logger.info(
            f"[MOCK] Getting order status on {exchange}: "
            f"exchange_order_id={exchange_order_id}"
        )

        # Mock: 대부분 OPEN 상태 반환
        return "OPEN"

    async def place_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> dict:
        """
        주문 실행 (Mock)

        Phase 4/5에서 사용될 예정

        Returns:
            {
                "exchange_order_id": "mock_order_12345",
                "status": "OPEN",
                "filled_quantity": 0.0,
                "timestamp": "2025-10-31T..."
            }
        """
        await asyncio.sleep(self.delay_ms / 1000.0)

        logger.info(
            f"[MOCK] Placing {order_type} order on {exchange}: "
            f"{side} {quantity} {symbol} @ {price}"
        )

        import random
        mock_order_id = f"mock_{int(datetime.utcnow().timestamp() * 1000)}"

        if random.random() > self.success_rate:
            raise Exception(f"Mock order placement failed for {symbol}")

        return {
            "exchange_order_id": mock_order_id,
            "status": "OPEN",
            "filled_quantity": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
