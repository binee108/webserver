"""
PublicWebSocketHandler - 실시간 가격 데이터 Public WebSocket 핸들러

거래소별 Public WebSocket 연결을 관리하고 실시간 가격 데이터를 정규화하여 제공

주요 기능:
- Binance/Bybit Public WebSocket 연결 관리
- 실시간 가격 데이터 수신 및 정규화
- 가격 데이터 캐싱 및 조회
- 심볼별 구독 관리
- 에러 처리 및 자동 재연결

아키텍처 개선 사항:
- 전략 패턴을 사용한 데이터 정규화 분리
- 설정 관리 분리 및 중앙화
- 성능 모니터링 및 메트릭 수집
- 향상된 에러 처리 및 로깅

@FEAT:websocket-integration @COMP:public-websocket @TYPE:price-data
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import websockets

# 내부 모듈 import
from .config import config_manager, ConnectionType
from .data_normalizers import DataNormalizerFactory
from .models import PriceQuote, ConnectionState, ConnectionMetrics

logger = logging.getLogger(__name__)


class PublicWebSocketHandler:
    """
    실시간 가격 데이터 Public WebSocket 핸들러

    역할:
    - 거래소별 Public WebSocket 연결 관리
    - 실시간 가격 데이터 수신 및 정규화
    - 가격 데이터 캐싱 및 조회
    - 심볼별 구독 관리
    - 에러 처리 및 자동 재연결
    - 성능 모니터링 및 메트릭 수집

    아키텍처 개선:
    - 전략 패턴을 사용한 데이터 정규화 분리
    - 설정 관리 분리 및 중앙화
    - 향상된 에러 처리 및 재시도 로직
    - 성능 메트릭 및 모니터링
    """

    def __init__(self, exchange: str, symbols: List[str] = None, testnet: bool = False):
        """
        PublicWebSocketHandler 초기화

        Args:
            exchange: 거래소 이름 ('binance', 'bybit')
            symbols: 구독할 심볼 목록
            testnet: 테스트넷 사용 여부

        Raises:
            ValueError: 지원하지 않는 거래소인 경우
        """
        # 거래소 검증
        if not config_manager.is_exchange_supported(exchange):
            supported = config_manager.get_custom_config('supported_exchanges',
                                                       DataNormalizerFactory.get_supported_exchanges())
            raise ValueError(f"지원하지 않는 거래소: {exchange}. 지원: {supported}")

        self.exchange = exchange.lower()
        self.testnet = testnet
        self.symbols: Set[str] = set(symbols or [])
        self.symbol_subscriptions: Set[str] = set()  # 실제 구독된 심볼

        # 연결 상태
        self.connection_state = ConnectionState.DISCONNECTED
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_count = 0

        # 데이터 캐시
        self.price_cache: Dict[str, PriceQuote] = {}
        self.cache_timestamps: Dict[str, float] = {}

        # 성능 메트릭
        self.metrics = ConnectionMetrics()

        # 콜백 함수
        self.on_price_update: Optional[Callable[[PriceQuote], None]] = None
        self.on_connection_change: Optional[Callable[[ConnectionState], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None

        # 데이터 정규화기
        self._normalizer = DataNormalizerFactory.get_normalizer(self.exchange)
        if not self._normalizer:
            raise ValueError(f"{self.exchange} 거래소에 대한 데이터 정규화기를 찾을 수 없습니다")

        # 설정
        self._config = config_manager.get_config()

        logger.info(f"✅ PublicWebSocketHandler 초기화 완료 - 거래소: {self.exchange}, "
                   f"심볼: {list(self.symbols)}, 테스트넷: {testnet}")

    @property
    def is_connected(self) -> bool:
        """연결 상태 반환"""
        return self.connection_state == ConnectionState.CONNECTED

    @property
    def subscriptions(self) -> List[str]:
        """현재 구독된 심볼 목록 반환"""
        return list(self.symbol_subscriptions)

    def _get_websocket_url(self) -> str:
        """
        거래소별 WebSocket URL 반환

        Returns:
            str: WebSocket URL
        """
        try:
            return config_manager.get_exchange_config(self.exchange, 'ws_url')
        except ValueError as e:
            logger.error(f"❌ WebSocket URL 조회 실패 - 거래소: {self.exchange}, 오류: {e}")
            raise

    def _create_subscription_message(self, symbols: List[str]) -> str:
        """
        거래소별 구독 메시지 생성

        Args:
            symbols: 구독할 심볼 목록

        Returns:
            str: 구독 메시지
        """
        try:
            if self.exchange == 'binance':
                # Binance: 개별 스트림 구독 메시지
                streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
                return json.dumps({
                    "method": "SUBSCRIBE",
                    "params": streams,
                    "id": int(time.time())
                })
            elif self.exchange == 'bybit':
                # Bybit: 구독 메시지
                return json.dumps({
                    "op": "subscribe",
                    "args": [f"tickers.{symbol}" for symbol in symbols]
                })
            else:
                raise ValueError(f"지원하지 않는 거래소: {self.exchange}")
        except Exception as e:
            logger.error(f"❌ 구독 메시지 생성 실패 - 거래소: {self.exchange}, 심볼: {symbols}, 오류: {e}")
            raise

    def _update_connection_state(self, new_state: ConnectionState) -> None:
        """
        연결 상태 업데이트 및 콜백 호출

        Args:
            new_state: 새로운 연결 상태
        """
        old_state = self.connection_state
        self.connection_state = new_state

        logger.debug(f"🔄 연결 상태 변경 - 거래소: {self.exchange}, {old_state.value} → {new_state.value}")

        # 상태 변경 콜백 호출
        if self.on_connection_change:
            try:
                self.on_connection_change(new_state)
            except Exception as e:
                logger.error(f"❌ 연결 상태 변경 콜백 오류: {e}")

        # 에러 상태에서 재연결 카운트 증가
        if new_state == ConnectionState.ERROR and old_state != ConnectionState.ERROR:
            self.metrics.reconnect_count += 1

    def _log_error(self, error: Exception, context: str = "") -> None:
        """
        에러 로깅 및 콜백 호출

        Args:
            error: 발생한 에러
            context: 에러 컨텍스트
        """
        self.metrics.errors_count += 1
        error_msg = f"❌ {context} 오류 - 거래소: {self.exchange}, 오류: {error}"
        logger.error(error_msg)

        # 에러 콜백 호출
        if self.on_error:
            try:
                self.on_error(error)
            except Exception as callback_error:
                logger.error(f"❌ 에러 콜백 처리 중 오류: {callback_error}")

    async def connect(self) -> None:
        """
        WebSocket 연결

        Raises:
            Exception: 연결 실패 시
        """
        if self.connection_state == ConnectionState.CONNECTED:
            logger.warning(f"⚠️ 이미 연결되어 있음 - 거래소: {self.exchange}")
            return

        self._update_connection_state(ConnectionState.CONNECTING)
        self._running = True

        try:
            url = self._get_websocket_url()
            logger.info(f"🔌 WebSocket 연결 시도 - 거래소: {self.exchange}, URL: {url}")

            # WebSocket 연결
            self.ws = await websockets.connect(
                url,
                ping_interval=self._config.HEARTBEAT_INTERVAL,
                ping_timeout=10,
                close_timeout=10
            )
            self._update_connection_state(ConnectionState.CONNECTED)
            self._reconnect_count = 0

            logger.info(f"✅ WebSocket 연결 성공 - 거래소: {self.exchange}")

            # 초기 심볼 구독
            if self.symbols:
                await self._subscribe_symbols(list(self.symbols))

            # 메시지 수신 시작
            asyncio.create_task(self._receive_messages())
            asyncio.create_task(self._cache_cleanup_task())

        except Exception as e:
            self._update_connection_state(ConnectionState.ERROR)
            self._log_error(e, "WebSocket 연결")
            raise

    async def disconnect(self) -> None:
        """WebSocket 연결 종료"""
        if not self.is_connected:
            return

        self._running = False
        self._update_connection_state(ConnectionState.DISCONNECTED)

        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                self._log_error(e, "WebSocket 연결 종료")
            finally:
                self.ws = None

        logger.info(f"🔌 WebSocket 연결 종료 - 거래소: {self.exchange}")

    async def _cache_cleanup_task(self) -> None:
        """캐시 정리 태스크"""
        while self._running:
            try:
                await asyncio.sleep(self._config.CACHE_CLEANUP_INTERVAL)
                if self._running:
                    self._cleanup_expired_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log_error(e, "캐시 정리")
                await asyncio.sleep(60)  # 에러 발생 시 1분 후 재시도

    async def disconnect(self) -> None:
        """WebSocket 연결 종료"""
        if not self.is_connected:
            return

        self._running = False
        self.connection_state = ConnectionState.DISCONNECTED

        if self.ws:
            await self.ws.close()
            self.ws = None

        logger.info(f"🔌 WebSocket 연결 종료 - 거래소: {self.exchange}")

    async def _subscribe_symbols(self, symbols: List[str]) -> None:
        """
        심볼 구독

        Args:
            symbols: 구독할 심볼 목록
        """
        if not self.ws or not self.is_connected:
            logger.warning("⚠️ WebSocket 연결이 없어 심볼 구독을 건너뜁니다")
            return

        try:
            message = self._create_subscription_message(symbols)

            if isinstance(message, str):
                await self.ws.send(message)
            else:
                await self.ws.send(json.dumps(message))

            # 구독 목록 업데이트
            self.symbol_subscriptions.update(symbols)

            logger.info(f"✅ 심볼 구독 완료 - 거래소: {self.exchange}, 심볼: {symbols}")

        except Exception as e:
            logger.error(f"❌ 심볼 구독 실패 - 거래소: {self.exchange}, 심볼: {symbols}, 오류: {e}")
            raise

    async def add_subscription(self, symbol: str) -> None:
        """
        새로운 심볼 구독 추가

        Args:
            symbol: 구독할 심볼
        """
        if symbol in self.symbol_subscriptions:
            logger.debug(f"📊 이미 구독된 심볼 - 거래소: {self.exchange}, 심볼: {symbol}")
            return

        await self._subscribe_symbols([symbol])
        self.symbols.add(symbol)

    async def remove_subscription(self, symbol: str) -> None:
        """
        심볼 구독 해지

        Args:
            symbol: 구독 해지할 심볼
        """
        if symbol not in self.symbol_subscriptions:
            logger.debug(f"📊 구독되지 않은 심볼 - 거래소: {self.exchange}, 심볼: {symbol}")
            return

        # TODO: 실제 구독 해지 로직 구현 (거래소별 API 호출)
        self.symbol_subscriptions.discard(symbol)
        self.symbols.discard(symbol)

        # 캐시에서도 제거
        if symbol in self.price_cache:
            del self.price_cache[symbol]
        if symbol in self.cache_timestamps:
            del self.cache_timestamps[symbol]

        logger.info(f"✅ 심볼 구독 해지 - 거래소: {self.exchange}, 심볼: {symbol}")

    async def _receive_messages(self) -> None:
        """WebSocket 메시지 수신 루프"""
        try:
            async for message in self.ws:
                if not self._running:
                    break

                try:
                    data = json.loads(message)
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 파싱 실패 - 거래소: {self.exchange}, 오류: {e}, 메시지: {message[:200]}...")

                except Exception as e:
                    logger.error(f"❌ 메시지 처리 오류 - 거래소: {self.exchange}, 오류: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"⚠️ WebSocket 연결 끊김 - 거래소: {self.exchange}")
            if self._running:
                await self._handle_reconnect()

        except Exception as e:
            logger.error(f"❌ WebSocket 수신 오류 - 거래소: {self.exchange}, 오류: {e}")
            if self._running:
                await self._handle_reconnect()

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """
        수신된 메시지 처리

        Args:
            data: WebSocket 메시지 데이터
        """
        try:
            # 가격 데이터 정규화
            price_quote = await self.normalize_price_data(data)

            if price_quote:
                # 캐싱
                await self.cache_price_data(price_quote)

                # 콜백 호출
                if self.on_price_update:
                    try:
                        await self.on_price_update(price_quote)
                    except Exception as e:
                        logger.error(f"❌ 가격 업데이트 콜백 오류: {e}")

        except Exception as e:
            logger.error(f"❌ 메시지 처리 오류 - 거래소: {self.exchange}, 오류: {e}")

    async def normalize_price_data(self, data: Dict[str, Any]) -> Optional[PriceQuote]:
        """
        거래소별 가격 데이터를 표준 PriceQuote 형식으로 정규화

        Args:
            data: 거래소별 가격 데이터

        Returns:
            Optional[PriceQuote]: 정규화된 가격 데이터
        """
        try:
            if self.exchange == 'binance':
                return self._normalize_binance_data(data)
            elif self.exchange == 'bybit':
                return self._normalize_bybit_data(data)
            else:
                logger.warning(f"⚠️ 지원하지 않는 거래소 데이터 형식: {self.exchange}")
                return None

        except Exception as e:
            logger.error(f"❌ 가격 데이터 정규화 실패 - 거래소: {self.exchange}, 오류: {e}")
            return None

    def _normalize_binance_data(self, data: Dict[str, Any]) -> Optional[PriceQuote]:
        """Binance 가격 데이터 정규화"""
        if data.get('e') != '24hrTicker':
            return None

        return PriceQuote(
            exchange="binance",
            symbol=data.get('s'),
            price=float(data.get('c', 0)),
            timestamp=data.get('E', int(time.time() * 1000)),
            volume=float(data.get('v', 0)),
            change_24h=float(data.get('P', 0))
        )

    def _normalize_bybit_data(self, data: Dict[str, Any]) -> Optional[PriceQuote]:
        """Bybit 가격 데이터 정규화"""
        if data.get('topic') != 'tickers':
            return None

        ticker_data = data.get('data', [])
        if not ticker_data:
            return None

        item = ticker_data[0] if isinstance(ticker_data, list) else ticker_data

        return PriceQuote(
            exchange="bybit",
            symbol=item.get('symbol'),
            price=float(item.get('lastPrice', 0)),
            timestamp=int(time.time() * 1000),  # Bybit는 타임스탬프가 없어 현재 시간 사용
            volume=float(item.get('volume24h', 0)),
            change_24h=float(item.get('turnover24h', 0))  # 24시간 변화율은 turnover24h로 대체
        )

    async def cache_price_data(self, quote: PriceQuote) -> None:
        """
        가격 데이터 캐싱

        Args:
            quote: 가격 데이터
        """
        # 캐시 크기 제한
        if len(self.price_cache) >= self._config.MAX_CACHE_SIZE:
            # 가장 오래된 데이터 제거
            oldest_symbol = min(self.cache_timestamps.keys(), key=lambda k: self.cache_timestamps[k])
            del self.price_cache[oldest_symbol]
            del self.cache_timestamps[oldest_symbol]

        # 데이터 캐싱
        self.price_cache[quote.symbol] = quote
        self.cache_timestamps[quote.symbol] = time.time()

        logger.debug(f"💰 가격 데이터 캐싱 - 거래소: {quote.exchange}, 심볼: {quote.symbol}, 가격: {quote.price}")

    def get_latest_price(self, symbol: str) -> Optional[PriceQuote]:
        """
        최신 가격 데이터 조회

        Args:
            symbol: 조회할 심볼

        Returns:
            Optional[PriceQuote]: 최신 가격 데이터
        """
        quote = self.price_cache.get(symbol)

        if quote:
            # 캐시 만료 확인
            cache_time = self.cache_timestamps.get(symbol, 0)
            if time.time() - cache_time > self._config.CACHE_EXPIRE_TIME:
                # 만료된 캐시 제거
                del self.price_cache[symbol]
                del self.cache_timestamps[symbol]
                logger.debug(f"⏰ 만료된 캐시 제거 - 심볼: {symbol}")
                return None

        return quote

    def get_all_cached_prices(self) -> Dict[str, PriceQuote]:
        """
        모든 캐시된 가격 데이터 반환

        Returns:
            Dict[str, PriceQuote]: 캐시된 가격 데이터
        """
        # 만료된 데이터 필터링
        current_time = time.time()
        expired_symbols = []

        for symbol, cache_time in self.cache_timestamps.items():
            if current_time - cache_time > self._config.CACHE_EXPIRE_TIME:
                expired_symbols.append(symbol)

        # 만료된 데이터 제거
        for symbol in expired_symbols:
            del self.price_cache[symbol]
            del self.cache_timestamps[symbol]

        return self.price_cache.copy()

    async def _handle_reconnect(self) -> None:
        """자동 재연결 처리"""
        if self._reconnect_count >= self._config.MAX_RECONNECT_ATTEMPTS:
            logger.error(f"❌ 최대 재연결 시도 횟수 초과 - 거래소: {self.exchange}")
            self.connection_state = ConnectionState.ERROR
            return

        self._reconnect_count += 1
        delay = self._config.RECONNECT_DELAY * self._reconnect_count

        logger.info(f"🔄 {delay}초 후 재연결 시도 - 거래소: {self.exchange} ({self._reconnect_count}/{self._config.MAX_RECONNECT_ATTEMPTS})")

        await asyncio.sleep(delay)

        try:
            # 기존 연결 정리
            if self.ws:
                await self.ws.close()
                self.ws = None

            # 재연결
            await self.connect()

        except Exception as e:
            logger.error(f"❌ 재연결 실패 - 거래소: {self.exchange}, 오류: {e}")
            self.connection_state = ConnectionState.ERROR

    def get_connection_info(self) -> Dict[str, Any]:
        """
        연결 정보 반환

        Returns:
            Dict[str, Any]: 연결 정보
        """
        return {
            'exchange': self.exchange,
            'connection_state': self.connection_state.value,
            'is_connected': self.is_connected,
            'symbols': list(self.symbols),
            'subscriptions': list(self.symbol_subscriptions),
            'cached_symbols': list(self.price_cache.keys()),
            'reconnect_count': self._reconnect_count,
            'cache_size': len(self.price_cache)
        }