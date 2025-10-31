"""
StrategyOrderLog 모델

전략별 주문 실행 결과를 추적하여 감사 로그를 제공합니다.

목적:
- 전략 단위로 주문 실행 결과 추적
- 계정별 성공/실패 통계
- 무손실 보장을 위한 감사 로그
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from app.db.base import Base


class StrategyOrderLog(Base):
    """전략별 주문 실행 로그 모델"""

    __tablename__ = "strategy_order_logs"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Foreign Keys
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="전략 ID"
    )
    webhook_log_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("webhook_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="웹훅 로그 ID (연결된 웹훅)"
    )

    # 주문 요청 정보
    symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="심볼 (예: BTC/USDT)"
    )
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="매매 방향 (buy, sell)"
    )
    order_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="주문 타입 (MARKET, LIMIT, STOP_LIMIT 등)"
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        comment="수량"
    )
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="지정가 (LIMIT 주문)"
    )
    stop_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
        comment="스탑 가격 (STOP 주문)"
    )

    # 계정별 실행 결과 (JSON)
    # 형식: {
    #   "account_1": {
    #     "success": true,
    #     "order_id": 123,
    #     "exchange_order_id": "abc123",
    #     "account_name": "Binance Main",
    #     "exchange": "binance"
    #   },
    #   "account_2": {
    #     "success": false,
    #     "error": "Insufficient balance",
    #     "account_name": "Bybit Sub",
    #     "exchange": "bybit"
    #   }
    # }
    execution_results: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default={},
        comment="계정별 실행 결과 (JSON)"
    )

    # 실행 통계
    total_accounts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="전체 계정 수"
    )
    successful_accounts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="성공한 계정 수"
    )
    failed_accounts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="실패한 계정 수"
    )

    # 상태
    status: Mapped[str] = mapped_column(
        String(20),
        default="PROCESSING",
        nullable=False,
        index=True,
        comment="실행 상태 (PROCESSING, COMPLETED, PARTIAL_FAILURE)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="생성 시각 (UTC)"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="완료 시각 (UTC)"
    )

    # 테이블 설정
    __table_args__ = (
        {"comment": "전략별 주문 실행 로그 - 무손실 보장을 위한 감사 로그"},
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyOrderLog("
            f"id={self.id}, "
            f"strategy_id={self.strategy_id}, "
            f"symbol={self.symbol}, "
            f"status={self.status}, "
            f"success={self.successful_accounts}/{self.total_accounts}"
            f")>"
        )

    @property
    def is_processing(self) -> bool:
        """처리 중인지 확인"""
        return self.status == "PROCESSING"

    @property
    def is_completed(self) -> bool:
        """완료되었는지 확인 (성공 또는 부분 실패)"""
        return self.status in ("COMPLETED", "PARTIAL_FAILURE")

    @property
    def is_all_success(self) -> bool:
        """모든 계정에서 성공했는지 확인"""
        return self.successful_accounts == self.total_accounts

    @property
    def is_partial_failure(self) -> bool:
        """일부 계정이 실패했는지 확인"""
        return 0 < self.failed_accounts < self.total_accounts

    @property
    def is_all_failed(self) -> bool:
        """모든 계정이 실패했는지 확인"""
        return self.failed_accounts == self.total_accounts

    @property
    def success_rate(self) -> float:
        """성공률 계산 (0.0 ~ 1.0)"""
        if self.total_accounts == 0:
            return 0.0
        return self.successful_accounts / self.total_accounts

    def update_statistics(
        self,
        execution_results: Dict[str, Any]
    ) -> None:
        """실행 결과를 기반으로 통계 업데이트"""
        self.execution_results = execution_results

        successful = 0
        failed = 0

        for account_key, result in execution_results.items():
            if result.get("success"):
                successful += 1
            else:
                failed += 1

        self.successful_accounts = successful
        self.failed_accounts = failed

        # 상태 결정
        if failed == 0:
            self.status = "COMPLETED"
        else:
            self.status = "PARTIAL_FAILURE"

        self.completed_at = datetime.utcnow()

    def get_failed_accounts(self) -> list[Dict[str, Any]]:
        """실패한 계정 목록 반환"""
        failed = []
        for account_key, result in self.execution_results.items():
            if not result.get("success"):
                failed.append({
                    "account_key": account_key,
                    **result
                })
        return failed

    def get_successful_accounts(self) -> list[Dict[str, Any]]:
        """성공한 계정 목록 반환"""
        successful = []
        for account_key, result in self.execution_results.items():
            if result.get("success"):
                successful.append({
                    "account_key": account_key,
                    **result
                })
        return successful
