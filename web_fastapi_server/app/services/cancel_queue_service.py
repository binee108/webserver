"""
Cancel Queue Service

고아 주문 방지를 위한 취소 대기열 관리 서비스
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cancel_queue import CancelQueue
from app.core.exceptions import DatabaseException, ValidationException

logger = logging.getLogger(__name__)


class CancelQueueService:
    """Cancel Queue 관리 서비스"""

    async def add_to_queue(
        self,
        db: AsyncSession,
        order_id: int,
        strategy_id: Optional[int] = None,
        account_id: Optional[int] = None,
    ) -> CancelQueue:
        """
        취소 요청을 큐에 추가

        Args:
            db: 데이터베이스 세션
            order_id: 취소할 주문 ID
            strategy_id: 전략 ID (선택)
            account_id: 계정 ID (선택)

        Returns:
            생성된 CancelQueue 객체

        Raises:
            ValidationException: 이미 큐에 존재하는 경우
            DatabaseException: DB 오류
        """
        try:
            # 1. 중복 확인 (이미 큐에 있는지)
            existing = await self.get_by_order_id(db, order_id)
            if existing and existing.status in ("PENDING", "PROCESSING"):
                logger.warning(f"Order {order_id} already in cancel queue (status={existing.status})")
                raise ValidationException(
                    message=f"Order {order_id} is already in cancel queue",
                    details={"order_id": order_id, "status": existing.status}
                )

            # 2. CancelQueue 레코드 생성
            cancel_item = CancelQueue(
                order_id=order_id,
                strategy_id=strategy_id,
                account_id=account_id,
                requested_at=datetime.utcnow(),
                status="PENDING",
            )

            # 3. DB 저장
            db.add(cancel_item)
            await db.commit()
            await db.refresh(cancel_item)

            # 4. 로그 기록
            logger.info(
                f"✅ Added order {order_id} to cancel queue "
                f"(id={cancel_item.id}, strategy_id={strategy_id})"
            )

            return cancel_item

        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"Failed to add order {order_id} to cancel queue: {e}")
            await db.rollback()
            raise DatabaseException(
                message="Failed to add to cancel queue",
                details={"order_id": order_id, "error": str(e)}
            )

    async def get_pending_cancels(
        self,
        db: AsyncSession,
        limit: int = 100
    ) -> List[CancelQueue]:
        """
        처리 대기 중인 취소 요청 조회

        조건:
        - status = PENDING
        - next_retry_at <= now 또는 NULL (재시도 시간 도래)

        Args:
            db: 데이터베이스 세션
            limit: 최대 조회 개수

        Returns:
            CancelQueue 객체 리스트
        """
        try:
            now = datetime.utcnow()

            stmt = select(CancelQueue).where(
                and_(
                    CancelQueue.status == "PENDING",
                    (CancelQueue.next_retry_at <= now) | (CancelQueue.next_retry_at.is_(None))
                )
            ).order_by(
                CancelQueue.requested_at.asc()
            ).limit(limit)

            result = await db.execute(stmt)
            items = result.scalars().all()

            logger.debug(f"Found {len(items)} pending cancel requests")
            return list(items)

        except Exception as e:
            logger.error(f"Failed to get pending cancels: {e}")
            raise DatabaseException(
                message="Failed to query cancel queue",
                details={"error": str(e)}
            )

    async def process_cancel(
        self,
        db: AsyncSession,
        cancel_item: CancelQueue,
        exchange_service
    ) -> bool:
        """
        개별 취소 요청 처리

        Args:
            db: 데이터베이스 세션
            cancel_item: 처리할 CancelQueue 항목
            exchange_service: 거래소 서비스 (MockExchangeService 등)

        Returns:
            성공 여부
        """
        try:
            # 1. 주문 상태 확인 (PENDING → OPEN?)
            order_status = await self.verify_order_status(db, cancel_item.order_id)

            logger.info(
                f"Processing cancel request {cancel_item.id} "
                f"(order_id={cancel_item.order_id}, status={order_status})"
            )

            # 2. 주문 상태에 따른 처리
            if order_status == "PENDING":
                # 아직 OPEN 전 → 재시도 필요
                logger.debug(f"Order {cancel_item.order_id} still PENDING, will retry later")
                cancel_item.increment_retry()
                await db.commit()
                return False

            elif order_status in ("FILLED", "CANCELLED", "EXPIRED"):
                # 이미 완료/취소/만료 → 취소 불필요 (성공 처리)
                logger.info(
                    f"Order {cancel_item.order_id} already {order_status}, "
                    "marking cancel as SUCCESS"
                )
                cancel_item.mark_success()
                await db.commit()
                return True

            elif order_status == "OPEN":
                # OPEN 상태 → 거래소 취소 실행
                try:
                    # Mock: exchange_order_id 가져오기 (실제는 open_orders 조회)
                    exchange_order_id = f"mock_{cancel_item.order_id}"

                    # 거래소 취소 실행
                    await exchange_service.cancel_order(
                        exchange="binance",  # Mock
                        exchange_order_id=exchange_order_id
                    )

                    # 성공: mark_success()
                    logger.info(f"✅ Successfully cancelled order {cancel_item.order_id}")
                    cancel_item.mark_success()
                    await db.commit()
                    return True

                except Exception as e:
                    # 실패: increment_retry() + 에러 로깅
                    error_msg = f"Exchange cancel failed: {str(e)}"
                    logger.error(
                        f"❌ Failed to cancel order {cancel_item.order_id}: {error_msg}"
                    )

                    if cancel_item.can_retry:
                        cancel_item.increment_retry()
                        await db.commit()
                        return False
                    else:
                        # 최종 실패: mark_failed()
                        cancel_item.mark_failed(error_msg)
                        await db.commit()
                        return False

            else:
                # 알 수 없는 상태
                error_msg = f"Unknown order status: {order_status}"
                logger.warning(error_msg)
                cancel_item.mark_failed(error_msg)
                await db.commit()
                return False

        except Exception as e:
            logger.exception(f"Unexpected error processing cancel {cancel_item.id}: {e}")
            await db.rollback()
            return False

    async def verify_order_status(
        self,
        db: AsyncSession,
        order_id: int
    ) -> str:
        """
        주문 현재 상태 확인

        Args:
            db: 데이터베이스 세션
            order_id: 주문 ID

        Returns:
            주문 상태 (PENDING, OPEN, FILLED, CANCELLED, EXPIRED)

        Note:
            Phase 2에서는 Mock 데이터 사용
            Phase 4+에서 실제 open_orders 테이블 조회로 변경
        """
        # TODO Phase 4: open_orders 테이블 조회
        # stmt = select(OpenOrder).where(OpenOrder.id == order_id)
        # result = await db.execute(stmt)
        # order = result.scalar_one_or_none()
        # return order.status if order else "UNKNOWN"

        # Phase 2: Mock 구현
        logger.debug(f"[MOCK] Verifying order status for order_id={order_id}")

        # Mock: 대부분 OPEN 상태로 가정
        # 실제로는 PENDING → OPEN 전환 시뮬레이션 필요
        import random
        statuses = ["PENDING", "OPEN", "OPEN", "OPEN"]  # OPEN 확률 높게
        return random.choice(statuses)

    async def get_by_order_id(
        self,
        db: AsyncSession,
        order_id: int
    ) -> Optional[CancelQueue]:
        """
        주문 ID로 Cancel Queue 조회

        Args:
            db: 데이터베이스 세션
            order_id: 주문 ID

        Returns:
            CancelQueue 객체 또는 None
        """
        try:
            stmt = select(CancelQueue).where(
                CancelQueue.order_id == order_id
            ).order_by(
                CancelQueue.created_at.desc()
            ).limit(1)

            result = await db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Failed to get cancel queue by order_id {order_id}: {e}")
            raise DatabaseException(
                message="Failed to query cancel queue",
                details={"order_id": order_id, "error": str(e)}
            )

    async def get_all(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[CancelQueue]:
        """
        Cancel Queue 목록 조회 (관리자용)

        Args:
            db: 데이터베이스 세션
            status: 상태 필터 (선택)
            limit: 최대 조회 개수
            offset: 오프셋

        Returns:
            CancelQueue 객체 리스트
        """
        try:
            stmt = select(CancelQueue)

            if status:
                stmt = stmt.where(CancelQueue.status == status)

            stmt = stmt.order_by(
                CancelQueue.created_at.desc()
            ).limit(limit).offset(offset)

            result = await db.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get cancel queue list: {e}")
            raise DatabaseException(
                message="Failed to query cancel queue",
                details={"error": str(e)}
            )

    async def delete(
        self,
        db: AsyncSession,
        cancel_id: int
    ) -> bool:
        """
        Cancel Queue 항목 삭제 (관리자용)

        Args:
            db: 데이터베이스 세션
            cancel_id: Cancel Queue ID

        Returns:
            성공 여부
        """
        try:
            stmt = select(CancelQueue).where(CancelQueue.id == cancel_id)
            result = await db.execute(stmt)
            cancel_item = result.scalar_one_or_none()

            if not cancel_item:
                logger.warning(f"Cancel queue item {cancel_id} not found")
                return False

            await db.delete(cancel_item)
            await db.commit()

            logger.info(f"Deleted cancel queue item {cancel_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete cancel queue {cancel_id}: {e}")
            await db.rollback()
            raise DatabaseException(
                message="Failed to delete cancel queue",
                details={"cancel_id": cancel_id, "error": str(e)}
            )
