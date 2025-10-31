"""
Cancel Queue Service 테스트

CancelQueueService의 모든 메서드를 테스트합니다.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.services.cancel_queue_service import CancelQueueService
from app.models.cancel_queue import CancelQueue
from app.core.exceptions import ValidationException, DatabaseException


@pytest.mark.skip(reason="Requires actual database connection")
class TestCancelQueueServiceIntegration:
    """실제 DB 연결이 필요한 통합 테스트"""

    @pytest_asyncio.fixture
    async def service(self):
        """CancelQueueService 인스턴스"""
        return CancelQueueService()

    @pytest.mark.asyncio
    async def test_add_to_queue_success(self, async_db_session, service):
        """취소 요청 추가 성공"""
        order_id = 1
        strategy_id = 100
        account_id = 10

        result = await service.add_to_queue(
            db=async_db_session,
            order_id=order_id,
            strategy_id=strategy_id,
            account_id=account_id
        )

        assert result.order_id == order_id
        assert result.strategy_id == strategy_id
        assert result.account_id == account_id
        assert result.status == "PENDING"
        assert result.retry_count == 0
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_add_to_queue_duplicate(self, async_db_session, service):
        """중복 취소 요청 방지"""
        order_id = 2

        # 첫 번째 추가
        await service.add_to_queue(db=async_db_session, order_id=order_id)

        # 두 번째 추가 시도 (중복)
        with pytest.raises(ValidationException) as exc_info:
            await service.add_to_queue(db=async_db_session, order_id=order_id)

        assert "already in cancel queue" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_get_pending_cancels_empty(self, async_db_session, service):
        """처리 대기 항목이 없을 때"""
        result = await service.get_pending_cancels(db=async_db_session, limit=100)

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_pending_cancels_with_items(self, async_db_session, service):
        """처리 대기 항목이 있을 때"""
        # 3개의 취소 요청 추가
        for i in range(3):
            await service.add_to_queue(db=async_db_session, order_id=100 + i)

        result = await service.get_pending_cancels(db=async_db_session, limit=100)

        assert len(result) == 3
        assert all(item.status == "PENDING" for item in result)

    @pytest.mark.asyncio
    async def test_get_pending_cancels_respects_retry_time(self, async_db_session, service):
        """next_retry_at이 미래인 항목은 제외"""
        # 즉시 처리 가능한 항목
        cancel1 = await service.add_to_queue(db=async_db_session, order_id=200)

        # 미래 재시도 항목
        cancel2 = await service.add_to_queue(db=async_db_session, order_id=201)
        cancel2.next_retry_at = datetime.utcnow() + timedelta(hours=1)
        async_db_session.add(cancel2)
        await async_db_session.commit()

        result = await service.get_pending_cancels(db=async_db_session, limit=100)

        assert len(result) == 1
        assert result[0].order_id == 200

    @pytest.mark.asyncio
    async def test_process_cancel_order_open(self, async_db_session, service):
        """OPEN 상태 주문 취소 처리"""
        # Mock exchange service
        mock_exchange = AsyncMock()
        mock_exchange.cancel_order = AsyncMock(return_value=True)

        # Cancel item 추가
        cancel_item = await service.add_to_queue(db=async_db_session, order_id=300)

        # Mock verify_order_status to return OPEN
        service.verify_order_status = AsyncMock(return_value="OPEN")

        # 처리
        result = await service.process_cancel(
            db=async_db_session,
            cancel_item=cancel_item,
            exchange_service=mock_exchange
        )

        assert result is True
        assert cancel_item.status == "SUCCESS"
        assert mock_exchange.cancel_order.called

    @pytest.mark.asyncio
    async def test_process_cancel_order_pending(self, async_db_session, service):
        """PENDING 상태 주문은 재시도"""
        mock_exchange = AsyncMock()
        cancel_item = await service.add_to_queue(db=async_db_session, order_id=400)

        # Mock verify_order_status to return PENDING
        service.verify_order_status = AsyncMock(return_value="PENDING")

        initial_retry_count = cancel_item.retry_count

        # 처리
        result = await service.process_cancel(
            db=async_db_session,
            cancel_item=cancel_item,
            exchange_service=mock_exchange
        )

        assert result is False
        assert cancel_item.status == "PENDING"
        assert cancel_item.retry_count == initial_retry_count + 1
        assert cancel_item.next_retry_at is not None

    @pytest.mark.asyncio
    async def test_process_cancel_order_filled(self, async_db_session, service):
        """FILLED 상태 주문은 취소 불필요"""
        mock_exchange = AsyncMock()
        cancel_item = await service.add_to_queue(db=async_db_session, order_id=500)

        # Mock verify_order_status to return FILLED
        service.verify_order_status = AsyncMock(return_value="FILLED")

        # 처리
        result = await service.process_cancel(
            db=async_db_session,
            cancel_item=cancel_item,
            exchange_service=mock_exchange
        )

        assert result is True
        assert cancel_item.status == "SUCCESS"
        assert not mock_exchange.cancel_order.called  # 거래소 호출 없음

    @pytest.mark.asyncio
    async def test_process_cancel_exchange_failure(self, async_db_session, service):
        """거래소 취소 실패 시 재시도"""
        # Mock exchange service that fails
        mock_exchange = AsyncMock()
        mock_exchange.cancel_order = AsyncMock(side_effect=Exception("Exchange API error"))

        cancel_item = await service.add_to_queue(db=async_db_session, order_id=600)

        # Mock verify_order_status to return OPEN
        service.verify_order_status = AsyncMock(return_value="OPEN")

        # 처리
        result = await service.process_cancel(
            db=async_db_session,
            cancel_item=cancel_item,
            exchange_service=mock_exchange
        )

        assert result is False
        assert cancel_item.status == "PENDING"
        assert cancel_item.retry_count == 1

    @pytest.mark.asyncio
    async def test_process_cancel_max_retries_exceeded(self, async_db_session, service):
        """최대 재시도 초과 시 FAILED"""
        mock_exchange = AsyncMock()
        mock_exchange.cancel_order = AsyncMock(side_effect=Exception("Persistent error"))

        cancel_item = await service.add_to_queue(db=async_db_session, order_id=700)
        cancel_item.retry_count = cancel_item.max_retries
        await async_db_session.commit()

        # Mock verify_order_status to return OPEN
        service.verify_order_status = AsyncMock(return_value="OPEN")

        # 처리
        result = await service.process_cancel(
            db=async_db_session,
            cancel_item=cancel_item,
            exchange_service=mock_exchange
        )

        assert result is False
        assert cancel_item.status == "FAILED"
        assert "Persistent error" in cancel_item.error_message

    @pytest.mark.asyncio
    async def test_get_by_order_id(self, async_db_session, service):
        """주문 ID로 조회"""
        order_id = 800

        # 추가
        cancel_item = await service.add_to_queue(db=async_db_session, order_id=order_id)

        # 조회
        result = await service.get_by_order_id(db=async_db_session, order_id=order_id)

        assert result is not None
        assert result.order_id == order_id
        assert result.id == cancel_item.id

    @pytest.mark.asyncio
    async def test_get_by_order_id_not_found(self, async_db_session, service):
        """존재하지 않는 주문 ID"""
        result = await service.get_by_order_id(db=async_db_session, order_id=9999)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_no_filter(self, async_db_session, service):
        """전체 조회 (필터 없음)"""
        # 여러 상태의 항목 추가
        for i in range(5):
            await service.add_to_queue(db=async_db_session, order_id=1000 + i)

        result = await service.get_all(db=async_db_session, limit=100)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_all_with_status_filter(self, async_db_session, service):
        """상태 필터 적용"""
        # PENDING 2개
        await service.add_to_queue(db=async_db_session, order_id=1100)
        await service.add_to_queue(db=async_db_session, order_id=1101)

        # SUCCESS 1개
        cancel3 = await service.add_to_queue(db=async_db_session, order_id=1102)
        cancel3.status = "SUCCESS"
        async_db_session.add(cancel3)
        await async_db_session.commit()

        # PENDING만 조회
        result = await service.get_all(db=async_db_session, status="PENDING")

        assert len(result) == 2
        assert all(item.status == "PENDING" for item in result)

    @pytest.mark.asyncio
    async def test_get_all_pagination(self, async_db_session, service):
        """페이지네이션"""
        # 10개 추가
        for i in range(10):
            await service.add_to_queue(db=async_db_session, order_id=1200 + i)

        # 첫 페이지 (3개)
        page1 = await service.get_all(db=async_db_session, limit=3, offset=0)
        assert len(page1) == 3

        # 두 번째 페이지 (3개)
        page2 = await service.get_all(db=async_db_session, limit=3, offset=3)
        assert len(page2) == 3

        # 다른 항목인지 확인
        page1_ids = {item.id for item in page1}
        page2_ids = {item.id for item in page2}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_delete_success(self, async_db_session, service):
        """삭제 성공"""
        cancel_item = await service.add_to_queue(db=async_db_session, order_id=1300)
        cancel_id = cancel_item.id

        # 삭제
        result = await service.delete(db=async_db_session, cancel_id=cancel_id)

        assert result is True

        # 삭제 확인
        deleted = await service.get_by_order_id(db=async_db_session, order_id=1300)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, async_db_session, service):
        """존재하지 않는 항목 삭제"""
        result = await service.delete(db=async_db_session, cancel_id=99999)

        assert result is False


class TestCancelQueueServiceUnit:
    """DB 없이 테스트 가능한 유닛 테스트"""

    def test_service_initialization(self):
        """서비스 초기화"""
        service = CancelQueueService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(self):
        """재시도 지연 시간 계산 (exponential backoff)"""
        from datetime import timedelta

        cancel_item = CancelQueue(
            order_id=1,
            requested_at=datetime.utcnow(),
            status="PENDING",
            retry_count=0,
            max_retries=5
        )

        # Retry 0 → 1: 2초 (수동으로 계산하여 전달)
        now = datetime.utcnow()
        next_retry_1 = now + timedelta(seconds=2 ** 1)
        cancel_item.increment_retry(next_retry_at=next_retry_1)
        assert cancel_item.retry_count == 1
        assert cancel_item.next_retry_at == next_retry_1

        # Retry 1 → 2: 4초
        next_retry_2 = now + timedelta(seconds=2 ** 2)
        cancel_item.increment_retry(next_retry_at=next_retry_2)
        assert cancel_item.retry_count == 2
        assert cancel_item.next_retry_at > next_retry_1

        # Retry 4 → 5: 32초
        cancel_item.retry_count = 4
        next_retry_5 = now + timedelta(seconds=2 ** 5)
        cancel_item.increment_retry(next_retry_at=next_retry_5)
        assert cancel_item.retry_count == 5

    def test_cancel_item_can_retry_property(self):
        """can_retry 프로퍼티 테스트"""
        cancel_item = CancelQueue(
            order_id=1,
            requested_at=datetime.utcnow(),
            status="PENDING",
            retry_count=3,
            max_retries=5
        )

        # 재시도 가능
        assert cancel_item.can_retry is True

        # 재시도 소진
        cancel_item.retry_count = 5
        assert cancel_item.can_retry is False

    def test_cancel_item_mark_success(self):
        """mark_success() 메서드 테스트"""
        cancel_item = CancelQueue(
            order_id=1,
            requested_at=datetime.utcnow(),
            status="PENDING",
            retry_count=2
        )

        cancel_item.mark_success()

        assert cancel_item.status == "SUCCESS"
        assert cancel_item.updated_at is not None
        assert cancel_item.error_message is None

    def test_cancel_item_mark_failed(self):
        """mark_failed() 메서드 테스트"""
        cancel_item = CancelQueue(
            order_id=1,
            requested_at=datetime.utcnow(),
            status="PENDING"
        )

        error_msg = "Exchange API error"
        cancel_item.mark_failed(error_msg)

        assert cancel_item.status == "FAILED"
        assert cancel_item.updated_at is not None
        assert cancel_item.error_message == error_msg
