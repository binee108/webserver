"""
Cancel Queue Pydantic Schemas
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class CancelQueueBase(BaseModel):
    """Cancel Queue 기본 스키마"""
    order_id: int = Field(..., description="취소할 주문 ID")
    strategy_id: Optional[int] = Field(None, description="전략 ID")
    account_id: Optional[int] = Field(None, description="계정 ID")


class CancelQueueCreate(CancelQueueBase):
    """Cancel Queue 생성 요청"""
    pass


class CancelQueueResponse(CancelQueueBase):
    """Cancel Queue 응답"""
    id: int = Field(..., description="Cancel Queue ID")
    requested_at: datetime = Field(..., description="취소 요청 시각")
    retry_count: int = Field(..., description="재시도 횟수")
    max_retries: int = Field(..., description="최대 재시도 횟수")
    next_retry_at: Optional[datetime] = Field(None, description="다음 재시도 시각")
    status: str = Field(..., description="취소 상태 (PENDING, PROCESSING, SUCCESS, FAILED)")
    error_message: Optional[str] = Field(None, description="에러 메시지")
    created_at: datetime = Field(..., description="생성 시각")
    updated_at: datetime = Field(..., description="수정 시각")

    model_config = ConfigDict(from_attributes=True)


class CancelRequestResponse(BaseModel):
    """취소 요청 응답"""
    message: str = Field(..., description="응답 메시지")
    order_id: int = Field(..., description="주문 ID")
    status: str = Field(..., description="처리 상태")
    cancel_queue_id: Optional[int] = Field(None, description="Cancel Queue ID (PENDING인 경우)")
    immediate: bool = Field(..., description="즉시 처리 여부")
