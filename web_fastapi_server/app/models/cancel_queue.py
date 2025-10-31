"""
CancelQueue 모델

PENDING 상태 주문의 취소 요청을 추적하여 고아 주문을 방지합니다.

취소 흐름:
1. PENDING 주문 취소 요청 → Cancel Queue에 등록 (status: PENDING)
2. PENDING → OPEN 전환 시 → Cancel Queue 확인 후 즉시 취소 시도
3. 취소 실패 시 → 재시도 (retry_count 증가, next_retry_at 설정)
4. 최대 재시도 횟수 초과 시 → status: FAILED
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional

from app.db.base import Base


class CancelQueue(Base):
    """주문 취소 대기열 모델"""

    __tablename__ = "cancel_queue"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Foreign Keys
    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("open_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="취소할 주문 ID"
    )
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="전략 ID"
    )
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="계정 ID"
    )

    # 취소 요청 정보
    requested_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="취소 요청 시각 (UTC)"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="재시도 횟수"
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        comment="최대 재시도 횟수"
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
        comment="다음 재시도 시각 (UTC)"
    )

    # 상태 추적
    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
        nullable=False,
        index=True,
        comment="취소 상태 (PENDING, PROCESSING, SUCCESS, FAILED)"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="오류 메시지"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="생성 시각 (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="수정 시각 (UTC)"
    )

    # 인덱스 (복합 인덱스)
    __table_args__ = (
        # (status, next_retry_at) 인덱스: 백그라운드 작업에서 재시도 대상 조회
        # Index('ix_cancel_queue_status_retry', 'status', 'next_retry_at'),
        {"comment": "주문 취소 대기열 - PENDING 주문 취소 추적"},
    )

    def __repr__(self) -> str:
        return (
            f"<CancelQueue("
            f"id={self.id}, "
            f"order_id={self.order_id}, "
            f"status={self.status}, "
            f"retry_count={self.retry_count}/{self.max_retries}"
            f")>"
        )

    @property
    def is_pending(self) -> bool:
        """대기 중인 취소 요청인지 확인"""
        return self.status == "PENDING"

    @property
    def is_processing(self) -> bool:
        """처리 중인 취소 요청인지 확인"""
        return self.status == "PROCESSING"

    @property
    def is_completed(self) -> bool:
        """완료된 취소 요청인지 확인"""
        return self.status in ("SUCCESS", "FAILED")

    @property
    def can_retry(self) -> bool:
        """재시도 가능한지 확인"""
        return self.retry_count < self.max_retries and not self.is_completed

    def increment_retry(self, next_retry_at: Optional[datetime] = None) -> None:
        """재시도 횟수 증가 및 다음 재시도 시각 설정"""
        self.retry_count += 1
        self.next_retry_at = next_retry_at
        self.status = "PENDING"
        self.updated_at = datetime.utcnow()

    def mark_success(self) -> None:
        """취소 성공으로 표시"""
        self.status = "SUCCESS"
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error_message: str) -> None:
        """취소 실패로 표시"""
        self.status = "FAILED"
        self.error_message = error_message
        self.updated_at = datetime.utcnow()
