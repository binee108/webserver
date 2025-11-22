"""
PublicWebSocketHandler 확장 테스트

리팩토링된 PublicWebSocketHandler의 추가 기능 테스트

@FEAT:websocket-integration @COMP:public-websocket @TYPE:test
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from app.services.websocket.public_websocket_handler import PublicWebSocketHandler
from app.services.websocket.models import PriceQuote, ConnectionState


class TestPublicWebSocketHandlerExtended:
    """PublicWebSocketHandler 확장 기능 테스트"""

    def setup_method(self):
        """각 테스트 전 설정"""
        self.handler = PublicWebSocketHandler(exchange="binance", symbols=["BTCUSDT"])

    def test_handler_initialization_with_testnet(self):
        """testnet 옵션을 사용한 핸들러 초기화 테스트"""
        # Arrange & Act
        handler = PublicWebSocketHandler(exchange="bybit", symbols=["ETHUSDT"], testnet=True)

        # Assert
        assert handler.exchange == "bybit"
        assert handler.testnet == True
        assert "ETHUSDT" in handler.symbols

    def test_handler_initialization_unsupported_exchange(self):
        """지원하지 않는 거래소로 초기화 테스트"""
        # Arrange, Act & Assert
        with pytest.raises(ValueError, match="지원하지 않는 거래소: unsupported"):
            PublicWebSocketHandler(exchange="unsupported", symbols=["BTCUSDT"])

    def test_get_websocket_url(self):
        """WebSocket URL 조회 테스트"""
        # Arrange & Act
        url = self.handler._get_websocket_url()

        # Assert
        assert url == "wss://stream.binance.com:9443/ws"

    def test_get_websocket_url_testnet(self):
        """Testnet WebSocket URL 조회 테스트"""
        # Arrange
        handler = PublicWebSocketHandler(exchange="bybit", testnet=True)

        # Act
        url = handler._get_websocket_url()

        # Assert
        assert url == "wss://stream-testnet.bybit.com/v5/public/linear"

    def test_create_subscription_message_binance(self):
        """Binance 구독 메시지 생성 테스트"""
        # Arrange & Act
        message = self.handler._create_subscription_message(["BTCUSDT", "ETHUSDT"])

        # Assert
        import json
        message_data = json.loads(message)
        assert message_data["method"] == "SUBSCRIBE"
        assert "btcusdt@ticker" in message_data["params"]
        assert "ethusdt@ticker" in message_data["params"]

    def test_create_subscription_message_bybit(self):
        """Bybit 구독 메시지 생성 테스트"""
        # Arrange
        handler = PublicWebSocketHandler(exchange="bybit")

        # Act
        message = handler._create_subscription_message(["BTCUSDT"])

        # Assert
        import json
        message_data = json.loads(message)
        assert message_data["op"] == "subscribe"
        assert "tickers.BTCUSDT" in message_data["args"]

    def test_create_subscription_message_unsupported_exchange(self):
        """지원하지 않는 거래소 구독 메시지 생성 테스트"""
        # Arrange
        handler = PublicWebSocketHandler(exchange="binance")
        handler.exchange = "unsupported"  # 강제로 지원하지 않는 거래소 설정

        # Act & Assert
        with pytest.raises(ValueError, match="지원하지 않는 거래소: unsupported"):
            handler._create_subscription_message(["BTCUSDT"])

    def test_update_connection_state(self):
        """연결 상태 업데이트 테스트"""
        # Arrange
        callback_called = False
        new_state = None

        def callback(state):
            nonlocal callback_called, new_state
            callback_called = True
            new_state = state

        self.handler.on_connection_change = callback

        # Act
        self.handler._update_connection_state(ConnectionState.CONNECTED)

        # Assert
        assert self.handler.connection_state == ConnectionState.CONNECTED
        assert callback_called == True
        assert new_state == ConnectionState.CONNECTED

    def test_update_connection_state_callback_error(self):
        """연결 상태 변경 콜백 오류 테스트"""
        # Arrange
        def error_callback(state):
            raise Exception("Callback error")

        self.handler.on_connection_change = error_callback

        # Act & Assert - 오류가 발생해도 상태는 변경되어야 함
        self.handler._update_connection_state(ConnectionState.CONNECTED)
        assert self.handler.connection_state == ConnectionState.CONNECTED

    def test_log_error(self):
        """에러 로깅 테스트"""
        # Arrange
        callback_called = False
        error_received = None

        def error_callback(error):
            nonlocal callback_called, error_received
            callback_called = True
            error_received = error

        self.handler.on_error = error_callback
        test_error = Exception("Test error")

        # Act
        self.handler._log_error(test_error, "테스트")

        # Assert
        assert self.handler.metrics.errors_count == 1
        assert callback_called == True
        assert error_received == test_error

    def test_log_error_callback_error(self):
        """에러 콜백에서 오류 발생 테스트"""
        # Arrange
        def error_callback(error):
            raise Exception("Callback error")

        self.handler.on_error = error_callback
        test_error = Exception("Test error")

        # Act & Assert - 콜백 오류가 발생해도 메트릭은 증가해야 함
        self.handler._log_error(test_error, "테스트")
        assert self.handler.metrics.errors_count == 1

    def test_connection_info(self):
        """연결 정보 반환 테스트"""
        # Act
        info = self.handler.get_connection_info()

        # Assert
        expected_keys = [
            'exchange', 'connection_state', 'is_connected',
            'symbols', 'subscriptions', 'cached_symbols',
            'reconnect_count', 'cache_size'
        ]
        for key in expected_keys:
            assert key in info

        assert info['exchange'] == 'binance'
        assert info['connection_state'] == 'disconnected'
        assert info['is_connected'] == False
        assert info['symbols'] == ['BTCUSDT']

    def test_get_all_cached_prices(self):
        """모든 캐시된 가격 데이터 조회 테스트"""
        # Arrange
        quote1 = PriceQuote("binance", "BTCUSDT", 50000.0, int(time.time() * 1000))
        quote2 = PriceQuote("binance", "ETHUSDT", 3000.0, int(time.time() * 1000))

        asyncio.run(self.handler.cache_price_data(quote1))
        asyncio.run(self.handler.cache_price_data(quote2))

        # Act
        cached_prices = self.handler.get_all_cached_prices()

        # Assert
        assert len(cached_prices) == 2
        assert "BTCUSDT" in cached_prices
        assert "ETHUSDT" in cached_prices
        assert cached_prices["BTCUSDT"].price == 50000.0
        assert cached_prices["ETHUSDT"].price == 3000.0

    def test_get_all_cached_prices_with_expired(self):
        """만료된 캐시 데이터 포함된 조회 테스트"""
        # Arrange
        current_time = int(time.time() * 1000)
        old_time = current_time - (120 * 1000)  # 2분 전

        fresh_quote = PriceQuote("binance", "BTCUSDT", 50000.0, current_time)
        old_quote = PriceQuote("binance", "ETHUSDT", 3000.0, old_time)

        asyncio.run(self.handler.cache_price_data(fresh_quote))
        asyncio.run(self.handler.cache_price_data(old_quote))

        # Act
        cached_prices = self.handler.get_all_cached_prices()

        # Assert - 만료된 데이터는 제외되어야 함
        assert len(cached_prices) == 1
        assert "BTCUSDT" in cached_prices
        assert "ETHUSDT" not in cached_prices

    def test_cleanup_expired_cache(self):
        """만료된 캐시 정리 테스트"""
        # Arrange
        current_time = int(time.time() * 1000)
        old_time = current_time - (120 * 1000)  # 2분 전

        fresh_quote = PriceQuote("binance", "BTCUSDT", 50000.0, current_time)
        old_quote = PriceQuote("binance", "ETHUSDT", 3000.0, old_time)

        asyncio.run(self.handler.cache_price_data(fresh_quote))
        asyncio.run(self.handler.cache_price_data(old_quote))

        # Act
        self.handler._cleanup_expired_cache()

        # Assert
        assert len(self.handler.price_cache) == 1
        assert "BTCUSDT" in self.handler.price_cache
        assert "ETHUSDT" not in self.handler.price_cache

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """이미 연결된 상태에서 재연결 시도 테스트"""
        # Arrange
        self.handler._update_connection_state(ConnectionState.CONNECTED)

        # Act
        await self.handler.connect()

        # Assert - 상태 변경이 없어야 함
        assert self.handler.connection_state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        """연결되지 않은 상태에서 연결 종료 테스트"""
        # Arrange
        assert self.handler.connection_state == ConnectionState.DISCONNECTED

        # Act
        await self.handler.disconnect()

        # Assert - 상태가 유지되어야 함
        assert self.handler.connection_state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_cache_cleanup_task(self):
        """캐시 정리 태스크 테스트"""
        # Arrange
        self.handler._running = True
        cleanup_called = False

        async def mock_sleep(duration):
            # 첫 번째 호출 후 종료
            if self.handler._running:
                self.handler._running = False
                cleanup_called = True

        with patch('asyncio.sleep', side_effect=mock_sleep):
            # Act
            await self.handler._cache_cleanup_task()

        # Assert
        assert cleanup_called == True

    @pytest.mark.asyncio
    async def test_cache_cleanup_task_error(self):
        """캐시 정리 태스크 오류 처리 테스트"""
        # Arrange
        self.handler._running = True
        cleanup_called = 0

        def mock_cleanup():
            nonlocal cleanup_called
            cleanup_called += 1
            if cleanup_called == 1:
                raise Exception("Cleanup error")

        self.handler._cleanup_expired_cache = mock_cleanup

        async def mock_sleep(duration):
            # 두 번의 정리 시도 후 종료
            if self.handler._running and cleanup_called < 2:
                pass
            else:
                self.handler._running = False

        with patch('asyncio.sleep', side_effect=mock_sleep):
            # Act
            await self.handler._cache_cleanup_task()

        # Assert - 오류 발생 후에도 계속 실행되어야 함
        assert cleanup_called == 2

    @pytest.mark.asyncio
    async def test_subscribe_symbols_not_connected(self):
        """연결되지 않은 상태에서 구독 시도 테스트"""
        # Arrange
        self.handler.ws = None

        # Act
        await self.handler._subscribe_symbols(["BTCUSDT"])

        # Assert - 아무것도 실행되지 않아야 함 (예외 없이 통과)
        assert True

    @pytest.mark.asyncio
    async def test_remove_subscription_not_subscribed(self):
        """구독되지 않은 심볼 구독 해지 테스트"""
        # Arrange
        assert "ETHUSDT" not in self.handler.symbol_subscriptions

        # Act
        await self.handler.remove_subscription("ETHUSDT")

        # Assert - 아무것도 실행되지 않아야 함
        assert "ETHUSDT" not in self.handler.symbol_subscriptions

    @pytest.mark.asyncio
    async def test_remove_subscription_cached_data(self):
        """캐시된 데이터가 있는 심볼 구독 해지 테스트"""
        # Arrange
        quote = PriceQuote("binance", "BTCUSDT", 50000.0, int(time.time() * 1000))
        await self.handler.cache_price_data(quote)

        # Act
        await self.handler.remove_subscription("BTCUSDT")

        # Assert - 캐시에서도 제거되어야 함
        assert "BTCUSDT" not in self.handler.price_cache
        assert "BTCUSDT" not in self.handler.cache_timestamps