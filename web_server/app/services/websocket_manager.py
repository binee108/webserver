"""
WebSocket 연결 관리자

계정별 WebSocket 연결 풀을 관리하고 자동 재연결 및 keep-alive를 제공합니다.

@FEAT:order-tracking @COMP:service @TYPE:websocket-integration
"""

import asyncio
import logging
import threading
import time
from enum import Enum
from typing import Dict, Optional, Set
from threading import Thread
from flask import Flask

from app.models import Account

logger = logging.getLogger(__name__)


# @FEAT:websocket-state-tracking @COMP:service @TYPE:validation
class ConnectionState(Enum):
    """WebSocket 연결 상태 열거형

    상태 전이 흐름:
    DISCONNECTED → CONNECTING → CONNECTED → DISCONNECTING → DISCONNECTED
                              ↓ ERROR         ↓ ERROR
                         RECONNECTING ←───────────────

    상태별 설명:
    - CONNECTING: 핸드셰이크 진행 중, WebSocket 연결 시도
    - CONNECTED: 성공적으로 연결됨, 데이터 수신 가능
    - DISCONNECTING: 연결 종료 중, 정리 절차 진행
    - DISCONNECTED: 연결 종료됨, 재연결 가능 상태
    - ERROR: 오류 상태, 복구 필요
    - RECONNECTING: 재연결 시도 중

    호환성: is_connected 속성은 CONNECTED 상태일 때만 True 반환
    """
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


