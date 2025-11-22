"""
WebSocket 관련 데이터 모델

가격 데이터, 연결 상태 등을 정의하는 공통 모델

@FEAT:websocket-integration @COMP:websocket-models @TYPE:data-models
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import time
from enum import Enum


class ConnectionState(Enum):
    """연결 상태 열거형"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ExchangeType(Enum):
    """지원하는 거래소 열거형"""
    BINANCE = "binance"
    BYBIT = "bybit"


@dataclass
class PriceQuote:
    """표준화된 가격 데이터 모델"""
    exchange: str
    symbol: str
    price: float
    timestamp: int
    volume: Optional[float] = None
    change_24h: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)

    def is_stale(self, max_age_seconds: int = 60) -> bool:
        """데이터 신선도 확인"""
        return (time.time() * 1000 - self.timestamp) > (max_age_seconds * 1000)

    def __str__(self) -> str:
        """문자열 표현"""
        return f"PriceQuote({self.exchange}:{self.symbol}=${self.price:.2f})"


@dataclass
class ConnectionMetrics:
    """연결 성능 메트릭"""
    messages_received: int = 0
    messages_processed: int = 0
    errors_count: int = 0
    reconnect_count: int = 0
    last_message_time: Optional[float] = None
    processing_time_total: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def success_rate(self) -> float:
        """메시지 처리 성공률"""
        if self.messages_received == 0:
            return 1.0
        return self.messages_processed / self.messages_received

    @property
    def average_processing_time(self) -> float:
        """평균 메시지 처리 시간"""
        if self.messages_processed == 0:
            return 0.0
        return self.processing_time_total / self.messages_processed

    @property
    def cache_hit_rate(self) -> float:
        """캐시 히트율"""
        total_cache_requests = self.cache_hits + self.cache_misses
        if total_cache_requests == 0:
            return 0.0
        return self.cache_hits / total_cache_requests

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'messages_received': self.messages_received,
            'messages_processed': self.messages_processed,
            'errors_count': self.errors_count,
            'reconnect_count': self.reconnect_count,
            'last_message_time': self.last_message_time,
            'success_rate': self.success_rate,
            'average_processing_time': self.average_processing_time,
            'cache_hit_rate': self.cache_hit_rate
        }