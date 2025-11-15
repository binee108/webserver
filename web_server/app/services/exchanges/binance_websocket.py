"""
Binance Futures User Data Stream WebSocket 구현

Binance Futures User Data Stream을 통해 주문 체결 이벤트를 실시간으로 수신합니다.

@FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:websocket-integration
"""

import asyncio
import json
import logging
import time
from typing import Optional, TYPE_CHECKING

import aiohttp
import websockets

from app.models import Account

if TYPE_CHECKING:
    from app.services.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


# @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:websocket-integration
class BinanceWebSocket:
    """Binance Futures User Data Stream WebSocket 클라이언트

    핵심 기능:
    - Listen Key 생성/갱신 (30분마다)
    - ORDER_TRADE_UPDATE 이벤트 수신
    - OrderFillMonitor에 이벤트 전달
    """

    BASE_URL = 'https://fapi.binance.com'
    WS_URL = 'wss://fstream.binance.com/ws'

    def __init__(self, account: Account, manager: 'WebSocketManager'):
        self.account = account
        self.manager = manager
        self.listen_key: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._renew_task: Optional[asyncio.Task] = None

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:integration
    async def create_listen_key(self) -> str:
        """Listen Key 생성

        Returns:
            str: Listen Key
        """
        try:
            url = f"{self.BASE_URL}/fapi/v1/listenKey"
            headers = {
                'X-MBX-APIKEY': self.account.api_key
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"Listen Key 생성 실패: {response.status} - {text}")

                    data = await response.json()
                    listen_key = data.get('listenKey')

                    if not listen_key:
                        raise Exception("Listen Key가 응답에 없습니다")

                    logger.info(f"✅ Listen Key 생성 완료 - 계정: {self.account.id}")
                    return listen_key

        except Exception as e:
            logger.error(f"❌ Listen Key 생성 실패 - 계정: {self.account.id}, 오류: {e}")
            raise

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def renew_listen_key(self):
        """Listen Key 갱신 (30분마다)"""
        while self._running:
            try:
                await asyncio.sleep(30 * 60)  # 30분

                if not self._running:
                    break

                logger.info(f"🔄 Listen Key 갱신 시도 - 계정: {self.account.id}")

                # PUT 요청으로 Listen Key 갱신
                async with aiohttp.ClientSession() as session:
                    headers = {'X-MBX-APIKEY': self.account.api_key}
                    url = f"{self.BASE_URL}/fapi/v1/listenKey"

                    async with session.put(url, headers=headers) as response:
                        if response.status == 200:
                            logger.info(f"✅ Listen Key 갱신 성공 - 계정: {self.account.id}")
                        else:
                            text = await response.text()
                            logger.error(f"❌ Listen Key 갱신 실패: {response.status} - {text}")

                            # 재연결 스케줄링 (루프는 계속 실행)
                            asyncio.create_task(
                                self.manager.auto_reconnect(self.account.id, 0)
                            )
                            # continue를 사용하여 루프 유지 (30분 후 재시도)

            except asyncio.CancelledError:
                logger.info(f"Listen Key 갱신 태스크 취소됨 - 계정: {self.account.id}")
                break
            except Exception as e:
                logger.error(f"❌ Listen Key 갱신 오류: {e}", exc_info=True)
                # 오류 발생해도 루프 계속 실행

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def connect(self):
        """WebSocket 연결"""
        try:
            # 기존 갱신 태스크 취소
            if hasattr(self, '_renew_task') and self._renew_task and not self._renew_task.done():
                self._renew_task.cancel()
                try:
                    await self._renew_task
                except asyncio.CancelledError as e:
                    logger.debug(f"갱신 태스크 취소 완료 - 계정: {self.account.id}: {e}")

            # Listen Key 생성
            self.listen_key = await self.create_listen_key()
            if not self.listen_key:
                raise Exception("Listen Key 생성 실패")

            # WebSocket 연결
            ws_url = f"wss://fstream.binance.com/ws/{self.listen_key}"
            self.ws = await websockets.connect(ws_url)

            self._running = True
            logger.info(f"✅ Binance WebSocket 연결 완료 - 계정: {self.account.id}")

            # 갱신 태스크 재시작
            self._renew_task = asyncio.create_task(self.renew_listen_key())

            # 메시지 수신 시작
            await self._receive_messages()

        except Exception as e:
            logger.error(f"❌ Binance WebSocket 연결 실패: {e}", exc_info=True)
            raise

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def disconnect(self):
        """WebSocket 연결 종료"""
        self._running = False

        if self._renew_task:
            self._renew_task.cancel()
            try:
                await self._renew_task
            except asyncio.CancelledError as e:
                logger.debug(f"갱신 태스크 취소 완료 (disconnect) - 계정: {self.account.id}: {e}")

        if self.ws:
            await self.ws.close()

        logger.info(f"🔌 Binance WebSocket 연결 종료 - 계정: {self.account.id}")

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
                    if '"e":"ORDER_TRADE_UPDATE"' in message:
                        logger.critical(f"🚨 체결 이벤트 파싱 실패! 메시지: {message}")

                        # 텔레그램 알림
                        try:
                            from app.services.telegram import telegram_service
                            if telegram_service.is_enabled():
                                telegram_service.send_error_alert(
                                    "WebSocket 파싱 실패",
                                    f"Binance 체결 이벤트 파싱 실패\n계정: {self.account.id}\n메시지: {message[:500]}"
                                )
                        except Exception as e:
                            logger.debug(f"텔레그램 알림 실패 (파싱 실패): {e}")
                except Exception as e:
                    logger.error(f"❌ 메시지 처리 오류: {e}", exc_info=True)

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"⚠️ Binance WebSocket 연결 끊김 - 계정: {self.account.id}")
            if self._running:
                # 재연결 시도
                await self.manager.auto_reconnect(self.account.id, 0)
        except Exception as e:
            logger.error(f"❌ Binance WebSocket 수신 오류 - 계정: {self.account.id}, 오류: {e}")
            if self._running:
                await self.manager.auto_reconnect(self.account.id, 0)

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:core
    async def on_message(self, data: dict):
        """WebSocket 메시지 수신 처리

        Args:
            data: WebSocket 메시지 데이터
        """
        try:
            event_type = data.get('e')

            if event_type == 'ORDER_TRADE_UPDATE':
                await self._handle_order_update(data['o'])
            elif event_type == 'ACCOUNT_UPDATE':
                # 계정 업데이트 이벤트 (선택적 처리)
                logger.debug(f"📊 계정 업데이트 이벤트 수신 - 계정: {self.account.id}")
            else:
                logger.debug(f"📊 알 수 없는 이벤트: {event_type}")

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
            symbol = order_data.get('s')  # BTCUSDT
            order_id = str(order_data.get('i'))  # 주문 ID
            status = order_data.get('X')  # NEW, FILLED, CANCELED, etc.

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

    # @FEAT:order-tracking @FEAT:exchange-integration @COMP:service @TYPE:helper
    async def ping(self):
        """Ping 전송 (keep-alive)"""
        if self.ws and not self.ws.closed:
            await self.ws.ping()
