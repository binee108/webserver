"""
WebSocket 설정 관리 모듈

거래소별 WebSocket 설정과 공통 설정을 중앙 관리

@FEAT:websocket-integration @COMP:websocket-config @TYPE:configuration
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ConnectionType(Enum):
    """연결 유형 열거형"""
    PUBLIC_PRICE_FEED = "price_feed"
    PRIVATE_ORDER_EXECUTION = "order_execution"
    PUBLIC_ORDER_BOOK = "order_book"
    PRIVATE_POSITION_UPDATE = "position_update"


@dataclass
class WebSocketConfig:
    """WebSocket 공통 설정"""
    # 재연결 설정
    RECONNECT_DELAY: float = 5.0  # 재연결 지연 시간 (초)
    MAX_RECONNECT_ATTEMPTS: int = 10  # 최대 재연결 시도 횟수
    RECONNECT_BACKOFF_MULTIPLIER: float = 1.5  # 재연결 지연 증가 배수

    # 캐시 설정
    CACHE_EXPIRE_TIME: int = 60  # 캐시 만료 시간 (초)
    MAX_CACHE_SIZE: int = 100  # 최대 캐시 크기
    CACHE_CLEANUP_INTERVAL: int = 300  # 캐시 정리 간격 (초)

    # 성능 설정
    MESSAGE_BUFFER_SIZE: int = 1000  # 메시지 버퍼 크기
    PROCESSING_TIMEOUT: float = 10.0  # 메시지 처리 타임아웃 (초)
    HEARTBEAT_INTERVAL: int = 30  # 하트비트 간격 (초)

    # 로깅 설정
    LOG_MESSAGE_SAMPLE_RATE: float = 0.01  # 메시지 로깅 샘플링 비율
    LOG_PERFORMANCE_METRICS: bool = True  # 성능 메트릭 로깅 여부


@dataclass
class ExchangeConfig:
    """거래소별 WebSocket 설정"""
    # Binance 설정
    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
    BINANCE_TESTNET_WS_URL = "wss://testnet.binance.vision/ws"
    BINANCE_MAX_CONNECTIONS = 10
    BINANCE_RATE_LIMIT = 5  # requests per second

    # Bybit 설정
    BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
    BYBIT_TESTNET_WS_URL = "wss://stream-testnet.bybit.com/v5/public/linear"
    BYBIT_MAX_CONNECTIONS = 10
    BYBIT_RATE_LIMIT = 5  # requests per second

    # 지원하는 거래소 목록
    SUPPORTED_EXCHANGES = ['binance', 'bybit']

    @classmethod
    def get_ws_url(cls, exchange: str, testnet: bool = False) -> str:
        """
        거래소별 WebSocket URL 반환

        Args:
            exchange: 거래소 이름
            testnet: 테스트넷 사용 여부

        Returns:
            str: WebSocket URL

        Raises:
            ValueError: 지원하지 않는 거래소인 경우
        """
        exchange = exchange.lower()

        if exchange == 'binance':
            return cls.BINANCE_TESTNET_WS_URL if testnet else cls.BINANCE_WS_URL
        elif exchange == 'bybit':
            return cls.BYBIT_TESTNET_WS_URL if testnet else cls.BYBIT_WS_URL
        else:
            raise ValueError(f"지원하지 않는 거래소: {exchange}")


class WebSocketConfigManager:
    """WebSocket 설정 관리자"""

    def __init__(self):
        self._config = WebSocketConfig()
        self._custom_configs: Dict[str, Dict[str, Any]] = {}

    def get_config(self) -> WebSocketConfig:
        """전역 WebSocket 설정 반환"""
        return self._config

    def set_custom_config(self, key: str, value: Any) -> None:
        """사용자 정의 설정 추가"""
        self._custom_configs[key] = value

    def get_custom_config(self, key: str, default: Any = None) -> Any:
        """사용자 정의 설정 조회"""
        return self._custom_configs.get(key, default)

    def is_exchange_supported(self, exchange: str) -> bool:
        """거래소 지원 여부 확인"""
        return exchange.lower() in ExchangeConfig.SUPPORTED_EXCHANGES

    def get_exchange_config(self, exchange: str, config_type: str = 'ws_url') -> Any:
        """
        거래소별 특정 설정 조회

        Args:
            exchange: 거래소 이름
            config_type: 설정 타입 ('ws_url', 'max_connections', 'rate_limit')

        Returns:
            Any: 설정값
        """
        exchange = exchange.lower()

        if config_type == 'ws_url':
            return ExchangeConfig.get_ws_url(exchange)
        elif config_type == 'max_connections':
            if exchange == 'binance':
                return ExchangeConfig.BINANCE_MAX_CONNECTIONS
            elif exchange == 'bybit':
                return ExchangeConfig.BYBIT_MAX_CONNECTIONS
        elif config_type == 'rate_limit':
            if exchange == 'binance':
                return ExchangeConfig.BINANCE_RATE_LIMIT
            elif exchange == 'bybit':
                return ExchangeConfig.BYBIT_RATE_LIMIT

        return None

    def reload_config(self) -> None:
        """설정 다시 로드 (환경 변수나 설정 파일에서)"""
        # TODO: 환경 변수나 설정 파일에서 설정 다시 로드 구현
        pass


# 전역 설정 관리자 인스턴스
config_manager = WebSocketConfigManager()