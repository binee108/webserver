"""
Cancel Queue API Endpoints
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cancel_queue_service import CancelQueueService
from app.schemas.cancel_queue import (
    CancelQueueResponse,
    CancelRequestResponse,
)
from app.core.exceptions import ValidationException, DatabaseException, NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cancel-queue", tags=["Cancel Queue"])


def get_cancel_queue_service() -> CancelQueueService:
    """Cancel Queue Service 의존성"""
    return CancelQueueService()


@router.post("/orders/{order_id}/cancel", response_model=CancelRequestResponse)
async def request_cancel(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    service: CancelQueueService = Depends(get_cancel_queue_service)
):
    """
    주문 취소 요청

    - PENDING 상태 주문: Cancel Queue에 추가 (202 Accepted)
    - OPEN 상태 주문: 즉시 거래소 취소 실행 (200 OK)
    - 이미 취소된 주문: 409 Conflict
    """
    try:
        # 1. 주문 상태 확인
        order_status = await service.verify_order_status(db, order_id)

        logger.info(f"Cancel request for order {order_id} (status={order_status})")

        # 2. PENDING이면 Cancel Queue에 추가
        if order_status == "PENDING":
            cancel_item = await service.add_to_queue(
                db=db,
                order_id=order_id,
                strategy_id=None,  # TODO: 실제 전략 ID 전달
                account_id=None,  # TODO: 실제 계정 ID 전달
            )

            return CancelRequestResponse(
                message="Cancel request added to queue",
                order_id=order_id,
                status="queued",
                cancel_queue_id=cancel_item.id,
                immediate=False
            )

        # 3. OPEN이면 즉시 거래소 취소 실행
        elif order_status == "OPEN":
            # TODO Phase 4: 실제 거래소 취소 실행
            logger.info(f"Immediately cancelling order {order_id}")

            return CancelRequestResponse(
                message="Order cancelled immediately",
                order_id=order_id,
                status="cancelled",
                cancel_queue_id=None,
                immediate=True
            )

        # 4. 이미 취소/체결/만료된 주문
        elif order_status in ("CANCELLED", "FILLED", "EXPIRED"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Order is already {order_status}"
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown order status: {order_status}"
            )

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except DatabaseException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )


@router.get("", response_model=List[CancelQueueResponse])
async def get_cancel_queue(
    status_filter: Optional[str] = Query(None, alias="status", description="상태 필터"),
    limit: int = Query(50, ge=1, le=200, description="최대 조회 개수"),
    offset: int = Query(0, ge=0, description="오프셋"),
    db: AsyncSession = Depends(get_db),
    service: CancelQueueService = Depends(get_cancel_queue_service)
):
    """
    Cancel Queue 조회 (관리자용)

    - 상태별 필터링 가능
    - 페이지네이션 지원
    """
    try:
        items = await service.get_all(
            db=db,
            status=status_filter,
            limit=limit,
            offset=offset
        )
        return items

    except DatabaseException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )


@router.get("/{cancel_id}", response_model=CancelQueueResponse)
async def get_cancel_queue_item(
    cancel_id: int,
    db: AsyncSession = Depends(get_db),
    service: CancelQueueService = Depends(get_cancel_queue_service)
):
    """
    Cancel Queue 개별 조회
    """
    try:
        # TODO: get_by_id 메서드 추가 필요
        items = await service.get_all(db=db, limit=1000)
        item = next((i for i in items if i.id == cancel_id), None)

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cancel queue item {cancel_id} not found"
            )

        return item

    except DatabaseException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )


@router.delete("/{cancel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cancel_queue_item(
    cancel_id: int,
    db: AsyncSession = Depends(get_db),
    service: CancelQueueService = Depends(get_cancel_queue_service)
):
    """
    Cancel Queue에서 제거 (관리자용)

    - 강제로 취소 요청 삭제
    - 주의: 고아 주문이 발생할 수 있음
    """
    try:
        success = await service.delete(db=db, cancel_id=cancel_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cancel queue item {cancel_id} not found"
            )

        return

    except DatabaseException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message
        )