# @FEAT:order-tracking @COMP:service @TYPE:websocket-integration
# @FEAT:websocket-state-tracking @COMP:service @TYPE:validation
class WebSocketConnection:
    """단일 WebSocket 연결 래퍼 (향상된 상태 추적 포함)

    기능:
    - 상태 기반 연결 관리 (ConnectionState enum)
    - 실시간 연결 상태 검증 (is_healthy)
    - 연결 메타데이터 추적 (ping/메시지 시간, 바이트 수, 오류 기록)
    - 상태 전이 유효성 검사 및 자동 복구
    - 레거시 호환성 지원 (is_connected 속성)

    사용 예시:
        connection = WebSocketConnection(12345, 'BINANCE', handler)
        connection.set_state(ConnectionState.CONNECTING)

        # WebSocket 연결 성공 후
        connection.set_state(ConnectionState.CONNECTED)

        # 상태 확인
        assert connection.state == ConnectionState.CONNECTED
        assert connection.is_connected == True  # 호환성

        # 상태 검증
        if connection.is_healthy():
            print("Connection is healthy")

    상태 전이 규칙:
    - 모든 상태 전이는 유효성 검사를 거침
    - 잘못된 전이 시도는 자동으로 ERROR 상태로 전환
    - ERROR 상태에서는 복구 전이 가능 (DISCONNECTED, RECONNECTING)
    """

    def __init__(self, account_id: int, exchange: str, handler: object):
        self.account_id = account_id
        self.exchange = exchange
        self.handler = handler  # BinanceWebSocket or BybitWebSocket

        # 상태 추적 (@FEAT:websocket-state-tracking)
        self._state = ConnectionState.DISCONNECTED
        self.state_changed_time = time.time()

        # 연결 상태 정보
        self.reconnect_count = 0
        self.connection_attempt_count = 0

        # 상태 추적 메타데이터
        self.last_ping_time: Optional[float] = None
        self.last_message_time: Optional[float] = None
        self.last_error: Optional[str] = None
        self.connection_start_time: Optional[float] = None
        self.bytes_received = 0
        self.bytes_sent = 0

        # 구독 정보
        self.subscribed_symbols: Set[str] = set()

    @property
    def state(self) -> ConnectionState:
        """현재 연결 상태 반환"""
        return self._state

    @property
    def is_connected(self) -> bool:
        """호환성을 위한 boolean 상태 (레거시 코드 지원)"""
        return self._state == ConnectionState.CONNECTED

    def set_state(self, new_state: ConnectionState, error: Optional[str] = None) -> None:
        """상태 전이 (유효성 검사 포함)"""
        old_state = self._state

        # 상태 전이 유효성 검사
        if not self._is_valid_transition(old_state, new_state):
            logger.warning(
                f"⚠️ 잘못된 상태 전이 시도: {old_state.value} → {new_state.value} "
                f"(계정: {self.account_id})"
            )
            # 에러 상태로 전이 허용 (복구를 위해)
            if new_state != ConnectionState.ERROR:
                new_state = ConnectionState.ERROR

        self._state = new_state
        self.state_changed_time = time.time()

        if error:
            self.last_error = error
            logger.warning(f"🔴 연결 오류 상태: {error} (계정: {self.account_id})")

        # 상태별 메타데이터 업데이트
        if new_state == ConnectionState.CONNECTING:
            self.connection_attempt_count += 1
        elif new_state == ConnectionState.CONNECTED:
            if not self.connection_start_time:
                self.connection_start_time = time.time()
        elif new_state == ConnectionState.DISCONNECTED:
            self.connection_start_time = None

    def _is_valid_transition(self, old_state: ConnectionState, new_state: ConnectionState) -> bool:
        """상태 전이 유효성 검사"""
        valid_transitions = {
            ConnectionState.DISCONNECTED: [
                ConnectionState.CONNECTING, ConnectionState.RECONNECTING, ConnectionState.CONNECTED
            ],
            ConnectionState.CONNECTING: [
                ConnectionState.CONNECTED, ConnectionState.ERROR, ConnectionState.DISCONNECTED
            ],
            ConnectionState.CONNECTED: [
                ConnectionState.DISCONNECTING, ConnectionState.ERROR, ConnectionState.DISCONNECTED
            ],
            ConnectionState.DISCONNECTING: [
                ConnectionState.DISCONNECTED, ConnectionState.ERROR
            ],
            ConnectionState.ERROR: [
                ConnectionState.DISCONNECTED, ConnectionState.RECONNECTING, ConnectionState.CONNECTING
            ],
            ConnectionState.RECONNECTING: [
                ConnectionState.CONNECTING, ConnectionState.ERROR, ConnectionState.DISCONNECTED
            ]
        }

        return new_state in valid_transitions.get(old_state, [])

    def update_health_metadata(self, ping_time: Optional[float] = None,
                             message_time: Optional[float] = None,
                             bytes_received: int = 0, bytes_sent: int = 0) -> None:
        """연결 상태 메타데이터 업데이트"""
        if ping_time:
            self.last_ping_time = ping_time
        if message_time:
            self.last_message_time = message_time

        self.bytes_received += bytes_received
        self.bytes_sent += bytes_sent

    def is_healthy(self) -> bool:
        """연결 상태 검증"""
        if self._state != ConnectionState.CONNECTED:
            return False

        current_time = time.time()

        # 마지막 핑/메시지 시간 검증 (30초 이내)
        if self.last_ping_time and (current_time - self.last_ping_time) > 60:
            return False

        if self.last_message_time and (current_time - self.last_message_time) > 120:
            return False

        return True

    def get_connection_info(self) -> Dict:
        """연결 정보 반환 (모니터링용)"""
        return {
            'account_id': self.account_id,
            'exchange': self.exchange,
            'state': self._state.value,
            'state_changed_time': self.state_changed_time,
            'reconnect_count': self.reconnect_count,
            'connection_attempt_count': self.connection_attempt_count,
            'last_ping_time': self.last_ping_time,
            'last_message_time': self.last_message_time,
            'last_error': self.last_error,
            'connection_start_time': self.connection_start_time,
            'bytes_received': self.bytes_received,
            'bytes_sent': self.bytes_sent,
            'subscribed_symbols_count': len(self.subscribed_symbols),
            'is_healthy': self.is_healthy()
        }


