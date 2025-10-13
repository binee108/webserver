"""
WebSocket 연결 관리자

계정별 WebSocket 연결 풀을 관리하고 자동 재연결 및 keep-alive를 제공합니다.

@FEAT:order-tracking @COMP:service @TYPE:websocket-integration
"""

import asyncio
import logging
import threading
from typing import Dict, Optional, Set
from threading import Thread
from flask import Flask

from app.models import Account

logger = logging.getLogger(__name__)


# @FEAT:order-tracking @COMP:service @TYPE:websocket-integration
class WebSocketConnection:
    """단일 WebSocket 연결 래퍼"""

    def __init__(self, account_id: int, exchange: str, handler: object):
        self.account_id = account_id
        self.exchange = exchange
        self.handler = handler  # BinanceWebSocket or BybitWebSocket
        self.is_connected = False
        self.reconnect_count = 0
        self.subscribed_symbols: Set[str] = set()


# @FEAT:order-tracking @COMP:service @TYPE:websocket-integration
class WebSocketManager:
    """WebSocket 연결 풀 관리자

    핵심 기능:
    - 계정별 WebSocket 연결 관리
    - 자동 재연결 (exponential backoff)
    - Ping/Pong keep-alive
    - 심볼 구독 관리 (카운트 기반)
    """

    def __init__(self, app: Flask):
        self.app = app
        self.connections: Dict[int, WebSocketConnection] = {}  # {account_id: connection}
        self.symbol_subscriptions: Dict[tuple, int] = {}  # {(account_id, symbol): count}
        self._subscription_lock = threading.Lock()  # 구독 카운트 동시성 제어
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
            # 모든 연결 닫기
            for account_id in list(self.connections.keys()):
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

                # 이미 연결된 경우 스킵
                if account_id in self.connections:
                    logger.debug(f"계정 {account_id}는 이미 연결되어 있습니다")
                    return True

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

                # 연결 생성
                connection = WebSocketConnection(account_id, exchange, handler)
                self.connections[account_id] = connection

                # WebSocket 연결
                await handler.connect()
                connection.is_connected = True

                logger.info(f"✅ WebSocket 연결 생성 완료 - 계정: {account_id}, 거래소: {exchange}")
                return True

        except Exception as e:
            logger.error(f"❌ WebSocket 연결 생성 실패 - 계정: {account_id}, 오류: {e}")
            return False

    # @FEAT:order-tracking @COMP:service @TYPE:core
    async def disconnect_account(self, account_id: int):
        """계정의 WebSocket 연결 종료

        Args:
            account_id: 계정 ID
        """
        try:
            connection = self.connections.get(account_id)
            if not connection:
                return

            # WebSocket 연결 종료
            if connection.handler and hasattr(connection.handler, 'disconnect'):
                await connection.handler.disconnect()

            connection.is_connected = False
            del self.connections[account_id]

            logger.info(f"🔌 WebSocket 연결 종료 - 계정: {account_id}")

        except Exception as e:
            logger.error(f"❌ WebSocket 연결 종료 실패 - 계정: {account_id}, 오류: {e}")

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
    def get_connection(self, account_id: int) -> Optional[WebSocketConnection]:
        """계정의 WebSocket 연결 반환

        Args:
            account_id: 계정 ID

        Returns:
            Optional[WebSocketConnection]: 연결 객체
        """
        return self.connections.get(account_id)

    # @FEAT:order-tracking @COMP:service @TYPE:helper
    def get_stats(self) -> Dict:
        """WebSocket 관리자 통계

        Returns:
            Dict: 통계 정보
        """
        return {
            'running': self._running,
            'total_connections': len(self.connections),
            'active_connections': sum(1 for c in self.connections.values() if c.is_connected),
            'total_subscriptions': sum(self.symbol_subscriptions.values()),
            'unique_symbols': len(self.symbol_subscriptions)
        }
