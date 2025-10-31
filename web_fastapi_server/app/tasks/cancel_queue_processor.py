"""
Cancel Queue Background Processor

주기적으로 Cancel Queue를 처리하는 백그라운드 작업
"""

import logging
import asyncio
from typing import Optional

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.services.cancel_queue_service import CancelQueueService
from app.services.mock_exchange_service import MockExchangeService

logger = logging.getLogger(__name__)


# 전역 Exchange Service (Phase 3에서 실제 구현으로 대체)
_exchange_service: Optional[MockExchangeService] = None


def get_exchange_service() -> MockExchangeService:
    """Exchange Service 싱글톤 반환"""
    global _exchange_service
    if _exchange_service is None:
        _exchange_service = MockExchangeService(
            success_rate=0.95,  # 95% 성공률 (테스트용)
            delay_ms=50  # 50ms 지연
        )
    return _exchange_service


async def process_cancel_queue():
    """
    Cancel Queue 백그라운드 처리

    주기적으로 다음 작업 수행:
    1. PENDING 상태의 취소 요청 조회
    2. 각 요청에 대해 주문 상태 확인 및 취소 실행
    3. 성공/실패 상태 업데이트
    4. 재시도 스케줄링 (exponential backoff)
    """
    logger.info(
        f"🔄 Cancel Queue Processor started "
        f"(interval={settings.CANCEL_QUEUE_INTERVAL}s, "
        f"max_retries={settings.MAX_CANCEL_RETRIES})"
    )

    exchange_service = get_exchange_service()
    iteration = 0

    while True:
        iteration += 1

        try:
            async with AsyncSessionLocal() as db:
                service = CancelQueueService()

                # 1. 대기 중인 취소 요청 조회
                pending_cancels = await service.get_pending_cancels(db, limit=100)

                if not pending_cancels:
                    logger.debug(f"[Iteration {iteration}] No pending cancel requests")
                else:
                    logger.info(
                        f"[Iteration {iteration}] Processing {len(pending_cancels)} "
                        f"cancel requests"
                    )

                # 2. 각 요청 처리
                success_count = 0
                retry_count = 0
                failed_count = 0

                for cancel_item in pending_cancels:
                    try:
                        # 상태를 PROCESSING으로 변경하여 다른 워커가 처리하지 않도록
                        if cancel_item.status == "PENDING":
                            cancel_item.status = "PROCESSING"
                            await db.commit()

                        # 취소 처리
                        success = await service.process_cancel(
                            db,
                            cancel_item,
                            exchange_service
                        )

                        if success:
                            success_count += 1
                        else:
                            # 실패 했지만 재시도 가능
                            if cancel_item.can_retry:
                                retry_count += 1
                                # 상태를 다시 PENDING으로 (재시도용)
                                cancel_item.status = "PENDING"
                                await db.commit()
                            else:
                                failed_count += 1

                    except Exception as e:
                        logger.error(
                            f"Error processing cancel request {cancel_item.id}: {e}",
                            exc_info=True
                        )
                        # 에러 발생 시 상태를 PENDING으로 되돌림 (재시도 가능)
                        try:
                            cancel_item.status = "PENDING"
                            cancel_item.increment_retry()
                            await db.commit()
                        except:
                            pass
                        continue

                # 3. 통계 로깅
                if pending_cancels:
                    logger.info(
                        f"[Iteration {iteration}] ✅ {success_count} succeeded, "
                        f"🔄 {retry_count} will retry, ❌ {failed_count} failed"
                    )

        except Exception as e:
            logger.exception(f"[Iteration {iteration}] Cancel queue processor error: {e}")

        # 설정된 간격만큼 대기
        await asyncio.sleep(settings.CANCEL_QUEUE_INTERVAL)


async def start_cancel_queue_processor():
    """
    Cancel Queue Processor 시작

    Returns:
        asyncio.Task: 백그라운드 작업 Task
    """
    task = asyncio.create_task(process_cancel_queue())
    logger.info("✅ Cancel Queue Processor task created")
    return task


async def stop_cancel_queue_processor(task: asyncio.Task):
    """
    Cancel Queue Processor 종료

    Args:
        task: 백그라운드 작업 Task
    """
    logger.info("Stopping Cancel Queue Processor...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("✅ Cancel Queue Processor stopped")