# @FEAT:order-tracking @COMP:service @TYPE:websocket-integration
# @FEAT:websocket-thread-safety @COMP:service @TYPE:synchronization
class WebSocketManager:
    """WebSocket 연결 풀 관리자 (스레드 안전 포함)

    핵심 기능:
    - 계정별 WebSocket 연결 관리
    - 자동 재연결 (exponential backoff)
    - Ping/Pong keep-alive
    - 심볼 구독 관리 (카운트 기반)
    - 상태 기반 연결 추적 (ConnectionState enum)
    - 스레드 안전 연결 관리 (RLock 기반)

    스레드 안전 (@FEAT:websocket-thread-safety):
    - 모든 연결 딕셔너리 접근은 RLock으로 보호
    - 재귀 락(Recursive Lock) 사용으로 교착 상태 방지
    - 원자적 연결 추가/제거/조회 메서드 제공
    - 스냅샷 기반 통계 수집으로 일관성 보장

    사용 시 주의사항:
    - 외부에서는 제공된 스레드 안전 메서드 사용 권장
    - 직접 connections 딕셔너리 접근 시 락 동기화 필요
    - 상태 변경 시 set_state() 메서드 사용 권장

    동시성 제어:
    - _connections_lock: 연결 딕셔너리 보호 (RLock)
    - _subscription_lock: 구독 카운트 보호 (Lock)
    """

    def __init__(self, app: Flask):
        self.app = app
        self.connections: Dict[int, WebSocketConnection] = {}  # {account_id: connection}
        self.symbol_subscriptions: Dict[tuple, int] = {}  # {(account_id, symbol): count}

        # 스레드 동기화 (@FEAT:websocket-thread-safety)
        # RLock(재귀 락) 사용: 동일 스레드에서의 중첩 락 허용, 교착 상태 방지
        self._connections_lock = threading.RLock()  # 연결 딕셔너리 동시성 제어
        self._subscription_lock = threading.Lock()  # 구독 카운트 동시성 제어 (기존)

        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[Thread] = None
        self._running = False

    # @FEAT:order-tracking @COMP:service @TYPE:core
    def start(self):
        """WebSocket 관리자 시작 (백그라운드 스레드에서 asyncio 이벤트 루프 실행)"""
        if self._running:
            logger.warning("WebSocketManager가 이미 실행 중입니다")
            return

        self._running = True

        def run_loop():
            """백그라운드 스레드에서 실행되는 이벤트 루프"""
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)

            try:
                logger.info("🔌 WebSocketManager 이벤트 루프 시작")
                self.event_loop.run_forever()
            except Exception as e:
                logger.error(f"❌ WebSocketManager 이벤트 루프 오류: {e}")
            finally:
                logger.info("🔌 WebSocketManager 이벤트 루프 종료")
                self.event_loop.close()

        self.thread = Thread(target=run_loop, daemon=True)
        self.thread.start()
        logger.info("✅ WebSocketManager 시작 완료")

    # @FEAT:order-tracking @COMP:service @TYPE:core
    def stop(self):
        """WebSocket 관리자 정지"""
        if not self._running:
            return

        self._running = False

        if self.event_loop:
            # 스레드 안전하게 모든 연결 닫기 (@FEAT:websocket-thread-safety)
            connections_copy = self._get_all_connections()
            for account_id in connections_copy.keys():
                self._schedule_coroutine(self.disconnect_account(account_id))

            self.event_loop.call_soon_threadsafe(self.event_loop.stop)

        if self.thread:
            self.thread.join(timeout=5)

        logger.info("🔌 WebSocketManager 정지 완료")

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    def _schedule_coroutine(self, coro):
        """백그라운드 스레드에서 코루틴 스케줄링 (에러 처리 포함)"""
        if self.event_loop and self._running:
            future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)

            # 콜백으로 에러 처리
            future.add_done_callback(self._handle_future_result)

            return future
        return None

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    def _handle_future_result(self, future):
        """코루틴 실행 결과 처리

        Args:
            future: asyncio.Future 객체
        """
        try:
            future.result()  # 예외가 있으면 여기서 발생
        except Exception as e:
            logger.error(f"❌ 코루틴 실행 실패: {e}", exc_info=True)

    # @FEAT:order-tracking @COMP:service @TYPE:core
    async def connect_account(self, account_id: int) -> bool:
        """계정의 WebSocket 연결 생성

        Args:
            account_id: 계정 ID

        Returns:
            bool: 연결 성공 여부
        """
        try:
            with self.app.app_context():
                account = Account.query.get(account_id)
                if not account:
                    logger.error(f"❌ 계정을 찾을 수 없습니다: {account_id}")
                    return False

                # 이미 연결된 경우 상태 확인 (@FEAT:websocket-state-tracking)
                # 스레드 안전한 연결 확인 (@FEAT:websocket-thread-safety)
                with self._connections_lock:
                    if account_id in self.connections:
                        connection = self.connections[account_id]
                        if connection.state == ConnectionState.CONNECTED:
                            logger.debug(f"계정 {account_id}는 이미 연결되어 있습니다")
                            return True
                        else:
                            logger.info(f"계정 {account_id} 연결 상태: {connection.state.value}, 재연결 시도")
                            # 기존 연결 정리 후 재연결
                            # 락을 해제하고 disconnect_account 호출 (disconnect_account가 내부적으로 락 사용)

                # 락 범위 밖에서 disconnect_account 호출
                existing_connection = self.get_connection(account_id)
                if existing_connection and existing_connection.state != ConnectionState.CONNECTED:
                    await self.disconnect_account(account_id)

                # 거래소별 WebSocket 핸들러 생성
                exchange = account.exchange.upper()

                if exchange == 'BINANCE':
                    from app.services.exchanges.binance_websocket import BinanceWebSocket
                    handler = BinanceWebSocket(account, self)
                elif exchange == 'BYBIT':
                    from app.services.exchanges.bybit_websocket import BybitWebSocket
                    handler = BybitWebSocket(account, self)
                else:
                    logger.error(f"❌ 지원하지 않는 거래소: {exchange}")
                    return False

                # 연결 객체 생성 (상태 추적 활성화)
                print(f"DEBUG: Creating WebSocketConnection")
                connection = WebSocketConnection(account_id, exchange, handler)
                connection.set_state(ConnectionState.CONNECTING)
                print(f"DEBUG: WebSocketConnection created, about to call handler.connect()")

                # WebSocket 연결 (HANDSHAKE FIRST - @FEAT:websocket-handshake-fix)
                # 중요: 연결 객체 등록 전에 WebSocket 핸드셰이크를 먼저 완료해야 함
                # 이전 버전의 버그: 핸드셰이크 실패 시에도 연결이 등록되어 고스트 연결 발생
                print(f"DEBUG: Right before await handler.connect()")
                try:
                    await handler.connect()
                    print(f"DEBUG: handler.connect() completed successfully")
                except Exception as inner_e:
                    print(f"DEBUG: Inner exception caught: {inner_e}")
                    raise inner_e

                # 연결 성공: 상태 전이 및 등록
                connection.set_state(ConnectionState.CONNECTED)
                self._add_connection(account_id, connection)  # 스레드 안전한 등록

                logger.info(f"✅ WebSocket 연결 생성 완료 - 계정: {account_id}, 거래소: {exchange}")
                print(f"DEBUG: About to return True")
                return True

        except Exception as e:
            print(f"DEBUG: Exception caught in connect_account: {e}")
            # 핸드셰이크 실패 시 상태 관리 (@FEAT:websocket-state-tracking)
            if 'connection' in locals():
                connection.set_state(ConnectionState.ERROR, str(e))
                # 오류 상태인 연결은 등록하지 않음
                logger.error(f"❌ WebSocket 핸드셰이크 실패 - 계정: {account_id}, 오류: {e}")
            else:
                logger.error(f"❌ WebSocket 연결 생성 실패 - 계정: {account_id}, 오류: {e}")
            print(f"DEBUG: About to return False from exception handler")
            return False

        # This line should never be reached due to explicit returns above
        logger.error(f"❌ connect_account reached unexpected end point - 계정: {account_id}")
        return False

    # @FEAT:order-tracking @COMP:service @TYPE:core
    async def disconnect_account(self, account_id: int):
        """계정의 WebSocket 연결 종료

        Args:
            account_id: 계정 ID
        """
        try:
            # 스레드 안전한 연결 가져오기 (@FEAT:websocket-thread-safety)
            connection = self.get_connection(account_id)
            if not connection:
                return

            # 상태 전이: CONNECTED -> DISCONNECTING (@FEAT:websocket-state-tracking)
            if connection.state == ConnectionState.CONNECTED:
                connection.set_state(ConnectionState.DISCONNECTING)

            # WebSocket 연결 종료
            if connection.handler and hasattr(connection.handler, 'disconnect'):
                await connection.handler.disconnect()

            # 상태 전이: DISCONNECTING -> DISCONNECTED
            connection.set_state(ConnectionState.DISCONNECTED)

            # 스레드 안전한 연결 제거 (@FEAT:websocket-thread-safety)
            self._remove_connection(account_id)

            logger.info(f"🔌 WebSocket 연결 종료 - 계정: {account_id}")

        except Exception as e:
            logger.error(f"❌ WebSocket 연결 종료 실패 - 계정: {account_id}, 오류: {e}")
            # 실패 시에도 상태를 ERROR로 설정
            if 'connection' in locals() and connection:
                connection.set_state(ConnectionState.ERROR, str(e))

    # @FEAT:order-tracking @COMP:service @TYPE:core
    async def subscribe_symbol(self, account_id: int, symbol: str):
        """심볼 구독 추가 (카운트 증가)

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼
        """
        key = (account_id, symbol)

        # 동시성 제어
        with self._subscription_lock:
            current_count = self.symbol_subscriptions.get(key, 0)
            self.symbol_subscriptions[key] = current_count + 1

            # 첫 구독인 경우에만 실제 구독 요청
            is_first_subscription = (current_count == 0)

        if is_first_subscription:
            connection = self.connections.get(account_id)
            if connection and connection.is_connected:
                connection.subscribed_symbols.add(symbol)
                logger.info(f"📊 심볼 구독 추가 - 계정: {account_id}, 심볼: {symbol}")
            else:
                logger.warning(f"⚠️ WebSocket 연결 없음 - 계정: {account_id}, 심볼: {symbol}")
        else:
            logger.debug(f"📊 심볼 구독 카운트 증가 - 계정: {account_id}, 심볼: {symbol}, 카운트: {self.symbol_subscriptions[key]}")

    # @FEAT:order-tracking @COMP:service @TYPE:core
    async def unsubscribe_symbol(self, account_id: int, symbol: str):
        """심볼 구독 제거 (카운트 감소)

        Args:
            account_id: 계정 ID
            symbol: 거래 심볼
        """
        key = (account_id, symbol)

        # 동시성 제어
        with self._subscription_lock:
            current_count = self.symbol_subscriptions.get(key, 0)

            if current_count <= 0:
                logger.warning(f"⚠️ 구독 카운트가 이미 0입니다 - 계정: {account_id}, 심볼: {symbol}")
                return

            new_count = current_count - 1
            self.symbol_subscriptions[key] = new_count

            # 마지막 구독 해제인 경우에만 실제 구독 해제
            is_last_unsubscription = (new_count == 0)

        if is_last_unsubscription:
            connection = self.connections.get(account_id)
            if connection and connection.is_connected:
                connection.subscribed_symbols.discard(symbol)
                logger.info(f"📊 심볼 구독 제거 - 계정: {account_id}, 심볼: {symbol}")

            # 카운트가 0이면 딕셔너리에서 제거 (메모리 절약)
            with self._subscription_lock:
                if key in self.symbol_subscriptions:
                    del self.symbol_subscriptions[key]
        else:
            logger.debug(f"📊 심볼 구독 카운트 감소 - 계정: {account_id}, 심볼: {symbol}, 카운트: {new_count}")

    # @FEAT:order-tracking @COMP:service @TYPE:core
    async def auto_reconnect(self, account_id: int, retry_count: int = 0):
        """자동 재연결 (exponential backoff)

        Args:
            account_id: 계정 ID
            retry_count: 재시도 횟수
        """
        max_retries = 10
        if retry_count >= max_retries:
            logger.error(f"❌ 최대 재연결 시도 초과 - 계정: {account_id}, 연결 객체 제거")

            # 연결 객체 제거하여 health check에서 재시도 가능하도록
            if account_id in self.connections:
                connection = self.connections[account_id]
                connection.is_connected = False
                del self.connections[account_id]

            # 텔레그램 알림
            try:
                from app.services.telegram import telegram_service
                if telegram_service.is_enabled():
                    telegram_service.send_error_alert(
                        "WebSocket 연결 실패",
                        f"계정 {account_id}의 WebSocket 연결이 10회 실패 후 중단되었습니다.\n"
                        f"health check에서 자동으로 재시도합니다."
                    )
            except Exception:
                pass

            return

        # Exponential backoff: 1, 2, 4, 8, 16, 32, 60, 60, 60, ...
        wait_seconds = min(2 ** retry_count, 60)

        logger.info(f"🔄 WebSocket 재연결 시도 ({retry_count + 1}/{max_retries}) - 계정: {account_id}, 대기: {wait_seconds}초")
        await asyncio.sleep(wait_seconds)

        success = await self.connect_account(account_id)
        if success:
            logger.info(f"✅ WebSocket 재연결 성공 - 계정: {account_id}")

            # 기존 구독 복원
            connection = self.connections.get(account_id)
            if connection:
                for symbol in connection.subscribed_symbols:
                    await self.subscribe_symbol(account_id, symbol)
        else:
            # 재시도
            await self.auto_reconnect(account_id, retry_count + 1)

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    async def keep_alive(self, account_id: int):
        """Ping/Pong keep-alive (30초 주기)

        Args:
            account_id: 계정 ID
        """
        while self._running:
            try:
                connection = self.connections.get(account_id)
                if not connection or not connection.is_connected:
                    break

                # Ping 전송 (거래소별 구현에 위임)
                if hasattr(connection.handler, 'ping'):
                    await connection.handler.ping()

                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"❌ Keep-alive 오류 - 계정: {account_id}, 오류: {e}")
                break

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    # @FEAT:websocket-thread-safety @COMP:service @TYPE:synchronization
    def get_connection(self, account_id: int) -> Optional[WebSocketConnection]:
        """계정의 WebSocket 연결 반환 (스레드 안전)

        Args:
            account_id: 계정 ID

        Returns:
            Optional[WebSocketConnection]: 연결 객체
        """
        with self._connections_lock:
            return self.connections.get(account_id)

    # @FEAT:websocket-thread-safety @COMP:service @TYPE:synchronization
    def _add_connection(self, account_id: int, connection: WebSocketConnection) -> None:
        """연결 객체 추가 (내부 스레드 안전 메서드)

        Args:
            account_id: 계정 ID
            connection: WebSocket 연결 객체
        """
        with self._connections_lock:
            self.connections[account_id] = connection

    # @FEAT:websocket-thread-safety @COMP:service @TYPE:synchronization
    def _remove_connection(self, account_id: int) -> Optional[WebSocketConnection]:
        """연결 객체 제거 (내부 스레드 안전 메서드)

        Args:
            account_id: 계정 ID

        Returns:
            Optional[WebSocketConnection]: 제거된 연결 객체
        """
        with self._connections_lock:
            return self.connections.pop(account_id, None)

    # @FEAT:websocket-thread-safety @COMP:service @TYPE:synchronization
    def _get_all_connections(self) -> Dict[int, WebSocketConnection]:
        """모든 연결 객체 반환 (내부 스레드 안전 메서드)

        Returns:
            Dict[int, WebSocketConnection]: 모든 연결 객체의 복사본
        """
        with self._connections_lock:
            return self.connections.copy()

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    # @FEAT:websocket-state-tracking @COMP:service @TYPE:validation
    def get_stats(self) -> Dict:
        """WebSocket 관리자 통계 (향상된 상태 추적 포함)

        Returns:
            Dict: 통계 정보 (상태별 연결 수 포함)
        """
        # 스레드 안전한 상태별 연결 수 집계 (@FEAT:websocket-thread-safety)
        connections_copy = self._get_all_connections()
        state_counts = {}
        healthy_count = 0

        for connection in connections_copy.values():
            state = connection.state.value
            state_counts[state] = state_counts.get(state, 0) + 1
            if connection.is_healthy():
                healthy_count += 1

        return {
            'running': self._running,
            'total_connections': len(connections_copy),
            'state_breakdown': state_counts,
            'healthy_connections': healthy_count,
            'active_connections': sum(1 for c in connections_copy.values() if c.is_connected),
            'total_subscriptions': sum(self.symbol_subscriptions.values()),
            'unique_symbols': len(self.symbol_subscriptions)
        }

    # @FEAT:websocket-state-tracking @COMP:service @TYPE:validation
    def get_connection_details(self) -> Dict:
        """모든 연결의 상세 정보 반환 (@FEAT:websocket-state-tracking)

        Returns:
            Dict: 계정별 연결 상세 정보
        """
        # 스레드 안전한 연결 정보 반환 (@FEAT:websocket-thread-safety)
        connections_copy = self._get_all_connections()
        return {
            account_id: connection.get_connection_info()
            for account_id, connection in connections_copy.items()
        }

    # @FEAT:websocket-state-tracking @COMP:service @TYPE:validation
    def get_unhealthy_connections(self) -> Dict:
        """상태 불량 연결 목록 반환 (@FEAT:websocket-state-tracking)

        Returns:
            Dict: 상태 불량 연결 정보
        """
        # 스레드 안전한 상태 불량 연결 검사 (@FEAT:websocket-thread-safety)
        connections_copy = self._get_all_connections()
        unhealthy = {}
        for account_id, connection in connections_copy.items():
            if not connection.is_healthy():
                unhealthy[account_id] = connection.get_connection_info()
        return unhealthy
