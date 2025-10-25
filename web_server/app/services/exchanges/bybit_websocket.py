"""
Bybit Private WebSocket 구현

Bybit Private WebSocket을 통해 주문 체결 이벤트를 실시간으로 수신합니다.

@FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:websocket-integration
"""

import asyncio
import hmac
import json
import logging
import time
from typing import Optional, TYPE_CHECKING

import websockets

from app.models import Account

if TYPE_CHECKING:
    from app.services.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


# @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:websocket-integration
class BybitWebSocket:
    """Bybit Private WebSocket 클라이언트

    핵심 기능:
    - HMAC SHA256 인증
    - order 토픽 구독
    - 주문 상태 변경 이벤트 수신
    """

    WS_URL = 'wss://stream.bybit.com/v5/private'

    def __init__(self, account: Account, manager: 'WebSocketManager'):
        self.account = account
        self.manager = manager
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._authenticated = False

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:integration
    async def authenticate(self):
        """HMAC SHA256 인증

        Bybit 인증 방식:
        1. 현재 타임스탬프 (밀리초)
        2. expires = timestamp + 10000
        3. signature = HMAC-SHA256(api_key + expires, secret)
        4. {"op": "auth", "args": [api_key, expires, signature]}
        """
        try:
            # 타임스탬프 생성 (밀리초)
            timestamp = int(time.time() * 1000)
            expires = timestamp + 10000

            # 서명 생성
            message = f"GET/realtime{expires}"
            signature = hmac.new(
                self.account.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                digestmod='sha256'
            ).hexdigest()

            # 인증 요청
            auth_message = {
                "op": "auth",
                "args": [self.account.api_key, expires, signature]
            }

            await self.ws.send(json.dumps(auth_message))

            # 인증 응답 대기
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)

            if data.get('success'):
                self._authenticated = True
                logger.info(f"✅ Bybit 인증 성공 - 계정: {self.account.id}")
            else:
                raise Exception(f"인증 실패: {data}")

        except Exception as e:
            logger.error(f"❌ Bybit 인증 실패 - 계정: {self.account.id}, 오류: {e}")
            raise

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def keep_alive(self):
        """Ping 메시지 전송 (20초마다)"""
        while self._running:
            try:
                await asyncio.sleep(20)

                if not self._running:
                    break

                if self.ws and not self.ws.closed:
                    await self.ws.send(json.dumps({"op": "ping"}))
                    logger.debug(f"📡 Ping 전송 - 계정: {self.account.id}")
                else:
                    logger.warning(f"⚠️ WebSocket 연결이 닫혀있음 - 계정: {self.account.id}")

                    # 재연결 스케줄링 (루프는 계속 실행)
                    asyncio.create_task(
                        self.manager.auto_reconnect(self.account.id, 0)
                    )

            except asyncio.CancelledError:
                logger.info(f"Keep-alive 태스크 취소됨 - 계정: {self.account.id}")
                break
            except Exception as e:
                logger.error(f"❌ Keep-alive 오류: {e}", exc_info=True)
                # 오류 발생해도 루프 계속 실행

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def connect(self):
        """WebSocket 연결 및 인증"""
        try:
            # 기존 keep-alive 태스크 취소
            if hasattr(self, '_keep_alive_task') and self._keep_alive_task and not self._keep_alive_task.done():
                self._keep_alive_task.cancel()
                try:
                    await self._keep_alive_task
                except asyncio.CancelledError as e:
                    logger.debug(f"Keep-alive 태스크 취소 완료 - 계정: {self.account.id}: {e}")

            # WebSocket 연결
            self.ws = await websockets.connect(self.WS_URL)
            self._running = True

            logger.info(f"✅ Bybit WebSocket 연결 완료 - 계정: {self.account.id}")

            # 인증
            await self.authenticate()

            # order 토픽 구독
            await self.subscribe_orders()

            # Keep-alive 태스크 시작
            self._keep_alive_task = asyncio.create_task(self.keep_alive())

            # 메시지 수신 태스크 시작
            asyncio.create_task(self._receive_messages())

        except Exception as e:
            logger.error(f"❌ Bybit WebSocket 연결 실패 - 계정: {self.account.id}, 오류: {e}")
            raise

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def disconnect(self):
        """WebSocket 연결 종료"""
        self._running = False

        # Keep-alive 태스크 취소
        if hasattr(self, '_keep_alive_task') and self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError as e:
                logger.debug(f"Keep-alive 태스크 취소 완료 (disconnect) - 계정: {self.account.id}: {e}")

        if self.ws:
            await self.ws.close()

        logger.info(f"🔌 Bybit WebSocket 연결 종료 - 계정: {self.account.id}")

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:integration
    async def subscribe_orders(self):
        """order 토픽 구독"""
        try:
            subscribe_message = {
                "op": "subscribe",
                "args": ["order"]
            }

            await self.ws.send(json.dumps(subscribe_message))
            logger.info(f"✅ Bybit order 토픽 구독 완료 - 계정: {self.account.id}")

        except Exception as e:
            logger.error(f"❌ Bybit order 토픽 구독 실패 - 계정: {self.account.id}, 오류: {e}")
            raise

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def _receive_messages(self):
        """WebSocket 메시지 수신 루프"""
        try:
            async for message in self.ws:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    await self.on_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 파싱 실패: {e}, 메시지: {message[:200]}...")

                    # 체결 이벤트인 경우 Critical 로그 + 텔레그램 알림
                    if '"topic":"order"' in message:
                        logger.critical(f"🚨 체결 이벤트 파싱 실패! 메시지: {message}")

                        # 텔레그램 알림
                        try:
                            from app.services.telegram import telegram_service
                            if telegram_service.is_enabled():
                                telegram_service.send_error_alert(
                                    "WebSocket 파싱 실패",
                                    f"Bybit 체결 이벤트 파싱 실패\n계정: {self.account.id}\n메시지: {message[:500]}"
                                )
                        except Exception as e:
                            logger.debug(f"텔레그램 알림 실패 (파싱 실패): {e}")
                except Exception as e:
                    logger.error(f"❌ 메시지 처리 오류: {e}", exc_info=True)

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"⚠️ Bybit WebSocket 연결 끊김 - 계정: {self.account.id}")
            if self._running:
                # 재연결 시도
                await self.manager.auto_reconnect(self.account.id, 0)
        except Exception as e:
            logger.error(f"❌ Bybit WebSocket 수신 오류 - 계정: {self.account.id}, 오류: {e}")
            if self._running:
                await self.manager.auto_reconnect(self.account.id, 0)

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def on_message(self, data: dict):
        """WebSocket 메시지 수신 처리

        Args:
            data: WebSocket 메시지 데이터
        """
        try:
            topic = data.get('topic')

            if topic == 'order':
                # 주문 업데이트 이벤트
                order_list = data.get('data', [])
                for order_data in order_list:
                    await self._handle_order_update(order_data)
            elif data.get('op') == 'pong':
                # Pong 응답
                logger.debug(f"🏓 Pong 수신 - 계정: {self.account.id}")
            else:
                logger.debug(f"📊 알 수 없는 메시지: {data}")

        except Exception as e:
            logger.error(f"❌ 메시지 처리 오류 - 계정: {self.account.id}, 오류: {e}")

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:integration @DEPS:order-fill-monitor
    async def _handle_order_update(self, order_data: dict):
        """주문 업데이트 처리 → OrderFillMonitor에 위임

        Args:
            order_data: 주문 데이터
        """
        try:
            # 주문 정보 추출
            symbol = order_data.get('symbol')  # BTCUSDT
            order_id = str(order_data.get('orderId'))  # 주문 ID
            status = order_data.get('orderStatus')  # New, Filled, Cancelled, etc.

            logger.info(
                f"📦 주문 업데이트 수신 - 계정: {self.account.id}, "
                f"심볼: {symbol}, 주문 ID: {order_id}, 상태: {status}"
            )

            # OrderFillMonitor에 전달
            from app.services.order_fill_monitor import order_fill_monitor
            await order_fill_monitor.on_order_update(
                account_id=self.account.id,
                exchange_order_id=order_id,
                symbol=symbol,
                status=status
            )

        except Exception as e:
            logger.error(f"❌ 주문 업데이트 처리 오류 - 계정: {self.account.id}, 오류: {e}")
