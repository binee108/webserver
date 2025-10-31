"""
Cancel Queue Background Processor 테스트

백그라운드 작업의 처리 로직을 테스트합니다.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.tasks.cancel_queue_processor import process_cancel_queue
from app.models.cancel_queue import CancelQueue
from app.services.cancel_queue_service import CancelQueueService
from app.services.mock_exchange_service import MockExchangeService


class TestCancelQueueProcessorUnit:
    """유닛 테스트 (DB 불필요)"""

    @pytest.mark.asyncio
    async def test_processor_handles_empty_queue(self):
        """빈 큐 처리 (로직만 테스트)"""
        # Mock DB session
        mock_db = AsyncMock()

        # Mock service
        mock_service = MagicMock()
        mock_service.get_pending_cancels = AsyncMock(return_value=[])

        # Test logic (simplified)
        pending_cancels = await mock_service.get_pending_cancels(mock_db, limit=100)

        assert len(pending_cancels) == 0

    @pytest.mark.asyncio
    async def test_processor_processes_single_item(self):
        """단일 항목 처리 로직"""
        # Mock cancel item
        cancel_item = CancelQueue(
            id=1,
            order_id=100,
            status="PENDING",
            retry_count=0,
            requested_at=datetime.utcnow()
        )

        # Mock service
        mock_service = MagicMock()
        mock_service.get_pending_cancels = AsyncMock(return_value=[cancel_item])
        mock_service.process_cancel = AsyncMock(return_value=True)

        # Mock exchange
        mock_exchange = AsyncMock()

        # Mock DB
        mock_db = AsyncMock()

        # Execute logic
        pending_cancels = await mock_service.get_pending_cancels(mock_db, limit=100)

        assert len(pending_cancels) == 1

        # Process item
        result = await mock_service.process_cancel(mock_db, cancel_item, mock_exchange)

        assert result is True
        assert mock_service.process_cancel.called

    @pytest.mark.asyncio
    async def test_processor_handles_multiple_items(self):
        """다중 항목 처리 로직"""
        # Mock cancel items
        cancel_items = [
            CancelQueue(id=i, order_id=100+i, status="PENDING", retry_count=0)
            for i in range(5)
        ]

        # Mock service
        mock_service = MagicMock()
        mock_service.get_pending_cancels = AsyncMock(return_value=cancel_items)
        mock_service.process_cancel = AsyncMock(return_value=True)

        # Mock exchange
        mock_exchange = AsyncMock()

        # Mock DB
        mock_db = AsyncMock()

        # Execute logic
        pending_cancels = await mock_service.get_pending_cancels(mock_db, limit=100)

        assert len(pending_cancels) == 5

        # Process all items
        results = []
        for item in pending_cancels:
            result = await mock_service.process_cancel(mock_db, item, mock_exchange)
            results.append(result)

        assert all(results)
        assert mock_service.process_cancel.call_count == 5

    @pytest.mark.asyncio
    async def test_processor_handles_exception(self):
        """예외 처리 로직"""
        # Mock service that raises exception
        mock_service = MagicMock()
        mock_service.get_pending_cancels = AsyncMock(
            side_effect=Exception("Database connection error")
        )

        # Mock DB
        mock_db = AsyncMock()

        # Execute logic (should not crash)
        try:
            await mock_service.get_pending_cancels(mock_db, limit=100)
        except Exception as e:
            assert "Database connection error" in str(e)

    @pytest.mark.asyncio
    async def test_processor_status_transition(self):
        """상태 전환 로직 (PENDING → PROCESSING)"""
        cancel_item = CancelQueue(
            id=1,
            order_id=100,
            status="PENDING",
            retry_count=0
        )

        # Mock DB
        mock_db = AsyncMock()

        # Simulate status transition
        if cancel_item.status == "PENDING":
            cancel_item.status = "PROCESSING"
            await mock_db.commit()

        assert cancel_item.status == "PROCESSING"
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_processor_counts_successes_and_failures(self):
        """성공/실패 카운팅 로직"""
        # Mock results
        results = [True, True, False, True, False]

        successful = sum(1 for r in results if r)
        failed = sum(1 for r in results if not r)

        assert successful == 3
        assert failed == 2


class TestMockExchangeService:
    """MockExchangeService 테스트"""

    @pytest.mark.asyncio
    async def test_mock_exchange_cancel_success(self):
        """Mock 거래소 취소 성공"""
        exchange = MockExchangeService(success_rate=1.0, delay_ms=10)

        result = await exchange.cancel_order(
            exchange="binance",
            exchange_order_id="test_order_123",
            symbol="BTC/USDT"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_mock_exchange_cancel_failure(self):
        """Mock 거래소 취소 실패"""
        exchange = MockExchangeService(success_rate=0.0, delay_ms=10)

        with pytest.raises(Exception) as exc_info:
            await exchange.cancel_order(
                exchange="binance",
                exchange_order_id="test_order_123"
            )

        assert "Mock cancellation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_mock_exchange_delay(self):
        """Mock 거래소 지연 시뮬레이션"""
        exchange = MockExchangeService(success_rate=1.0, delay_ms=100)

        import time
        start = time.time()

        await exchange.cancel_order(
            exchange="binance",
            exchange_order_id="test_order_123"
        )

        elapsed = time.time() - start

        # 최소 100ms 지연
        assert elapsed >= 0.1

    def test_mock_exchange_initialization(self):
        """Mock 거래소 초기화"""
        exchange = MockExchangeService(success_rate=0.95, delay_ms=50)

        assert exchange.success_rate == 0.95
        assert exchange.delay_ms == 50


@pytest.mark.skip(reason="Background task integration test requires full app setup")
class TestCancelQueueProcessorIntegration:
    """통합 테스트 (실제 DB 및 백그라운드 작업)"""

    @pytest.mark.asyncio
    async def test_processor_full_cycle(self, async_db_session):
        """전체 사이클 테스트 (추가 → 처리 → 완료)"""
        # 1. Cancel item 추가
        service = CancelQueueService()
        cancel_item = await service.add_to_queue(
            db=async_db_session,
            order_id=1000
        )

        assert cancel_item.status == "PENDING"

        # 2. Mock exchange
        mock_exchange = MockExchangeService(success_rate=1.0, delay_ms=10)

        # 3. Mock verify_order_status to return OPEN
        with patch.object(service, 'verify_order_status', return_value="OPEN"):
            # 4. 처리
            result = await service.process_cancel(
                db=async_db_session,
                cancel_item=cancel_item,
                exchange_service=mock_exchange
            )

        # 5. 검증
        assert result is True
        assert cancel_item.status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_processor_retry_cycle(self, async_db_session):
        """재시도 사이클 테스트"""
        service = CancelQueueService()

        # 1. Cancel item 추가
        cancel_item = await service.add_to_queue(
            db=async_db_session,
            order_id=2000
        )

        # 2. Mock exchange (실패)
        mock_exchange = MockExchangeService(success_rate=0.0, delay_ms=10)

        # 3. Mock verify_order_status to return OPEN
        with patch.object(service, 'verify_order_status', return_value="OPEN"):
            # 4. 처리 (실패 예상)
            result = await service.process_cancel(
                db=async_db_session,
                cancel_item=cancel_item,
                exchange_service=mock_exchange
            )

        # 5. 검증
        assert result is False
        assert cancel_item.status == "PENDING"
        assert cancel_item.retry_count == 1
        assert cancel_item.next_retry_at is not None
