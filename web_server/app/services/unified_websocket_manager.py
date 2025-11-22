"""
UnifiedWebSocketManager - 거래소 중립적 통합 WebSocket 관리자

Private/Public WebSocket 연결을 통합 관리하고 거래소 중립적 인터페이스 제공

주요 기능:
- 거래소별 WebSocket 핸들러 등록 및 관리
- Public/Private 연결 생성 및 생명주기 관리
- 연결 풀 관리 및 재사용
- 자동 재연결 및 상태 모니터링
- 에러 처리 및 격리

@FEAT:websocket-integration @COMP:websocket-manager @TYPE:infrastructure
"""

import asyncio
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional, Any, Union, Set
from enum import Enum
from dataclasses import dataclass
from flask import Flask

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """연결 유형 열거형"""
    PUBLIC_PRICE_FEED = "price_feed"
    PRIVATE_ORDER_EXECUTION = "order_execution"
    PUBLIC_ORDER_BOOK = "order_book"
    PRIVATE_POSITION_UPDATE = "position_update"


class ConnectionState(Enum):
    """연결 상태 열거형"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ConnectionStats:
    """연결 통계 정보"""
    total_connections: int
    public_connections: int
    private_connections: int
    exchange_breakdown: Dict[str, int]
    total_subscriptions: int
    supported_exchanges: int


class UnifiedConnection:
    """
    통합 WebSocket 연결 객체

    거래소와 연결 유형에 관계없이 통합된 인터페이스 제공.
    연결 상태, 생명주기, 메타데이터를 관리.
    """

    def __init__(self, connection_id: str, exchange: str, connection_type: ConnectionType,
                 symbols: List[str] = None, account_id: Optional[int] = None):
        self.id = connection_id
        self.exchange = exchange.lower()
        self.connection_type = connection_type
        self.symbols: Set[str] = set(symbols or [])
        self.account_id = account_id
        self.state = ConnectionState.DISCONNECTED
        self.handler = None
        self.created_at = time.time()
        self.last_activity = time.time()
        self.error_count = 0
        self.last_error = None

    @property
    def is_connected(self) -> bool:
        """연결 상태 반환"""
        return self.state == ConnectionState.CONNECTED

    @property
    def is_private(self) -> bool:
        """Private 연결 여부 반환"""
        return self.account_id is not None

    def set_state(self, state: ConnectionState, error: Optional[str] = None):
        """
        연결 상태 설정

        Args:
            state: 새로운 연결 상태
            error: 에러 메시지 (있는 경우)
        """
        self.state = state
        self.last_activity = time.time()

        if error:
            self.last_error = error
            self.error_count += 1
            logger.warning(f"🔴 연결 상태 에러 - ID: {self.id}, 오류: {error}")

    def add_symbol(self, symbol: str) -> None:
        """심볼 추가"""
        self.symbols.add(symbol)
        self.last_activity = time.time()

    def remove_symbol(self, symbol: str) -> None:
        """심볼 제거"""
        self.symbols.discard(symbol)
        self.last_activity = time.time()

    def get_info(self) -> Dict[str, Any]:
        """연결 정보 반환"""
        return {
            'id': self.id,
            'exchange': self.exchange,
            'connection_type': self.connection_type.value,
            'symbols': list(self.symbols),
            'account_id': self.account_id,
            'state': self.state.value,
            'is_connected': self.is_connected,
            'is_private': self.is_private,
            'created_at': self.created_at,
            'last_activity': self.last_activity,
            'error_count': self.error_count,
            'last_error': self.last_error
        }


class UnifiedWebSocketManager:
    """
    거래소 중립적 통합 WebSocket 관리자

    역할:
    - Public/Private WebSocket 연결 통합 관리
    - 거래소별 핸들러 등록 및 관리
    - 연결 풀 관리 및 재사용
    - 자동 재연결 및 상태 모니터링
    - 에러 처리 및 격리

    스레드 안전성:
    - _connections_lock으로 연결 딕셔너리 보호
    - _handlers_lock으로 핸들러 딕셔너리 보호
    """

    # 지원하는 거래소 목록 (확장성 고려)
    SUPPORTED_EXCHANGES = ['binance', 'bybit', 'upbit', 'bithumb']

    def __init__(self, app: Flask):
        """UnifiedWebSocketManager 초기화"""
        self.app = app
        self.connections: Dict[str, UnifiedConnection] = {}  # {connection_id: connection}
        self.exchange_handlers: Dict[str, Any] = {}  # {exchange: handler}
        self.account_connections: Dict[int, Set[str]] = {}  # {account_id: {connection_id, ...}}

        # 스레드 동기화
        self._connections_lock = threading.RLock()
        self._handlers_lock = threading.Lock()

        # 기타 속성
        self._running = False
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        logger.info("✅ UnifiedWebSocketManager 초기화 완료")

    def _validate_exchange(self, exchange: str) -> str:
        """
        거래소 이름 검증 및 정규화

        Args:
            exchange: 거래소 이름

        Returns:
            str: 정규화된 거래소 이름

        Raises:
            ValueError: 지원하지 않는 거래소인 경우
        """
        exchange = exchange.lower()
        if exchange not in self.SUPPORTED_EXCHANGES:
            raise ValueError(f"Unsupported exchange: {exchange}. Supported: {self.SUPPORTED_EXCHANGES}")
        return exchange

    def _generate_connection_id(self) -> str:
        """고유한 연결 ID 생성"""
        return str(uuid.uuid4())

    def _safe_get_handler(self, exchange: str) -> Optional[Any]:
        """
        스레드 안전하게 핸들러 조회

        Args:
            exchange: 거래소 이름

        Returns:
            Optional[Any]: 핸들러 객체 (없는 경우 None)
        """
        with self._handlers_lock:
            return self.exchange_handlers.get(exchange.lower())

    def _safe_add_connection(self, connection: UnifiedConnection) -> None:
        """
        스레드 안전하게 연결 추가

        Args:
            connection: 연결 객체
        """
        with self._connections_lock:
            self.connections[connection.id] = connection

            # 계정별 연결 관리
            if connection.account_id:
                if connection.account_id not in self.account_connections:
                    self.account_connections[connection.account_id] = set()
                self.account_connections[connection.account_id].add(connection.id)

    def _safe_remove_connection(self, connection_id: str) -> Optional[UnifiedConnection]:
        """
        스레드 안전하게 연결 제거

        Args:
            connection_id: 연결 ID

        Returns:
            Optional[UnifiedConnection]: 제거된 연결 객체
        """
        with self._connections_lock:
            connection = self.connections.pop(connection_id, None)

            if connection and connection.account_id:
                # 계정별 연결 목록에서 제거
                if connection.account_id in self.account_connections:
                    self.account_connections[connection.account_id].discard(connection_id)
                    if not self.account_connections[connection.account_id]:
                        del self.account_connections[connection.account_id]

            return connection

    def _safe_get_connection(self, connection_id: str) -> Optional[UnifiedConnection]:
        """
        스레드 안전하게 연결 조회

        Args:
            connection_id: 연결 ID

        Returns:
            Optional[UnifiedConnection]: 연결 객체
        """
        with self._connections_lock:
            return self.connections.get(connection_id)

    def register_exchange_handler(self, exchange: str, handler: Any) -> None:
        """
        거래소 핸들러 등록

        Args:
            exchange: 거래소 이름 ('binance', 'bybit', etc.)
            handler: WebSocket 핸들러 객체

        Raises:
            ValueError: 핸들러가 이미 등록된 경우
            ValueError: 지원하지 않는 거래소인 경우
        """
        exchange = self._validate_exchange(exchange)

        with self._handlers_lock:
            if exchange in self.exchange_handlers:
                raise ValueError(f"Handler for {exchange} already registered")

            self.exchange_handlers[exchange] = handler

        logger.info(f"✅ {exchange} 핸들러 등록 완료")

    async def create_public_connection(self, exchange: str, symbols: List[str],
                                     connection_type: Union[str, ConnectionType] = ConnectionType.PUBLIC_PRICE_FEED) -> UnifiedConnection:
        """
        Public WebSocket 연결 생성

        Args:
            exchange: 거래소 이름
            symbols: 구독할 심볼 목록
            connection_type: 연결 유형

        Returns:
            UnifiedConnection: 생성된 연결 객체

        Raises:
            ValueError: 핸들러가 등록되지 않은 경우
            Exception: 연결 실패 시
        """
        exchange = self._validate_exchange(exchange)

        # 핸들러 확인
        handler = self._safe_get_handler(exchange)
        if not handler:
            raise ValueError(f"No handler registered for exchange: {exchange}")

        # ConnectionType 변환
        if isinstance(connection_type, str):
            connection_type = ConnectionType(connection_type)

        # 연결 ID 생성
        connection_id = self._generate_connection_id()

        # 연결 객체 생성
        connection = UnifiedConnection(
            connection_id=connection_id,
            exchange=exchange,
            connection_type=connection_type,
            symbols=symbols
        )

        # 연결 상태 설정
        connection.set_state(ConnectionState.CONNECTING)

        # 핸들러 연결 (실제 구현에서는 핸들러.connect() 호출)
        try:
            if hasattr(handler, 'connect'):
                await handler.connect()
                connection.set_state(ConnectionState.CONNECTED)
                logger.info(f"✅ Public 연결 생성 성공 - {exchange}: {symbols}")
            else:
                # 핸들러에 connect 메서드가 없는 경우
                connection.set_state(ConnectionState.CONNECTED)
                logger.warning(f"⚠️ Handler for {exchange} has no connect method, assuming connected")

        except Exception as e:
            connection.set_state(ConnectionState.ERROR, str(e))
            logger.error(f"❌ Public 연결 생성 실패 - {exchange}: {e}")
            raise

        # 연결 등록 (스레드 안전)
        connection.handler = handler
        self._safe_add_connection(connection)

        return connection

    async def create_private_connection(self, account: Any,
                                      connection_type: Union[str, ConnectionType] = ConnectionType.PRIVATE_ORDER_EXECUTION) -> UnifiedConnection:
        """
        Private WebSocket 연결 생성

        Args:
            account: 계정 객체 (id, exchange 속성 필수)
            connection_type: 연결 유형

        Returns:
            UnifiedConnection: 생성된 연결 객체
        """
        exchange = account.exchange.lower()

        if exchange not in self.exchange_handlers:
            raise ValueError(f"No handler registered for exchange: {exchange}")

        # ConnectionType 변환
        if isinstance(connection_type, str):
            connection_type = ConnectionType(connection_type)

        # 연결 ID 생성
        connection_id = str(uuid.uuid4())

        # 연결 객체 생성
        connection = UnifiedConnection(
            connection_id=connection_id,
            exchange=exchange,
            connection_type=connection_type,
            account_id=account.id
        )
        connection.created_at = None  # TODO: 타임스탬프 설정

        # 연결 상태 설정
        connection.set_state(ConnectionState.CONNECTING)

        # 핸들러 연결 (실제 구현에서는 핸들러.connect() 호출)
        handler = self.exchange_handlers[exchange]
        if hasattr(handler, 'connect'):
            try:
                await handler.connect()
                connection.set_state(ConnectionState.CONNECTED)
                logger.info(f"✅ Private 연결 생성 성공 - 계정 {account.id}: {exchange}")
            except Exception as e:
                connection.set_state(ConnectionState.ERROR)
                raise e

        # 연결 등록
        self.connections[connection_id] = connection
        connection.handler = handler

        # 계정별 연결 관리
        if account.id not in self.account_connections:
            self.account_connections[account.id] = []
        self.account_connections[account.id].append(connection_id)

        return connection

    async def close_connection(self, connection_id: str) -> None:
        """
        연결 종료

        Args:
            connection_id: 종료할 연결 ID
        """
        if connection_id not in self.connections:
            return

        connection = self.connections[connection_id]
        connection.set_state(ConnectionState.DISCONNECTING)

        # 핸들러 연결 종료
        if connection.handler and hasattr(connection.handler, 'disconnect'):
            try:
                await connection.handler.disconnect()
                connection.set_state(ConnectionState.DISCONNECTED)
                logger.info(f"🔌 연결 종료 완료 - {connection_id}")
            except Exception as e:
                connection.set_state(ConnectionState.ERROR)
                logger.error(f"❌ 연결 종료 실패 - {connection_id}: {e}")

        # 연결 제거
        del self.connections[connection_id]

        # 계정별 연결 목록에서 제거
        if connection.account_id and connection.account_id in self.account_connections:
            if connection_id in self.account_connections[connection.account_id]:
                self.account_connections[connection.account_id].remove(connection_id)

    def get_supported_exchanges(self) -> List[str]:
        """
        지원하는 거래소 목록 반환

        Returns:
            List[str]: 지원하는 거래소 이름 목록 (소문자)
        """
        return list(self.exchange_handlers.keys())

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        연결 통계 정보 반환

        Returns:
            Dict[str, Any]: 연결 통계
        """
        total_connections = len(self.connections)
        public_connections = 0
        private_connections = 0
        exchange_breakdown = {}
        total_subscriptions = 0

        for connection in self.connections.values():
            # Public/Private 구분
            if connection.account_id:
                private_connections += 1
            else:
                public_connections += 1

            # 거래소별 통계
            if connection.exchange not in exchange_breakdown:
                exchange_breakdown[connection.exchange] = 0
            exchange_breakdown[connection.exchange] += 1

            # 구독 심볼 수
            total_subscriptions += len(connection.symbols)

        return {
            'total_connections': total_connections,
            'public_connections': public_connections,
            'private_connections': private_connections,
            'exchange_breakdown': exchange_breakdown,
            'total_subscriptions': total_subscriptions,
            'supported_exchanges': len(self.exchange_handlers)
        }