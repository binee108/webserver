"""
Webhook Pydantic Schemas

웹훅 요청/응답 데이터 검증 및 직렬화
"""

from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)


class OrderTypeEnum(str, Enum):
    """주문 타입 Enum (Phase 4: MARKET/CANCEL 집중)"""
    MARKET = "MARKET"
    CANCEL = "CANCEL"
    # Phase 5 예정
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class SideEnum(str, Enum):
    """주문 방향"""
    BUY = "BUY"
    SELL = "SELL"
    buy = "buy"  # 소문자도 허용
    sell = "sell"


class ActionEnum(str, Enum):
    """웹훅 액션"""
    TRADING_SIGNAL = "trading_signal"
    TEST = "test"


class WebhookRequest(BaseModel):
    """
    웹훅 요청 스키마

    TradingView 또는 외부 시스템에서 전송되는 웹훅 데이터를 검증합니다.
    """
    # 필수 필드
    group_name: str = Field(..., description="전략 그룹명 (Strategy.group_name)")
    token: str = Field(..., description="웹훅 인증 토큰")
    action: ActionEnum = Field(..., description="웹훅 액션 타입")
    order_type: OrderTypeEnum = Field(..., description="주문 타입")
    side: SideEnum = Field(..., description="주문 방향")
    symbol: str = Field(..., description="거래 심볼 (예: BTC/USDT)")

    # 선택 필드
    quantity: Optional[float] = Field(None, description="주문 수량")
    price: Optional[float] = Field(None, description="지정가 (LIMIT 주문)")
    stop_price: Optional[float] = Field(None, description="스톱 가격 (STOP 주문)")
    exchange: Optional[str] = Field(None, description="거래소 지정 (선택)")

    # Phase 4: MARKET/CANCEL 주문 타입 검증
    @validator('order_type')
    def validate_order_type_phase4(cls, v):
        """Phase 4에서는 MARKET/CANCEL만 지원"""
        if v not in [OrderTypeEnum.MARKET, OrderTypeEnum.CANCEL]:
            raise ValueError(
                f"Phase 4에서는 MARKET/CANCEL 주문만 지원됩니다. "
                f"받은 주문 타입: {v}. "
                f"LIMIT/STOP 주문은 Phase 5에서 구현될 예정입니다."
            )
        return v

    @validator('quantity')
    def validate_quantity_for_market(cls, v, values):
        """MARKET 주문은 quantity 필수"""
        order_type = values.get('order_type')
        if order_type == OrderTypeEnum.MARKET and not v:
            raise ValueError("MARKET 주문에는 quantity가 필수입니다")
        return v

    @validator('side')
    def normalize_side(cls, v):
        """side를 대문자로 정규화"""
        return v.upper()

    class Config:
        use_enum_values = True


class OrderResult(BaseModel):
    """개별 주문 실행 결과"""
    account_id: int
    account_name: str
    exchange: str
    symbol: str
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    executed_quantity: Optional[float] = None
    executed_price: Optional[float] = None


class OrderSummary(BaseModel):
    """주문 실행 요약"""
    total_accounts: int
    successful_orders: int
    failed_orders: int
    success_rate: float


class PerformanceMetrics(BaseModel):
    """성능 메트릭"""
    total_processing_time_ms: float
    validation_time_ms: Optional[float] = None
    execution_time_ms: Optional[float] = None


class WebhookResponse(BaseModel):
    """
    웹훅 응답 스키마

    성공/실패 여부, 실행 결과, 성능 메트릭 포함
    """
    success: bool
    action: str
    strategy: str
    message: str
    results: List[OrderResult]
    summary: OrderSummary
    performance_metrics: PerformanceMetrics
    timeout: Optional[bool] = Field(None, description="타임아웃 발생 여부")
    error: Optional[str] = Field(None, description="에러 메시지 (실패 시)")


class WebhookErrorResponse(BaseModel):
    """웹훅 에러 응답"""
    success: bool = False
    error: str
    timeout: Optional[bool] = None
    processing_time_ms: Optional[float] = None
